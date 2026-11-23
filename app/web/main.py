"""Versão web (só para demonstração): o mesmo app do WhatsApp mais um chat no navegador.

Rotas a mais:
- GET /    a página do chat (index.html), com os avisos de demo e de cota grátis
- POST /chat  responde sem assinatura, com limite de perguntas por dia; "fallback": true quando a IA caiu
"""
import logging
import os
from collections import Counter
from datetime import date
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core import rag
from app.whatsapp.main import ERROR, create_app as create_whatsapp_app

log = logging.getLogger("agro")
PAGE = Path(__file__).with_name("index.html")


def create_app(base_dir="base", db_path="agro.db", **kwargs):
    app = create_whatsapp_app(base_dir, db_path, **kwargs)
    base = app.state.base
    daily_limit = int(os.environ.get("CHAT_DAILY_LIMIT", "20"))
    used = Counter()  # shortcut: em memória e zera ao reiniciar; serve para uma demo, não para cobrar

    @app.get("/", response_class=HTMLResponse)
    def page():
        return HTMLResponse(PAGE.read_text(encoding="utf-8"))

    @app.post("/chat")
    async def chat(request: Request):
        question = str((await request.json()).get("question", "")).strip()[:500]
        if not question:
            raise HTTPException(400, "Escreva uma pergunta.")
        # atrás do proxy (Vercel) o IP real vem no X-Forwarded-For
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0]
        key = (ip.strip(), date.today())
        if used[key] >= daily_limit:
            raise HTTPException(429, f"Limite de {daily_limit} perguntas por dia nesta demo. Volte amanhã!")
        used[key] += 1
        failed = []  # a página mostra o aviso de "acabaram os tokens" quando a IA cai para os trechos
        try:
            text = rag.answer(base, question, "web", on_llm_error=lambda: failed.append(True))
            return {"answer": text, "left": daily_limit - used[key], "fallback": bool(failed)}
        except Exception:
            log.exception("falha no chat web")
            return {"answer": ERROR, "left": daily_limit - used[key]}

    return app
