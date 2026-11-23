# Hugging Face Spaces (SDK Docker): roda como o usuário 1000 e espera a porta 7860
FROM python:3.13-slim
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .
ENV DEMO=1 PATH=/home/user/.local/bin:$PATH
EXPOSE 7860
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers"]
