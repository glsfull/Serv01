FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERV01_DATABASE_URL=sqlite+pysqlite:////data/serv01.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && addgroup --system serv01 \
    && adduser --system --ingroup serv01 serv01 \
    && mkdir /data \
    && chown serv01:serv01 /data

USER serv01

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "serv01.main:app", "--host", "0.0.0.0", "--port", "8000"]
