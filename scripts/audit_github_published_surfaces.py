#!/usr/bin/env python3
"""Privately collect and secret-scan selected published GitHub surfaces.

The caller selects exact pull-request and workflow-run IDs. Downloaded bytes,
API payloads and scanner reports remain in private temporary directories.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import tempfile
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile
import io


MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_FILES = 20_000
MAX_ENTRY_BYTES = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
NESTED_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class AuditFailure(Exception):
    """Private details must never be printed by the CLI."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise AuditFailure()


@contextmanager
def absolute_deadline(seconds):
    """Bound connection, headers and body by one Linux wall-clock deadline."""
    try:
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
        if previous_timer != (0.0, 0.0):
            raise AuditFailure()

        def expired(_signum, _frame):
            raise AuditFailure()

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


class PrivateRedirectHandler(HTTPRedirectHandler):
    """Never forward the GitHub bearer token to a download origin."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        redirected = super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )
        if redirected is None:
            return None
        old = urlparse(request.full_url)
        new = urlparse(new_url)
        if new.scheme not in {"http", "https"}:
            raise AuditFailure()
        if old.scheme == "https" and new.scheme != "https":
            raise AuditFailure()
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            redirected.remove_header("Authorization")
        return redirected


def scanner_module():
    path = Path(__file__).with_name("security_scan.py")
    spec = importlib.util.spec_from_file_location("fire_aios_private_scanner", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def request_bytes(url, token, *, accept="application/vnd.github+json"):
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "User-Agent": "fire-aios-private-published-surface-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with absolute_deadline(DOWNLOAD_TIMEOUT_SECONDS):
            with build_opener(PrivateRedirectHandler()).open(
                request, timeout=DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                expected = response.headers.get("Content-Length")
                if expected and int(expected) > MAX_DOWNLOAD_BYTES:
                    raise AuditFailure()
                chunks = []
                size = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise AuditFailure()
                    chunks.append(chunk)
                return b"".join(chunks)
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def json_request(url, token):
    try:
        value = json.loads(request_bytes(url, token))
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error
    return value


def paginated_list(api_url, path, token):
    rows = []
    for page in range(1, 1001):
        query = urlencode({"per_page": 100, "page": page})
        value = json_request(f"{api_url}{path}?{query}", token)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise AuditFailure()
        rows.extend(value)
        if len(value) < 100:
            return rows
    raise AuditFailure()


def artifact_list(api_url, repository, run_id, token):
    rows = []
    expected = None
    for page in range(1, 1001):
        query = urlencode({"per_page": 100, "page": page})
        value = json_request(
            f"{api_url}/repos/{repository}/actions/runs/{run_id}/artifacts?{query}", token
        )
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("artifacts"), list)
            or any(not isinstance(row, dict) for row in value["artifacts"])
        ):
            raise AuditFailure()
        if expected is None:
            expected = value.get("total_count")
            if type(expected) is not int or expected < 0:
                raise AuditFailure()
        rows.extend(value["artifacts"])
        if len(value["artifacts"]) < 100:
            if len(rows) != expected:
                raise AuditFailure()
            return rows
    raise AuditFailure()


def is_nested_archive(path, payload):
    if path.suffix.lower() in NESTED_ARCHIVE_SUFFIXES:
        return True
    signatures = (
        b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b",
        b"7z\xbc\xaf\x27\x1c", b"\xfd7zXZ\x00", b"BZh",
        b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00",
    )
    return (
        payload.startswith(signatures)
        or payload[257:262] == b"ustar"
        or zipfile.is_zipfile(io.BytesIO(payload))
    )


def extract_zip(payload, destination):
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except Exception as error:
        raise AuditFailure() from error
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    total = 0
    files = 0
    try:
        with archive:
            members = archive.infolist()
            paths = set()
            for member in members:
                path = PurePosixPath(member.filename)
                mode = member.external_attr >> 16
                if path.is_absolute() or not path.parts or ".." in path.parts:
                    raise AuditFailure()
                if path.parts in paths:
                    raise AuditFailure()
                paths.add(path.parts)
                file_type = stat.S_IFMT(mode)
                if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
                    raise AuditFailure()
                if member.is_dir():
                    continue
                files += 1
                total += member.file_size
                if files > MAX_FILES or member.file_size > MAX_ENTRY_BYTES or total > MAX_EXTRACTED_BYTES:
                    raise AuditFailure()
            for member in members:
                if member.is_dir():
                    continue
                target = destination.joinpath(*PurePosixPath(member.filename).parts)
                data = archive.read(member)
                if len(data) != member.file_size or is_nested_archive(target, data):
                    raise AuditFailure()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    except AuditFailure:
        raise
    except Exception as error:
        raise AuditFailure() from error


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def parse_id_list(value, repeated):
    if not value:
        return list(repeated)
    if not re.fullmatch(r"[1-9][0-9]*(,[1-9][0-9]*)*", value):
        raise AuditFailure()
    return [int(item) for item in value.split(",")] + list(repeated)


def collect_surfaces(api_url, repository, pull_requests, workflow_runs, token, root):
    if not token or not REPOSITORY.fullmatch(repository):
        raise AuditFailure()
    pull_requests = sorted(set(pull_requests))
    workflow_runs = sorted(set(workflow_runs))
    if not pull_requests and not workflow_runs:
        raise AuditFailure()
    if any(value <= 0 for value in pull_requests + workflow_runs):
        raise AuditFailure()
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = {"pull_requests": 0, "workflow_runs": 0, "artifacts": 0}

    for number in pull_requests:
        base = f"/repos/{repository}"
        metadata = json_request(f"{api_url}{base}/pulls/{number}", token)
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("number")) is not int
            or metadata.get("number") != number
        ):
            raise AuditFailure()
        location = root / "pull-requests" / str(number)
        write_json(location / "metadata.json", metadata)
        write_json(location / "issue-comments.json", paginated_list(api_url, f"{base}/issues/{number}/comments", token))
        write_json(location / "review-comments.json", paginated_list(api_url, f"{base}/pulls/{number}/comments", token))
        write_json(location / "reviews.json", paginated_list(api_url, f"{base}/pulls/{number}/reviews", token))
        manifest["pull_requests"] += 1

    for run_id in workflow_runs:
        base = f"/repos/{repository}/actions"
        metadata = json_request(f"{api_url}{base}/runs/{run_id}", token)
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("id")) is not int
            or metadata.get("id") != run_id
            or metadata.get("status") != "completed"
            or metadata.get("repository", {}).get("full_name") != repository
        ):
            raise AuditFailure()
        location = root / "workflow-runs" / str(run_id)
        write_json(location / "metadata.json", metadata)
        logs = request_bytes(
            f"{api_url}{base}/runs/{run_id}/logs", token, accept="application/vnd.github+json"
        )
        extract_zip(logs, location / "logs")
        artifacts = artifact_list(api_url, repository, run_id, token)
        write_json(location / "artifacts.json", artifacts)
        for artifact in artifacts:
            artifact_id = artifact.get("id") if isinstance(artifact, dict) else None
            if type(artifact_id) is not int or artifact_id <= 0 or artifact.get("expired") is not False:
                raise AuditFailure()
            payload = request_bytes(
                f"{api_url}{base}/artifacts/{artifact_id}/zip", token,
                accept="application/vnd.github+json",
            )
            extract_zip(payload, location / "artifacts" / str(artifact_id))
            manifest["artifacts"] += 1
        manifest["workflow_runs"] += 1
    write_json(root / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = SafeParser(description="Privately scan selected published GitHub surfaces.")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, action="append", default=[])
    parser.add_argument("--workflow-run", type=int, action="append", default=[])
    parser.add_argument("--pull-requests", default="")
    parser.add_argument("--workflow-runs", default="")
    parser.add_argument("--gitleaks", type=Path, required=True)
    parser.add_argument("--api-url", default="https://api.github.com", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
        token = os.environ.get("FIRE_AI_GITHUB_AUDIT_TOKEN")
        if not token:
            raise AuditFailure()
        with tempfile.TemporaryDirectory(
            prefix="fire-aios-published-surface-", dir="/tmp"
        ) as location:
            private = Path(location) / "collected"
            manifest = collect_surfaces(
                args.api_url.rstrip("/"), args.repository,
                parse_id_list(args.pull_requests, args.pull_request),
                parse_id_list(args.workflow_runs, args.workflow_run), token, private,
            )
            findings = scanner_module().scan_directory(private, args.gitleaks)
        counts = "; ".join(f"{key}={value}" for key, value in manifest.items())
        print(
            f"Published-surface secret audit {'blocked' if findings else 'passed'}; "
            f"{counts}; findings={findings}"
        )
        return 1 if findings else 0
    except Exception:
        print("Published-surface secret audit failed closed; findings=unknown")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
