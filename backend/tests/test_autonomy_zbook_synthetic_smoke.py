"""Synthetic-only validation tests for local Ollama/Aider end-to-end smoke."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/autonomy/zbook_synthetic_smoke.py"
spec = importlib.util.spec_from_file_location("aios_zbook_synthetic_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_exact_synthetic_edit_is_accepted_without_execution():
    assert smoke.validate_synthetic_edit('def status():\n    return "ready"\n') is True


@pytest.mark.parametrize("payload", [
    'def status():\n    return "not-ready"\n',
    "import os\ndef status():\n    return 'ready'\n",
    "def status():\n    return 'ready'\n\nprint('would have executed')\n",
    "def status():\n    return os.getenv('TOKEN')\n",
    "def status():\n    return 'ready'\n    pass\n",
    "def status(x):\n    return 'ready'\n",
    "def status():\n    return 'ready'\n" + "# padding\n" * 500,
    "def status(:\n    return 'ready'\n",
])
def test_unsafe_or_unexpected_generated_code_is_rejected(payload):
    with pytest.raises(smoke.SmokeError):
        smoke.validate_synthetic_edit(payload)


def test_model_identifier_is_bounded():
    with pytest.raises(smoke.SmokeError):
        smoke.smoke("../unsafe")


def test_environment_excludes_sensitive_github_variables(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-token")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-token")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-token")
    settings = smoke.safe_env()
    assert settings["OLLAMA_API_BASE"] == "http://127.0.0.1:11434"
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY"):
        assert name not in settings
