"""Tests for "matches for your own words" (ml/semantic.py) and the assistant chatbot (backend/assistant.py).

Gemini is never called for real: httpx.MockTransport plays the Gemini server, so no key or internet is needed.
"""
import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402

from backend import assistant  # noqa: E402
from backend.main import AppContext, app, get_context  # noqa: E402
from backend.repository import MemoryRepository  # noqa: E402
from ml.localise import apply_local_rules  # noqa: E402
from ml.recommender_v2 import load_onet_v2  # noqa: E402
from ml.semantic import SemanticMatcher  # noqa: E402

LAB = "19-0001.00"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-only-for-pytest-0123456789abcdef")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def ctx(onet_dir):
    data = apply_local_rules(load_onet_v2(onet_dir), onet_dir)
    repo = MemoryRepository()
    return AppContext(data, repo, repo.career_ids(data), "files")


@pytest.fixture
def client(ctx):
    app.dependency_overrides[get_context] = lambda: ctx
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- matching the student's own words
def test_match_text_tfidf(client):
    body = client.post("/match/text", json={"text": "I want to work as a lab scientist"}).json()
    assert body["method"] in ("tfidf",) or body["method"].startswith("sbert")
    assert body["results"][0]["code"] == LAB and 0 < body["results"][0]["similarity"] <= 1


class FakeSbert:
    """Stands in for Sentence-BERT: counts letters, so the test runs offline."""
    name = "sbert:fake"
    calls = 0

    def fit(self, texts):
        return self

    def encode(self, texts):
        FakeSbert.calls += len(texts)
        v = np.array([[t.lower().count(ch) for ch in "abcdefghijklmnopqrstuvwxyz"] for t in texts], dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def test_sbert_vectors_are_cached(ctx, tmp_path):
    FakeSbert.calls = 0
    SemanticMatcher(ctx.data, encoder=FakeSbert(), cache_dir=tmp_path)
    first = FakeSbert.calls
    assert first == len(ctx.data["codes"]) and len(list(tmp_path.glob("career_embeddings_*.npy"))) == 1
    m = SemanticMatcher(ctx.data, encoder=FakeSbert(), cache_dir=tmp_path)
    assert FakeSbert.calls == first                     # loaded from the cache, not encoded again
    assert m.method == "sbert:fake" and len(m.match("science", top_n=2)) == 2


# ---------------------------------------------------------------- assistant
def test_assistant_offline_without_key(client):
    r = client.post("/assistant/chat", json={"message": "I want to be a lab scientist"})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "offline"
    assert "GEMINI_API_KEY" in body["reply"] and body["sources"][0]["code"] == LAB
    assert client.get("/assistant/status").json()["mode"] == "offline"


def gemini_mock(seen, missing_model=None):
    def handler(request):
        if request.method == "GET":                     # list models
            return httpx.Response(200, json={"models": [
                {"name": "models/gemini-10-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-omni-1-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-9-flash-preview", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]}]})
        seen.append(request)
        if missing_model and missing_model in request.url.path:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Try Research Scientist."}]}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_request_is_grounded(ctx):
    seen = []
    client = assistant.GeminiClient("fake-key", model="gemini-test", http=gemini_mock(seen))
    history = [{"role": "assistant", "text": "Hi!"}, {"role": "user", "text": "hello"},
               {"role": "assistant", "text": "How can I help?"}]
    reply, mode = assistant.answer(ctx, "What does a lab scientist do?", history, [LAB], client=client)
    assert (reply, mode) == ("Try Research Scientist.", "gemini")
    req = seen[0]
    body = json.loads(req.content)
    assert req.headers["x-goog-api-key"] == "fake-key" and req.url.path.endswith("/models/gemini-test:generateContent")
    system = body["system_instruction"]["parts"][0]["text"]
    assert "Lab Scientist" in system and "Salary in India: not in our data" in system and "Never invent" in system
    roles = [c["role"] for c in body["contents"]]
    assert roles == ["user", "model", "user"]           # leading assistant turn dropped, last = the question


def test_gemini_retired_model_falls_back_to_available_flash(ctx):
    seen = []
    client = assistant.GeminiClient("k", model="gemini-old", http=gemini_mock(seen, missing_model="gemini-old"))
    assistant.answer(ctx, "hi", [], [LAB], client=client)
    # newest numbered version, not alphabetical order ("9" > "10") and not the omni / latest variants
    assert client.model == "gemini-10-flash" and seen[-1].url.path.endswith("gemini-10-flash:generateContent")


def test_chat_endpoint_reports_gemini_errors(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad")
    def refuse(request):
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})
    real = assistant.GeminiClient
    monkeypatch.setattr(assistant, "GeminiClient",
                        lambda key: real(key, "m", httpx.Client(transport=httpx.MockTransport(refuse))))
    r = client.post("/assistant/chat", json={"message": "hello"})
    assert r.status_code == 502 and "GEMINI_API_KEY" in r.json()["detail"]


def busy_mock(seen, busy_models):
    """Models in busy_models answer 503 "high demand" (as Google did on 29 Oct); the others answer."""
    def handler(request):
        seen.append(request.url.path)
        if any(f"/{m}:" in request.url.path for m in busy_models):
            return httpx.Response(503, json={"error": {"code": 503, "message": "high demand"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Backup answer."}]}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_busy_retries_then_uses_a_backup_model(ctx, monkeypatch):
    monkeypatch.setattr(assistant, "RETRY_WAIT_SECONDS", 0)
    monkeypatch.delenv("GEMINI_BACKUP_MODELS", raising=False)
    seen = []
    client = assistant.GeminiClient("k", model="main-model", http=busy_mock(seen, ["main-model"]))
    reply, mode = assistant.answer(ctx, "hi", [], [LAB], client=client)
    assert (reply, mode) == ("Backup answer.", "gemini")
    assert [p.split("/")[-1] for p in seen] == ["main-model:generateContent", "main-model:generateContent",
                                                f"{assistant.BACKUP_MODELS[0]}:generateContent"]
    assert client.model == "main-model"                 # the main model is tried first again next time


def test_gemini_all_busy_gives_a_clear_message(ctx, monkeypatch):
    monkeypatch.setattr(assistant, "RETRY_WAIT_SECONDS", 0)
    monkeypatch.setenv("GEMINI_BACKUP_MODELS", "b1, b2")
    seen = []
    client = assistant.GeminiClient("k", model="m", http=busy_mock(seen, ["m", "b1", "b2"]))
    with pytest.raises(assistant.GeminiError, match="very busy"):
        client.generate("system", [{"role": "user", "text": "hi"}])
    assert len(seen) == 4                               # m, m again, b1, b2
