# Alcohol Label Checker

MVP web app for checking alcohol label data against submitted form data.

This repository contains:
- a `FastAPI` backend (`backend/`)
- a `React + Vite` frontend (`frontend/`)
- hermetic fixtures and test data (`tests/fixtures/`)

## Current Status

Implemented MVP workflow:
- Single check endpoint: `POST /verify/single`
- Batch check endpoint: `POST /verify/batch`
- Batch progress websocket: `WS /verify/batch/{job_id}/events`
- Batch report endpoint: `GET /verify/batch/{job_id}/report`

Also included:
- in-memory batch state and report generation
- retention guards and cleanup endpoints
- backend integration tests
- frontend Playwright smoke tests

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- npm

## Local Setup

### 1) Backend

```bash
cd backend
uv sync --extra dev
```

Run API:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Frontend

```bash
cd frontend
npm ci
npm run dev
```

The frontend assumes the backend is reachable on the same host.

## Testing

### Backend

Run unit + integration suites:

```bash
cd backend
uv run pytest tests/unit tests/integration -q
```

### Frontend

Build:

```bash
cd frontend
npm run build
```

Run smoke E2E tests:

```bash
npm run test:e2e -- tests/e2e/smoke.spec.ts tests/e2e/batch-progress.spec.ts
```

## API Summary

This README uses **backend** and **API** for the same FastAPI app, but for different purposes. **Backend** refers to the `backend/` codebase—installing dependencies, running the server, and running tests. **API** refers to the HTTP and WebSocket surface—routes, methods, and request shapes for callers.

- `GET /health`
- `POST /verify/single`
  - multipart fields:
    - `form_pdf`
    - `label_image`
- `POST /verify/batch`
- `GET /verify/batch/{job_id}/report`
  - optional query: `purge=true`
- `DELETE /verify/batch/{job_id}`
- `DELETE /verify/batch`
- `WS /verify/batch/{job_id}/events`

## Fixtures and Test Data

Hermetic fixtures live under:
- `tests/fixtures/labels/`
- `tests/fixtures/batch/`

Fixture generator script:
- `scripts/generate_synthetic_label_fixtures.py`

Manifest validation test:
- `backend/tests/unit/test_fixture_manifest.py`

## Notes / MVP Limitations

- The single upload path includes a deterministic fallback response (`review_required`) for non-parseable binary payloads to avoid hard failures.
- Batch report cleanup supports `purge=true` and TTL-based eviction.
- Data is designed to remain in memory; no persistent database is used in this MVP.
