# ---- 1. Build the React UI ----
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app

# LibreOffice (no GUI) converts old Word files (.doc/.rtf/.odt) to .docx
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reader/ reader/
COPY app/ app/
COPY --from=ui /ui/dist frontend/dist

# Run as an unprivileged user, never root
RUN useradd --create-home --uid 1000 appuser && mkdir -p /data && chown appuser /data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

# --no-access-log: audio URLs carry ?token=..., so request logs would leak it
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
