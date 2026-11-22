"""Assistente agrícola no WhatsApp: WhatsApp + respostas dos materiais técnicos + assinatura pelo Asaas.

Rotas:
- GET/POST /webhooks/whatsapp  verificação e mensagens da WhatsApp Cloud API (assinatura X-Hub-Signature-256)
- POST /webhooks/asaas          eventos de cobrança do Asaas (header asaas-access-token)
- POST /ask                     só com DEMO=1: a mesma resposta que iria pelo WhatsApp, para testar sem a Meta
"""
import hashlib
import hmac
import logging
import os
from datetime import date, timedelta
from secrets import compare_digest

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app import rag
from app.store import Store

log = logging.getLogger("agro")

PAYWALL = ("Olá! Eu sou o assistente agrícola. Para tirar suas dúvidas sobre a lavoura, ative sua assinatura "
           "mensal neste link: {link}\nAssim que o pagamento for confirmado, eu te aviso por aqui.")
WELCOME = "Pagamento confirmado! Sua assinatura está ativa até {until}. Pode mandar sua pergunta."
OVERDUE = "Sua assinatura está com pagamento em atraso, então pausei as respostas. Regularize aqui: {link}"
CANCELLED = "Sua assinatura foi cancelada. Se quiser voltar, é só assinar de novo: {link}"
ONLY_TEXT = "Por enquanto eu só entendo mensagens de texto. Pode escrever sua pergunta?"
ERROR = "Tive um problema para responder agora. Tente de novo em alguns minutos."


def send_whatsapp(to, text):
    token, number_id = os.environ.get("WHATSAPP_TOKEN"), os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not (token and number_id):
        log.info("whatsapp (não configurado) para %s: %s", to, text)
        return
    r = httpx.post(f"https://graph.facebook.com/v21.0/{number_id}/messages", timeout=30,
                   headers={"Authorization": "Bearer " + token},
                   json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}})
    r.raise_for_status()


def create_app(base_dir="base", db_path="agro.db", send=send_whatsapp):
    app = FastAPI(title="Assistente agrícola no WhatsApp")
    base, store = rag.Base(base_dir), Store(db_path)
    link = lambda: os.environ.get("PAYMENT_LINK", "(link de pagamento do Asaas)")  # noqa: E731

    def reply_text(phone, question):
        if not store.has_access(phone):
            return PAYWALL.format(link=link())
        try:
            return rag.answer(base, question, phone)
        except Exception:
            log.exception("falha ao responder %s", phone)
            return ERROR

    @app.get("/webhooks/whatsapp")
    def verify(request: Request):
        p = request.query_params
        expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        if p.get("hub.mode") == "subscribe" and expected and compare_digest(p.get("hub.verify_token", ""), expected):
            return PlainTextResponse(p.get("hub.challenge", ""))
        raise HTTPException(403)

    @app.post("/webhooks/whatsapp")
    async def whatsapp(request: Request, tasks: BackgroundTasks):
        body = await request.body()
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not secret or not compare_digest(request.headers.get("x-hub-signature-256", ""), sig):
            raise HTTPException(401)
        for entry in (await request.json()).get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    if store.seen(msg["id"]):  # a Meta reenvia quando demora: não responder duas vezes
                        continue
                    store.mark(msg["id"])
                    if msg.get("type") == "text":
                        tasks.add_task(lambda m=msg: send(m["from"], reply_text(m["from"], m["text"]["body"])))
                    else:
                        tasks.add_task(send, msg["from"], ONLY_TEXT)
        return {"ok": True}  # responder rápido; a resposta vai em segundo plano

    @app.post("/webhooks/asaas")
    async def asaas(request: Request):
        expected = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")
        if not expected or not compare_digest(request.headers.get("asaas-access-token", ""), expected):
            raise HTTPException(401)
        ev = await request.json()
        if ev.get("id") and store.seen(ev["id"]):  # o Asaas reenvia eventos: cada um vale uma vez
            return {"ok": True, "duplicate": True}
        kind = ev.get("event", "")
        obj = ev.get("payment") or ev.get("subscription") or {}
        phone = obj.get("externalReference")  # o telefone vai no externalReference ao criar a assinatura
        if phone:
            if kind in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
                # pago em atraso conta a partir de hoje, para o produtor não perder dias de acesso
                start = max(date.fromisoformat(obj.get("dueDate", date.today().isoformat())), date.today())
                until = start + timedelta(days=31)
                store.set_status(phone, "active", until)
                send(phone, WELCOME.format(until=until.strftime("%d/%m/%Y")))
            elif kind == "PAYMENT_OVERDUE":
                store.set_status(phone, "blocked")
                send(phone, OVERDUE.format(link=link()))
            elif kind in ("SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"):
                store.set_status(phone, "cancelled")
                send(phone, CANCELLED.format(link=link()))
        if ev.get("id"):
            store.mark(ev["id"])
        return {"ok": True}

    @app.post("/ask")
    async def ask(request: Request):
        if os.environ.get("DEMO") != "1":
            raise HTTPException(404)
        data = await request.json()
        return {"answer": reply_text(data["phone"], data["question"])}

    return app
