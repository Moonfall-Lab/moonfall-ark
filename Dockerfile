FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    RUNTIME_HOST=0.0.0.0 \
    RUNTIME_PORT=8000 \
    SQLITE_DB_PATH=/data/moonfall.db

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin moonfall \
    && mkdir -p /data \
    && chown -R moonfall:moonfall /data

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/backend/requirements.txt

COPY backend /app/backend
RUN chown -R moonfall:moonfall /app/backend

USER moonfall
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
