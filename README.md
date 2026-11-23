# Assistente agrícola no WhatsApp (demo)

Um assistente de agronomia no WhatsApp, por assinatura mensal. Ele responde com base em materiais técnicos e libera ou bloqueia o acesso sozinho conforme o pagamento no Asaas.

```
Produtor ──WhatsApp──▶ /webhooks/whatsapp ──▶ assinante ativo? ──não──▶ link de pagamento
                                                   │ sim
                                                   ▼
                                    Dify (agente do cliente)  ou  base local + OpenAI
                                                   │
                                                   ▼
                                      resposta com a fonte, pelo WhatsApp

Asaas ──webhook──▶ /webhooks/asaas ──▶ pago: ativa por 31 dias · atraso: bloqueia · cancelou: encerra
```

## Versão online

Tem um chat no navegador (`/`) para testar sem WhatsApp nem assinatura. Ele usa um modelo aberto grátis pelo
Groq, com limite de perguntas por dia. Se a cota grátis acabar, responde com os trechos dos materiais.

**Publicar no Vercel (grátis):**

1. Em https://vercel.com/new importe este repositório do GitHub (não precisa mudar nada; a entrada é o `index.py`).
2. Em https://console.groq.com/keys crie uma chave (grátis, sem cartão).
3. No projeto do Vercel, em **Settings > Environment Variables**, adicione:
   - `OPENAI_API_KEY` = a chave `gsk_...`
   - `OPENAI_BASE_URL` = `https://api.groq.com/openai/v1`
   - `OPENAI_MODEL` = `llama-3.1-8b-instant`
4. Faça um *Redeploy*. A cada push no `main`, o Vercel publica sozinho.

Sem as variáveis, o chat funciona do mesmo jeito, devolvendo os trechos. O `Dockerfile` serve para hospedar em
qualquer lugar com Docker (porta 7860).

## O que tem aqui

| Parte | Onde |
|---|---|
| Busca nos materiais (BM25) e resposta só com o que está neles | `app/rag.py` |
| Integração com o **Dify** (o agente que o cliente já tem) ou com a OpenAI | `app/rag.py` |
| WhatsApp Cloud API: verificação, assinatura HMAC da Meta e envio de respostas | `app/main.py` |
| Asaas: confirmação, atraso e cancelamento, com token do webhook | `app/main.py` |
| Assinantes e eventos já processados (SQLite) | `app/store.py` |
| Materiais de exemplo (`.md`, `.txt` ou `.pdf`) | `base/` |
| Chat web da versão online | `app/index.html` |
| Entrada do Vercel / imagem Docker | `index.py` / `Dockerfile` |
| Testes | `tests/test_app.py` |

Cuidados que costumam ficar de fora:
- **Resposta inventada:** se a pergunta não está nos materiais, ele diz que não sabe e indica um agrônomo.
- **Eventos repetidos:** a Meta e o Asaas reenviam eventos, e cada um é processado uma vez só.
- **Webhooks falsos:** o do WhatsApp só aceita mensagens com a assinatura da Meta, e o do Asaas só com o token configurado.
- **Pagamento atrasado:** quem paga atrasado ganha 31 dias contados do dia do pagamento, sem perder dias de acesso.

## Rodar

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pytest                        # 13 testes
```

Servidor local, sem WhatsApp nem chaves (modo demo):

```bash
set DEMO=1 & set ASAAS_WEBHOOK_TOKEN=teste
uvicorn app.main:create_app --factory --reload
```

Abra http://localhost:8000 para o chat web, ou use a rota `/ask`, que simula o WhatsApp com assinatura:

```bash
# sem assinatura: recebe o link de pagamento
curl -X POST localhost:8000/ask -H "content-type: application/json" -d "{\"phone\":\"5527999990000\",\"question\":\"quando aplicar calcario?\"}"

# o Asaas avisa que o pagamento foi confirmado
curl -X POST localhost:8000/webhooks/asaas -H "asaas-access-token: teste" -H "content-type: application/json" -d "{\"id\":\"evt_1\",\"event\":\"PAYMENT_CONFIRMED\",\"payment\":{\"externalReference\":\"5527999990000\",\"dueDate\":\"2026-12-01\"}}"

# agora responde com base nos materiais
curl -X POST localhost:8000/ask -H "content-type: application/json" -d "{\"phone\":\"5527999990000\",\"question\":\"quando aplicar calcario?\"}"
```

Em produção, preencha o `.env` a partir do `.env.example` e deixe `DEMO` vazio.

## Ligando nos serviços reais

- **Asaas:** crie a assinatura com `externalReference` = telefone do produtor (com DDI e DDD). Cadastre o webhook apontando para `/webhooks/asaas`, com os eventos de cobrança e assinatura e um token de autenticação igual a `ASAAS_WEBHOOK_TOKEN`.
- **WhatsApp:** no Meta for Developers, aponte o webhook para `/webhooks/whatsapp`, usando `WHATSAPP_VERIFY_TOKEN` na verificação, e assine o campo `messages`.
- **Dify:** com `DIFY_API_KEY`, as respostas vêm do app do Dify, e a base de conhecimento fica lá. Sem ela, usa a pasta `base/` com a OpenAI.

Os textos de `base/` são exemplos escritos para a demo, não recomendações técnicas.
