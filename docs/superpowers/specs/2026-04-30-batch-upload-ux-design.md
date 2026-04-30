# Batch upload UX redesign

**Status:** Design approved
**Date:** 2026-04-30

## Problem

The current batch upload flow demands that the user hand-author a JSON file containing **already-extracted form data** plus **base64-encoded label images**. That JSON is the upload contract. No real user authors this by hand — it's the API's internal shape leaked into the UI. The single-upload flow already accepts raw PDFs and images via multipart, so the building blocks for a friendly batch flow exist; they just aren't connected.

Constraint the original PRD missed: a single TTB form can have multiple label images (front / back / wraparound), so any redesign must support 1-form-to-N-labels (currently capped at 10 by the internal model).

## Goal

Replace the JSON upload contract with a drag-drop / file-picker flow. Auto-pair forms to label images using deterministic rules. Surface anything ambiguous in a small review panel the user must explicitly resolve. Convert to the existing internal JSON shape on the server. The internal `BatchItemPayload` structure and `create_batch_job` machinery do not change.

## High-level flow

```
[ Drop zone / folder picker ]   ← user gives raw PDFs + images
            ↓
[ Pairing engine (browser) ]    ← runs auto-pairing locally, no upload yet
            ↓
[ Preview + orphan tray (UI) ]  ← user resolves leftovers, confirms
            ↓
[ POST /verify/batch (multipart) ]  ← raw files + small mapping doc
            ↓
[ Backend ingest → existing batch_manager.create_batch_job ]
            ↓
[ WebSocket progress → report download ]   ← unchanged
```

Pairing is browser-side and reversible until the user clicks Start. Once the multipart POST happens, behavior matches today (job_id, WS events, report endpoint, retention guards).

## Pairing engine (browser)

Pure function. **Input:** list of `File` objects, each with `webkitRelativePath` (folder drop) or just `name` (flat drop). **Output:** `{ items, orphanPdfs, orphanImages }`.

### Algorithm

Single pass:

1. **Filter unsupported extensions.** Keep only `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`. Surface a small "ignored N files" notice for anything dropped.
2. **Bucket by parent directory.** Group files by their parent path. Flat drops all share `""` as parent. Folder drops naturally split per subfolder.
3. **Per-bucket folder-as-form rule.** If a bucket contains exactly one PDF and ≥1 image, emit one item — that PDF + every sibling image. Done with that bucket.
4. **Per-bucket strict-prefix stem rule (case-sensitive).** For remaining PDFs in a bucket, an image belongs to a PDF if `image.stem.startsWith(pdf.stem)` AND no other PDF in the same bucket has a longer matching stem (longest-prefix wins).
5. **Validate each emitted item.** If 0 labels → demote PDF to orphan-PDFs. If >10 labels → keep as an item but flag it so the user trims via remove-chips.
6. **Collect orphans.** Any PDF that ended with 0 labels, any image that no PDF claimed.

### Edge cases

| Situation | Behavior |
|---|---|
| Bucket has 2+ PDFs and loose images | Skip folder rule; fall through to stem matching |
| Image stem matches no PDF | Orphan image |
| Image stem matches two PDFs in same bucket | Longest-prefix wins; tie → orphan image with "ambiguous" flag |
| PDF alone in a folder, no images | Orphan PDF |
| File extension outside the allow-list | Filtered at intake; "ignored N files" notice |
| Item ends with 11+ matched labels | Item emitted but flagged; user must trim via remove-chips before Start |

### Item ID

Default to the PDF's filename stem. If empty or duplicated across items, append `-2`, `-3`, etc. User-visible in WS progress events; matches what the user recognizes from their filenames.

## Preview + orphan tray (UI)

Replaces the body of `frontend/src/components/BatchUpload.tsx`. Three stacked regions:

### 1. Drop zone / picker (top)

Single dashed area that accepts drag-drop, plus two buttons inside: **Pick folder** (`<input webkitdirectory>`) and **Pick files** (`<input multiple>`). After a drop the zone collapses to a one-line summary ("47 files: 23 PDFs, 24 images") with an **Add more** link that re-opens the picker. Adding more re-runs pairing on the combined set.

### 2. Paired items list (middle)

One row per item:

- PDF filename (the `item_id`)
- Filename chips for each label (no actual image render — stays cheap)
- Label-count badge: green if 1–10, red if >10

Rows with 11+ labels render the labels as removable chips. Clicking a chip removes that label from the item and sends it back to the orphan-images pool. Otherwise rows are display-only.

### 3. Orphan tray (bottom, hidden when empty)

Two columns:

- **Orphan PDFs:** each shows **Discard** and **Attach images…** (opens a small picker over the orphan-image pool).
- **Orphan images:** each shows **Discard** and is draggable. Drop targets:
  - A row in the paired list → attach to that item.
  - An orphan-PDF row → makes it a paired item with that one image.

### Start gating

Start button enabled only when ALL of:

- ≥1 valid item exists
- Every item has 1–10 labels
- Orphan tray is empty (every leftover explicitly resolved or discarded)

Tooltip on hover when disabled explains which condition failed. **No global "ignore N orphans" button** — every leftover must be resolved item-by-item so the user is aware of unprocessed items.

### State

Single React state object: `{ items, orphanPdfs, orphanImages }` plus a `Map<File, fileId>` so DOM events reference files by id. No upload happens until Start. On Start: build the multipart `FormData`, POST, then transition the UI to the existing job-progress / download view (unchanged).

## Backend endpoint

**Replace** `POST /verify/batch` (currently JSON) with a multipart endpoint at the same path. The existing JSON contract is broken cleanly — no programmatic users today.

### Request

```
POST /verify/batch
Content-Type: multipart/form-data

files:    [PDFs and images, repeated form field]
mapping:  application/json
  {
    "items": [
      { "item_id": "widget-001",
        "form_filename": "widget-001.pdf",
        "label_filenames": ["widget-001-front.png", "widget-001-back.png"] },
      ...
    ]
  }
```

Filenames in `mapping` reference the multipart `files` part by their original filename.

### Server behavior

1. Read all `files` into a `dict[str, bytes]` keyed by original filename.
2. Walk `mapping.items`, building the internal payload:
   - `form_payload` ← `{"pdf_base64": b64encode(pdf_bytes)}`. The PDF is **not** parsed at intake — raw bytes pass through so the worker can parse and surface per-item parse failures as `review_required` via its existing retry/exception path.
   - `label_payloads[]` ← `[{ "image_base64": b64encode(image_bytes) }, ...]` — matches what `_coerce_label_bytes` already decodes.
3. Call `create_batch_job(items)` exactly as today.

### Response

Unchanged: `202 { "job_id": "..." }`. WS events, `/verify/batch/{job_id}/report`, retention guards: all unchanged.

### Validation (fail-fast at intake → 400, no job created)

| Rule | Error message |
|---|---|
| `files` empty or `mapping` missing | "missing files or mapping" |
| `mapping` not parseable JSON | "invalid mapping" |
| Any `items[i].label_filenames` length not in 1..10 | "item X must have 1–10 labels" |
| Any referenced filename not present in `files` | "missing file: X" |
| Duplicate `item_id` across items | "duplicate item_id: X" |
| `items` length > 300 | "batch exceeds 300 items" |

**No total-upload-size cap server-side.** Rely on reverse-proxy / CDN limits and browser memory pressure. Per-item PDF parse failures are NOT intake-time errors — they propagate as `review_required` per existing worker behavior.

## Internal contract — minimally adapted

`batch_manager.create_batch_job` continues to consume a per-item dict, with one adjustment to `form_payload` so the worker handles PDF parsing (enabling parse-failure → `review_required` per the worker's existing retry path):

```python
{
  "item_id": str,
  "form_payload": {"pdf_base64": str},
  "label_payloads": [{"image_base64": str}, ...],
}
```

`_verify_item_payload` in `backend/app/services/batch_manager.py` changes one line: instead of `form_bytes = bytearray(json.dumps(form_payload).encode("utf-8"))`, it does `form_bytes = bytearray(b64decode(form_payload["pdf_base64"]))`. The downstream call to `extract_ground_truth(bytes(form_bytes))` is unchanged. WS event schema, retention guards, retry behavior, and report builder are all untouched.

The new endpoint is a thin adapter that builds this from raw multipart files.

## Testing

### Pairing engine (vitest, browser, pure function — highest leverage)

- Flat drop, all match by stem prefix → 0 orphans
- Folder-per-form drop, one PDF per subfolder → 0 orphans
- Mixed drop (some folders, some flat root files) → handled per-bucket
- Two PDFs sharing a stem prefix in same bucket (`widget-1.pdf`, `widget-10.pdf`) → longest-prefix-wins, no images leaked to wrong PDF
- PDF alone in a folder → orphan PDF
- Image with no matching PDF → orphan image
- Item with 11 matched labels → emitted with flag
- Duplicate filename stems across items → `item_id` suffixed `-2`, `-3`

### UI E2E (Playwright, extends `frontend/tests/e2e/batch-progress.spec.ts`)

- Happy path: drop a fixture folder (PDFs + images), preview renders correct pair counts, Start, WS progress streams, report downloads.
- Adversarial: orphan PDF + orphan image present → Start disabled. After discarding one and attaching the other, Start enables. Job runs and report downloads.

Folder-drop in Playwright: pre-stage fixture files and use `setInputFiles` against the `webkitdirectory` input — Playwright supports paths with directory structure.

### Backend (FastAPI integration, extends `backend/tests/integration/test_batch_verify_api.py`)

- Multipart with valid mapping → 202 + `job_id`, downstream WS/report flow works
- Missing referenced filename in `mapping` → 400, missing filename in error message
- Duplicate `item_id` → 400
- Mapping JSON unparseable → 400
- Batch of 3 with one malformed PDF → 202 (job created), that item ends `review_required`, others complete normally

### Out of scope for E2E

Exhaustive pairing edge-case coverage. Those live in the vitest unit tests where they're cheap. E2E covers the wiring, not the algorithm.

## Files affected

- `frontend/src/components/BatchUpload.tsx` — full rewrite
- `frontend/src/lib/pairing.ts` — new pure function module + tests (`pairing.test.ts`)
- `frontend/tests/e2e/batch-progress.spec.ts` — extend
- `backend/app/api/routes_verify.py` — replace `verify_batch` with multipart handler; drop the `BatchVerifyRequest` / `BatchItemPayload` Pydantic models from this file
- `backend/app/services/batch_manager.py` — one-line change in `_verify_item_payload` (json-dump → base64-decode) per the internal-contract section
- `backend/tests/integration/test_batch_verify_api.py` — rewrite to multipart
- `backend/tests/integration/test_batch_ws_progress.py`, `backend/tests/unit/test_batch_manager_retention.py` — adjust any direct fixtures that build the old `form_payload` dict shape
- `tests/fixtures/labels/` — add a small folder fixture for the E2E happy path

## Out of scope

- Multi-tenant or auth (matches existing app posture)
- Resumable uploads / chunked upload (out of scope for batch-of-300)
- Server-side rendering of label thumbnails in the preview (filenames only)
- A `mapping.csv` file inside the upload folder (auto-pairing replaces it; not adding a file-based override path)
