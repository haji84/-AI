"""Published-surface audit tests use generated synthetic content only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import bz2
from collections import namedtuple
import errno
import gzip
import importlib.util
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
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


def reviewed_import_preview_traceback(
    key=None,
    *,
    router_line="backend/app/routers/workforce.py:182: in confirm_import",
):
    """Return synthetic text matching the one privately reviewed traceback shape."""
    if key is None:
        key = "-".join(("d5071b4a", "b15d", "4fc8", "9f0c", "a46f1f62c7c9"))
    prefix = "2026-10-06T16:14:57.1234567Z "
    lines = [
        router_line,
        "    out=svc.confirm_import(db,user,key,payload.expected_version,payload.file_sha256);svc.save(db);return out",
        "",
        "synthetic traceback field 1",
        "synthetic traceback field 2",
        "synthetic traceback field 3",
        "synthetic traceback field 4",
        f"key = '{key}', expected_version = 1",
        "file_sha256 = '2c48e04a0c378fdc0def569487a61b24ba75923bfc7a59a38b0841fdcf485fe2'",
        "",
        "def confirm_import(db,user,key,expected_version,file_sha256):",
        "    preview=get_row(db,WorkforceImportPreview,key,True);check_version(preview,expected_version)",
        ">   if preview.status != 'validated':",
        "        raise ValueError('synthetic')",
        "E       TypeError: can't compare offset-naive and offset-aware datetimes",
    ]
    return "\n".join(prefix + line for line in lines) + "\n"


def pin_reviewed_identity(audit, monkeypatch, source_root, candidate):
    """Pin a synthetic fixture without exposing the production log identity."""
    data = candidate.read_bytes()
    lines = data.decode().splitlines()
    index = next(
        index
        for index, line in enumerate(lines)
        if "expected_version = 1" in line
    )
    finding_text = "key = '" + lines[index].split("key = '", 1)[1].split("',", 1)[0] + "'"
    offset = lines[index].index(finding_text)
    identity = (
        candidate.relative_to(source_root).as_posix(),
        hashlib.sha256(data).hexdigest(),
        "generic-api-key",
        index + 1,
        index + 1,
        offset + 2,
        offset + len(finding_text) + 1,
    )
    commitment = hashlib.sha256(
        json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    monkeypatch.setattr(
        audit, "REVIEWED_WORKFLOW_LOG_IDENTITY_SHA256", commitment
    )
    return frozenset({identity})


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


def gzip_tar_archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for name, payload in entries.items():
            data = payload.encode() if isinstance(payload, str) else payload
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def unsafe_tar_link():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        info = tarfile.TarInfo("unsafe-link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../outside"
        bundle.addfile(info)
    return stream.getvalue()


def gzip_tar_with_directories(count):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for index in range(count):
            info = tarfile.TarInfo(f"directory-{index}/")
            info.type = tarfile.DIRTYPE
            bundle.addfile(info)
    return stream.getvalue()


def gzip_pax_tar(comment_size):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.PAX_FORMAT) as bundle:
        info = tarfile.TarInfo("inside.txt")
        info.size = 1
        info.pax_headers = {"comment": "x" * comment_size}
        bundle.addfile(info, io.BytesIO(b"x"))
    return stream.getvalue()


def pax_sparse_tar(entries, logical_size):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as bundle:
        for index in range(entries):
            info = tarfile.TarInfo(f"sparse-{index}.bin")
            info.size = 0
            info.pax_headers = {
                "GNU.sparse.map": "0,0",
                "GNU.sparse.size": str(logical_size),
            }
            bundle.addfile(info, io.BytesIO())
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
                if callable(response):
                    response = response()
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


def readable_private_text(root):
    values = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            values.append(path.read_text())
        except UnicodeDecodeError:
            pass
    return values


def discover_workflow_names(directory):
    names = set()
    candidates = set(directory.glob("*.yml")) | set(directory.glob("*.yaml"))
    for candidate in sorted(candidates):
        match = re.search(
            r"(?m)^name:\s*([A-Za-z0-9][A-Za-z0-9._ -]*)\s*$",
            candidate.read_text(),
        )
        assert match, f"{candidate.name} must use a simple top-level workflow name"
        names.add(match.group(1).strip())
    return names


def test_workflow_name_discovery_covers_both_yaml_extensions(tmp_path):
    (tmp_path / "one.yml").write_text("name: one\n")
    (tmp_path / "two.yaml").write_text("name: two\n")

    assert discover_workflow_names(tmp_path) == {"one", "two"}


def test_workflow_name_discovery_rejects_ambiguous_inline_comments(tmp_path):
    (tmp_path / "ambiguous.yaml").write_text("name: ambiguous # not part of name\n")

    with pytest.raises(AssertionError, match="simple top-level workflow name"):
        discover_workflow_names(tmp_path)


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


def test_release_artifact_expands_bounded_private_archive_layers(tmp_path, monkeypatch):
    audit = module()
    embedded = b"synthetic-prefix\n" + archive(
        {"embedded.txt": "synthetic embedded ZIP"}
    )
    monkeypatch.setattr(
        audit,
        "REVIEWED_EMBEDDED_ZIP_WRAPPERS",
        frozenset(
            {
                (
                    "synthetic/lib.so",
                    hashlib.sha256(embedded).hexdigest(),
                )
            }
        ),
    )
    outer = archive(
        {
            "source/source.tar.gz": gzip_tar_archive(
                {"source/backend/app.py": "synthetic source"}
            ),
            "wheelhouse/synthetic.whl": archive(
                {
                    "synthetic/__init__.py": "synthetic wheel",
                    "docx/templates/default.docx": archive(
                        {"word/document.xml": "synthetic document"}
                    ),
                    "synthetic/lib.so": embedded,
                }
            ),
        }
    )

    audit.extract_zip(outer, tmp_path / "release", max_nested_depth=2)

    contents = set(readable_private_text(tmp_path / "release"))
    assert "synthetic source" in contents
    assert "synthetic wheel" in contents
    assert "synthetic document" in contents
    assert "synthetic embedded ZIP" in contents
    assert (tmp_path / "release/wheelhouse/synthetic.whl").is_file()
    assert (
        tmp_path
        / "release/wheelhouse/synthetic.whl.expanded/docx/templates/default.docx"
    ).is_file()


def test_unreviewed_or_mutated_embedded_zip_wrapper_fails_closed(
    tmp_path, monkeypatch
):
    audit = module()
    embedded = b"synthetic-prefix\n" + archive(
        {"embedded.txt": "synthetic embedded ZIP"}
    )
    monkeypatch.setattr(
        audit,
        "REVIEWED_EMBEDDED_ZIP_WRAPPERS",
        frozenset(
            {
                (
                    "synthetic/lib.so",
                    hashlib.sha256(embedded).hexdigest(),
                )
            }
        ),
    )

    for wrapper in (
        b"unreviewed-prefix\n" + archive({"embedded.txt": "synthetic"}),
        embedded + b"mutated-suffix",
    ):
        outer = archive(
            {
                "wheelhouse/synthetic.whl": archive(
                    {"synthetic/lib.so": wrapper}
                )
            }
        )
        with pytest.raises(audit.AuditFailure):
            audit.extract_zip(
                outer,
                tmp_path / secrets.token_hex(4),
                max_nested_depth=2,
            )


def test_release_artifact_rejects_archive_beyond_bounded_depth(tmp_path):
    audit = module()
    outer = archive(
        {
            "wheelhouse/synthetic.whl": archive(
                {
                    "synthetic/document.docx": archive(
                        {
                            "word/nested.zip": archive(
                                {"payload.txt": "synthetic"}
                            )
                        }
                    )
                }
            )
        }
    )

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(outer, tmp_path / "release", max_nested_depth=2)


def test_release_artifact_rejects_cross_layer_expansion_collision(tmp_path):
    audit = module()
    outer = archive(
        {
            "wheelhouse/bundle.whl": archive(
                {"evidence.txt": "synthetic credential evidence"}
            ),
            "wheelhouse/bundle.whl.expanded/evidence.txt": "clean overwrite",
        }
    )

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(outer, tmp_path / "release", max_nested_depth=2)


def test_release_artifact_rejects_unsafe_tar_member(tmp_path):
    audit = module()
    outer = archive({"source/source.tar.gz": unsafe_tar_link()})

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(outer, tmp_path / "release", max_nested_depth=1)
    assert not (tmp_path.parent / "outside").exists()


def test_release_artifact_uses_one_aggregate_expansion_budget(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 1_000)
    outer = archive(
        {
            "wheelhouse/one.whl": archive({"one.py": "x" * 600}),
            "wheelhouse/two.whl": archive({"two.py": "y" * 600}),
        }
    )

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(outer, tmp_path / "release", max_nested_depth=1)


def test_zip_entry_count_is_rejected_before_zipfile_materializes(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_FILES", 2)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        for index in range(3):
            bundle.writestr(f"directory-{index}/", b"")
    payload = bytearray(stream.getvalue())
    end = payload.rfind(zipfile.stringEndArchive)
    assert end >= 0
    payload[end + 8 : end + 12] = (1).to_bytes(2, "little") * 2
    constructor_called = False

    def unexpected_constructor(*_args, **_kwargs):
        nonlocal constructor_called
        constructor_called = True
        raise AssertionError("oversized central directory was materialized")

    monkeypatch.setattr(audit.zipfile, "ZipFile", unexpected_constructor)

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(bytes(payload), tmp_path / "release")
    assert constructor_called is False


def test_nested_zip_directories_share_the_outer_entry_budget(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_FILES", 3)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as bundle:
        for index in range(3):
            bundle.writestr(f"directory-{index}/", b"")
    outer = archive({"wheelhouse/bundle.whl": nested.getvalue()})

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(outer, tmp_path / "release", max_nested_depth=1)


def test_concatenated_zip_archives_fail_closed(tmp_path):
    audit = module()
    payload = archive({"hidden.txt": "synthetic hidden content"}) + archive(
        {"visible.txt": "synthetic visible content"}
    )

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(payload, tmp_path / "release")


def test_zip_with_unconsumed_suffix_fails_closed(tmp_path):
    audit = module()

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(
            archive({"visible.txt": "synthetic visible content"}) + b"trailing",
            tmp_path / "release",
        )


def test_tar_directory_headers_count_toward_aggregate_file_budget(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_FILES", 2)

    with pytest.raises(audit.AuditFailure):
        audit.extract_tar(gzip_tar_with_directories(3), tmp_path / "release")


def test_tar_metadata_counts_toward_aggregate_byte_budget(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_000)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 1_000)

    with pytest.raises(audit.AuditFailure):
        audit.extract_tar(gzip_pax_tar(2_000), tmp_path / "release")


def test_tar_sparse_members_fail_closed_before_hole_expansion(tmp_path, monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 50_000)

    with pytest.raises(audit.AuditFailure):
        audit.extract_tar(
            pax_sparse_tar(entries=10, logical_size=32_768),
            tmp_path / "release",
        )


@pytest.mark.parametrize(
    "compressor",
    [gzip.compress, bz2.compress, lzma.compress],
    ids=["gzip", "bzip2", "xz"],
)
def test_concatenated_compressed_tar_streams_fail_closed(tmp_path, compressor):
    audit = module()
    payload = compressor(tar_archive()) + compressor(tar_archive())

    with pytest.raises(audit.AuditFailure):
        audit.extract_tar(payload, tmp_path / "release")


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


def test_reviewed_workflow_log_finding_derives_one_exact_identity(
    tmp_path, monkeypatch
):
    audit = module()
    source_root = tmp_path / "workflow-run"
    candidate = source_root / "logs" / "backend-tests.txt"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(reviewed_import_preview_traceback())
    expected = pin_reviewed_identity(
        audit, monkeypatch, source_root, candidate
    )

    identities = audit.reviewed_workflow_log_findings(37493709157, source_root)

    assert identities == expected


@pytest.mark.parametrize(
    ("run_id", "key", "router_line"),
    [
        (37493709158, "d5071b4a-b15d-4fc8-9f0c-a46f1f62c7c9", "backend/app/routers/workforce.py:182: in confirm_import"),
        (37493709157, "d5071b4a-b15d-3fc8-9f0c-a46f1f62c7c9", "backend/app/routers/workforce.py:182: in confirm_import"),
        (37493709157, "d5071b4a-b15d-4fc8-7f0c-a46f1f62c7c9", "backend/app/routers/workforce.py:182: in confirm_import"),
        (37493709157, "d5071b4a-b15d-4fc8-9f0c-a46f1f62c7c9", "backend/app/routers/workforce.py:183: in confirm_import"),
    ],
    ids=["different-run", "wrong-version", "wrong-variant", "changed-context"],
)
def test_reviewed_workflow_log_finding_rejects_inexact_context(
    tmp_path, monkeypatch, run_id, key, router_line
):
    audit = module()
    source_root = tmp_path / "workflow-run"
    candidate = source_root / "logs" / "job.txt"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
        reviewed_import_preview_traceback(key, router_line=router_line)
    )
    pin_reviewed_identity(audit, monkeypatch, source_root, candidate)

    assert audit.reviewed_workflow_log_findings(run_id, source_root) == frozenset()


def test_reviewed_workflow_log_finding_rejects_duplicate_context(
    tmp_path, monkeypatch
):
    audit = module()
    source_root = tmp_path / "workflow-run"
    logs = source_root / "logs"
    logs.mkdir(parents=True)
    for name in ("first.txt", "second.txt"):
        (logs / name).write_text(reviewed_import_preview_traceback())
    pin_reviewed_identity(audit, monkeypatch, source_root, logs / "first.txt")

    assert (
        audit.reviewed_workflow_log_findings(37493709157, source_root)
        == frozenset()
    )


def test_reviewed_workflow_log_finding_rejects_symlinked_log(tmp_path):
    audit = module()
    source_root = tmp_path / "workflow-run"
    logs = source_root / "logs"
    logs.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text(reviewed_import_preview_traceback())
    (logs / "job.txt").symlink_to(outside)

    with pytest.raises(audit.AuditFailure):
        audit.reviewed_workflow_log_findings(37493709157, source_root)


def test_reviewed_workflow_log_finding_filters_only_exact_pinned_gitleaks_result(
    tmp_path, monkeypatch,
):
    audit = module()
    scanner = security_module()
    binary_value = os.environ.get("FIRE_AI_GITLEAKS_BIN")
    assert binary_value, "FIRE_AI_GITLEAKS_BIN must identify the pinned official binary"
    source_root = tmp_path / "workflow-run"
    candidate = source_root / "logs" / "job.txt"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(reviewed_import_preview_traceback())
    expected = pin_reviewed_identity(
        audit, monkeypatch, source_root, candidate
    )
    identities = audit.reviewed_workflow_log_findings(37493709157, source_root)
    assert identities == expected
    observed_identities = []
    finding_identity = scanner.finding_identity

    def record_identity(finding, target):
        identity = finding_identity(finding, target)
        observed_identities.append(identity)
        return identity

    monkeypatch.setattr(scanner, "finding_identity", record_identity)

    assert scanner.scan_directory_summary(source_root, Path(binary_value)).findings == 1
    assert frozenset(observed_identities) == identities
    assert scanner.scan_directory_summary(
        source_root,
        Path(binary_value),
        accepted_findings=identities,
    ).findings == 0

    unrelated_key = "-".join(("0996a6f0", "c9b0", "4ce7", "aa5a", "2355e7529371"))
    with candidate.open("a") as stream:
        stream.write(f"{'key'} = '{unrelated_key}'\n")
    changed_identities = audit.reviewed_workflow_log_findings(
        37493709157, source_root
    )
    assert changed_identities == frozenset()
    assert scanner.scan_directory_summary(
        source_root,
        Path(binary_value),
        accepted_findings=changed_identities,
    ).findings == 2


def test_reviewed_workflow_log_finding_rejects_relocated_or_repositioned_log(
    tmp_path, monkeypatch
):
    audit = module()
    source_root = tmp_path / "workflow-run"
    candidate = source_root / "logs" / "backend-tests.txt"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(reviewed_import_preview_traceback())
    pin_reviewed_identity(audit, monkeypatch, source_root, candidate)

    relocated = candidate.with_name("relocated.txt")
    candidate.rename(relocated)
    assert audit.reviewed_workflow_log_findings(
        37493709157, source_root
    ) == frozenset()

    candidate.write_text("2026-10-06T16:14:57.1234567Z extra line\n")
    with relocated.open() as stream:
        candidate.write_text(candidate.read_text() + stream.read())
    relocated.unlink()
    assert audit.reviewed_workflow_log_findings(
        37493709157, source_root
    ) == frozenset()


def test_private_scanner_summary_exposes_only_safe_rule_ids(tmp_path):
    scanner = security_module()
    binary_value = os.environ.get("FIRE_AI_GITLEAKS_BIN")
    assert binary_value, "FIRE_AI_GITLEAKS_BIN must identify the pinned official binary"
    sentinel = fake_token()
    private = tmp_path / "private"
    private.mkdir()
    (private / "sensitive-name.txt").write_text(f"credential = {sentinel}\n")

    summary = scanner.scan_directory_summary(private, Path(binary_value))

    assert summary.findings == 1
    assert summary.rule_ids
    assert all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) for value in summary.rule_ids)
    public = repr(summary)
    assert sentinel not in public
    assert "sensitive-name.txt" not in public
    assert str(private) not in public


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


def test_private_file_download_is_mode_600_and_capacity_bounded(tmp_path):
    audit = module()
    payload = b"x" * 2_048
    with FixtureApi({("/payload", ""): ("application/octet-stream", payload)}) as api:
        destination = tmp_path / "private" / "artifact.zip"
        audit.download_to_private_file(
            f"{api.base_url}/payload",
            "synthetic-token",
            destination,
            max_bytes=len(payload),
        )
        assert destination.read_bytes() == payload
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600

        rejected = tmp_path / "private" / "too-large.zip"
        with pytest.raises(audit.AuditFailure):
            audit.download_to_private_file(
                f"{api.base_url}/payload",
                "synthetic-token",
                rejected,
                max_bytes=len(payload) - 1,
            )
        assert not rejected.exists()


def test_file_backed_zip_rejects_prefix_and_unconsumed_suffix(tmp_path):
    audit = module()
    for payload in (
        archive({"hidden.txt": "hidden"}) + archive({"visible.txt": "visible"}),
        archive({"visible.txt": "visible"}) + b"trailing",
    ):
        source = tmp_path / f"{secrets.token_hex(4)}.zip"
        source.write_bytes(payload)
        with pytest.raises(audit.AuditFailure):
            audit.extract_zip_file(source, tmp_path / secrets.token_hex(4))


def test_file_backed_zip_accepts_valid_zip64(tmp_path, monkeypatch):
    audit = module()
    with monkeypatch.context() as patch:
        patch.setattr(zipfile, "ZIP64_LIMIT", 0)
        payload = archive({"evidence.txt": "synthetic"})
    source = tmp_path / "valid-zip64.zip"
    source.write_bytes(payload)

    audit.extract_zip(payload, tmp_path / "memory")
    audit.extract_zip_file(source, tmp_path / "file")

    assert (tmp_path / "file/evidence.txt").read_text() == "synthetic"


def test_file_backed_zip_rejects_truncated_declared_comment(tmp_path):
    audit = module()
    payload = bytearray(archive({"evidence.txt": "synthetic"}))
    end = payload.rfind(zipfile.stringEndArchive)
    assert end >= 0
    payload[end + zipfile.sizeEndCentDir - 2 : end + zipfile.sizeEndCentDir] = (
        10
    ).to_bytes(2, "little")
    payload.extend(b"x")
    source = tmp_path / "truncated-comment.zip"
    source.write_bytes(payload)

    with pytest.raises(audit.AuditFailure):
        audit.extract_zip(bytes(payload), tmp_path / "memory")
    with pytest.raises(audit.AuditFailure):
        audit.extract_zip_file(source, tmp_path / "file")


def test_large_nested_zip_is_scanned_in_existing_bounded_batches(
    tmp_path, monkeypatch
):
    audit = module()
    payloads = {
        f"part-{index}.bin": secrets.token_bytes(700) for index in range(3)
    }
    nested = archive(payloads)
    assert len(nested) > 1_024
    source = tmp_path / "outer.zip"
    source.write_bytes(
        archive({"large.zip": nested, "manifest.json": b"synthetic manifest"})
    )
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_024)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 2_048)
    monkeypatch.setattr(audit, "MAX_FILES", 2)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_BYTES", 16_384)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_FILES", 10)
    observed = {}
    batch_shapes = []

    def scan_batch(root):
        files = sorted(path for path in root.rglob("*") if path.is_file())
        batch_shapes.append((len(files), sum(path.stat().st_size for path in files)))
        for path in files:
            observed[path.relative_to(root).as_posix()] = path.read_bytes()
        return 0

    batches, findings = audit.scan_zip_file_in_bounded_batches(
        source,
        tmp_path / "staging",
        Path("surface"),
        max_nested_depth=2,
        scan_batch=scan_batch,
    )

    assert batches >= 2
    assert findings == 0
    assert all(files <= 2 and size <= 2_048 for files, size in batch_shapes)
    assert observed["surface/manifest.json"] == b"synthetic manifest"
    for name, payload in payloads.items():
        assert observed[f"surface/large.zip.expanded/{name}"] == payload
    assert not (tmp_path / "staging").exists()


def test_streamed_zip_accepts_only_reviewed_embedded_zip_wrapper(
    tmp_path, monkeypatch
):
    audit = module()
    embedded = (
        b"synthetic-prefix\n"
        + archive({"embedded.txt": "synthetic embedded ZIP"})
        + b"\nsynthetic-suffix"
    )
    monkeypatch.setattr(
        audit,
        "REVIEWED_EMBEDDED_ZIP_WRAPPERS",
        frozenset(
            {
                (
                    "synthetic/lib.so",
                    hashlib.sha256(embedded).hexdigest(),
                )
            }
        ),
    )
    source = tmp_path / "outer.zip"
    source.write_bytes(
        archive(
            {
                "wheelhouse/synthetic.whl": archive(
                    {"synthetic/lib.so": embedded}
                )
            }
        )
    )
    observed = {}

    def scan_batch(root):
        for path in root.rglob("*"):
            if path.is_file():
                observed[path.relative_to(root).as_posix()] = path.read_bytes()
        return 0

    batches, findings = audit.scan_zip_file_in_bounded_batches(
        source,
        tmp_path / "staging",
        Path("surface"),
        max_nested_depth=2,
        scan_batch=scan_batch,
    )

    assert batches >= 1
    assert findings == 0
    assert observed[
        "surface/wheelhouse/synthetic.whl.expanded/"
        "synthetic/lib.so.expanded/embedded.txt"
    ] == b"synthetic embedded ZIP"
    assert not (tmp_path / "staging").exists()

    corrupted = bytearray(embedded)
    end_record = corrupted.rfind(zipfile.stringEndArchive)
    assert end_record >= 0
    corrupted[end_record : end_record + len(zipfile.stringEndArchive)] = b"BAD!"

    for index, wrapper in enumerate(
        (
            b"unreviewed-prefix\n" + archive({"embedded.txt": "synthetic"}),
            bytes(corrupted),
        )
    ):
        source.write_bytes(
            archive(
                {
                    "wheelhouse/synthetic.whl": archive(
                        {"synthetic/lib.so": wrapper}
                    )
                }
            )
        )
        rejected_staging = tmp_path / f"rejected-staging-{index}"
        with pytest.raises(audit.AuditFailure):
            audit.scan_zip_file_in_bounded_batches(
                source,
                rejected_staging,
                Path("surface"),
                max_nested_depth=2,
                scan_batch=scan_batch,
            )
        assert not rejected_staging.exists()


def test_streamed_zip_total_work_cap_still_fails_closed(tmp_path, monkeypatch):
    audit = module()
    nested = archive(
        {f"part-{index}.bin": secrets.token_bytes(700) for index in range(3)}
    )
    source = tmp_path / "outer.zip"
    source.write_bytes(archive({"large.zip": nested}))
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_024)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 2_048)
    monkeypatch.setattr(audit, "MAX_FILES", 2)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_BYTES", len(nested) - 1)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_FILES", 10)
    scanned = False

    def unexpected_scan(_root):
        nonlocal scanned
        scanned = True
        return 0

    with pytest.raises(audit.AuditFailure):
        audit.scan_zip_file_in_bounded_batches(
            source,
            tmp_path / "staging",
            Path("surface"),
            max_nested_depth=2,
            scan_batch=unexpected_scan,
        )

    assert scanned is False
    assert not (tmp_path / "staging").exists()


def test_streamed_zip_scans_nested_container_bytes(tmp_path):
    audit = module()
    sentinel = b"container-metadata-only-sentinel"
    nested_stream = io.BytesIO()
    with zipfile.ZipFile(nested_stream, "w") as nested_archive:
        nested_archive.writestr("content.txt", b"expanded content")
        nested_archive.comment = sentinel
    source = tmp_path / "outer.zip"
    source.write_bytes(archive({"nested.zip": nested_stream.getvalue()}))
    observed_container_metadata = False

    def scan_batch(root):
        nonlocal observed_container_metadata
        for path in root.rglob("*"):
            if path.is_file() and sentinel in path.read_bytes():
                observed_container_metadata = True
        return 0

    audit.scan_zip_file_in_bounded_batches(
        source,
        tmp_path / "staging",
        Path("surface"),
        max_nested_depth=2,
        scan_batch=scan_batch,
    )

    assert observed_container_metadata is True


def test_private_tree_cleanup_retries_enotempty_once(tmp_path, monkeypatch):
    audit = module()
    private = tmp_path / "private"
    private.mkdir()
    (private / "evidence.txt").write_text("synthetic evidence")
    real_rmtree = audit.shutil.rmtree
    calls = 0

    def transient_enotempty(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.ENOTEMPTY, "synthetic overlay race")
        return real_rmtree(path)

    monkeypatch.setattr(audit.shutil, "rmtree", transient_enotempty)

    audit.remove_private_tree(private)

    assert calls == 2
    assert not private.exists()


def test_private_tree_cleanup_does_not_confuse_interior_enoent_with_root_absence(
    tmp_path, monkeypatch
):
    audit = module()
    private = tmp_path / "private"
    private.mkdir()
    evidence = private / "evidence.txt"
    evidence.write_text("synthetic evidence")

    def interior_enoent(_path):
        raise FileNotFoundError(errno.ENOENT, "synthetic interior race")

    monkeypatch.setattr(audit.shutil, "rmtree", interior_enoent)

    with pytest.raises(audit.AuditFailure):
        audit.remove_private_tree(private)

    assert private.exists()
    assert evidence.exists()


def test_streamed_zip_container_metadata_is_scanned_by_pinned_gitleaks(tmp_path):
    audit = module()
    scanner = security_module()
    binary_value = os.environ.get("FIRE_AI_GITLEAKS_BIN")
    assert binary_value, "FIRE_AI_GITLEAKS_BIN must identify the pinned official binary"
    binary = Path(binary_value)
    sentinel = fake_token().encode()
    nested_stream = io.BytesIO()
    with zipfile.ZipFile(nested_stream, "w") as nested_archive:
        nested_archive.writestr("content.txt", b"synthetic clean content")
        nested_archive.comment = sentinel
    source = tmp_path / "outer.zip"
    source.write_bytes(archive({"nested.zip": nested_stream.getvalue()}))

    batches, findings = audit.scan_zip_file_in_bounded_batches(
        source,
        tmp_path / "staging",
        Path("surface"),
        max_nested_depth=2,
        scan_batch=lambda root: scanner.scan_directory(root, binary),
    )

    assert batches >= 1
    assert findings == 1


def test_streamed_zip_rejects_later_expansion_namespace_collision(
    tmp_path, monkeypatch
):
    audit = module()
    nested = archive(
        {
            "content-0.bin": secrets.token_bytes(700),
            "content-1.bin": secrets.token_bytes(700),
        }
    )
    source = tmp_path / "outer.zip"
    source.write_bytes(
        archive(
            {
                "large.zip": nested,
                "large.zip.expanded/spoof.txt": b"ambiguous evidence",
            }
        )
    )
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_024)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 4_096)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_BYTES", 16_384)
    scanned = False

    def unexpected_scan(_root):
        nonlocal scanned
        scanned = True
        return 0

    with pytest.raises(audit.AuditFailure):
        audit.scan_zip_file_in_bounded_batches(
            source,
            tmp_path / "staging",
            Path("surface"),
            max_nested_depth=2,
            scan_batch=unexpected_scan,
        )

    assert scanned is False
    assert not (tmp_path / "staging").exists()


def test_collects_selected_pr_logs_and_artifacts_privately(tmp_path):
    audit = module()
    token = fake_token()
    log_zip = archive({"job.txt": "credential = " + token})
    artifact_zip = archive(
        {
            "source/source.tar.gz": gzip_tar_archive(
                {"evidence.json": json.dumps({"value": token})}
            ),
            "wheelhouse/synthetic.whl": archive(
                {"synthetic/__init__.py": "clean synthetic wheel"}
            ),
        }
    )
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
    assert token in "\n".join(readable_private_text(root))
    assert all(auth == "Bearer synthetic-token" for _, _, auth in api.requests)


def test_collects_artifact_over_in_memory_download_limit_via_private_file(
    tmp_path, monkeypatch
):
    audit = module()
    artifact_zip = archive({"evidence.bin": b"x" * 4_096})
    assert len(artifact_zip) > 1_024
    monkeypatch.setattr(audit, "MAX_DOWNLOAD_BYTES", 1_024)
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip",
            archive({"job.txt": "clean"}),
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": False}]}
        ),
        ("/repos/haji84/-AI/actions/artifacts/11/zip", ""): (
            "application/zip",
            artifact_zip,
        ),
    }

    with FixtureApi(routes) as api:
        root = tmp_path / "private"
        manifest = audit.collect_surfaces(
            api.base_url, "haji84/-AI", [], [9], "synthetic-token", root
        )

    assert manifest == {"pull_requests": 0, "workflow_runs": 1, "artifacts": 1}
    assert (root / "workflow-runs/9/artifacts/11/evidence.bin").read_bytes() == b"x" * 4_096
    assert not (root / "workflow-runs/9/artifact-downloads/11.zip").exists()


def test_collects_large_nested_artifact_through_bounded_batch_scanner(
    tmp_path, monkeypatch
):
    audit = module()
    nested = archive(
        {f"part-{index}.bin": secrets.token_bytes(700) for index in range(3)}
    )
    artifact_zip = archive(
        {"large.zip": nested, "manifest.json": b"synthetic manifest"}
    )
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_024)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 2_048)
    monkeypatch.setattr(audit, "MAX_FILES", 2)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_BYTES", 16_384)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_FILES", 10)
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip",
            archive({"job.txt": "clean"}),
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": False}]}
        ),
        ("/repos/haji84/-AI/actions/artifacts/11/zip", ""): (
            "application/zip",
            artifact_zip,
        ),
    }
    observed = set()

    def scan_batch(root):
        observed.update(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )
        return 0

    with FixtureApi(routes) as api:
        root = tmp_path / "private"
        manifest = audit.collect_surfaces(
            api.base_url,
            "haji84/-AI",
            [],
            [9],
            "synthetic-token",
            root,
            scan_batch=scan_batch,
        )

    assert manifest["pull_requests"] == 0
    assert manifest["workflow_runs"] == 1
    assert manifest["artifacts"] == 1
    assert manifest["streamed_batches"] >= 3
    assert manifest["streamed_findings"] == 0
    assert {
        "workflow-runs/9/artifacts/11/large.zip.expanded/part-0.bin",
        "workflow-runs/9/artifacts/11/large.zip.expanded/part-1.bin",
        "workflow-runs/9/artifacts/11/large.zip.expanded/part-2.bin",
        "workflow-runs/9/artifacts/11/manifest.json",
    }.issubset(observed)
    assert any("/.container-parts/" in path for path in observed)
    assert not (root / "workflow-runs/9/artifact-streaming/11").exists()


def test_collects_safe_finding_source_without_secret_material(tmp_path):
    audit = module()
    sentinel = fake_token()
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip",
            archive({"job.txt": "clean"}),
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": False}]}
        ),
        ("/repos/haji84/-AI/actions/artifacts/11/zip", ""): (
            "application/zip",
            archive({"evidence.txt": f"credential = {sentinel}"}),
        ),
    }

    def scan_batch(root):
        contents = b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())
        if sentinel.encode() in contents:
            return 1, ("generic-api-key",)
        return 0, ()

    with FixtureApi(routes) as api:
        root = tmp_path / "private"
        manifest = audit.collect_surfaces(
            api.base_url,
            "haji84/-AI",
            [],
            [9],
            "synthetic-token",
            root,
            scan_batch=scan_batch,
        )

    assert manifest["streamed_findings"] == 1
    assert manifest["finding_sources"] == "workflow-run:9/artifact:11/rules:generic-api-key"
    assert sentinel not in repr(manifest)


def test_collects_highly_compressed_nested_artifact_without_retry(
    tmp_path, monkeypatch
):
    audit = module()
    nested_stream = io.BytesIO()
    with zipfile.ZipFile(
        nested_stream, "w", compression=zipfile.ZIP_DEFLATED
    ) as nested_archive:
        for index in range(4):
            nested_archive.writestr(f"expanded-{index}.txt", b"x" * 900)
    nested = nested_stream.getvalue()
    assert len(nested) < 1_024
    artifact_zip = archive({"compact.zip": nested})
    monkeypatch.setattr(audit, "MAX_ENTRY_BYTES", 1_024)
    monkeypatch.setattr(audit, "MAX_EXTRACTED_BYTES", 2_048)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_BYTES", 16_384)
    monkeypatch.setattr(audit, "MAX_STREAMED_AUDIT_FILES", 10)
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip",
            archive({"job.txt": "clean"}),
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 1, "artifacts": [{"id": 11, "expired": False}]}
        ),
        ("/repos/haji84/-AI/actions/artifacts/11/zip", ""): (
            "application/zip",
            artifact_zip,
        ),
    }
    observed_expanded = set()

    def scan_batch(root):
        observed_expanded.update(
            path.name
            for path in root.rglob("expanded-*.txt")
            if path.is_file() and path.read_bytes() == b"x" * 900
        )
        return 0

    with FixtureApi(routes) as api:
        audit.collect_surfaces(
            api.base_url,
            "haji84/-AI",
            [],
            [9],
            "synthetic-token",
            tmp_path / "private",
            scan_batch=scan_batch,
        )

    assert observed_expanded == {f"expanded-{index}.txt" for index in range(4)}


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


def test_historical_inventory_is_complete_stable_and_repository_bound():
    audit = module()
    pull_requests = [
        {"number": number, "base": {"repo": {"full_name": "haji84/-AI"}}}
        for number in range(1, 102)
    ]
    workflow_runs = [
        {
            "id": run_id,
            "status": "completed",
            "repository": {"full_name": "haji84/-AI"},
        }
        for run_id in range(200, 99, -1)
    ] + [
        {
            "id": 99,
            "status": "in_progress",
            "repository": {"full_name": "haji84/-AI"},
        }
    ]
    routes = {
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=1",
        ): encoded(pull_requests[:100]),
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=2",
        ): encoded(pull_requests[100:]),
        (
            "/repos/haji84/-AI/actions/runs",
            "per_page=100&page=1",
        ): encoded({"total_count": 102, "workflow_runs": workflow_runs[:100]}),
        (
            "/repos/haji84/-AI/actions/runs",
            "per_page=100&page=2",
        ): encoded({"total_count": 102, "workflow_runs": workflow_runs[100:]}),
    }

    with FixtureApi(routes) as api:
        inventory = audit.discover_historical_inventory(
            api.base_url, "haji84/-AI", "synthetic-token"
        )

    assert inventory["pull_requests"] == list(range(1, 102))
    assert inventory["workflow_runs"] == list(range(99, 201))
    assert inventory["completed_workflow_runs"] == list(range(100, 201))
    assert inventory["pull_request_count"] == 101
    assert inventory["workflow_run_count"] == 102
    assert inventory["completed_workflow_run_count"] == 101
    assert re.fullmatch(r"[0-9a-f]{64}", inventory["inventory_sha256"])
    assert len(api.requests) == 8  # every discovered page is re-read for stability
    assert all(auth == "Bearer synthetic-token" for _, _, auth in api.requests)


def test_historical_pull_request_inventory_rechecks_every_page():
    audit = module()
    repository = "haji84/-AI"
    first_page = [
        {"number": number, "base": {"repo": {"full_name": repository}}}
        for number in range(1, 101)
    ]
    page_two_versions = iter(
        [
            [{"number": 101, "base": {"repo": {"full_name": repository}}}],
            [
                {"number": 101, "base": {"repo": {"full_name": repository}}},
                {"number": 102, "base": {"repo": {"full_name": repository}}},
            ],
        ]
    )
    routes = {
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=1",
        ): encoded(first_page),
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=2",
        ): lambda: encoded(next(page_two_versions)),
    }

    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit._historical_pull_requests(
                api.base_url,
                repository,
                "synthetic-token",
                time.monotonic() + 10,
            )


def test_historical_pull_request_inventory_ignores_non_identity_drift():
    audit = module()
    repository = "haji84/-AI"
    versions = iter(
        [
            [
                {
                    "number": 1,
                    "state": "open",
                    "updated_at": "2026-10-12T00:00:00Z",
                    "base": {"repo": {"full_name": repository}},
                }
            ],
            [
                {
                    "number": 1,
                    "state": "closed",
                    "updated_at": "2026-10-12T00:00:01Z",
                    "base": {"repo": {"full_name": repository}},
                }
            ],
        ]
    )
    routes = {
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=1",
        ): lambda: encoded(next(versions)),
    }

    with FixtureApi(routes) as api:
        assert audit._historical_pull_requests(
            api.base_url,
            repository,
            "synthetic-token",
            time.monotonic() + 10,
        ) == [1]


def test_historical_workflow_inventory_rechecks_later_page_status():
    audit = module()
    repository = "haji84/-AI"
    first_page = [
        {
            "id": run_id,
            "status": "completed",
            "repository": {"full_name": repository},
        }
        for run_id in range(201, 101, -1)
    ]
    page_two_versions = iter(
        [
            [
                {
                    "id": 101,
                    "status": "in_progress",
                    "repository": {"full_name": repository},
                }
            ],
            [
                {
                    "id": 101,
                    "status": "completed",
                    "repository": {"full_name": repository},
                }
            ],
        ]
    )
    routes = {
        ("/repos/haji84/-AI/actions/runs", "per_page=100&page=1"): encoded(
            {"total_count": 101, "workflow_runs": first_page}
        ),
        ("/repos/haji84/-AI/actions/runs", "per_page=100&page=2"): lambda: encoded(
            {"total_count": 101, "workflow_runs": next(page_two_versions)}
        ),
    }

    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit._historical_workflow_runs(
                api.base_url,
                repository,
                "synthetic-token",
                time.monotonic() + 10,
            )


def test_historical_workflow_inventory_ignores_non_completed_status_drift():
    audit = module()
    repository = "haji84/-AI"
    versions = iter(
        [
            {
                "total_count": 1,
                "workflow_runs": [
                    {
                        "id": 101,
                        "status": "queued",
                        "updated_at": "2026-10-12T00:00:00Z",
                        "repository": {"full_name": repository},
                    }
                ],
            },
            {
                "total_count": 1,
                "workflow_runs": [
                    {
                        "id": 101,
                        "status": "in_progress",
                        "updated_at": "2026-10-12T00:00:01Z",
                        "repository": {"full_name": repository},
                    }
                ],
            },
        ]
    )
    routes = {
        ("/repos/haji84/-AI/actions/runs", "per_page=100&page=1"): lambda: encoded(
            next(versions)
        ),
    }

    with FixtureApi(routes) as api:
        assert audit._historical_workflow_runs(
            api.base_url,
            repository,
            "synthetic-token",
            time.monotonic() + 10,
        ) == ([101], [])


@pytest.mark.parametrize(
    ("pull_requests", "workflow_total", "workflow_runs"),
    [
        ([{"number": True, "base": {"repo": {"full_name": "haji84/-AI"}}}], 0, []),
        (
            [
                {"number": 7, "base": {"repo": {"full_name": "haji84/-AI"}}},
                {"number": 7, "base": {"repo": {"full_name": "haji84/-AI"}}},
            ],
            0,
            [],
        ),
        (
            [{"number": 7, "base": {"repo": {"full_name": "other/repo"}}}],
            0,
            [],
        ),
        (
            [],
            True,
            [],
        ),
        (
            [],
            1,
            [
                {
                    "id": 9,
                    "status": 7,
                    "repository": {"full_name": "haji84/-AI"},
                }
            ],
        ),
        (
            [],
            1,
            [
                {
                    "id": 9,
                    "status": "completed",
                    "repository": {"full_name": "other/repo"},
                }
            ],
        ),
    ],
)
def test_historical_inventory_rejects_ambiguous_or_cross_repository_rows(
    pull_requests, workflow_total, workflow_runs
):
    audit = module()
    routes = {
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=1",
        ): encoded(pull_requests),
        (
            "/repos/haji84/-AI/actions/runs",
            "per_page=100&page=1",
        ): encoded(
            {"total_count": workflow_total, "workflow_runs": workflow_runs}
        ),
    }

    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.discover_historical_inventory(
                api.base_url, "haji84/-AI", "synthetic-token"
            )


def test_historical_batch_is_bounded_restartable_and_rejects_bad_cursors():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [2, 7, 12],
        "workflow_runs": [9, 11, 15],
        "completed_workflow_runs": [9, 11, 15],
        "pull_request_count": 3,
        "workflow_run_count": 3,
        "completed_workflow_run_count": 3,
        "inventory_sha256": "a" * 64,
    }

    snapshot_sha256 = audit.historical_snapshot_sha256(
        inventory, through_pull_request=12, through_workflow_run=15
    )
    cursor_sha256 = audit.historical_cursor_sha256(
        inventory,
        after_pull_request=2,
        after_workflow_run=9,
        through_pull_request=12,
        through_workflow_run=15,
        snapshot_initialized=True,
    )
    batch = audit.select_historical_batch(
        inventory,
        after_pull_request=2,
        after_workflow_run=9,
        pull_request_limit=1,
        workflow_run_limit=1,
        expected_cursor_sha256=cursor_sha256,
        through_pull_request=12,
        through_workflow_run=15,
        snapshot_initialized=True,
        expected_snapshot_sha256=snapshot_sha256,
    )

    assert batch == {
        "pull_requests": [7],
        "workflow_runs": [11],
        "next_pull_request": 7,
        "next_workflow_run": 11,
        "remaining_pull_requests": 1,
        "remaining_workflow_runs": 1,
        "blocked_workflow_run": None,
        "snapshot_pull_request": 12,
        "snapshot_workflow_run": 15,
        "snapshot_initialized": True,
        "snapshot_sha256": snapshot_sha256,
        "next_cursor_sha256": audit.historical_cursor_sha256(
            inventory,
            after_pull_request=7,
            after_workflow_run=11,
            through_pull_request=12,
            through_workflow_run=15,
            snapshot_initialized=True,
        ),
    }
    for bad in (-1, True, 1.5):
        with pytest.raises(audit.AuditFailure):
            audit.select_historical_batch(
                inventory,
                after_pull_request=bad,
                after_workflow_run=0,
                pull_request_limit=1,
                workflow_run_limit=1,
                expected_cursor_sha256="",
            )
    with pytest.raises(audit.AuditFailure):
        audit.select_historical_batch(
            inventory,
            after_pull_request=3,
            after_workflow_run=0,
            pull_request_limit=1,
            workflow_run_limit=1,
            expected_cursor_sha256="",
        )


def test_historical_cursor_is_bound_to_the_audited_inventory_prefix():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [2, 7, 12],
        "workflow_runs": [100, 200, 300],
        "completed_workflow_runs": [100, 300],
    }
    snapshot_sha256 = audit.historical_snapshot_sha256(
        inventory, through_pull_request=12, through_workflow_run=300
    )
    cursor_sha256 = audit.historical_cursor_sha256(
        inventory,
        after_pull_request=7,
        after_workflow_run=300,
        through_pull_request=12,
        through_workflow_run=300,
        snapshot_initialized=True,
    )

    changed = dict(inventory, completed_workflow_runs=[100, 200, 300])
    with pytest.raises(audit.AuditFailure):
        audit.select_historical_batch(
            changed,
            after_pull_request=7,
            after_workflow_run=300,
            pull_request_limit=1,
            workflow_run_limit=1,
            expected_cursor_sha256=cursor_sha256,
            through_pull_request=12,
            through_workflow_run=300,
            snapshot_initialized=True,
            expected_snapshot_sha256=snapshot_sha256,
        )


def test_first_historical_batch_cannot_start_after_zero():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [1, 2],
        "workflow_runs": [10, 20],
        "completed_workflow_runs": [10, 20],
    }
    with pytest.raises(audit.AuditFailure):
        audit.select_historical_batch(
            inventory,
            after_pull_request=1,
            after_workflow_run=10,
            pull_request_limit=1,
            workflow_run_limit=1,
            expected_cursor_sha256=audit.historical_cursor_sha256(
                inventory, after_pull_request=1, after_workflow_run=10
            ),
        )


def test_historical_snapshot_has_a_finite_end_when_new_surfaces_arrive():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [1, 2],
        "workflow_runs": [10, 20],
        "completed_workflow_runs": [10, 20],
    }
    first = audit.select_historical_batch(
        inventory,
        after_pull_request=0,
        after_workflow_run=0,
        through_pull_request=0,
        through_workflow_run=0,
        pull_request_limit=100,
        workflow_run_limit=100,
        expected_cursor_sha256="",
    )
    assert first["snapshot_pull_request"] == 2
    assert first["snapshot_workflow_run"] == 20

    expanded = {
        **inventory,
        "pull_requests": [1, 2, 3],
        "workflow_runs": [10, 20, 30],
        "completed_workflow_runs": [10, 20, 30],
    }
    finished = audit.select_historical_batch(
        expanded,
        after_pull_request=first["next_pull_request"],
        after_workflow_run=first["next_workflow_run"],
        through_pull_request=first["snapshot_pull_request"],
        through_workflow_run=first["snapshot_workflow_run"],
        snapshot_initialized=True,
        expected_snapshot_sha256=first["snapshot_sha256"],
        pull_request_limit=100,
        workflow_run_limit=100,
        expected_cursor_sha256=first["next_cursor_sha256"],
    )
    assert finished["pull_requests"] == []
    assert finished["workflow_runs"] == []
    assert finished["remaining_pull_requests"] == 0
    assert finished["remaining_workflow_runs"] == 0


def test_historical_snapshot_rejects_deleted_unprocessed_run():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [],
        "workflow_runs": [100, 200, 300],
        "completed_workflow_runs": [100, 200, 300],
    }
    first = audit.select_historical_batch(
        inventory,
        after_pull_request=0,
        after_workflow_run=0,
        pull_request_limit=1,
        workflow_run_limit=1,
    )
    deleted = {
        **inventory,
        "workflow_runs": [100, 300],
        "completed_workflow_runs": [100, 300],
    }

    with pytest.raises(audit.AuditFailure):
        audit.select_historical_batch(
            deleted,
            after_pull_request=first["next_pull_request"],
            after_workflow_run=first["next_workflow_run"],
            through_pull_request=first["snapshot_pull_request"],
            through_workflow_run=first["snapshot_workflow_run"],
            snapshot_initialized=True,
            expected_snapshot_sha256=first["snapshot_sha256"],
            pull_request_limit=1,
            workflow_run_limit=1,
            expected_cursor_sha256=first["next_cursor_sha256"],
        )


def test_historical_snapshot_preserves_an_initially_empty_category():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [],
        "workflow_runs": [10],
        "completed_workflow_runs": [],
    }
    first = audit.select_historical_batch(
        inventory,
        after_pull_request=0,
        after_workflow_run=0,
        pull_request_limit=1,
        workflow_run_limit=1,
    )
    assert first["snapshot_pull_request"] == 0

    expanded = {**inventory, "pull_requests": [1]}
    continued = audit.select_historical_batch(
        expanded,
        after_pull_request=0,
        after_workflow_run=0,
        through_pull_request=0,
        through_workflow_run=10,
        snapshot_initialized=True,
        expected_snapshot_sha256=first["snapshot_sha256"],
        pull_request_limit=1,
        workflow_run_limit=1,
        expected_cursor_sha256=first["next_cursor_sha256"],
    )
    assert continued["snapshot_pull_request"] == 0
    assert continued["pull_requests"] == []


def test_historical_batch_never_crosses_an_incomplete_workflow_run():
    audit = module()
    inventory = {
        "repository": "haji84/-AI",
        "pull_requests": [],
        "workflow_runs": [100, 200, 300],
        "completed_workflow_runs": [100, 300],
    }

    batch = audit.select_historical_batch(
        inventory,
        after_pull_request=0,
        after_workflow_run=100,
        pull_request_limit=1,
        workflow_run_limit=2,
        expected_cursor_sha256=audit.historical_cursor_sha256(
            inventory,
            after_pull_request=0,
            after_workflow_run=100,
            through_pull_request=0,
            through_workflow_run=300,
            snapshot_initialized=True,
        ),
        through_pull_request=0,
        through_workflow_run=300,
        snapshot_initialized=True,
        expected_snapshot_sha256=audit.historical_snapshot_sha256(
            inventory, through_pull_request=0, through_workflow_run=300
        ),
    )

    assert batch["workflow_runs"] == []
    assert batch["next_workflow_run"] == 100
    assert batch["blocked_workflow_run"] == 200
    assert batch["remaining_workflow_runs"] == 1


def test_historical_inventory_applies_a_global_surface_count_bound(monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_HISTORY_SURFACES", 2)
    pull_requests = [
        {"number": number, "base": {"repo": {"full_name": "haji84/-AI"}}}
        for number in range(1, 4)
    ]
    routes = {
        (
            "/repos/haji84/-AI/pulls",
            "state=all&sort=created&direction=asc&per_page=100&page=1",
        ): encoded(pull_requests),
        (
            "/repos/haji84/-AI/actions/runs",
            "per_page=100&page=1",
        ): encoded({"total_count": 0, "workflow_runs": []}),
    }

    with FixtureApi(routes) as api:
        with pytest.raises(audit.AuditFailure):
            audit.discover_historical_inventory(
                api.base_url, "haji84/-AI", "synthetic-token"
            )


def test_historical_inventory_has_one_bounded_discovery_deadline(monkeypatch):
    audit = module()
    monkeypatch.setattr(audit, "MAX_HISTORY_DISCOVERY_SECONDS", 0)

    with pytest.raises(audit.AuditFailure):
        audit.discover_historical_inventory(
            "https://api.github.invalid", "haji84/-AI", "synthetic-token"
        )


def test_history_request_cannot_outlive_the_shared_discovery_deadline(monkeypatch):
    audit = module()

    class SlowResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            time.sleep(0.2)
            return b""

    class SlowOpener:
        def open(self, _request, timeout):
            assert 0 < timeout < audit.DOWNLOAD_TIMEOUT_SECONDS
            return SlowResponse()

    monkeypatch.setattr(audit, "build_opener", lambda *_handlers: SlowOpener())
    started = time.monotonic()
    with pytest.raises(audit.AuditFailure):
        audit.request_bytes(
            "https://api.github.invalid/synthetic",
            "synthetic-token",
            deadline=time.monotonic() + 0.03,
        )
    assert time.monotonic() - started < 0.15


def test_security_workflow_has_manual_private_published_surface_gate():
    workflow = SCRIPT.parents[1] / ".github/workflows/security-checks.yml"
    content = workflow.read_text()
    expected_workflows = discover_workflow_names(workflow.parent) - {"security-checks"}

    watched_block = re.search(
        r"workflow_run:\s*\n\s+workflows:\s*\[(.*?)\]\s*\n",
        content,
        re.DOTALL,
    )
    assert watched_block, "workflow_run must declare an explicit workflow allowlist"
    watched_workflows = set(re.findall(r'"([^"]+)"', watched_block.group(1)))

    assert "workflow_dispatch:" in content
    assert "historical:" in content
    assert "history_after_pull_request:" in content
    assert "history_after_workflow_run:" in content
    assert "history_pull_request_limit:" in content
    assert "history_workflow_run_limit:" in content
    assert "history_cursor_sha256:" in content
    assert "history_through_pull_request:" in content
    assert "history_through_workflow_run:" in content
    assert "history_snapshot_initialized:" in content
    assert "history_snapshot_sha256:" in content
    assert "workflow_run:" in content
    assert watched_workflows == expected_workflows
    assert "security-checks" not in watched_workflows
    assert "types: [completed]" in content
    assert "published-surface-audit:" in content
    assert "actions: read" in content
    assert "pull-requests: read" in content
    assert "FIRE_AI_GITHUB_AUDIT_TOKEN: ${{ github.token }}" in content
    assert "scripts/audit_github_published_surfaces.py" in content
    assert "github.event.workflow_run.id" in content
    assert "--historical" in content
    assert "--history-after-pull-request" in content
    assert "--history-after-workflow-run" in content
    assert "--history-pull-request-limit" in content
    assert "--history-workflow-run-limit" in content
    assert "--history-cursor-sha256" in content
    assert "--history-through-pull-request" in content
    assert "--history-through-workflow-run" in content
    assert "--history-snapshot-initialized" in content
    assert "--history-snapshot-sha256" in content
    history_branch = content.index('if [[ "$FIRE_AI_HISTORY_MODE" == "true" ]]')
    assert content.index('--pull-requests "$FIRE_AI_PULL_REQUEST_IDS"') < history_branch
    assert content.index('--workflow-runs "$FIRE_AI_WORKFLOW_RUN_IDS"') < history_branch
    assert "upload-artifact" not in content


def test_cli_errors_never_echo_token_repository_or_private_payload(monkeypatch, capsys):
    audit = module()
    sentinel = "private-fixture-" + secrets.token_hex(12)
    monkeypatch.setenv("FIRE_AI_GITHUB_AUDIT_TOKEN", sentinel)
    assert audit.main(["--repository", sentinel, "--pull-request", "7", "--gitleaks", sentinel]) == 2
    output = capsys.readouterr().out
    assert sentinel not in output
    assert output.strip() == "Published-surface secret audit failed closed; findings=unknown"


def test_cli_attributes_workflow_log_finding_to_run_without_secret(monkeypatch, capsys):
    audit = module()
    binary_value = os.environ.get("FIRE_AI_GITLEAKS_BIN")
    assert binary_value, "FIRE_AI_GITLEAKS_BIN must identify the pinned official binary"
    sentinel = fake_token()
    routes = {
        ("/repos/haji84/-AI/actions/runs/9", ""): encoded(
            {"id": 9, "status": "completed", "repository": {"full_name": "haji84/-AI"}}
        ),
        ("/repos/haji84/-AI/actions/runs/9/logs", ""): (
            "application/zip",
            archive({"job.txt": f"credential = {sentinel}"}),
        ),
        ("/repos/haji84/-AI/actions/runs/9/artifacts", "per_page=100&page=1"): encoded(
            {"total_count": 0, "artifacts": []}
        ),
    }
    monkeypatch.setenv("FIRE_AI_GITHUB_AUDIT_TOKEN", "synthetic-token")

    with FixtureApi(routes) as api:
        result = audit.main(
            [
                "--repository",
                "haji84/-AI",
                "--workflow-run",
                "9",
                "--gitleaks",
                binary_value,
                "--api-url",
                api.base_url,
            ]
        )

    output = capsys.readouterr().out.strip()
    assert result == 1
    assert "workflow-run:9/rules:" in output
    assert "collected-metadata" not in output
    assert sentinel not in output


def test_cli_aggregates_streamed_and_collected_findings(monkeypatch, capsys):
    audit = module()
    scanner_calls = []
    summary = namedtuple("Summary", ("findings", "rule_ids"))

    class Scanner:
        def scan_directory_summary(self, root, binary, *, accepted_findings):
            scanner_calls.append((root, binary, accepted_findings))
            return summary(
                3 if root == Path("synthetic-batch") else 2,
                ("generic-api-key",),
            )

    def collect(
        _api_url,
        _repository,
        _pull_requests,
        _workflow_runs,
        _token,
        _root,
        *,
        scan_batch,
    ):
        assert scan_batch(Path("synthetic-batch")).findings == 3
        return {
            "pull_requests": 0,
            "workflow_runs": 1,
            "artifacts": 1,
            "streamed_batches": 1,
            "streamed_findings": 3,
            "finding_sources": "workflow-run:9/artifact:11/rules:generic-api-key",
        }

    monkeypatch.setenv("FIRE_AI_GITHUB_AUDIT_TOKEN", "synthetic-token")
    monkeypatch.setattr(audit, "scanner_module", lambda: Scanner())
    monkeypatch.setattr(audit, "collect_surfaces", collect)

    assert audit.main(
        [
            "--repository",
            "haji84/-AI",
            "--workflow-run",
            "9",
            "--gitleaks",
            "/synthetic/gitleaks",
        ]
    ) == 1
    output = capsys.readouterr().out.strip()
    assert "streamed_batches=1" in output
    assert "streamed_findings" not in output
    assert "workflow-run:9/artifact:11/rules:generic-api-key" in output
    assert "workflow-run:9/rules:generic-api-key" in output
    assert output.endswith("findings=5")
    assert len(scanner_calls) == 2


def test_cli_scopes_reviewed_workflow_log_identity_to_exact_source_scan(
    tmp_path, monkeypatch, capsys
):
    audit = module()
    calls = []
    summary = namedtuple("Summary", ("findings", "rule_ids"))

    class Scanner:
        def scan_directory_summary(self, root, binary, *, accepted_findings):
            calls.append((root, binary, accepted_findings))
            return summary(0, ())

    def collect(
        _api_url,
        _repository,
        _pull_requests,
        workflow_runs,
        _token,
        root,
        *,
        scan_batch,
    ):
        assert workflow_runs == [37493709157]
        assert scan_batch(Path("synthetic-artifact-batch")).findings == 0
        source_root = root / "workflow-runs" / "37493709157"
        candidate = source_root / "logs" / "backend-tests.txt"
        candidate.parent.mkdir(parents=True)
        candidate.write_text(reviewed_import_preview_traceback())
        pin_reviewed_identity(audit, monkeypatch, source_root, candidate)
        return {
            "pull_requests": 0,
            "workflow_runs": 1,
            "artifacts": 0,
            "streamed_batches": 0,
            "streamed_findings": 0,
        }

    monkeypatch.setenv("FIRE_AI_GITHUB_AUDIT_TOKEN", "synthetic-token")
    monkeypatch.setattr(audit, "scanner_module", lambda: Scanner())
    monkeypatch.setattr(audit, "collect_surfaces", collect)

    assert audit.main(
        [
            "--repository",
            "haji84/-AI",
            "--workflow-run",
            "37493709157",
            "--gitleaks",
            str(tmp_path / "gitleaks"),
        ]
    ) == 0
    assert capsys.readouterr().out.startswith("Published-surface secret audit passed;")
    assert len(calls) == 2
    artifact_acceptance = calls[0][2]
    source_acceptance = calls[1][2]
    assert artifact_acceptance == audit.REVIEWED_PUBLIC_DEPENDENCY_FINDINGS
    assert source_acceptance > artifact_acceptance
    assert len(source_acceptance - artifact_acceptance) == 1
