"""Synthetic-only tests for the resolved dependency vulnerability gate."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_dependencies.py"
ROOT = SCRIPT.parents[1]


def module():
    spec = importlib.util.spec_from_file_location("audit_dependencies", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def report(*dependencies):
    return json.dumps({"dependencies": list(dependencies), "fixes": []}).encode()


def dependency(name, version, vulns=None):
    return {"name": name, "version": version, "vulns": vulns or []}


def test_clean_exact_inventory_is_accepted_and_evidence_is_deterministic():
    audit = module()
    inventory = {"Alpha_Pkg": "1.2.3", "beta.pkg": "4.5.6"}
    payload = report(dependency("alpha-pkg", "1.2.3"), dependency("beta-pkg", "4.5.6"))

    evidence = audit.evaluate_report("backend-test", inventory, 0, payload)

    assert evidence == {
        "auditor": "pip-audit/2.10.1",
        "inventory_sha256": "2379327adf2a88751f65a46f21e6a3ff4435222a20f23c320f52d6843c6f4ee9",
        "packages": [
            {"name": "alpha-pkg", "version": "1.2.3"},
            {"name": "beta-pkg", "version": "4.5.6"},
        ],
        "scope": "backend-test",
        "vulnerability_service": "pypi",
    }


def test_synthetic_advisory_fails_without_an_ignore_baseline():
    audit = module()
    payload = report(dependency(
        "alpha-pkg", "1.2.3",
        [
            {"id": "PYSEC-SYNTHETIC-1", "fix_versions": ["1.2.4"]},
            {"id": "PYSEC-SYNTHETIC-1", "fix_versions": ["1.2.4"]},
        ],
    ))

    with pytest.raises(audit.VulnerabilityFound) as captured:
        audit.evaluate_report("runtime", {"alpha-pkg": "1.2.3"}, 1, payload)

    assert captured.value.count == 1
    assert captured.value.findings == [
        {
            "fix_versions": ["1.2.4"],
            "id": "PYSEC-SYNTHETIC-1",
            "name": "alpha-pkg",
            "version": "1.2.3",
        }
    ]
    assert audit.format_findings(captured.value.findings) == (
        '[{"fix_versions":["1.2.4"],"id":"PYSEC-SYNTHETIC-1",'
        '"name":"alpha-pkg","version":"1.2.3"}]'
    )


def test_conflicting_duplicate_advisory_fails_closed():
    audit = module()
    payload = report(dependency(
        "alpha-pkg", "1.2.3",
        [
            {"id": "PYSEC-SYNTHETIC-1", "fix_versions": ["1.2.4"]},
            {"id": "PYSEC-SYNTHETIC-1", "fix_versions": ["1.2.5"]},
        ],
    ))

    with pytest.raises(audit.AuditFailure) as captured:
        audit.evaluate_report("runtime", {"alpha-pkg": "1.2.3"}, 1, payload)

    assert not isinstance(captured.value, audit.VulnerabilityFound)


@pytest.mark.parametrize("returncode,payload", [(2, b""), (0, b"not-json"), (0, b"[]")])
def test_service_or_report_failure_fails_closed(returncode, payload):
    audit = module()

    with pytest.raises(audit.AuditFailure):
        audit.evaluate_report("runtime", {"alpha-pkg": "1.2.3"}, returncode, payload)


def test_unscanned_inventory_package_fails_closed():
    audit = module()
    payload = report(dependency("alpha-pkg", "1.2.3"))

    with pytest.raises(audit.AuditFailure):
        audit.evaluate_report(
            "browser",
            {"alpha-pkg": "1.2.3", "unreported-pkg": "9.9.9"},
            0,
            payload,
        )


def test_explicitly_skipped_report_row_fails_closed():
    audit = module()
    skipped = dependency("alpha-pkg", "1.2.3")
    skipped["skip_reason"] = "synthetic package was not audited"

    with pytest.raises(audit.AuditFailure):
        audit.evaluate_report(
            "runtime", {"alpha-pkg": "1.2.3"}, 0, report(skipped)
        )


@pytest.mark.parametrize(
    "dependencies",
    [
        [dependency("alpha-pkg", "0.0.1")],
        [dependency("alpha-pkg", "1.2.3"), dependency("extra-pkg", "2.0")],
        [dependency("alpha-pkg", "1.2.3"), dependency("ALPHA_PKG", "1.2.3")],
    ],
)
def test_mismatched_extra_or_duplicate_report_package_fails_closed(dependencies):
    audit = module()

    with pytest.raises(audit.AuditFailure):
        audit.evaluate_report(
            "runtime", {"alpha-pkg": "1.2.3"}, 0, report(*dependencies)
        )


def test_auditor_command_is_strict_and_has_no_waiver_or_mutation(tmp_path):
    audit = module()
    command = audit.build_command(
        tmp_path / "auditor" / "bin" / "pip-audit",
        [tmp_path / "target" / "purelib", tmp_path / "target" / "platlib"],
    )

    assert command[:2] == [str(tmp_path / "auditor" / "bin" / "pip-audit"), "--format"]
    assert "--strict" in command
    assert command.count("--path") == 2
    assert "--ignore-vuln" not in command
    assert "--fix" not in command
    assert "--dry-run" not in command
    assert "--skip-editable" not in command


def test_auditor_must_be_version_2_10_1_and_separate_from_target(tmp_path):
    audit = module()
    same = tmp_path / "same" / "bin"

    with pytest.raises(audit.AuditFailure):
        audit.validate_environment_paths(same / "python", same / "pip-audit")
    with pytest.raises(audit.AuditFailure):
        audit.validate_auditor_version(0, b"pip-audit 2.10.0\n")
    assert audit.validate_auditor_version(0, b"pip-audit 2.10.1\n") is None


def test_target_python_path_preserves_virtual_environment_symlink(tmp_path):
    audit = module()
    target = tmp_path / "target" / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.symlink_to(sys.executable)

    assert audit.execution_path(target) == target.absolute()
    assert audit.execution_path(target) != target.resolve()


def test_dependency_workflow_has_three_scopes_and_read_only_checkout():
    workflow = (ROOT / ".github/workflows/dependency-checks.yml").read_text()
    project = (ROOT / "backend/pyproject.toml").read_text()

    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "pip-audit==2.10.1" in workflow
    assert "--upgrade pip setuptools" in workflow
    assert workflow.count("scope:") == 3
    for scope in ("runtime", "backend-test", "browser"):
        assert f"scope: {scope}" in workflow
    for forbidden in ("--ignore-vuln", "--fix", "continue-on-error"):
        assert forbidden not in workflow
    assert "-m pip uninstall --yes fire-ai-local-backend" in workflow
    assert "scripts/audit_dependencies.py" in workflow
    assert '"cryptography>=50,<51"' in project
    assert 'test = ["pytest>=9.0.3,<10"' in project
