# MAFI — Docker image (cloud / VPS)
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/backend/ /app/backend/
COPY app/frontend/ /app/frontend/

WORKDIR /app/backend

ENV MAFI_HOST=0.0.0.0
ENV MAFI_PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1

CMD ["python", "main.py"]
