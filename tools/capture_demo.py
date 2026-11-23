"""Runs the real demo flow in-process and writes what each step returned, for the demo video."""
import json
import os
import sys
import tempfile
from datetime import date

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.whatsapp.main import create_app  # noqa: E402

os.environ.update(DEMO="1", ASAAS_WEBHOOK_TOKEN="teste", PAYMENT_LINK="https://www.asaas.com/c/assinatura-demo")
for k in ("DIFY_API_KEY", "OPENAI_API_KEY", "WHATSAPP_TOKEN"):
    os.environ.pop(k, None)

PHONE = "5527999990000"
sent = []
client = TestClient(create_app("base", os.path.join(tempfile.mkdtemp(), "demo.db"),
                               send=lambda to, text: sent.append(text)))
ask = lambda q: client.post("/ask", json={"phone": PHONE, "question": q}).json()["answer"]  # noqa: E731
event = {"id": "evt_1", "event": "PAYMENT_CONFIRMED",
         "payment": {"externalReference": PHONE, "dueDate": date.today().isoformat()}}
hook = lambda token: client.post("/webhooks/asaas", json=event, headers={"asaas-access-token": token})  # noqa: E731

out = {"q_calagem": "Quando devo aplicar calcário?", "q_lagarta": "Tem lagarta no cartucho do milho, o que eu faço?",
       "q_boi": "Qual o preço do boi gordo hoje?"}
out["paywall"] = ask(out["q_calagem"])
out["fake_webhook_status"] = hook("errado").status_code
out["webhook"] = hook("teste").json()
out["welcome"] = sent[-1]
out["webhook_dup"] = hook("teste").json()
out["messages_after_dup"] = len(sent)
out["calagem"] = ask(out["q_calagem"])
out["lagarta"] = ask(out["q_lagarta"])
out["boi"] = ask(out["q_boi"])
print(json.dumps(out, ensure_ascii=False, indent=1))
