FROM python:3.11.9-slim
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker/worker.py worker/clean.py worker/verify_shards.py ./
COPY prompts/teacher_prompt.txt ./teacher_prompt.txt
COPY data/schema.json ./schema.json
USER 10001
CMD ["python", "worker.py"]
