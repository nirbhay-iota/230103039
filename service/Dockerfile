FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/hf TRANSFORMERS_OFFLINE=1

WORKDIR /app
COPY service/requirements.txt .
RUN pip install -r requirements.txt && rm -rf /root/.cache

COPY service/app.py service/validation.py service/runner.py service/prompt.py service/schema.json ./

USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
