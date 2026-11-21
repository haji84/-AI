"""Synthetic responses test transport/schema/provenance, not model accuracy."""
import base64
from io import BytesIO
import json
from urllib.error import URLError

import pytest
from PIL import Image

from app import emergency_local_ai as local_ai


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, data, url="http://127.0.0.1:11434/api/chat"):
        self.body = BytesIO(data)
        self.url = url

    def read(self, size=-1):
        return self.body.read(size)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.body.close()


def install_reply(monkeypatch, content, **outer):
    captured = {}
    envelope = {"message": {"role": "assistant", "content": json.dumps(content)}, "done": True, **outer}
    response = FakeResponse(json.dumps(envelope).encode())

    class Opener:
        def open(self, request, timeout):
            captured.update(url=request.full_url, payload=json.loads(request.data), timeout=timeout)
            return response

    def build(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(local_ai, "build_opener", build)
    return captured


def pages():
    return [{"page": 1, "text": "合成の記録。A欄は1、説明は2。"}]


def candidate(**updates):
    return {"page": 1, "quote": "A欄は1、説明は2", "reason": "合成の一致確認候補", **updates}


def png():
    output = BytesIO()
    Image.new("RGB", (4, 4), "white").save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


def test_unconfigured_ai_has_no_network_access(monkeypatch):
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: pytest.fail("network must remain unused"))
    result = local_ai.review_text(pages(), model=None)
    assert result["status"] == "NOT_CONFIGURED"
    assert result["formal_decision"] is False


def test_text_review_uses_literal_loopback_without_proxy_redirect_stream_or_tools(monkeypatch):
    captured = install_reply(monkeypatch, {"candidates": [candidate()]})
    result = local_ai.review_text(pages(), model="synthetic-local:1")
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["quote"] == "A欄は1、説明は2"
    assert result["human_review_required"] is True and result["formal_decision"] is False
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert isinstance(captured["payload"]["format"], dict)
    assert "tools" not in captured["payload"]
    assert 0 < captured["timeout"] <= 30
    proxy = next(item for item in captured["handlers"] if isinstance(item, local_ai.ProxyHandler))
    assert proxy.proxies == {}
    redirect = next(item for item in captured["handlers"] if isinstance(item, local_ai.NoRedirect))
    assert redirect.redirect_request(None, None, 302, "redirect", {}, "https://example.invalid") is None


def test_empty_model_result_is_not_report_approval(monkeypatch):
    install_reply(monkeypatch, {"candidates": []})
    result = local_ai.review_text(pages(), model="synthetic-local")
    assert result["status"] == "NO_CANDIDATE"
    assert result["formal_decision"] is False
    assert result["accuracy_measured"] is False


@pytest.mark.parametrize("content", [
    {"candidates": [candidate(quote="原文にない引用")]},
    {"candidates": [candidate(page=2)]},
    {"candidates": [candidate(page=True)]},
    {"candidates": [candidate(approve=True)]},
    {"candidates": [], "diagnosis": "invented"},
    {"candidates": [candidate(reason="")]},
])
def test_untrusted_or_ungrounded_output_is_unavailable_never_clear(monkeypatch, content):
    install_reply(monkeypatch, content)
    result = local_ai.review_text(pages(), model="synthetic-local")
    assert result["status"] == "UNAVAILABLE"
    assert result["candidates"] == []


def test_truncated_generation_is_not_accepted(monkeypatch):
    install_reply(monkeypatch, {"candidates": []}, done=False)
    assert local_ai.review_text(pages(), model="synthetic-local")["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("model", ["https://external.invalid/model", "model-cloud", "model:cloud", "x\nsecret", "../model"])
def test_external_or_cloud_model_configuration_is_rejected_without_request(monkeypatch, model):
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: pytest.fail("invalid model must not make a request"))
    assert local_ai.review_text(pages(), model=model)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("port", [0, 65536, True, "11434"])
def test_invalid_ports_do_not_reach_network(monkeypatch, port):
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: pytest.fail("invalid port"))
    assert local_ai.review_text(pages(), model="synthetic-local", port=port)["status"] == "UNAVAILABLE"


def test_unavailable_model_never_echoes_private_exception(monkeypatch, caplog):
    marker = "SYNTHETIC_PRIVATE_SENTINEL"

    class Broken:
        def open(self, *args, **kwargs):
            raise URLError(marker)

    monkeypatch.setattr(local_ai, "build_opener", lambda *args: Broken())
    result = local_ai.review_text([{ "page": 1, "text": marker}], model="synthetic-local")
    assert result["status"] == "UNAVAILABLE"
    assert marker not in json.dumps(result) and marker not in caplog.text


@pytest.mark.parametrize("payload", [
    [{"page": 1, "text": "A"}, {"page": 1, "text": "B"}],
    [{"page": 0, "text": "A"}], [{"page": True, "text": "A"}],
    [{"page": 1, "text": "A", "path": "/private"}],
    [{"page": 1, "text": "A" * 50001}], [],
])
def test_invalid_pages_fail_before_request(monkeypatch, payload):
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: pytest.fail("invalid input"))
    assert local_ai.review_text(payload, model="synthetic-local")["status"] == "UNAVAILABLE"


def test_oversized_response_is_not_parsed(monkeypatch):
    class Oversized:
        def open(self, *args, **kwargs):
            return FakeResponse(b"x" * (local_ai.MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: Oversized())
    assert local_ai.review_text(pages(), model="synthetic-local")["status"] == "UNAVAILABLE"


def test_vision_candidates_are_bounded_and_always_unconfirmed(monkeypatch):
    captured = install_reply(monkeypatch, {"candidates": [
        {"bbox": [0.1, 0.2, 0.5, 0.7], "text": "合成の手書き", "kind": "handwritten"}]})
    result = local_ai.read_image_candidates(png(), model="synthetic-vision", page=3)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["state"] == "unconfirmed"
    assert result["candidates"][0]["page"] == 3
    assert result["accuracy_measured"] is False
    assert len(captured["payload"]["messages"][-1]["images"]) == 1


@pytest.mark.parametrize("bbox", [[0, 0, 2, 1], [0.7, 0, 0.2, 1], [0, 0.6, 1, 0.1], [False, 0, 1, 1], [0, 0, float("nan"), 1]])
def test_invalid_vision_boxes_cannot_be_used(monkeypatch, bbox):
    install_reply(monkeypatch, {"candidates": [{"bbox": bbox, "text": "Synthetic", "kind": "printed"}]})
    assert local_ai.read_image_candidates(png(), model="synthetic-vision")["status"] == "UNAVAILABLE"


def test_image_input_is_png_bytes_not_path_or_url(monkeypatch):
    monkeypatch.setattr(local_ai, "build_opener", lambda *a: pytest.fail("invalid image"))
    for value in ("/private/original.png", "https://external.invalid/image.png", base64.b64encode(b"not PNG").decode()):
        assert local_ai.read_image_candidates(value, model="synthetic-vision")["status"] == "UNAVAILABLE"
