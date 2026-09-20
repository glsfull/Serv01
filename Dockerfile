FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SERV01_DATABASE_URL=sqlite+pysqlite:////data/serv01.db \
    SERV01_SCREENSHOT_DIR=/data/screenshots

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && addgroup --system serv01 \
    && adduser --system --ingroup serv01 serv01 \
    && mkdir -p /data/screenshots \
    && chown -R serv01:serv01 /data /ms-playwright

USER serv01

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "serv01.main:app", "--host", "0.0.0.0", "--port", "8000"]
