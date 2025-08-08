FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

# Persistence directory
RUN mkdir -p /app_data

EXPOSE 8000

ENV MONITOR_MODE=winrm \
    SAMPLE_INTERVAL_SECONDS=1 \
    PERSIST_PATH=/app_data/metrics.json

CMD ["gunicorn", "-b", "0.0.0.0:8000", "app.server:app", "--workers", "1", "--threads", "4"]
