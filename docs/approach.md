# Brief documentation: approach, tools, assumptions
This doc captures the **current MVP implementation** in this repo (not the full PRD vision).

## Approach (current MVP)

### Single verification flow (`POST /verify/single`)
- **Inputs**: one `form_pdf` (PDF) + 1–10 `label_images`.
- **Runtime pipeline per request** (see `backend/app/api/routes_verify.py`):
  - Parse/derive **ground truth** from the uploaded PDF (`extract_ground_truth`).
  - For each label image:
    - Preprocess image bytes (`preprocess_image`) to improve OCR robustness.
    - Run local OCR via Tesseract (`TesseractEngine().extract_text(...)`).
    - Convert OCR text into structured extracted fields (`extract_fields`).
    - Compare extracted fields vs ground truth (`match_fields`).
  - Return:
    - Per-image results (`image_results[]`)
    - An **aggregate best-of** field result set across all images (prefers `pass` > `review_required` > `fail`).
- **Failure behavior**:
  - If parsing/OCR/extraction throws `UnicodeDecodeError`, `JSONDecodeError`, or `ValueError`, the endpoint returns a **deterministic fallback** response with overall `review_required` (never a hard 5xx for those cases).
- **Retention**:
  - The request uses `forbid_disk_writes()` to prevent accidental disk IO during processing.
  - A `finally` block clears in-memory artifacts (`clear_single_artifacts(...)`).

### Batch verification flow (`POST /verify/batch` + websocket + report)
- **Upload**: `POST /verify/batch` accepts:
  - `files`: multiple uploads (PDFs and images)
  - `mapping`: a JSON string (form field) with `{"items":[...]}`
    - Each item references uploaded filenames (`form_filename`, `label_filenames[]`) and may include an optional `item_id`.
    - Server enforces **1–10 labels per item** and **<= 300 items per batch**.
- **Job model**:
  - The server creates an **in-memory batch job** (`create_batch_job(...)`) and returns a `job_id` immediately (202 Accepted).
  - Progress is streamed via WebSocket:
    - `WS /verify/batch/{job_id}/events` (also available at `WS /ws/batch/{job_id}`)
  - The batch report is fetched via:
    - `GET /verify/batch/{job_id}/report` (returns 202 while queued/running, 200 when complete)
    - Optional `purge=true` deletes the job after a completed (200) report.
  - Cleanup endpoints:
    - `DELETE /verify/batch/{job_id}` removes a specific job
    - `DELETE /verify/batch` clears all jobs

## Matching rules (current MVP)

### General fields (case-insensitive exact)
For “general” fields, comparison is:
- `strip()` + `casefold()` on both expected and extracted values
- **pass** only if normalized strings are exactly equal; otherwise **fail**

### Government warning (strict + OCR-aware review threshold)
The government warning field uses:
- Exact string equality ⇒ **pass**
- Otherwise similarity via `difflib.SequenceMatcher(...).ratio()`
  - similarity >= **0.97** ⇒ **review_required**
  - else ⇒ **fail**

This intentionally creates a narrow “OCR artifacts likely” band that escalates to human review instead of passing.

## Tools used (repo reality)

### Backend
- **FastAPI** for HTTP routes and WebSocket progress streaming
- **Pydantic** for request/response modeling where needed
- **Tesseract OCR** (via `app/services/ocr/tesseract_engine.py`)
- **Image preprocessing** (`app/services/image_preprocess.py`) before OCR
- **In-memory batch manager** + event log (`app/services/batch_manager.py`)
- **pytest** integration tests under `backend/tests/`
- **uv** for Python dependency management and running commands (see `README.md`)

### Frontend
- **React + Vite** (`frontend/`)
- **Playwright** smoke tests (`frontend/tests/e2e/...`)

### Fixture/test tooling
- Hermetic fixtures under `tests/fixtures/`
- Fixture generator scripts under `scripts/`

## Assumptions and known gaps (vs PRD)
- **No database / persistence**: batch state and reports are in memory; jobs are cleared via explicit endpoints and optional purge.
- **Zero-retention intent**:
  - Single verification explicitly forbids disk writes and clears in-memory buffers.
  - Batch jobs necessarily retain items/results **in memory** until completion (and optionally until purged).
- **OCR stack**:
  - Current implementation uses Tesseract (local). The PRD’s “two-tier” OCR fallback is not implemented here.
- **Matching strictness**:
  - General fields are case-insensitive exact matches (no fuzzy matching).
  - Government warning uses a similarity threshold that yields `review_required` rather than `pass`.
- **Latency targets**:
  - The PRD specifies <= 5 seconds/item; this repo includes tests and a deterministic fallback path, but does not guarantee SLA enforcement.

