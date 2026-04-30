# Alcohol Label Checker MVP Design

Date: 2026-04-29
Scope: MVP only
Status: Approved in brainstorming session

## 1. Goals and Constraints

### Goals
- Verify alcohol label content against uploaded TTB F 5100.31 data.
- Support both single checks and batch runs (up to 300 mapped pairs).
- Return outcomes quickly enough to beat manual review flow.
- Keep user interaction simple and no-training-friendly.

### Hard Constraints
- Processing SLA target: <= 5 seconds per item.
- Zero-retention: no persisted PII and no payload/text storage beyond in-memory processing lifecycle.
- Local-first OCR/parsing behavior for network-constrained government environment.
- Python backend on Azure.

## 2. Selected Architecture

Recommended and selected approach: modular monolith with in-process async queue.

- Frontend: React + Vite SPA.
- Backend: FastAPI + Uvicorn.
- Progress: WebSocket stream for batch updates.
- Execution: in-process `asyncio` job manager with bounded concurrency.
- Queue/backends: abstractions designed now to allow future external queue adoption without endpoint rewrites.

Rationale:
- Fastest path to MVP delivery with lowest operational complexity.
- Strong fit for zero-retention controls because all state can remain in RAM.
- Enables robust batch UX without early infrastructure coupling.

## 3. Key Product Decisions Captured

- MVP scope only (no production-hardening expansion in this phase).
- OCR strategy: Tesseract now; interfaces prepared for future fallback (e.g., EasyOCR) without refactor.
- Batch result handling: live in-memory progress plus immediate downloadable report.
- Government warning policy: fail-closed on uncertain matching.
- Batch failure policy: continue processing, auto-retry each failed item once, then mark `review_required`.
- Frontend strategy: separate React/Vite app calling FastAPI APIs.

## 4. Backend Component Boundaries

### API Layer (`api/`)
- `POST /verify/single`: one PDF + one label image, synchronous result.
- `POST /verify/batch`: folder payload intake, mapping validation, `job_id` creation.
- `GET /verify/batch/{job_id}/report`: in-memory CSV/JSON report download.
- `WS /verify/batch/{job_id}/events`: per-item and aggregate progress events.

### Domain Models (`domain/models.py`)
- Core entities: `GroundTruthFields`, `LabelExtractedFields`, `FieldResult`, `ItemResult`, `BatchJobState`.
- Status values:
  - Job: `queued`, `running`, `completed`, `completed_with_failures`
  - Item: `queued`, `processing`, `retrying`, `completed`, `review_required`

### Services
- `services/pdf_parser.py`: extract Item 5, Item 6, Item 8 from TTB PDF.
- `services/image_preprocess.py`: OpenCV normalization (deskew, denoise, glare reduction, thresholding).
- `services/ocr/ocr_engine.py`: OCR interface.
- `services/ocr/tesseract_engine.py`: current OCR implementation.
- `services/extractor.py`: parse OCR text into required 7 fields.
- `services/matcher.py`: field comparison logic, including warning-specific strict handling.
- `services/batch_manager.py`: in-memory job registry, bounded worker pool, retry-once behavior.
- `services/retention_guard.py`: centralized memory cleanup and lifecycle purge enforcement.

## 5. End-to-End Data Flows

### Single Flow
1. Client uploads one PDF and one image to `POST /verify/single`.
2. Backend extracts ground truth from PDF.
3. Backend preprocesses image and runs OCR.
4. Extractor derives label fields from OCR output.
5. Matcher computes per-field pass/fail/review outcomes.
6. Response returns structured result payload.
7. Retention guard purges all transient artifacts immediately after response lifecycle.

### Batch Flow
1. Client uploads directory payload (CSV + files) to `POST /verify/batch`.
2. Backend validates CSV mappings and creates an in-memory job.
3. Worker pool processes each pair through same pipeline as single flow.
4. Item errors trigger one retry; second failure becomes `review_required`.
5. WebSocket emits progress and per-item status updates.
6. On completion, backend assembles report in memory for download.
7. After report delivery (or expiry), job artifacts are purged from memory.

## 6. Matching Policy

### General Fields
- Case-insensitive comparison for standard fields to tolerate acceptable styling variations.

### Government Warning (Compliance-Critical)
- Fail-closed policy.
- Strict matching intent with OCR-aware tolerance for narrowly scoped artifacts.
- Normalization and high-threshold similarity are allowed only for known OCR noise patterns.
- Any unresolved uncertainty maps to mismatch/review-required, never auto-pass.

## 7. Error Handling and Operational Safety

### Error Handling
- Validate early: malformed CSV, missing files, unsupported types rejected with clear client errors.
- Categorize errors predictably: `parse_error`, `ocr_error`, `mapping_error`, `validation_error`, `internal_error`.
- Isolate failures per batch item to prevent whole-job collapse.

### Performance Controls
- Bounded concurrency tuned to available VM CPU.
- Stage timing metrics for parse/preprocess/OCR/match.
- Backpressure behavior when system is saturated.
- Minimal deterministic preprocessing in MVP to limit latency variance.

### Zero-Retention Security Controls
- No disk writes for payloads, extracted text, or reports.
- No raw extracted content in logs.
- Opaque short-lived job IDs.
- Aggressive explicit memory cleanup plus TTL sweeper safeguards.

## 8. Test Strategy

### Unit and Service Tests
- PDF extraction correctness for Item 5/6/8.
- Field extraction coverage for all 7 required fields.
- Matching policy tests, especially warning fail-closed behavior.
- Service pipeline tests for single and batch execution paths.

### API Contract Tests
- Endpoint request/response shape verification.
- WebSocket event schema and ordering checks.
- Report generation and delivery checks.

### Security and Retention Tests
- Assert no payload artifacts are written to disk.
- Assert post-completion state and artifact purge.
- Assert logs do not contain extracted label/form text.

### Performance Tests
- Single-item latency checks against SLA targets.
- Batch soak tests (up to 300 items) to validate stability and bounded resource behavior.

## 9. Hermetic E2E Dataset and Coverage Plan

### E2E Scope
- Add deterministic E2E coverage for `pass`, `fail`, and `review_required`.
- Run both API-level E2E and browser E2E smoke tests.

### Fixture Strategy
- Mixed fixture set:
  - Curated realistic fixtures (public-style structure, locally committed).
  - Generated adversarial fixtures (glare, skew, blur, tiny text, punctuation OCR noise).
- All test assets are committed and offline; no runtime internet dependency.

### Fixture Layout
- `tests/fixtures/labels/images/`
- `tests/fixtures/labels/forms/`
- `tests/fixtures/labels/truth/`
- `tests/fixtures/labels/expected/`
- `tests/fixtures/labels/fixtures_manifest.json` (checksums + provenance notes)

### Batch CSV Fixture Set
- `tests/fixtures/batch/batch_all_pass.csv`
- `tests/fixtures/batch/batch_mixed_results.csv`
- `tests/fixtures/batch/batch_with_missing_file.csv`
- `tests/fixtures/batch/batch_with_retry_then_review.csv`

### API E2E (Required CI Gate)
- Exercise:
  - `POST /verify/single`
  - `POST /verify/batch`
  - `WS /verify/batch/{job_id}/events`
  - `GET /verify/batch/{job_id}/report`
- Assert:
  - expected outcomes by fixture,
  - retry-once semantics,
  - report content integrity,
  - retention cleanup guarantees.

### Browser E2E (CI Smoke)
- Flow 1: single upload to final result view.
- Flow 2: batch upload, live progress updates, report download availability.
- Keep smoke suite small; broader browser suite can run on scheduled jobs.

## 10. Delivery Milestones

- M1: project skeleton and API contracts.
- M2: single verification path (PDF parse, preprocess, OCR, extract, match).
- M3: batch pipeline with in-memory queue and websocket progress.
- M3.5: hermetic E2E harness (fixtures, API E2E, browser smoke, CI integration).
- M4: zero-retention hardening, error taxonomy, observability, SLA tuning.
- M5: Azure deployment and acceptance verification.

## 11. Deferred Items (Explicitly Out of MVP)

- Persistent/distributed queue infrastructure.
- External OCR providers or remote inference APIs.
- Automatic model fallback beyond prepared OCR abstraction interfaces.
- Integration with legacy .NET COLA systems.

