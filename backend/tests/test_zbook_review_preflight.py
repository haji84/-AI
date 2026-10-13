"""Local reviewer preflight synthetic regressions, never contacts Ollama."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/autonomy/zbook_review_preflight.py"
spec = importlib.util.spec_from_file_location("aios_zbook_review_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def test_ready_without_secrets_or_cli_credentials(tmp_path):
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda: True)
    assert report["ready_for_isolated_inference_trial"] is True
    assert report["real_inference_completed"] is False
    assert report["github_approved"] is False


def test_reject_env_token(tmp_path):
    report = preflight.inspect(
        environ={"GH_TOKEN": "test-only-placeholder"}, home=tmp_path,
        probe_model=lambda: True)
    assert report["secret_environment_present"] is True
    assert report["ready_for_isolated_inference_trial"] is False


def test_reject_gh_cli_credential_file(tmp_path):
    gh = tmp_path / ".config" / "gh"
    gh.mkdir(parents=True)
    (gh / "hosts.yml").write_text("synthetic-placeholder")
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda: True)
    assert report["github_cli_credential_store_found"] is True
    assert report["ready_for_isolated_inference_trial"] is False


def test_reject_unavailable_model(tmp_path):
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda: False)
    assert report["ollama_model_available"] is False
    assert report["ready_for_isolated_inference_trial"] is False


def test_failed_ollama_probe_is_safe_stop(tmp_path):
    def fail():
        raise TimeoutError("synthetic local server offline")
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=fail)
    assert report["ready_for_isolated_inference_trial"] is False
