"""Entrada do Vercel: ele procura um `app` no index.py da raiz. Só o disco /tmp aceita escrita lá."""
import os

from app.main import create_app

os.environ.setdefault("DEMO", "1")  # o site público é a versão online, com o chat web
app = create_app(db_path="/tmp/agro.db" if os.environ.get("VERCEL") else "agro.db")
