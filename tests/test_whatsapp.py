import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import rag
from app.whatsapp.main import PAYWALL, create_app

PHONE = "5527999990000"


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("DIFY_API_KEY", "OPENAI_API_KEY", "WHATSAPP_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "asaas-secret")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "meta-secret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("PAYMENT_LINK", "https://asaas.test/pagar")
    monkeypatch.setenv("DEMO", "1")
    sent = []
    client = TestClient(create_app("base", str(tmp_path / "t.db"), send=lambda to, text: sent.append((to, text))))
    return client, sent


def asaas(client, event, ev_id="evt_1", due=None, token="asaas-secret"):
    payment = {"id": "pay_1", "externalReference": PHONE, "dueDate": (due or date.today()).isoformat()}
    return client.post("/webhooks/asaas", headers={"asaas-access-token": token},
                       json={"id": ev_id, "event": event, "payment": payment})


def whatsapp(client, text, msg_id="wamid.1", secret="meta-secret"):
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"id": msg_id, "from": PHONE, "type": "text", "text": {"body": text}}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body,
                       headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def test_search_finds_the_right_document():
    base = rag.Base("base")
    assert base.search("quando aplicar calcário antes do plantio")[0][0] == "calagem.md"
    assert base.search("lagarta no cartucho do milho")[0][0] == "lagarta-do-cartucho.md"
    assert base.search("ureia em cobertura V4")[0][0] == "adubacao-milho.md"
    assert base.search("preço do boi gordo hoje") == []


def test_unknown_question_is_not_made_up():
    assert rag.answer(rag.Base("base"), "qual o preço do boi gordo", PHONE) == rag.NOT_FOUND


def test_greeting_gets_a_welcome_not_a_refusal():
    base = rag.Base("base")
    for hello in ("Oi", "Bom dia!", "olá, tudo bem?", "E aí"):
        assert rag.answer(base, hello, PHONE) == rag.GREETING, hello
    # cumprimento junto com pergunta continua sendo pergunta
    assert "calagem.md" in rag.answer(base, "Boa noite, quando aplicar calcário?", PHONE)


def test_non_subscriber_gets_payment_link(env):
    client, _ = env
    r = client.post("/ask", json={"phone": PHONE, "question": "calagem"})
    assert r.json()["answer"] == PAYWALL.format(link="https://asaas.test/pagar")
    assert r.headers["content-type"] == "application/json; charset=utf-8"  # clientes antigos dependem do charset


def test_payment_unlocks_then_overdue_blocks(env):
    client, sent = env
    assert asaas(client, "PAYMENT_CONFIRMED").status_code == 200
    assert sent[-1][1].startswith("Pagamento confirmado")
    answer = client.post("/ask", json={"phone": PHONE, "question": "quando aplicar calcário?"}).json()["answer"]
    assert "calagem.md" in answer

    asaas(client, "PAYMENT_OVERDUE", ev_id="evt_2")
    assert "atraso" in sent[-1][1]
    assert "link" in client.post("/ask", json={"phone": PHONE, "question": "calagem"}).json()["answer"]


def test_late_payment_counts_from_today(env):
    client, sent = env
    asaas(client, "PAYMENT_RECEIVED", due=date.today() - timedelta(days=20))
    assert (date.today() + timedelta(days=31)).strftime("%d/%m/%Y") in sent[-1][1]


def test_asaas_rejects_wrong_token_and_ignores_retries(env):
    client, sent = env
    assert asaas(client, "PAYMENT_CONFIRMED", token="errado").status_code == 401
    assert sent == []
    asaas(client, "PAYMENT_CONFIRMED")
    assert asaas(client, "PAYMENT_CONFIRMED").json().get("duplicate") is True
    assert len(sent) == 1


def test_whatsapp_answers_subscriber_once(env):
    client, sent = env
    asaas(client, "PAYMENT_CONFIRMED")
    assert whatsapp(client, "tem lagarta no cartucho do milho, o que faço?").status_code == 200
    assert sent[-1][0] == PHONE and "lagarta-do-cartucho.md" in sent[-1][1]
    count = len(sent)
    whatsapp(client, "tem lagarta no cartucho do milho, o que faço?")  # mesma mensagem reenviada pela Meta
    assert len(sent) == count


def test_whatsapp_rejects_bad_signature(env):
    client, sent = env
    assert whatsapp(client, "oi", secret="outro").status_code == 401
    assert sent == []


def test_whatsapp_verification(env):
    client, _ = env
    ok = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "123"}
    assert client.get("/webhooks/whatsapp", params=ok).text == "123"
    assert client.get("/webhooks/whatsapp", params={**ok, "hub.verify_token": "x"}).status_code == 403


def test_llm_failure_falls_back_to_sources(monkeypatch):
    import httpx
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "hf_x")

    def boom(*a, **k):
        raise httpx.ConnectError("sem cota")
    monkeypatch.setattr(rag.httpx, "post", boom)
    assert "calagem.md" in rag.answer(rag.Base("base"), "quando aplicar calcário?", PHONE)


def test_llm_gets_questions_without_sources_to_handle_small_talk(monkeypatch):
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "gsk_x")
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Eu tiro dúvidas da lavoura!"}}]}

    def fake_post(url, **kw):
        sent.update(kw["json"])
        return Resp()
    monkeypatch.setattr(rag.httpx, "post", fake_post)
    assert rag.answer(rag.Base("base"), "como você pode me ajudar?", PHONE) == "Eu tiro dúvidas da lavoura!"
    assert "(nenhum trecho encontrado)" in sent["messages"][1]["content"]
    assert "calagem" in sent["messages"][0]["content"]  # os assuntos da base vão no prompt
