# Real Batch E2E Tests on TTB COLA Fixtures

**Date:** 2026-05-01
**Status:** Approved

## Problem

The existing Playwright E2E tests mock the entire backend (HTTP routes + WebSocket). They verify frontend behaviour but tell us nothing about whether the OCR pipeline, field extraction, or report generation work correctly on real label images.

## Goal

Add a small suite of Playwright E2E tests that run against a real backend (real Tesseract OCR, real field extraction) using actual label images downloaded from the TTB COLA public registry and committed to the repo.

## Scope

- 3 new Playwright tests (one beer, one wine, one distilled spirits label)
- 1 new Playwright config file (`playwright.real.config.ts`)
- 1 new fixture download script (`scripts/download_ttb_fixtures.py`)
- 3 new fixture sets added to the existing `tests/fixtures/labels/` manifest
- 1 new CI job (`test-real`), triggered manually or nightly — not on every PR

No changes to `playwright.config.ts` or the existing mocked test suite.

## Architecture

### Config split

Two Playwright config files with no shared state:

| File | Suite | Backend | Trigger |
|---|---|---|---|
| `playwright.config.ts` | Mocked (existing) | Fake WebSocket + `page.route()` | Every PR |
| `playwright.real.config.ts` | Real (new) | Live uvicorn + Tesseract | Manual / nightly |

Running the suites:
```
npx playwright test                                    # mocked — unchanged
npx playwright test --config playwright.real.config.ts # real stack
```

`playwright.real.config.ts` adds two `webServer` entries:
1. Vite dev server on `http://localhost:5173`
2. FastAPI backend on `http://localhost:8000` (`uvicorn app.main:app --port 8000`)

Playwright waits for both health checks before running any test.

### Fixtures

Real COLA label images are downloaded once via `scripts/download_ttb_fixtures.py`, inspected visually, then committed. Tests never fetch at runtime.

**Fixture files per label (example: `ttb_beer`):**
- `tests/fixtures/labels/images/ttb_beer.png` — downloaded COLA label scan
- `tests/fixtures/labels/forms/ttb_beer.json` — ground truth JSON (same content as `truth/`; placed in `forms/` to satisfy the manifest schema; the E2E test reads this file and passes it as the "form PDF" bytes)
- `tests/fixtures/labels/truth/ttb_beer.json` — same as `forms/`; identical file, separate path required by manifest schema
- `tests/fixtures/labels/expected/ttb_beer.json` — expected batch outcome, e.g. `{"status": "pass"}`; reuses the same file as other passing fixtures
- Entry in `tests/fixtures/labels/fixtures_manifest.json` with `source: "ttb-cola"`, `sample_type: "realistic"`, and SHA256 checksums for all four files

**Download script workflow (`scripts/download_ttb_fixtures.py`):**
1. Hardcodes a list of specific TTB COLA IDs for reproducibility
2. Fetches each label image from the TTB COLA public portal by ID
3. Writes image to `tests/fixtures/labels/images/ttb_<cola_id>.png`
4. Prints SHA256 of each file for the developer to record in the manifest

After running the script, the developer:
1. Visually inspects each downloaded image
2. Hand-writes `tests/fixtures/labels/truth/ttb_<cola_id>.json` with the five fields
3. Adds the manifest entry with checksums
4. Commits all files

**Ground truth JSON shape** (matches existing fixture format):
```json
{
  "brand_name": "...",
  "class_type": "...",
  "alcohol_content": "...",
  "net_contents": "...",
  "government_warning": "GOVERNMENT WARNING: ..."
}
```

The government warning is always the standard legal text, so it is never ambiguous.

### Test structure (`frontend/tests/e2e/real-labels.spec.ts`)

Three `test()` blocks in a loop over `["ttb_beer", "ttb_wine", "ttb_spirits"]`. Each test:

1. Reads image bytes and ground truth JSON from `tests/fixtures/labels/`
2. Navigates to `/`
3. Calls `setInputFiles` on the batch section's file input with:
   - `{ name: "<id>.pdf", mimeType: "application/pdf", buffer: Buffer.from(JSON.stringify(groundTruth)) }` — ground truth JSON passed as the form PDF; the backend's PDF parser falls back to JSON parsing (same technique used in existing integration tests)
   - `{ name: "<id>-front.png", mimeType: "image/png", buffer: imageBytes }` — the real COLA label image
4. Stem-matching auto-pairs them into one batch item
5. Clicks **Start batch check**
6. Waits up to **60 seconds** for `Batch progress: 1/1` — real Tesseract needs breathing room
7. Clicks **Download batch report**, captures the `download` event, reads the temp file as JSON
8. Asserts completion and field accuracy (see below)

### Assertions

**Smoke (completion):**
```
report.summary.total === 1
```
Verifies the batch completed without crashing — no error state, no hung progress.

**Field accuracy (per-field similarity thresholds):**

| Field | Threshold | Rationale |
|---|---|---|
| `brand_name` | ≥ 0.80 | Large text, consistently legible |
| `class_type` | ≥ 0.80 | Short, standardised vocabulary |
| `alcohol_content` | ≥ 0.60 | Units vary across label styles |
| `net_contents` | ≥ 0.60 | Mixed numeric/text, font size varies |
| `government_warning` | ≥ 0.80 | Long but fully standardised legal text |

Similarity is character-overlap ratio (same approach as `test_single_verify_uses_real_ocr_for_fixture_image` in the backend). `similarity(expected, null)` returns `0.0` — no special null guard needed; the assertion error message prints both values.

### Error handling

| Failure mode | Behaviour |
|---|---|
| Backend fails to start | `webServer` health-check times out before any test runs — clear error, no silent failures |
| OCR takes too long | 60s `toBeVisible` timeout fires with locator name in the error message |
| Field completely illegible (`extracted_value` is `null`) | `similarity()` returns 0.0, threshold assertion fails with actual vs expected printed |

### CI job (`test-real`)

- Triggered manually or on a nightly schedule — not on every PR push
- Runner prerequisites: `tesseract-ocr` (`apt-get install tesseract-ocr`), Python deps (`uv sync`), Node deps (`npm ci`), Playwright browsers (`npx playwright install`)
- Command: `npx playwright test --config playwright.real.config.ts`
- Expected duration: 5–10 minutes (acceptable for a nightly job)
- The existing `test-e2e` CI job is not modified

## Files to create / modify

| Path | Action |
|---|---|
| `playwright.real.config.ts` | Create |
| `frontend/tests/e2e/real-labels.spec.ts` | Create |
| `scripts/download_ttb_fixtures.py` | Create |
| `tests/fixtures/labels/images/ttb_beer.png` | Create (after running script) |
| `tests/fixtures/labels/images/ttb_wine.png` | Create (after running script) |
| `tests/fixtures/labels/images/ttb_spirits.png` | Create (after running script) |
| `tests/fixtures/labels/truth/ttb_beer.json` | Create (hand-written) |
| `tests/fixtures/labels/truth/ttb_wine.json` | Create (hand-written) |
| `tests/fixtures/labels/truth/ttb_spirits.json` | Create (hand-written) |
| `tests/fixtures/labels/fixtures_manifest.json` | Modify (add 3 entries) |
| `.github/workflows/` (or equivalent CI config) | Modify (add `test-real` job) |
