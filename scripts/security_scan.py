#!/usr/bin/env python3
"""Fail-closed, private secret gate for fetched Git refs and working-tree files.

The caller fetches all required refs and installs the pinned Linux x64 binary.
No download, baseline, repository configuration, or skip mode is supported.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import tempfile
import time

VERSION = "8.30.1"
BINARY_SHA256 = "88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509"
TIMEOUT_SECONDS = 300
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
TRUSTED_CONFIG = "[extend]\nuseDefault = true\n"


class ScanFailure(Exception):
    """Internal details must never be printed by the CLI."""


def report_bytes(private_dir):
    size = 0
    for path in private_dir.glob("*.json"):
        try:
            size += path.stat().st_size
        except FileNotFoundError:
            # Gitleaks can replace its report atomically while running.
            # RLIMIT_FSIZE bounds each write; final report is required below.
            continue
    return size


def run_private(command, private_dir, env, *, timeout=TIMEOUT_SECONDS,
                max_bytes=MAX_CAPTURE_BYTES):
    """Capture private output with a finite deadline and byte budget (Linux).

    Streams are drained in bounded chunks into private files, never inherited
    by the parent terminal. Reports share the byte budget. Kill the entire
    scanner/Git process group on failure.
    """
    started = time.monotonic()
    stdout_path = private_dir / "stdout"
    stderr_path = private_dir / "stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=private_dir, env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True,
                                   preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (max_bytes, max_bytes)))
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, stdout)
                selector.register(process.stderr, selectors.EVENT_READ, stderr)
                captured = 0
                while selector.get_map() or process.poll() is None:
                    if time.monotonic() - started > timeout:
                        raise ScanFailure()
                    report_size = report_bytes(private_dir)
                    if captured + report_size > max_bytes:
                        raise ScanFailure()
                    for key, _ in selector.select(timeout=0.05):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            captured += len(chunk)
                            if captured + report_size > max_bytes:
                                raise ScanFailure()
                            key.data.write(chunk)
                stdout.flush()
                stderr.flush()
                if captured + report_bytes(private_dir) > max_bytes:
                    raise ScanFailure()
            return process.wait(), stdout_path.read_bytes()
        finally:
            # Descendants can retain pipes after their parent has exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
            process.stderr.close()


def safe_environment():
    # Repository routing and caller-supplied config cannot change the scope.
    return {"PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat", "GIT_NO_REPLACE_OBJECTS": "1"}


def scan(repository, binary):
    repository = repository.resolve(strict=True)
    binary = binary.resolve(strict=True)
    if not repository.is_dir() or not (repository / ".git").exists():
        raise ScanFailure()
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != BINARY_SHA256:
        raise ScanFailure()
    # Hard-code /tmp rather than honoring an untrusted TMPDIR inside the repo.
    with tempfile.TemporaryDirectory(prefix="fire-aios-secret-gate-", dir="/tmp") as location:
        private = Path(location)
        if private.is_relative_to(repository):
            raise ScanFailure()
        config = private / "trusted.toml"
        ignore = private / "empty.ignore"
        config.write_text(TRUSTED_CONFIG)
        ignore.write_text("")
        env = safe_environment()
        code, output = run_private([str(binary), "version"], private, env, timeout=10)
        if code != 0 or output.decode("ascii").strip() != VERSION:
            raise ScanFailure()
        total = 0
        for mode in ("git", "dir"):
            report = private / "report.json"
            report.unlink(missing_ok=True)
            command = [str(binary), mode, str(repository), "--config", str(config),
                       "--gitleaks-ignore-path", str(ignore), "--ignore-gitleaks-allow",
                       "--redact=100", "--no-banner", "--no-color",
                       "--report-format", "json", "--report-path", str(report),
                       "--timeout", str(TIMEOUT_SECONDS)]
            if mode == "git":
                command.extend(["--log-opts", "--all --full-history --text --no-ext-diff --no-textconv"])
            code, _ = run_private(command, private, env)
            if config.read_text() != TRUSTED_CONFIG or ignore.read_bytes() != b"":
                raise ScanFailure()
            if code not in (0, 1) or not report.is_file() or report.stat().st_size > MAX_CAPTURE_BYTES:
                raise ScanFailure()
            findings = json.loads(report.read_text())
            if not isinstance(findings, list) or any(not isinstance(row, dict) for row in findings):
                raise ScanFailure()
            if (code == 0) != (len(findings) == 0):
                raise ScanFailure()
            total += len(findings)
        return total


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ScanFailure()


def main(argv=None):
    parser = SafeParser(description="Scan all locally fetched refs and regular working-tree files with pinned Gitleaks.")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--gitleaks", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        findings = scan(args.repository, args.gitleaks)
    except Exception:
        print("Secret scan failed closed; scope=fetched-refs+working-tree; findings=unknown")
        return 2
    print(f"Secret scan {'blocked' if findings else 'passed'}; scope=fetched-refs+working-tree; findings={findings}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
