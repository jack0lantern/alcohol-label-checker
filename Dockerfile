# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/app ./app

RUN pip install --no-cache-dir \
    "cryptography>=47.0.0" \
    "fastapi>=0.111.0" \
    "pillow>=10.4.0" \
    "pypdf>=6.10.2" \
    "python-multipart>=0.0.9" \
    "uvicorn[standard]>=0.30.0"

COPY --from=frontend-build /app/frontend/dist /app/static

ENV FRONTEND_DIST=/app/static
ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
