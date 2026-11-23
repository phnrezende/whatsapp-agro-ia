# Assistente agrícola no WhatsApp (demo)

Um assistente de agronomia no WhatsApp, por assinatura mensal. Ele responde com base em materiais técnicos e libera ou bloqueia o acesso sozinho conforme o pagamento no Asaas.

**Teste online: https://whatsapp-agro-ia.vercel.app**

> O projeto foi feito para rodar com o **GPT (OpenAI)** ou com um agente no **Dify**, como descrito abaixo.
> O site acima é só uma demonstração: usa uma IA gratuita e mais fraca (Groq), sem WhatsApp e sem assinatura.

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

## Versão online (demo)

Em https://whatsapp-agro-ia.vercel.app tem um chat no navegador para testar sem WhatsApp nem assinatura.

Como funciona:

```
Navegador ──pergunta──▶ /chat ──▶ limite de 20 perguntas por dia por IP
                                        │
                                        ▼
                     busca os trechos nos materiais (BM25, em base/)
                                        │
                                        ▼
               IA grátis do Groq responde só com esses trechos e cita a fonte
                                        │ se a cota grátis acabar ou a IA cair
                                        ▼
               devolve o próprio trecho + pop-up avisando que é uma resposta padrão
```

- Ao abrir a página, um aviso explica que é uma demo com IA gratuita e que a cota pode acabar por um tempo.
- A busca e a regra de "não inventar" são as mesmas da versão do WhatsApp (`app/core/`). Só muda o modelo:
  aqui é o `openai/gpt-oss-20b` do Groq, que é grátis; em produção, o GPT ou o agente do Dify.
- Pergunta fora dos materiais recebe "não encontrei" e a indicação de um agrônomo, nos dois casos.
- O Groq funciona porque usa o mesmo formato de API da OpenAI: o código é o mesmo, só mudam as variáveis
  `OPENAI_BASE_URL`, `OPENAI_MODEL` e `OPENAI_API_KEY`.

**Publicar no Vercel (grátis):**

1. Em https://vercel.com/new importe este repositório do GitHub (não precisa mudar nada; a entrada é o `index.py`, que sobe `app/web/`).
2. Em https://console.groq.com/keys crie uma chave (grátis, sem cartão).
3. No projeto do Vercel, em **Settings > Environment Variables**, adicione:
   - `OPENAI_API_KEY` = a chave `gsk_...`
   - `OPENAI_BASE_URL` = `https://api.groq.com/openai/v1`
   - `OPENAI_MODEL` = `openai/gpt-oss-20b`
4. Faça um *Redeploy*. A cada push no `main`, o Vercel publica sozinho.

Sem as variáveis, o chat funciona do mesmo jeito, devolvendo os trechos. O `Dockerfile` serve para hospedar em
qualquer lugar com Docker (porta 7860).

## O que tem aqui

```
app/
├── core/          compartilhado pelas duas versões
│   ├── rag.py       busca nos materiais (BM25) e resposta pelo Dify, OpenAI ou Groq
│   └── store.py     assinantes e eventos já processados (SQLite)
├── whatsapp/      versão de produção (pronta para implementar no cliente)
│   └── main.py      webhooks do WhatsApp Cloud API e do Asaas, rota /ask de teste
└── web/           só para a demo online
    ├── main.py      o app do WhatsApp + chat no navegador (/ e /chat), limite diário
    └── index.html   página do chat, aviso de demo e pop-up de cota grátis esgotada
base/              materiais de exemplo (.md, .txt ou .pdf)
tests/             test_whatsapp.py (produção) e test_web.py (demo)
tools/             capture_demo.py, que gera os dados do vídeo
index.py           entrada do Vercel (versão web)
Dockerfile         imagem Docker da versão web (porta 7860)
```

Para o cliente, só `app/core/` e `app/whatsapp/` importam. `app/web/`, `index.py` e o `Dockerfile` podem ser
apagados sem afetar nada da produção.

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
pytest                        # 17 testes
```

Produção (WhatsApp), local, sem WhatsApp nem chaves (modo demo):

```bash
set DEMO=1 & set ASAAS_WEBHOOK_TOKEN=teste
uvicorn app.whatsapp.main:create_app --factory --reload
```

Para a versão web, troque por `app.web.main:create_app` e abra http://localhost:8000.

A rota `/ask` simula o WhatsApp com assinatura:

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
