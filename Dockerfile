FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UI_HOST=0.0.0.0 \
    UI_PORT=8765 \
    RUNNING_IN_DOCKER=1 \
    UPLOADS_DIR=/data/uploads

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agentic_pi_migration ./agentic_pi_migration
COPY web ./web
COPY scenarios ./scenarios

RUN useradd --create-home --uid 10001 migration \
    && mkdir -p /data/uploads /data/reports \
    && chown -R migration:migration /app /data

USER migration
EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/health', timeout=2)"]

CMD ["python", "-m", "agentic_pi_migration.web.server"]
