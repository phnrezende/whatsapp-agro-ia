"""Versão web (demo): chat no navegador, limite diário e aviso de cota grátis."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import rag
from app.web.main import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    for k in ("DIFY_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CHAT_DAILY_LIMIT", "3")
    return TestClient(create_app("base", str(tmp_path / "t.db"), send=lambda to, text: None))


def test_page_and_chat_answer_without_subscription(client):
    assert "<form" in client.get("/").text
    r = client.post("/chat", json={"question": "quando aplicar calcário?"}).json()
    assert "calagem.md" in r["answer"] and r["fallback"] is False  # sem chave não é falha
    assert client.post("/chat", json={"question": "  "}).status_code == 400


def test_daily_limit(client):
    codes = [client.post("/chat", json={"question": "calagem"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_llm_failure_is_flagged_for_the_popup(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "gsk_x")

    def boom(*a, **k):
        raise httpx.ConnectError("sem cota")
    monkeypatch.setattr(rag.httpx, "post", boom)
    r = client.post("/chat", json={"question": "quando aplicar calcário?"}).json()
    assert r["fallback"] is True and "calagem.md" in r["answer"]


def test_whatsapp_routes_still_there(client):
    assert client.post("/webhooks/asaas").status_code == 401


def test_bad_body_is_400_not_500(client):
    assert client.post("/chat", content="Como voc\xea".encode("latin-1"),
                       headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/chat", json=["lista"]).status_code == 400
