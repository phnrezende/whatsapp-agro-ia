"""Respostas fundamentadas nos materiais técnicos.

Busca os trechos mais relevantes da base (BM25) e responde por um destes caminhos, o primeiro configurado:
1. Dify (DIFY_API_KEY): o agente que o cliente já tem; a base de conhecimento fica no Dify.
2. OpenAI (OPENAI_API_KEY): os trechos achados aqui vão no prompt, com a ordem de responder só com eles.
   Qualquer API no formato da OpenAI serve: com OPENAI_BASE_URL=https://api.groq.com/openai/v1 e uma chave
   do Groq no OPENAI_API_KEY, usa um modelo aberto do plano grátis.
3. Nenhum: devolve os próprios trechos, com a fonte (modo demo, sem chave).
"""
import logging
import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

import httpx

log = logging.getLogger("agro")

STOPWORDS = set("""a o as os de da do das dos e em no na nos nas um uma uns umas para por com sem que se ao aos
como mais menos ou mas sobre entre ate apos antes depois quando qual quais isso isto esse essa este esta pelo pela
pelos pelas sao ser ter tem foi muito muita pode deve meu minha seu sua the and""".split())
NOT_FOUND = ("Não encontrei isso nos materiais técnicos que eu tenho. Para não te passar uma informação errada, "
             "procure um agrônomo ou a assistência técnica da sua região.")
GREETING = ("Olá! Sou o assistente agrícola. Pode me perguntar sobre o manejo da sua lavoura, como calagem, "
            "adubação e pragas, que eu respondo com base nos materiais técnicos.")
GREETING_WORDS = set("oi ola opa salve eae eai e ai bom boa dia tarde noite tudo bem beleza".split())


def words(text):
    """Minúsculas, sem acento e sem pontuação: "Olá, Bom DIA!" vira ["ola", "bom", "dia"]."""
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", text)


def tokens(text):
    return [w for w in words(text) if len(w) > 2 and w not in STOPWORDS]


def is_greeting(text):
    """Só cumprimento, sem pergunta junto: "oi, tudo bem?" sim; "bom dia, quando aplico calcário?" não."""
    ws = words(text)
    return bool(ws) and all(w in GREETING_WORDS for w in ws)


def read_text(path):
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def chunk(text, size=120):
    """Pedaços de ~size palavras, cortados em parágrafos para não partir uma frase ao meio."""
    out, cur = [], []
    for para in re.split(r"\n\s*\n", text):
        if para.lstrip().startswith(("#", ">")):  # títulos e notas do arquivo não são resposta
            continue
        words = para.split()
        if cur and len(cur) + len(words) > size:
            out.append(" ".join(cur))
            cur = []
        cur += words
    if cur:
        out.append(" ".join(cur))
    return out


class Base:
    def __init__(self, folder):
        self.chunks = [(p.name, c) for p in sorted(Path(folder).glob("*"))
                       if p.suffix.lower() in (".md", ".txt", ".pdf") for c in chunk(read_text(p))]
        self.tf = [Counter(tokens(c)) for _, c in self.chunks]
        self.avg = sum(sum(t.values()) for t in self.tf) / max(len(self.tf), 1)
        df = Counter(w for t in self.tf for w in t)
        n = len(self.tf)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def search(self, query, k=3, k1=1.5, b=0.75):
        q = tokens(query)
        scored = []
        for i, tf in enumerate(self.tf):
            size = sum(tf.values())
            s = sum(self.idf.get(w, 0) * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * size / self.avg))
                    for w in q if w in tf)
            if s > 0:
                scored.append((s, i))
        return [self.chunks[i] for _, i in sorted(scored, reverse=True)[:k]]


def answer(base, question, user):
    if os.environ.get("DIFY_API_KEY"):
        # shortcut: each message starts a new Dify conversation; keep conversation_id per user for follow-ups
        r = httpx.post(os.environ.get("DIFY_BASE_URL", "https://api.dify.ai") + "/v1/chat-messages", timeout=60,
                       headers={"Authorization": "Bearer " + os.environ["DIFY_API_KEY"]},
                       json={"inputs": {}, "query": question, "response_mode": "blocking", "user": user})
        r.raise_for_status()
        return r.json()["answer"]

    if is_greeting(question):  # no Dify, o próprio agente cumprimenta; aqui a busca não teria o que achar
        return GREETING
    found = base.search(question)
    if not found:
        return NOT_FOUND
    sources = "\n\n".join(f"[{name}]\n{text}" for name, text in found)

    if os.environ.get("OPENAI_API_KEY"):
        try:
            return ask_llm(question, sources)
        except httpx.HTTPError:  # cota grátis acabou ou modelo fora do ar: os trechos ainda respondem
            log.exception("falha no modelo; respondendo com os trechos")

    best_name, best_text = found[0]
    return f"Pelos materiais técnicos ({best_name}):\n\n{best_text}"


def ask_llm(question, sources):
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    r = httpx.post(base_url + "/chat/completions", timeout=60,
                   headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                   json={"model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"), "max_tokens": 1500, "messages": [
                       {"role": "system", "content":
                        "Você é um assistente agrícola, falando com produtores rurais pelo WhatsApp. Responda em "
                        "português simples e curto, usando SOMENTE os trechos abaixo, e cite a fonte entre "
                        "colchetes. Texto simples, sem markdown (nada de ** ou #). Se os trechos não responderem a pergunta, diga exatamente: " + NOT_FOUND},
                       {"role": "user", "content": f"Trechos:\n{sources}\n\nPergunta: {question}"}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
