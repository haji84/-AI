#!/usr/bin/env python3
"""Fail closed while auditing every package in one resolved Python environment.

The target environment must not contain the local Fire AIOS distribution.  CI
installs the project to resolve its dependencies, removes only that local
distribution, and then audits the remaining third-party inventory.  The pinned
auditor runs from a different virtual environment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


AUDITOR_VERSION = "2.10.1"
AUDITOR_ID = f"pip-audit/{AUDITOR_VERSION}"
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 180
NAME_PATTERN = re.compile(r"[-_.]+")
SCOPE_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}")
INVENTORY_PROGRAM = r"""
import importlib.metadata
import json
import sysconfig

packages = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name")
    if not name:
        raise RuntimeError("distribution without Name metadata")
    packages.append({"name": name, "version": distribution.version})
paths = []
for key in ("purelib", "platlib"):
    value = sysconfig.get_path(key)
    if value and value not in paths:
        paths.append(value)
print(json.dumps({"packages": packages, "paths": paths}, sort_keys=True))
"""


class AuditFailure(Exception):
    """The gate could not establish a complete clean audit."""


class VulnerabilityFound(AuditFailure):
    """The complete inventory contains one or more known vulnerabilities."""

    def __init__(self, findings):
        super().__init__("known vulnerabilities detected")
        self.findings = findings
        self.count = len(findings)


def canonical_name(value):
    if not isinstance(value, str) or not value or len(value) > 256 or not value.isascii():
        raise AuditFailure()
    normalized = NAME_PATTERN.sub("-", value).lower()
    if not normalized or any(ord(character) < 33 for character in normalized):
        raise AuditFailure()
    return normalized


def normalize_inventory(inventory):
    if not isinstance(inventory, dict) or not inventory:
        raise AuditFailure()
    normalized = {}
    for raw_name, version in inventory.items():
        name = canonical_name(raw_name)
        if name in normalized or not isinstance(version, str) or not version or len(version) > 256:
            raise AuditFailure()
        normalized[name] = version
    return normalized


def safe_report_value(value):
    if not isinstance(value, str) or not value or len(value) > 256 or not value.isascii():
        raise AuditFailure()
    return value


def format_findings(findings):
    """Return compact, escaped public advisory metadata for CI diagnosis."""
    return json.dumps(findings, sort_keys=True, separators=(",", ":"))


def evaluate_report(scope, inventory, returncode, payload):
    """Require a one-to-one package/version report and no findings."""
    if not SCOPE_PATTERN.fullmatch(scope) or returncode not in (0, 1):
        raise AuditFailure()
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_CAPTURE_BYTES:
        raise AuditFailure()
    expected = normalize_inventory(inventory)
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AuditFailure() from None
    if not isinstance(document, dict) or set(document) != {"dependencies", "fixes"}:
        raise AuditFailure()
    if not isinstance(document["dependencies"], list) or document["fixes"] != []:
        raise AuditFailure()

    observed = {}
    findings = []
    for row in document["dependencies"]:
        if not isinstance(row, dict) or set(row) != {"name", "version", "vulns"}:
            raise AuditFailure()
        name = canonical_name(row.get("name"))
        version = row.get("version")
        vulns = row.get("vulns")
        if name in observed or not isinstance(version, str) or not isinstance(vulns, list):
            raise AuditFailure()
        for vulnerability in vulns:
            if not isinstance(vulnerability, dict):
                raise AuditFailure()
            advisory_id = safe_report_value(vulnerability.get("id"))
            fix_versions = vulnerability.get("fix_versions")
            if not isinstance(fix_versions, list):
                raise AuditFailure()
            fixes = sorted(safe_report_value(item) for item in fix_versions)
            findings.append({
                "fix_versions": fixes,
                "id": advisory_id,
                "name": name,
                "version": safe_report_value(version),
            })
        observed[name] = version

    if observed != expected:
        raise AuditFailure()
    if findings:
        if returncode != 1:
            raise AuditFailure()
        findings.sort(key=lambda item: (item["name"], item["version"], item["id"]))
        raise VulnerabilityFound(findings)
    if returncode != 0:
        raise AuditFailure()

    packages = [{"name": name, "version": expected[name]} for name in sorted(expected)]
    canonical = json.dumps(packages, sort_keys=True, separators=(",", ":")).encode()
    return {
        "auditor": AUDITOR_ID,
        "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "packages": packages,
        "scope": scope,
        "vulnerability_service": "pypi",
    }


def build_command(auditor, paths):
    command = [
        str(auditor), "--format", "json", "--progress-spinner", "off",
        "--desc", "off", "--aliases", "off", "--strict", "--timeout", "15",
    ]
    for path in paths:
        command.extend(["--path", str(path)])
    return command


def execution_path(path):
    """Normalize dot segments without dereferencing a virtualenv symlink."""
    return Path(os.path.abspath(path))


def validate_environment_paths(target_python, auditor):
    target_root = execution_path(target_python).parent.parent
    auditor_root = execution_path(auditor).parent.parent
    if target_root == auditor_root:
        raise AuditFailure()


def validate_auditor_version(returncode, output):
    if returncode != 0 or output != f"pip-audit {AUDITOR_VERSION}\n".encode():
        raise AuditFailure()


def safe_run(command, *, environment, timeout=PROCESS_TIMEOUT_SECONDS):
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise AuditFailure() from None
    if len(result.stdout) > MAX_CAPTURE_BYTES or len(result.stderr) > MAX_CAPTURE_BYTES:
        raise AuditFailure()
    return result


def safe_environment(home):
    return {
        "HOME": str(home),
        "LC_ALL": "C",
        "PATH": os.defpath,
        "PIP_CACHE_DIR": str(home / "pip-cache"),
        "PYTHONNOUSERSITE": "1",
    }


def collect_inventory(target_python, environment):
    result = safe_run([str(target_python), "-I", "-c", INVENTORY_PROGRAM], environment=environment)
    if result.returncode != 0 or not result.stdout:
        raise AuditFailure()
    try:
        document = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AuditFailure() from None
    if not isinstance(document, dict) or set(document) != {"packages", "paths"}:
        raise AuditFailure()
    packages = document["packages"]
    paths = document["paths"]
    if not isinstance(packages, list) or not isinstance(paths, list) or not paths:
        raise AuditFailure()
    inventory = {}
    for row in packages:
        if not isinstance(row, dict) or set(row) != {"name", "version"}:
            raise AuditFailure()
        name = canonical_name(row["name"])
        if name in inventory:
            raise AuditFailure()
        inventory[name] = row["version"]
    resolved_paths = []
    for raw_path in paths:
        if not isinstance(raw_path, str):
            raise AuditFailure()
        path = Path(raw_path).resolve(strict=True)
        if not path.is_dir() or path in resolved_paths:
            raise AuditFailure()
        resolved_paths.append(path)
    return normalize_inventory(inventory), resolved_paths


def write_evidence(path, evidence):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=path.name + ".",
                                     delete=False, encoding="utf-8") as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    temporary.chmod(0o600)
    temporary.replace(path)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise AuditFailure()


def main(argv=None):
    parser = SafeParser(description="Audit a complete resolved third-party Python environment.")
    parser.add_argument("--target-python", required=True, type=Path)
    parser.add_argument("--auditor", required=True, type=Path)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    scope = "unknown"
    try:
        args = parser.parse_args(argv)
        scope = args.scope if SCOPE_PATTERN.fullmatch(args.scope) else "unknown"
        if scope == "unknown":
            raise AuditFailure()
        target_python = execution_path(args.target_python)
        auditor = execution_path(args.auditor)
        if not target_python.is_file() or not auditor.is_file():
            raise AuditFailure()
        validate_environment_paths(target_python, auditor)
        with tempfile.TemporaryDirectory(prefix="fire-aios-dependency-audit-", dir="/tmp") as location:
            environment = safe_environment(Path(location))
            version = safe_run([str(auditor), "--version"], environment=environment, timeout=15)
            validate_auditor_version(version.returncode, version.stdout)
            inventory, paths = collect_inventory(target_python, environment)
            result = safe_run(build_command(auditor, paths), environment=environment)
            evidence = evaluate_report(scope, inventory, result.returncode, result.stdout)
        write_evidence(args.evidence, evidence)
    except VulnerabilityFound as exc:
        print(
            f"Dependency audit blocked; scope={scope}; findings={exc.count}; "
            f"advisories={format_findings(exc.findings)}"
        )
        return 1
    except Exception:
        print(f"Dependency audit failed closed; scope={scope}; findings=unknown")
        return 2
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
