"""Published-surface audit tests use generated synthetic content only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import bz2
import importlib.util
import hashlib
import io
import json
import lzma
from pathlib import Path
import secrets
import stat
import tarfile
import threading
import time
import warnings
from urllib.parse import urlparse
from urllib.request import Request
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/audit_github_published_surfaces.py"


def module():
    assert SCRIPT.is_file(), "published-surface audit CLI is missing"
    spec = importlib.util.spec_from_file_location("published_surface_audit", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def security_module():
    path = SCRIPT.with_name("security_scan.py")
    spec = importlib.util.spec_from_file_location("security_scan_for_published_test", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def fake_token():
    return "gh" + "p_" + "".join(
        secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        for _ in range(36)
    )


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        for name, value in entries.items():
            bundle.writestr(name, value)
    return stream.getvalue()


def symlink_archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        info = zipfile.ZipInfo("unsafe-link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, "outside")
    return stream.getvalue()


def duplicate_archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr("duplicate.txt", "first")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            bundle.writestr("duplicate.txt", "second")
    return stream.getvalue()


def tar_archive():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as bundle:
        info = tarfile.TarInfo("inside.txt")
        payload = b"synthetic"
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))
    return stream.getvalue()


class FixtureApi:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __enter__(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                fixture.requests.append((parsed.path, parsed.query, self.headers.get("Authorization")))
                response = fixture.routes.get((parsed.path, parsed.query))
                if response is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if len(response) == 3:
                    status, location, body = response
                    content_type = "application/octet-stream"
                else:
                    status, location = 200, None
                    content_type, body = response
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                if location:
                    self.send_header("Location", location)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def encoded(value):
    return "application/json", json.dumps(value).encode()


def test_safe_zip_extraction_rejects_escape_symlink_and_nested_archive(tmp_path):
    audit = module()
    for payload in (
        archive({"../escape.txt": "x"}),
        symlink_archive(),
        archive({"nested.zip": archive({"inside.txt": "x"})}),
        archive({"renamed-sfx.bin": b"MZsynthetic-stub" + archive({"inside.txt": "x"})}),
        duplicate_archive(),
        archive({"renamed-xz.bin": lzma.compress(b"synthetic")}),
        archive({"renamed-bzip2.bin": bz2.compress(b"synthetic")}),
        archive({"renamed-rar.bin": b"Rar!\x1a\x07\x01\x00synthetic"}),
        archive({"renamed-tar.bin": tar_archive()}),
    ):
        with pytest.raises(audit.AuditFailure):
            audit.extract_zip(payload, tmp_path / secrets.token_hex(4))
    assert not (tmp_path.parent / "escape.txt").exists()


def test_existing_private_scanner_can_scan_a_collected_directory(tmp_path, monkeypatch):
    scanner = security_module()
    binary = tmp_path / "gitleaks"
    binary.write_bytes(b"synthetic-scanner")
    monkeypatch.setattr(scanner, "BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest())

    def run(command, private, _env, **_kwargs):
        if command[1] == "version":
            return 0, scanner.VERSION.encode()
        (private / "report.json").write_text("[]")
        return 0, b""

    monkeypatch.setattr(scanner, "run_private", run)
    collected = tmp_path / "collected"
    collected.mkdir()
    (collected / "surface.txt").write_text("synthetic clean content")
    assert scanner.scan_directory(collected, binary) == 0


def test_cross_origin_download_redirect_does_not_forward_bearer_token():
    audit = module()
    with FixtureApi({("/payload", ""): ("application/octet-stream", b"payload")}) as target:
        routes = {("/redirect", ""): (302, f"{target.base_url}/payload", b"")}
        with FixtureApi(routes) as source:
            assert audit.request_bytes(f"{source.base_url}/redirect", "synthetic-token") == b"payload"
    assert source.requests == [("/redirect", "", "Bearer synthetic-token")]
    assert target.requests == [("/payload", "", None)]


def test_https_download_redirect_cannot_downgrade_transport():
    audit = module()
    request = Request(
        "https://api.github.com/repos/haji84/-AI/actions/runs/9/logs",
        headers={"Authorization": "Bearer synthetic-token"},
    )
    with pytest.raises(audit.AuditFailure):
        audit.PrivateRedirectHandler().redirect_request(
            request, None, 302, "Found", {}, "http://downloads.invalid/logs.zip"
        )


def test_download_uses_absolute_deadline_not_only_socket_inactivity(monkeypatch):
    audit = module()

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            time.sleep(1)
            return b"trickle"

    class Opener:
        def open(self, _request, timeout):
            assert timeout == 0.01
            return Response()

    monkeypatch.setattr(audit, "DOWNLOAD_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(audit, "build_opener", lambda *_args: Opener())
    with pytest.raises(audit.AuditFailure):
        audit.request_bytes("https://api.github.com/synthetic", "synthetic-token")


def test_collects_selected_pr_logs_and_artifacts_privately(tmp_path):
    audit = module()
    token = fake_token()
    log_zip = archive({"job.txt": "credential = " + token})
    artifact_zip = archive({"evidence.json": json.dumps({"value": token})})
    routes = {
        ("/repos/haji84/-AI/pulls/7", ""): encoded({"number": 7, "body": token}),
        ("/repos/haji84/-AI/issues/7/comments", "per_page=100&page=1"): encoded([{"body": token}]),
        ("/repos/haji84/-AI/pulls/7/comments", "per_page=100&page=1"): encoded([{"body": token}]),
        ("/repos/haji84/-AI/pulls/7/reviews", "per_page=100&page=1"): encoded([{"body": token}]),
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): ("application/zip", log_zip),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": False}]}
        ),
        ("/repos/haji84/-AI/actions/artifacts/11/zip", ""): ("application/zip", artifact_zip),
    }
    with FixtureApi(routes) as api:
        root = tmp_path / "private"
        manifest = audit.collect_surfaces(
            api.base_url, "haji84/-AI", [7], [9], "synthetic-token", root
        )
    assert manifest == {"pull_requests": 1, "workflow_runs": 1, "artifacts": 1}
    assert token in "\n".join(path.read_text() for path in root.rglob("*") if path.is_file())
    assert all(auth == "Bearer synthetic-token" for _, _, auth in api.requests)


def test_expired_or_unavailable_requested_surface_fails_closed(tmp_path):
    audit = module()
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): ("application/zip", archive({"job.txt": "clean"})),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": True}]}
        ),
    }
    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.collect_surfaces(api.base_url, "haji84/-AI", [], [9], "token", tmp_path / "private")


def test_malformed_paginated_rows_and_boolean_counts_fail_closed(tmp_path):
    audit = module()
    pr_routes = {
        ("/repos/haji84/-AI/pulls/7", ""): encoded({"number": 7}),
        ("/repos/haji84/-AI/issues/7/comments", "per_page=100&page=1"): encoded(
            ["not-an-object"]
        ),
        ("/repos/haji84/-AI/pulls/7/comments", "per_page=100&page=1"): encoded([]),
        ("/repos/haji84/-AI/pulls/7/reviews", "per_page=100&page=1"): encoded([]),
    }
    with FixtureApi(pr_routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.collect_surfaces(
                api.base_url, "haji84/-AI", [7], [], "token", tmp_path / "private-pr"
            )

    artifact_routes = {
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": True, "artifacts": [{"id": 11, "expired": False}]}
        )
    }
    with FixtureApi(artifact_routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.artifact_list(api.base_url, "haji84/-AI", 9, "token")


@pytest.mark.parametrize("status", [None, "queued", "in_progress"])
def test_non_completed_workflow_run_fails_closed(tmp_path, status):
    audit = module()
    metadata = {"id": 9, "repository": {"full_name": "haji84/-AI"}}
    if status is not None:
        metadata["status"] = status
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(metadata),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip", archive({"job.txt": "clean"})
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 0, "artifacts": []}
        ),
    }
    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.collect_surfaces(
                api.base_url, "haji84/-AI", [], [9], "token", tmp_path / "private"
            )


def test_dispatch_id_lists_accept_only_exact_positive_decimal_ids():
    audit = module()
    assert audit.parse_id_list("", [7]) == [7]
    assert audit.parse_id_list("7,9", [11]) == [7, 9, 11]
    for value in ("0", "-1", "7,", "7 9", "7;9", "1e3"):
        with pytest.raises(audit.AuditFailure):
            audit.parse_id_list(value, [])


def test_security_workflow_has_manual_private_published_surface_gate():
    workflow = SCRIPT.parents[1] / ".github/workflows/security-checks.yml"
    content = workflow.read_text()
    assert "workflow_dispatch:" in content
    assert "workflow_run:" in content
    assert 'workflows: ["project-checks"]' in content
    assert "types: [completed]" in content
    assert "published-surface-audit:" in content
    assert "actions: read" in content
    assert "pull-requests: read" in content
    assert "FIRE_AI_GITHUB_AUDIT_TOKEN: ${{ github.token }}" in content
    assert "scripts/audit_github_published_surfaces.py" in content
    assert "github.event.workflow_run.id" in content
    assert "upload-artifact" not in content


def test_cli_errors_never_echo_token_repository_or_private_payload(monkeypatch, capsys):
    audit = module()
    sentinel = "private-fixture-" + secrets.token_hex(12)
    monkeypatch.setenv("FIRE_AI_GITHUB_AUDIT_TOKEN", sentinel)
    assert audit.main(["--repository", sentinel, "--pull-request", "7", "--gitleaks", sentinel]) == 2
    output = capsys.readouterr().out
    assert sentinel not in output
    assert output.strip() == "Published-surface secret audit failed closed; findings=unknown"
