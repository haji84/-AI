"""Local reviewer preflight synthetic regressions, never contacts Ollama."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/autonomy/zbook_review_preflight.py"
spec = importlib.util.spec_from_file_location("aios_zbook_review_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def test_ready_without_secrets_or_cli_credentials(tmp_path):
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda name: True)
    assert report["ready_for_isolated_inference_trial"] is True
    assert report["real_inference_completed"] is False
    assert report["github_approved"] is False


def test_reject_env_token(tmp_path):
    report = preflight.inspect(
        environ={"GH_TOKEN": "test-only-placeholder"}, home=tmp_path,
        probe_model=lambda name: True)
    assert report["secret_environment_present"] is True
    assert report["ready_for_isolated_inference_trial"] is False


def test_reject_gh_cli_credential_file(tmp_path):
    gh = tmp_path / ".config" / "gh"
    gh.mkdir(parents=True)
    (gh / "hosts.yml").write_text("synthetic-placeholder")
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda name: True)
    assert report["github_cli_credential_store_found"] is True
    assert report["ready_for_isolated_inference_trial"] is False


def test_reject_unavailable_model(tmp_path):
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=lambda name: False)
    assert report["ollama_model_available"] is False
    assert report["ready_for_isolated_inference_trial"] is False


def test_failed_ollama_probe_is_safe_stop(tmp_path):
    def fail(name):
        raise TimeoutError("synthetic local server offline")
    report = preflight.inspect(environ={}, home=tmp_path, probe_model=fail)
    assert report["ready_for_isolated_inference_trial"] is False


def test_unexpected_model_response_is_rejected(monkeypatch):
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            return b'[]'
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse()
    monkeypatch.setattr(preflight, 'build_opener', lambda handler: FakeOpener())
    assert preflight.model_available() is False

def test_3b_preflight_checks_selected_model(tmp_path):
    names = []
    def probe(name):
        names.append(name)
        return name == "qwen2.5-coder:3b"
    report = preflight.inspect(model_name="qwen2.5-coder:3b",
                               environ={}, home=tmp_path, probe_model=probe)
    assert names == ["qwen2.5-coder:3b"]
    assert report["model"] == "qwen2.5-coder:3b"
    assert report["ready_for_isolated_inference_trial"] is True
