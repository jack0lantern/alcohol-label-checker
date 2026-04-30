# Batch Upload UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-authored JSON batch upload contract with a drag-drop / file-picker flow that auto-pairs PDFs to label images, surfaces orphans for explicit resolution, and POSTs raw files via multipart.

**Architecture:** Browser-side pairing (pure function) feeds a stateful preview UI; user resolves orphans before clicking Start; new multipart `/verify/batch` endpoint adapts the upload to the existing internal `BatchItemPayload` shape (with one minor adjustment: `form_payload` now carries raw PDF bytes via base64, so the worker handles parse failures as `review_required` per the existing retry path).

**Tech Stack:** TypeScript / React 18 / Vite (frontend), Python 3.12 / FastAPI / pytest (backend), Playwright (E2E), vitest (new — frontend unit tests).

**Spec:** `docs/superpowers/specs/2026-04-30-batch-upload-ux-design.md`

---

## File Structure

**New files:**
- `frontend/src/lib/pairing.ts` — pure pairing function and types
- `frontend/src/lib/pairing.test.ts` — vitest unit tests
- `frontend/vitest.config.ts` — vitest config (extends vite config)

**Modified files:**
- `frontend/package.json` — add vitest devDep + `test` script
- `frontend/src/components/BatchUpload.tsx` — full rewrite
- `frontend/src/index.css` — new class rules for preview & orphan UI
- `frontend/tests/e2e/batch-progress.spec.ts` — adapt to multi-file drop
- `backend/app/api/routes_verify.py` — replace JSON `/verify/batch` with multipart handler; drop `BatchItemPayload`/`BatchVerifyRequest`
- `backend/app/services/batch_manager.py` — `_verify_item_payload` reads `pdf_base64` from `form_payload`
- `backend/tests/integration/test_batch_verify_api.py` — rewrite to multipart
- `backend/tests/integration/test_batch_ws_progress.py` — adjust fixture shape
- `backend/tests/unit/test_batch_manager_retention.py` — adjust fixture shape

---

## Task 1: Internal worker contract — `pdf_base64` in `form_payload`

Why first: every test fixture below depends on the new shape. Worker change is isolated and small.

**Files:**
- Modify: `backend/app/services/batch_manager.py:220-260` (`_verify_item_payload`)
- Modify: `backend/tests/unit/test_batch_manager_retention.py`
- Modify: `backend/tests/integration/test_batch_ws_progress.py`

- [ ] **Step 1: Read the current `_verify_item_payload`**

Open `backend/app/services/batch_manager.py` and re-read the function at line 220 to confirm the change site.

- [ ] **Step 2: Add a failing unit test that asserts `pdf_base64` is decoded**

Append to `backend/tests/unit/test_batch_manager_retention.py`:

```python
import base64
from pathlib import Path

from app.services.batch_manager import _verify_item_payload

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def test_verify_item_payload_decodes_pdf_base64() -> None:
    pdf_bytes = (FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf").read_bytes()
    image_bytes = (FIXTURES_ROOT / "images/realistic_clean_lager.png").read_bytes()

    item_payload = {
        "form_payload": {"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")},
        "label_payloads": [{"image_base64": base64.b64encode(image_bytes).decode("ascii")}],
    }

    result = _verify_item_payload(item_payload)
    assert result["status"] in {"pass", "fail", "review_required"}
    assert "field_results" in result
```

- [ ] **Step 3: Run the new test — expected failure**

Run: `cd backend && pytest tests/unit/test_batch_manager_retention.py::test_verify_item_payload_decodes_pdf_base64 -v`
Expected: FAIL — current code does `json.dumps(form_payload)`, which produces a JSON-bytes blob that `extract_ground_truth` will JSON-parse, but the JSON dict `{"pdf_base64": "..."}` doesn't carry a real form, so `_build_ground_truth_fields` either raises or yields a degenerate ground-truth that fails matching.

- [ ] **Step 4: Apply the worker change**

In `backend/app/services/batch_manager.py`, replace the `form_bytes` line in `_verify_item_payload`:

```python
def _verify_item_payload(item_payload: dict[str, Any]) -> dict[str, Any]:
    form_payload = item_payload.get("form_payload")
    label_payloads = item_payload.get("label_payloads")
    if not isinstance(label_payloads, list) or not 1 <= len(label_payloads) <= 10:
        raise ValueError("label_payloads must include between 1 and 10 payloads")
    if not isinstance(form_payload, dict):
        raise ValueError("form_payload must be a JSON object")
    pdf_base64 = form_payload.get("pdf_base64")
    if not isinstance(pdf_base64, str) or not pdf_base64:
        raise ValueError("form_payload missing pdf_base64")

    form_bytes = bytearray(b64decode(pdf_base64))
    label_bytes_list = [bytearray(_coerce_label_bytes(label_payload)) for label_payload in label_payloads]
    extracted_payloads: list[Any] = []

    try:
        with forbid_disk_writes():
            ground_truth = extract_ground_truth(bytes(form_bytes))
            image_results: list[dict[str, Any]] = []
            for label_bytes in label_bytes_list:
                try:
                    preprocessed_image = preprocess_image(bytes(label_bytes))
                    ocr_text = TesseractEngine().extract_text(preprocessed_image)
                    extracted_fields = extract_fields(ocr_text)
                    field_results = match_fields(ground_truth, extracted_fields)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    image_results.append(_build_single_image_fallback_result())
                    continue

                extracted_payloads.extend([preprocessed_image, ocr_text, extracted_fields, field_results])
                image_results.append(
                    {
                        "status": _compute_overall_status(field_results),
                        "field_results": _serialize_field_results(field_results),
                    }
                )

        aggregate_field_results = _aggregate_field_results(image_results)
        return {
            "status": _compute_overall_status_from_serialized(aggregate_field_results),
            "field_results": aggregate_field_results,
            "image_results": image_results,
        }
    finally:
        clear_single_artifacts(form_bytes, *label_bytes_list, extracted_payloads)
```

(Only the validation block and `form_bytes` line change. The rest of the function body above is unchanged from the original — copy it from the file if in doubt.)

- [ ] **Step 5: Run the new test — should pass**

Run: `cd backend && pytest tests/unit/test_batch_manager_retention.py::test_verify_item_payload_decodes_pdf_base64 -v`
Expected: PASS.

- [ ] **Step 6: Update `test_batch_ws_progress.py` fixtures to new shape**

Open `backend/tests/integration/test_batch_ws_progress.py`. For every dict that builds `form_payload` as `{"brand_name": "...", "class_type": "...", ...}`, replace with:

```python
import base64
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def _b64_pdf(name: str) -> str:
    return base64.b64encode((FIXTURES_ROOT / "forms" / name).read_bytes()).decode("ascii")


def _b64_image(name: str) -> str:
    return base64.b64encode((FIXTURES_ROOT / "images" / name).read_bytes()).decode("ascii")
```

Then, in each test that previously called `create_batch_job([{"item_id": ..., "form_payload": {...}, "label_payloads": [...]}])`, rewrite as:

```python
create_batch_job([
    {
        "item_id": "item-1",
        "form_payload": {"pdf_base64": _b64_pdf("realistic_clean_lager_f510031.pdf")},
        "label_payloads": [{"image_base64": _b64_image("realistic_clean_lager.png")}],
    },
])
```

(Adjust pdf/image filenames per what each test was asserting. If a test was probing pass/fail behavior by sending mismatched fields, swap to a known-pass fixture (`realistic_clean_lager*`) for pass cases and `adversarial_*` for fail/review cases — these PDFs and images are already paired by name in the fixture directory.)

- [ ] **Step 7: Run the WS progress tests**

Run: `cd backend && pytest tests/integration/test_batch_ws_progress.py -v`
Expected: PASS.

- [ ] **Step 8: Update `test_batch_manager_retention.py` existing tests similarly**

Apply the same fixture replacement pattern to any existing tests in `test_batch_manager_retention.py` that build `form_payload` as a fields dict.

Run: `cd backend && pytest tests/unit/test_batch_manager_retention.py -v`
Expected: PASS.

- [ ] **Step 9: Verify nothing else regressed**

Run: `cd backend && pytest tests/ -v --ignore=tests/integration/test_batch_verify_api.py`
Expected: PASS (we ignore the API test because we'll rewrite it in Task 2).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/batch_manager.py \
        backend/tests/unit/test_batch_manager_retention.py \
        backend/tests/integration/test_batch_ws_progress.py
git commit -m "refactor(batch): worker reads pdf_base64 from form_payload"
```

---

## Task 2: Multipart `/verify/batch` endpoint

**Files:**
- Modify: `backend/app/api/routes_verify.py:22-78` (drop Pydantic models, replace `verify_batch`)
- Rewrite: `backend/tests/integration/test_batch_verify_api.py`

- [ ] **Step 1: Write a failing happy-path multipart test**

Replace the contents of `backend/tests/integration/test_batch_verify_api.py` with:

```python
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/labels"


def _wait_completed(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/verify/batch/{job_id}/report")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not complete within {timeout}s")


def test_batch_verify_multipart_happy_path() -> None:
    app = create_app()
    client = TestClient(app)

    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"

    mapping = json.dumps({
        "items": [
            {
                "item_id": "lager-1",
                "form_filename": pdf_path.name,
                "label_filenames": [image_path.name],
            }
        ]
    })

    with pdf_path.open("rb") as form_file, image_path.open("rb") as label_file:
        response = client.post(
            "/verify/batch",
            data={"mapping": mapping},
            files=[
                ("files", (pdf_path.name, form_file, "application/pdf")),
                ("files", (image_path.name, label_file, "image/png")),
            ],
        )

    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    report = _wait_completed(client, job_id)
    assert report["job_id"] == job_id
    assert report["summary"]["total"] == 1
```

- [ ] **Step 2: Run it — expected failure**

Run: `cd backend && pytest tests/integration/test_batch_verify_api.py::test_batch_verify_multipart_happy_path -v`
Expected: FAIL with 422 (FastAPI rejects multipart against the JSON-bound endpoint).

- [ ] **Step 3: Replace the endpoint**

In `backend/app/api/routes_verify.py`, remove these:
- `BatchItemPayload` Pydantic class (around lines 22-25)
- `BatchVerifyRequest` Pydantic class (around lines 28-29)
- The existing `@router.post("/verify/batch", ...) async def verify_batch(...)` handler

Replace with:

```python
from base64 import b64encode

from fastapi import Form

@router.post("/verify/batch", status_code=202)
async def verify_batch(
    files: list[UploadFile] = File(...),
    mapping: str = Form(...),
) -> dict[str, str]:
    try:
        mapping_doc = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid mapping")

    items_spec = mapping_doc.get("items") if isinstance(mapping_doc, dict) else None
    if not isinstance(items_spec, list) or not items_spec:
        raise HTTPException(status_code=400, detail="missing files or mapping")
    if len(items_spec) > 300:
        raise HTTPException(status_code=400, detail="batch exceeds 300 items")
    if not files:
        raise HTTPException(status_code=400, detail="missing files or mapping")

    file_bytes_by_name: dict[str, bytes] = {}
    for upload in files:
        if upload.filename is None:
            raise HTTPException(status_code=400, detail="file without filename")
        file_bytes_by_name[upload.filename] = await upload.read()

    seen_ids: set[str] = set()
    items: list[dict[str, Any]] = []
    for index, item_spec in enumerate(items_spec):
        if not isinstance(item_spec, dict):
            raise HTTPException(status_code=400, detail=f"item {index} must be a JSON object")

        raw_item_id = item_spec.get("item_id")
        item_id = raw_item_id if isinstance(raw_item_id, str) and raw_item_id.strip() else f"item-{index + 1}"
        if item_id in seen_ids:
            raise HTTPException(status_code=400, detail=f"duplicate item_id: {item_id}")
        seen_ids.add(item_id)

        form_filename = item_spec.get("form_filename")
        label_filenames = item_spec.get("label_filenames")
        if not isinstance(form_filename, str):
            raise HTTPException(status_code=400, detail=f"item {item_id} missing form_filename")
        if not isinstance(label_filenames, list) or not 1 <= len(label_filenames) <= 10:
            raise HTTPException(status_code=400, detail=f"item {item_id} must have 1-10 labels")
        if form_filename not in file_bytes_by_name:
            raise HTTPException(status_code=400, detail=f"missing file: {form_filename}")
        for label_filename in label_filenames:
            if not isinstance(label_filename, str):
                raise HTTPException(status_code=400, detail=f"item {item_id} has non-string label filename")
            if label_filename not in file_bytes_by_name:
                raise HTTPException(status_code=400, detail=f"missing file: {label_filename}")

        items.append({
            "item_id": item_id,
            "form_payload": {
                "pdf_base64": b64encode(file_bytes_by_name[form_filename]).decode("ascii"),
            },
            "label_payloads": [
                {"image_base64": b64encode(file_bytes_by_name[name]).decode("ascii")}
                for name in label_filenames
            ],
        })

    job_id = create_batch_job(items)
    return {"job_id": job_id}
```

Make sure `from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile` is at the top (add `Form` if missing).

- [ ] **Step 4: Run the happy-path test — should pass**

Run: `cd backend && pytest tests/integration/test_batch_verify_api.py::test_batch_verify_multipart_happy_path -v`
Expected: PASS.

- [ ] **Step 5: Add validation tests**

Append to `backend/tests/integration/test_batch_verify_api.py`:

```python
def _post(client: TestClient, mapping: str, files: list[tuple]) -> "Response":
    return client.post("/verify/batch", data={"mapping": mapping}, files=files)


def test_batch_verify_invalid_mapping_json() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    with pdf_path.open("rb") as f:
        response = _post(client, "{not json", [("files", (pdf_path.name, f, "application/pdf"))])
    assert response.status_code == 400
    assert "invalid mapping" in response.json()["detail"].lower()


def test_batch_verify_missing_referenced_file() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"

    mapping = json.dumps({
        "items": [{
            "item_id": "x",
            "form_filename": pdf_path.name,
            "label_filenames": ["does-not-exist.png"],
        }]
    })

    with pdf_path.open("rb") as form_file, image_path.open("rb") as label_file:
        response = _post(
            client,
            mapping,
            [
                ("files", (pdf_path.name, form_file, "application/pdf")),
                ("files", (image_path.name, label_file, "image/png")),
            ],
        )
    assert response.status_code == 400
    assert "does-not-exist.png" in response.json()["detail"]


def test_batch_verify_duplicate_item_id() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image_path = FIXTURES_ROOT / "images/realistic_clean_lager.png"

    mapping = json.dumps({
        "items": [
            {"item_id": "dup", "form_filename": pdf_path.name, "label_filenames": [image_path.name]},
            {"item_id": "dup", "form_filename": pdf_path.name, "label_filenames": [image_path.name]},
        ]
    })

    with pdf_path.open("rb") as f1, image_path.open("rb") as f2:
        response = _post(client, mapping, [
            ("files", (pdf_path.name, f1, "application/pdf")),
            ("files", (image_path.name, f2, "image/png")),
        ])
    assert response.status_code == 400
    assert "duplicate item_id" in response.json()["detail"]


def test_batch_verify_label_count_out_of_range() -> None:
    app = create_app()
    client = TestClient(app)
    pdf_path = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    mapping = json.dumps({
        "items": [{"item_id": "x", "form_filename": pdf_path.name, "label_filenames": []}]
    })
    with pdf_path.open("rb") as f:
        response = _post(client, mapping, [("files", (pdf_path.name, f, "application/pdf"))])
    assert response.status_code == 400
    assert "1-10 labels" in response.json()["detail"]


def test_batch_verify_one_malformed_pdf_yields_review_required() -> None:
    """Per-item parse failure does NOT reject the batch; that item ends review_required."""
    app = create_app()
    client = TestClient(app)
    good_pdf = FIXTURES_ROOT / "forms/realistic_clean_lager_f510031.pdf"
    image = FIXTURES_ROOT / "images/realistic_clean_lager.png"
    bad_pdf_bytes = b"this is not a pdf"

    mapping = json.dumps({
        "items": [
            {"item_id": "good", "form_filename": good_pdf.name, "label_filenames": [image.name]},
            {"item_id": "bad", "form_filename": "broken.pdf", "label_filenames": [image.name]},
        ]
    })

    with good_pdf.open("rb") as g, image.open("rb") as i:
        response = client.post(
            "/verify/batch",
            data={"mapping": mapping},
            files=[
                ("files", (good_pdf.name, g, "application/pdf")),
                ("files", (image.name, i, "image/png")),
                ("files", ("broken.pdf", bad_pdf_bytes, "application/pdf")),
            ],
        )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    report = _wait_completed(client, job_id)
    assert report["summary"]["total"] == 2
    statuses = {item["item_id"]: item["overall_status"] for item in report["items"]}
    assert statuses["bad"] == "review_required"
```

- [ ] **Step 6: Run all batch API tests — should pass**

Run: `cd backend && pytest tests/integration/test_batch_verify_api.py -v`
Expected: All PASS.

- [ ] **Step 7: Verify backend suite is green**

Run: `cd backend && pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes_verify.py backend/tests/integration/test_batch_verify_api.py
git commit -m "feat(api): multipart /verify/batch with intake validation"
```

---

## Task 3: Set up vitest for the frontend

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`

- [ ] **Step 1: Install vitest as a devDependency**

```bash
cd frontend && npm install --save-dev vitest
```

Expected: `package.json` and `package-lock.json` updated.

- [ ] **Step 2: Add a `test` script in `frontend/package.json`**

In the `scripts` block, add:

```json
"test": "vitest run",
"test:watch": "vitest"
```

Final scripts block:

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:e2e": "playwright test"
}
```

- [ ] **Step 3: Create `frontend/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

- [ ] **Step 4: Add a smoke test to confirm vitest runs**

Create `frontend/src/lib/_smoke.test.ts`:

```ts
import { describe, expect, it } from "vitest";

describe("vitest smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 5: Run vitest**

Run: `cd frontend && npm test`
Expected: 1 test passes.

- [ ] **Step 6: Delete the smoke test**

```bash
rm frontend/src/lib/_smoke.test.ts
```

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts
git commit -m "chore(frontend): set up vitest for unit tests"
```

---

## Task 4: Pairing engine (`pairing.ts`) with full unit-test coverage

**Files:**
- Create: `frontend/src/lib/pairing.ts`
- Create: `frontend/src/lib/pairing.test.ts`

- [ ] **Step 1: Write the failing test file with comprehensive cases**

Create `frontend/src/lib/pairing.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { pairFiles, type DroppedFile } from "./pairing";

function makeFile(relativePath: string): DroppedFile {
  const filename = relativePath.split("/").pop() ?? relativePath;
  return {
    file: new File([new Uint8Array([0])], filename),
    relativePath,
  };
}

describe("pairFiles — flat drop, stem-prefix matching", () => {
  it("pairs each PDF with its stem-prefixed images", () => {
    const result = pairFiles([
      makeFile("widget-001.pdf"),
      makeFile("widget-001-front.png"),
      makeFile("widget-001-back.jpg"),
      makeFile("widget-002.pdf"),
      makeFile("widget-002.png"),
    ]);
    expect(result.items).toHaveLength(2);
    expect(result.orphanPdfs).toHaveLength(0);
    expect(result.orphanImages).toHaveLength(0);
    const firstItem = result.items.find((it) => it.itemId === "widget-001")!;
    expect(firstItem.labels.map((l) => l.relativePath).sort()).toEqual([
      "widget-001-back.jpg",
      "widget-001-front.png",
    ]);
  });

  it("longest-prefix-wins prevents shorter-stem PDF from stealing", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-2.pdf"),
      makeFile("widget-2-front.png"),
      makeFile("widget-front.png"),
    ]);
    const longerItem = result.items.find((it) => it.itemId === "widget-2")!;
    const shorterItem = result.items.find((it) => it.itemId === "widget")!;
    expect(longerItem.labels.map((l) => l.relativePath)).toEqual(["widget-2-front.png"]);
    expect(shorterItem.labels.map((l) => l.relativePath)).toEqual(["widget-front.png"]);
  });

  it("image with no matching PDF stem becomes an orphan image", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-front.png"),
      makeFile("unrelated.png"),
    ]);
    expect(result.items).toHaveLength(1);
    expect(result.orphanImages.map((i) => i.relativePath)).toEqual(["unrelated.png"]);
  });

  it("PDF with no matching images becomes an orphan PDF", () => {
    const result = pairFiles([makeFile("alone.pdf"), makeFile("other.pdf"), makeFile("other-front.png")]);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].itemId).toBe("other");
    expect(result.orphanPdfs.map((p) => p.relativePath)).toEqual(["alone.pdf"]);
  });
});

describe("pairFiles — folder-as-form rule", () => {
  it("emits one item per subfolder when subfolder has exactly one PDF and >=1 image", () => {
    const result = pairFiles([
      makeFile("batch/widget-001/form.pdf"),
      makeFile("batch/widget-001/front.png"),
      makeFile("batch/widget-001/back.png"),
      makeFile("batch/widget-002/form.pdf"),
      makeFile("batch/widget-002/wrap.png"),
    ]);
    expect(result.items).toHaveLength(2);
    expect(result.orphanPdfs).toHaveLength(0);
    expect(result.orphanImages).toHaveLength(0);
  });

  it("subfolder with 2+ PDFs falls through to stem matching", () => {
    const result = pairFiles([
      makeFile("batch/widget-a.pdf"),
      makeFile("batch/widget-b.pdf"),
      makeFile("batch/widget-a-front.png"),
      makeFile("batch/widget-b-back.png"),
    ]);
    expect(result.items).toHaveLength(2);
    const a = result.items.find((it) => it.itemId === "widget-a")!;
    const b = result.items.find((it) => it.itemId === "widget-b")!;
    expect(a.labels.map((l) => l.relativePath)).toEqual(["batch/widget-a-front.png"]);
    expect(b.labels.map((l) => l.relativePath)).toEqual(["batch/widget-b-back.png"]);
  });

  it("subfolder with PDF only (no images) yields orphan PDF", () => {
    const result = pairFiles([makeFile("batch/lonely/form.pdf")]);
    expect(result.items).toHaveLength(0);
    expect(result.orphanPdfs).toHaveLength(1);
  });
});

describe("pairFiles — flagging and validation", () => {
  it("flags items with more than 10 matched labels", () => {
    const files = [makeFile("widget.pdf")];
    for (let i = 0; i < 11; i++) {
      files.push(makeFile(`widget-${i}.png`));
    }
    const result = pairFiles(files);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].labels).toHaveLength(11);
    expect(result.items[0].isOverLabelLimit).toBe(true);
  });

  it("filters unsupported extensions into ignoredFiles", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-front.png"),
      makeFile("notes.txt"),
      makeFile("data.csv"),
    ]);
    expect(result.ignoredFiles.map((f) => f.relativePath).sort()).toEqual(["data.csv", "notes.txt"]);
    expect(result.items).toHaveLength(1);
  });

  it("dedupes duplicate item IDs across buckets with -2/-3 suffix", () => {
    const result = pairFiles([
      makeFile("a/widget.pdf"),
      makeFile("a/widget-front.png"),
      makeFile("b/widget.pdf"),
      makeFile("b/widget-back.png"),
    ]);
    const ids = result.items.map((it) => it.itemId).sort();
    expect(ids).toEqual(["widget", "widget-2"]);
  });
});
```

- [ ] **Step 2: Run the test file — expected failure (module not found)**

Run: `cd frontend && npm test -- src/lib/pairing.test.ts`
Expected: FAIL — `Cannot find module './pairing'`.

- [ ] **Step 3: Create `frontend/src/lib/pairing.ts`**

```ts
export type DroppedFile = {
  file: File;
  relativePath: string;
};

export type PairedItem = {
  itemId: string;
  pdf: DroppedFile;
  labels: DroppedFile[];
  isOverLabelLimit: boolean;
};

export type PairingResult = {
  items: PairedItem[];
  orphanPdfs: DroppedFile[];
  orphanImages: DroppedFile[];
  ignoredFiles: DroppedFile[];
};

const PDF_EXTENSIONS = new Set([".pdf"]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);

function getFilename(relativePath: string): string {
  const slashIndex = relativePath.lastIndexOf("/");
  return slashIndex >= 0 ? relativePath.slice(slashIndex + 1) : relativePath;
}

function getExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
}

function getStem(filename: string): string {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(0, dotIndex) : filename;
}

function getParentPath(relativePath: string): string {
  const slashIndex = relativePath.lastIndexOf("/");
  return slashIndex >= 0 ? relativePath.slice(0, slashIndex) : "";
}

function isPdf(file: DroppedFile): boolean {
  return PDF_EXTENSIONS.has(getExtension(getFilename(file.relativePath)));
}

function isImage(file: DroppedFile): boolean {
  return IMAGE_EXTENSIONS.has(getExtension(getFilename(file.relativePath)));
}

export function pairFiles(input: DroppedFile[]): PairingResult {
  const ignoredFiles: DroppedFile[] = [];
  const supported: DroppedFile[] = [];
  for (const f of input) {
    if (isPdf(f) || isImage(f)) {
      supported.push(f);
    } else {
      ignoredFiles.push(f);
    }
  }

  const buckets = new Map<string, DroppedFile[]>();
  for (const f of supported) {
    const parent = getParentPath(f.relativePath);
    const list = buckets.get(parent) ?? [];
    list.push(f);
    buckets.set(parent, list);
  }

  const items: PairedItem[] = [];
  const orphanPdfs: DroppedFile[] = [];
  const orphanImages: DroppedFile[] = [];

  for (const bucketFiles of buckets.values()) {
    const pdfs = bucketFiles.filter(isPdf);
    const images = bucketFiles.filter(isImage);

    // Folder-as-form rule
    if (pdfs.length === 1 && images.length >= 1) {
      items.push(makeItem(pdfs[0], images));
      continue;
    }

    // Stem-prefix matching with longest-prefix-wins
    const slots = pdfs.map((pdf) => ({ pdf, labels: [] as DroppedFile[] }));
    for (const image of images) {
      const imageStem = getStem(getFilename(image.relativePath));
      let bestSlot: { pdf: DroppedFile; labels: DroppedFile[] } | null = null;
      let bestStemLength = -1;
      let tied = false;
      for (const slot of slots) {
        const pdfStem = getStem(getFilename(slot.pdf.relativePath));
        if (imageStem.startsWith(pdfStem)) {
          if (pdfStem.length > bestStemLength) {
            bestSlot = slot;
            bestStemLength = pdfStem.length;
            tied = false;
          } else if (pdfStem.length === bestStemLength) {
            tied = true;
          }
        }
      }
      if (bestSlot !== null && !tied) {
        bestSlot.labels.push(image);
      } else {
        orphanImages.push(image);
      }
    }

    for (const slot of slots) {
      if (slot.labels.length === 0) {
        orphanPdfs.push(slot.pdf);
      } else {
        items.push(makeItem(slot.pdf, slot.labels));
      }
    }
  }

  // Deduplicate item IDs
  const seenIds = new Set<string>();
  for (const item of items) {
    const baseId = item.itemId;
    let candidate = baseId;
    let suffix = 1;
    while (seenIds.has(candidate)) {
      suffix += 1;
      candidate = `${baseId}-${suffix}`;
    }
    item.itemId = candidate;
    seenIds.add(candidate);
  }

  return { items, orphanPdfs, orphanImages, ignoredFiles };
}

function makeItem(pdf: DroppedFile, labels: DroppedFile[]): PairedItem {
  const stem = getStem(getFilename(pdf.relativePath));
  return {
    itemId: stem,
    pdf,
    labels,
    isOverLabelLimit: labels.length > 10,
  };
}
```

- [ ] **Step 4: Run the test file — should pass**

Run: `cd frontend && npm test -- src/lib/pairing.test.ts`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/pairing.ts frontend/src/lib/pairing.test.ts
git commit -m "feat(frontend): pairing engine for batch upload"
```

---

## Task 5: BatchUpload — drop zone & file collection

This task replaces only the **upload region** of the component with a working drop zone that runs pairing and stores state. Preview rendering and orphan tray come in Tasks 6–7. The existing job-progress / report-download UI below stays intact for now (it'll be wired up in Task 8).

**Files:**
- Modify: `frontend/src/components/BatchUpload.tsx`
- Modify: `frontend/src/index.css` (add `.batch-drop-zone`, `.batch-summary` rules)

- [ ] **Step 1: Replace `BatchUpload.tsx` skeleton**

Open `frontend/src/components/BatchUpload.tsx` and replace its contents:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";

import { apiUrl, batchEventsWebSocketUrl, unreachableApiHint } from "../apiClient";
import { pairFiles, type DroppedFile, type PairingResult } from "../lib/pairing";

type BatchReportResponse = {
  job_id: string;
  status: "queued" | "running" | "completed" | "completed_with_failures";
  summary: { processed: number; total: number; pass: number; fail: number; review_required: number };
  items: Array<Record<string, unknown>>;
};

type WorkingState = {
  fileById: Map<string, DroppedFile>;
  itemPdfFileId: Map<string, string>; // itemId -> pdf fileId
  itemLabelFileIds: Map<string, string[]>;
  itemOverLimit: Map<string, boolean>;
  orphanPdfFileIds: string[];
  orphanImageFileIds: string[];
  ignoredFileIds: string[];
};

const EMPTY_STATE: WorkingState = {
  fileById: new Map(),
  itemPdfFileId: new Map(),
  itemLabelFileIds: new Map(),
  itemOverLimit: new Map(),
  orphanPdfFileIds: [],
  orphanImageFileIds: [],
  ignoredFileIds: [],
};

let nextFileId = 0;
function generateFileId(): string {
  nextFileId += 1;
  return `f${nextFileId}`;
}

function normalizeRelativePath(file: File): string {
  // webkitRelativePath is set when user picks a folder; otherwise empty
  const wkrp = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath ?? "";
  if (wkrp) return wkrp;
  return file.name;
}

function mergePairing(prev: WorkingState, addition: PairingResult, fileIds: Map<DroppedFile, string>): WorkingState {
  const next: WorkingState = {
    fileById: new Map(prev.fileById),
    itemPdfFileId: new Map(prev.itemPdfFileId),
    itemLabelFileIds: new Map(prev.itemLabelFileIds),
    itemOverLimit: new Map(prev.itemOverLimit),
    orphanPdfFileIds: [...prev.orphanPdfFileIds],
    orphanImageFileIds: [...prev.orphanImageFileIds],
    ignoredFileIds: [...prev.ignoredFileIds],
  };

  for (const [df, id] of fileIds) {
    next.fileById.set(id, df);
  }

  // Dedupe item IDs against existing ones
  const usedIds = new Set(next.itemPdfFileId.keys());
  for (const item of addition.items) {
    let candidate = item.itemId;
    let suffix = 1;
    while (usedIds.has(candidate)) {
      suffix += 1;
      candidate = `${item.itemId}-${suffix}`;
    }
    usedIds.add(candidate);
    next.itemPdfFileId.set(candidate, fileIds.get(item.pdf)!);
    next.itemLabelFileIds.set(
      candidate,
      item.labels.map((l) => fileIds.get(l)!),
    );
    next.itemOverLimit.set(candidate, item.isOverLabelLimit);
  }

  for (const orphan of addition.orphanPdfs) {
    next.orphanPdfFileIds.push(fileIds.get(orphan)!);
  }
  for (const orphan of addition.orphanImages) {
    next.orphanImageFileIds.push(fileIds.get(orphan)!);
  }
  for (const ignored of addition.ignoredFiles) {
    next.ignoredFileIds.push(fileIds.get(ignored)!);
  }

  return next;
}

function BatchUpload() {
  const [state, setState] = useState<WorkingState>(EMPTY_STATE);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const filesInputRef = useRef<HTMLInputElement | null>(null);

  const summary = useMemo(() => {
    let pdfCount = 0;
    let imageCount = 0;
    for (const f of state.fileById.values()) {
      const ext = f.relativePath.toLowerCase();
      if (ext.endsWith(".pdf")) pdfCount += 1;
      else if (ext.match(/\.(png|jpe?g|webp)$/)) imageCount += 1;
    }
    return { total: state.fileById.size, pdfCount, imageCount };
  }, [state.fileById]);

  const ingestFiles = (rawFiles: FileList | File[]) => {
    setErrorMessage(null);
    const droppedFiles: DroppedFile[] = [];
    const fileIds = new Map<DroppedFile, string>();
    for (const f of Array.from(rawFiles)) {
      const df: DroppedFile = { file: f, relativePath: normalizeRelativePath(f) };
      droppedFiles.push(df);
      fileIds.set(df, generateFileId());
    }
    const result = pairFiles(droppedFiles);
    setState((prev) => mergePairing(prev, result, fileIds));
  };

  const onFolderPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files;
    if (files) ingestFiles(files);
    event.currentTarget.value = ""; // reset so re-picking same folder still fires
  };

  const onFilesPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files;
    if (files) ingestFiles(files);
    event.currentTarget.value = "";
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const items = event.dataTransfer.items;
    if (items && items.length > 0) {
      const collected: File[] = [];
      const promises: Promise<void>[] = [];
      for (const it of Array.from(items)) {
        const entry = (it as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntry | null }).webkitGetAsEntry?.();
        if (entry) {
          promises.push(walkEntry(entry, "", collected));
        } else {
          const file = it.getAsFile();
          if (file) collected.push(file);
        }
      }
      Promise.all(promises).then(() => ingestFiles(collected));
    } else if (event.dataTransfer.files) {
      ingestFiles(event.dataTransfer.files);
    }
  };

  return (
    <section aria-label="Batch upload">
      <h2>Batch Check</h2>

      <div
        className="batch-drop-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        {state.fileById.size === 0 ? (
          <span className="placeholder">Drop a folder or files, or use the buttons below</span>
        ) : (
          <span className="batch-summary">
            {summary.total} files: {summary.pdfCount} PDFs, {summary.imageCount} images
            {state.ignoredFileIds.length > 0 ? ` (${state.ignoredFileIds.length} ignored)` : ""}
          </span>
        )}
      </div>

      <div className="batch-pickers">
        <button type="button" onClick={() => folderInputRef.current?.click()}>Pick folder</button>
        <button type="button" onClick={() => filesInputRef.current?.click()}>Pick files</button>
        <input
          ref={folderInputRef}
          type="file"
          // @ts-expect-error webkitdirectory is non-standard but supported by Chrome/Edge/Firefox
          webkitdirectory=""
          multiple
          hidden
          onChange={onFolderPicked}
        />
        <input
          ref={filesInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          hidden
          onChange={onFilesPicked}
        />
      </div>

      {errorMessage != null ? <div className="error-message" role="alert">{errorMessage}</div> : null}
    </section>
  );
}

async function walkEntry(entry: FileSystemEntry, parentPath: string, out: File[]): Promise<void> {
  if (entry.isFile) {
    const fileEntry = entry as FileSystemFileEntry;
    return new Promise((resolve) => {
      fileEntry.file((file) => {
        const path = parentPath ? `${parentPath}/${file.name}` : file.name;
        Object.defineProperty(file, "webkitRelativePath", { value: path });
        out.push(file);
        resolve();
      });
    });
  }
  if (entry.isDirectory) {
    const dirEntry = entry as FileSystemDirectoryEntry;
    const reader = dirEntry.createReader();
    const subPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
    return new Promise((resolve) => {
      const collected: FileSystemEntry[] = [];
      const readBatch = () => {
        reader.readEntries(async (entries) => {
          if (entries.length === 0) {
            await Promise.all(collected.map((e) => walkEntry(e, subPath, out)));
            resolve();
          } else {
            collected.push(...entries);
            readBatch();
          }
        });
      };
      readBatch();
    });
  }
}

export default BatchUpload;
```

- [ ] **Step 2: Add minimal CSS rules**

Append to `frontend/src/index.css`:

```css
.batch-drop-zone {
  border: 2px dashed var(--color-border, #ccc);
  padding: var(--spacing-lg, 1.5rem);
  text-align: center;
  border-radius: 8px;
  margin-bottom: var(--spacing-md, 1rem);
}
.batch-pickers {
  display: flex;
  gap: var(--spacing-sm, 0.5rem);
  margin-bottom: var(--spacing-md, 1rem);
}
```

- [ ] **Step 3: Run the dev server and confirm files can be picked**

Run: `cd frontend && npm run dev`

In a browser, open the dev URL, click "Pick files", select a PDF + a few images, and verify the drop-zone summary shows correct counts. Click "Pick folder" and select the `tests/fixtures/labels/` directory; verify counts include all files.

(Manual verification only — no automated test for this step. The pairing logic is already covered in Task 4.)

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BatchUpload.tsx frontend/src/index.css
git commit -m "feat(frontend): batch upload drop zone with auto-pairing"
```

---

## Task 6: BatchUpload — paired items list with remove-chip

**Files:**
- Modify: `frontend/src/components/BatchUpload.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Add the `removeLabelFromItem` helper inside `BatchUpload`**

Just above the `return` statement in `BatchUpload.tsx`:

```tsx
const removeLabelFromItem = (itemId: string, labelId: string) => {
  setState((prev) => {
    const newLabelIds = (prev.itemLabelFileIds.get(itemId) ?? []).filter((id) => id !== labelId);
    const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
    newItemLabelFileIds.set(itemId, newLabelIds);
    const newItemOverLimit = new Map(prev.itemOverLimit);
    newItemOverLimit.set(itemId, newLabelIds.length > 10);
    return {
      ...prev,
      itemLabelFileIds: newItemLabelFileIds,
      itemOverLimit: newItemOverLimit,
      orphanImageFileIds: [...prev.orphanImageFileIds, labelId],
    };
  });
};
```

- [ ] **Step 2: Add the paired-items list rendering**

In `BatchUpload.tsx`, inside the `return`, after the `</div>` closing `.batch-pickers` and before `errorMessage`, add:

```tsx
{state.itemPdfFileId.size > 0 ? (
  <div className="batch-items">
    <h3>Paired items</h3>
    {Array.from(state.itemPdfFileId.keys()).map((itemId) => {
      const pdfId = state.itemPdfFileId.get(itemId)!;
      const labelIds = state.itemLabelFileIds.get(itemId) ?? [];
      const overLimit = state.itemOverLimit.get(itemId) ?? false;
      const pdfFile = state.fileById.get(pdfId)!;
      return (
        <div className={`batch-item-row${overLimit ? " over-limit" : ""}`} key={itemId}>
          <div className="batch-item-pdf">{pdfFile.relativePath}</div>
          <div className="batch-item-labels">
            {labelIds.map((lid) => {
              const f = state.fileById.get(lid)!;
              return (
                <span key={lid} className="label-chip">
                  {f.relativePath}
                  {overLimit ? (
                    <button type="button" aria-label={`Remove ${f.relativePath}`} onClick={() => removeLabelFromItem(itemId, lid)}>×</button>
                  ) : null}
                </span>
              );
            })}
            <span className={`label-count-badge${overLimit ? " over-limit" : ""}`}>{labelIds.length}/10</span>
          </div>
        </div>
      );
    })}
  </div>
) : null}
```

- [ ] **Step 3: Add CSS for the items list**

Append to `frontend/src/index.css`:

```css
.batch-items { margin-top: var(--spacing-md, 1rem); }
.batch-item-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--color-border, #eee);
}
.batch-item-row.over-limit { background: #fff5f5; }
.batch-item-pdf { font-weight: 600; }
.batch-item-labels { display: flex; flex-wrap: wrap; gap: 0.25rem; }
.label-chip {
  background: #eef;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  font-size: 0.85rem;
}
.label-chip button { margin-left: 0.25rem; background: transparent; border: 0; cursor: pointer; }
.label-count-badge { color: green; }
.label-count-badge.over-limit { color: #c00; font-weight: 600; }
```

- [ ] **Step 4: Manually verify in the dev server**

Run: `cd frontend && npm run dev`. Drop `tests/fixtures/labels/forms/realistic_clean_lager_f510031.pdf` together with `tests/fixtures/labels/images/realistic_clean_lager.png`. Verify:
- One item row appears with `realistic_clean_lager_f510031` (this is the PDF stem; image stem `realistic_clean_lager` does NOT prefix-match → orphan image expected; this confirms strict matching).

**Note** for the engineer: that fixture pair will NOT auto-pair under strict prefix matching (PDF stem is longer than image stem). To validate the happy-rendering path manually, drop two files where the image filename is prefixed by the PDF stem — e.g., create `widget.pdf` and `widget-front.png` via the Pick-files dialog with renamed copies, OR exercise this fully via Task 9's E2E.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BatchUpload.tsx frontend/src/index.css
git commit -m "feat(frontend): batch upload paired-items list with remove-chip"
```

---

## Task 7: BatchUpload — orphan tray with discard & attach

**Files:**
- Modify: `frontend/src/components/BatchUpload.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Add state mutators for orphan actions**

Inside `BatchUpload`, just above `return`, add:

```tsx
const discardOrphanPdf = (fileId: string) => {
  setState((prev) => {
    const fileById = new Map(prev.fileById);
    fileById.delete(fileId);
    return {
      ...prev,
      fileById,
      orphanPdfFileIds: prev.orphanPdfFileIds.filter((id) => id !== fileId),
    };
  });
};

const discardOrphanImage = (fileId: string) => {
  setState((prev) => {
    const fileById = new Map(prev.fileById);
    fileById.delete(fileId);
    return {
      ...prev,
      fileById,
      orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== fileId),
    };
  });
};

const attachOrphanImageToItem = (imageFileId: string, itemId: string) => {
  setState((prev) => {
    if (!prev.itemPdfFileId.has(itemId)) return prev;
    const newLabelIds = [...(prev.itemLabelFileIds.get(itemId) ?? []), imageFileId];
    const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
    newItemLabelFileIds.set(itemId, newLabelIds);
    const newItemOverLimit = new Map(prev.itemOverLimit);
    newItemOverLimit.set(itemId, newLabelIds.length > 10);
    return {
      ...prev,
      itemLabelFileIds: newItemLabelFileIds,
      itemOverLimit: newItemOverLimit,
      orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== imageFileId),
    };
  });
};

const promoteOrphanPdfWithImage = (pdfFileId: string, imageFileId: string) => {
  setState((prev) => {
    if (!prev.fileById.has(pdfFileId) || !prev.fileById.has(imageFileId)) return prev;
    const pdfFile = prev.fileById.get(pdfFileId)!;
    const filename = pdfFile.relativePath.split("/").pop() ?? pdfFile.relativePath;
    const baseId = filename.replace(/\.[^.]+$/, "");
    let candidate = baseId;
    let suffix = 1;
    while (prev.itemPdfFileId.has(candidate)) {
      suffix += 1;
      candidate = `${baseId}-${suffix}`;
    }
    const newItemPdfFileId = new Map(prev.itemPdfFileId);
    newItemPdfFileId.set(candidate, pdfFileId);
    const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
    newItemLabelFileIds.set(candidate, [imageFileId]);
    const newItemOverLimit = new Map(prev.itemOverLimit);
    newItemOverLimit.set(candidate, false);
    return {
      ...prev,
      itemPdfFileId: newItemPdfFileId,
      itemLabelFileIds: newItemLabelFileIds,
      itemOverLimit: newItemOverLimit,
      orphanPdfFileIds: prev.orphanPdfFileIds.filter((id) => id !== pdfFileId),
      orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== imageFileId),
    };
  });
};
```

- [ ] **Step 2: Add drop targets on paired item rows (update Task 6 JSX)**

Find the `<div className={...batch-item-row...}` from Task 6 and add `onDragOver` + `onDrop` props so orphan images can be dragged directly onto a paired item:

```tsx
<div
  className={`batch-item-row${overLimit ? " over-limit" : ""}`}
  key={itemId}
  onDragOver={(e) => e.preventDefault()}
  onDrop={(e) => {
    e.preventDefault();
    const droppedId = e.dataTransfer.getData("text/orphan-image-id");
    if (droppedId) attachOrphanImageToItem(droppedId, itemId);
  }}
>
```

(Replace the existing opening `<div className={...}>` for each row. The rest of the row JSX is unchanged.)

- [ ] **Step 4: Render the orphan tray**

After the `</div>` closing `.batch-items` block, add:

```tsx
{(state.orphanPdfFileIds.length + state.orphanImageFileIds.length) > 0 ? (
  <div className="orphan-tray">
    <h3>Needs review ({state.orphanPdfFileIds.length + state.orphanImageFileIds.length})</h3>
    {state.orphanPdfFileIds.length > 0 ? (
      <div className="orphan-section">
        <h4>Orphan PDFs</h4>
        {state.orphanPdfFileIds.map((id) => {
          const f = state.fileById.get(id)!;
          return (
            <div
              className="orphan-row"
              key={id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const droppedId = e.dataTransfer.getData("text/orphan-image-id");
                if (droppedId) promoteOrphanPdfWithImage(id, droppedId);
              }}
            >
              <span>{f.relativePath}</span>
              <button type="button" onClick={() => discardOrphanPdf(id)}>Discard</button>
              <select
                aria-label={`Attach images to ${f.relativePath}`}
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    promoteOrphanPdfWithImage(id, e.target.value);
                  }
                }}
              >
                <option value="">Attach orphan image…</option>
                {state.orphanImageFileIds.map((imgId) => (
                  <option key={imgId} value={imgId}>
                    {state.fileById.get(imgId)!.relativePath}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    ) : null}
    {state.orphanImageFileIds.length > 0 ? (
      <div className="orphan-section">
        <h4>Orphan images</h4>
        {state.orphanImageFileIds.map((id) => {
          const f = state.fileById.get(id)!;
          return (
            <div
              className="orphan-row"
              key={id}
              draggable
              onDragStart={(e) => e.dataTransfer.setData("text/orphan-image-id", id)}
            >
              <span>{f.relativePath}</span>
              <button type="button" onClick={() => discardOrphanImage(id)}>Discard</button>
              <select
                aria-label={`Attach ${f.relativePath} to item`}
                value=""
                onChange={(e) => {
                  if (e.target.value) attachOrphanImageToItem(id, e.target.value);
                }}
              >
                <option value="">Attach to item…</option>
                {Array.from(state.itemPdfFileId.keys()).map((itemId) => (
                  <option key={itemId} value={itemId}>
                    {itemId}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    ) : null}
  </div>
) : null}
```

(The `<select>` controls give a non-drag fallback that's much easier to E2E than HTML5 drag-drop, while preserving drag-drop for desktop users.)

- [ ] **Step 5: CSS for the orphan tray**

Append to `frontend/src/index.css`:

```css
.orphan-tray {
  border-top: 2px solid var(--color-border, #eee);
  margin-top: var(--spacing-md, 1rem);
  padding-top: var(--spacing-md, 1rem);
}
.orphan-section { margin-bottom: var(--spacing-sm, 0.5rem); }
.orphan-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem;
}
.orphan-row span { flex: 1; }
```

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Manual smoke check**

Run dev server, drop a PDF that won't match anything (e.g., `lonely.pdf`) plus a stranger image (`unrelated.png`). Verify:
- Both appear in the orphan tray
- "Discard" removes them
- The two `<select>` controls list the right options
- Picking an image from the orphan PDF row creates a new item row above
- Dragging an orphan image onto a paired item row attaches it

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/BatchUpload.tsx frontend/src/index.css
git commit -m "feat(frontend): orphan tray with discard and attach"
```

---

## Task 8: BatchUpload — Start gating + multipart submit + wire job-progress UI

**Files:**
- Modify: `frontend/src/components/BatchUpload.tsx`

- [ ] **Step 1: Add submission state hooks at the TOP of `BatchUpload` (with the other state declarations)**

In `BatchUpload.tsx`, directly after the existing `const [errorMessage, ...]` and `const folderInputRef` declarations (and before `ingestFiles`), add these hook calls:

```tsx
const [isSubmitting, setIsSubmitting] = useState(false);
const [isDownloading, setIsDownloading] = useState(false);
const [jobId, setJobId] = useState<string | null>(null);
const [progressText, setProgressText] = useState<string | null>(null);
const [reportReady, setReportReady] = useState(false);
const websocketRef = useRef<WebSocket | null>(null);

useEffect(() => () => {
  websocketRef.current?.close();
  websocketRef.current = null;
}, []);
```

React hooks must be at the top level of the component body — not inside event handlers, JSX, or conditionals.

- [ ] **Step 2: Add `blockingReason`, `startBatch`, and `downloadReport` before `return`**

Just above the `return` statement (after the other helper functions), add:

```tsx
const blockingReason = (() => {
  if (state.itemPdfFileId.size === 0) return "Add at least one form-and-label item.";
  for (const [, overLimit] of state.itemOverLimit) {
    if (overLimit) return "Trim items with more than 10 labels.";
  }
  if (state.orphanPdfFileIds.length + state.orphanImageFileIds.length > 0) {
    return "Resolve all items in the Needs Review tray.";
  }
  return null;
})();
```

Then add the `startBatch` and `downloadReport` functions:

```tsx
const startBatch = async () => {
  if (blockingReason !== null || isSubmitting) return;
  setIsSubmitting(true);
  setErrorMessage(null);
  setJobId(null);
  setReportReady(false);
  setProgressText(null);

  try {
    const formData = new FormData();
    const usedFilenames = new Set<string>();
    const itemSpecs: Array<{ item_id: string; form_filename: string; label_filenames: string[] }> = [];
    for (const [itemId, pdfFileId] of state.itemPdfFileId) {
      const pdfFile = state.fileById.get(pdfFileId)!;
      const pdfName = pdfFile.relativePath.split("/").pop()!;
      if (!usedFilenames.has(pdfFile.relativePath)) {
        formData.append("files", pdfFile.file, pdfName);
        usedFilenames.add(pdfFile.relativePath);
      }
      const labelIds = state.itemLabelFileIds.get(itemId) ?? [];
      const labelNames: string[] = [];
      for (const lid of labelIds) {
        const lf = state.fileById.get(lid)!;
        const lname = lf.relativePath.split("/").pop()!;
        if (!usedFilenames.has(lf.relativePath)) {
          formData.append("files", lf.file, lname);
          usedFilenames.add(lf.relativePath);
        }
        labelNames.push(lname);
      }
      itemSpecs.push({ item_id: itemId, form_filename: pdfName, label_filenames: labelNames });
    }
    formData.append("mapping", JSON.stringify({ items: itemSpecs }));

    const response = await fetch(apiUrl("/verify/batch"), { method: "POST", body: formData });
    if (!response.ok) {
      const detail = response.status === 400 ? (await response.json()).detail ?? "Bad request" : "Batch verification failed";
      throw new Error(detail);
    }
    const body = (await response.json()) as { job_id: string };
    setJobId(body.job_id);
    const ws = new WebSocket(batchEventsWebSocketUrl(body.job_id));
    websocketRef.current = ws;
    ws.addEventListener("message", (event) => {
      let parsed: Record<string, unknown> | null = null;
      try {
        parsed = JSON.parse(event.data) as Record<string, unknown>;
      } catch {
        return;
      }
      const processed = parsed.processed;
      const total = parsed.total;
      if (typeof processed === "number" && typeof total === "number") {
        setProgressText(`Batch progress: ${processed}/${total}`);
      }
      if (parsed.event_type === "job_completed") {
        setReportReady(true);
        ws.close();
        websocketRef.current = null;
      }
    });
    ws.addEventListener("error", () => setErrorMessage("Batch progress stream failed"));
  } catch (error) {
    const message =
      error instanceof TypeError && error.message === "Failed to fetch"
        ? `Unable to reach the API. ${unreachableApiHint()}`
        : error instanceof Error
          ? error.message
          : "Batch verification failed";
    setErrorMessage(message);
  } finally {
    setIsSubmitting(false);
  }
};

const downloadReport = async () => {
  if (jobId == null) return;
  setIsDownloading(true);
  setErrorMessage(null);
  try {
    const response = await fetch(apiUrl(`/verify/batch/${jobId}/report?purge=true`));
    if (!response.ok) throw new Error("Batch report request failed");
    const report = (await response.json()) as BatchReportResponse;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.job_id}-report.json`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    const message =
      error instanceof TypeError && error.message === "Failed to fetch"
        ? `Unable to reach the API. ${unreachableApiHint()}`
        : error instanceof Error
          ? error.message
          : "Batch report request failed";
    setErrorMessage(message);
  } finally {
    setIsDownloading(false);
  }
};
```

- [ ] **Step 3: Add Start button + progress section JSX**

Inside the `return`, just before the closing `</section>`, add:

```tsx
<button
  type="button"
  disabled={blockingReason !== null || isSubmitting}
  title={blockingReason ?? ""}
  onClick={() => void startBatch()}
>
  {isSubmitting ? "Starting batch check..." : "Start batch check"}
</button>

{jobId != null || progressText != null ? (
  <div className="result-panel">
    <h3>Job Status</h3>
    {jobId != null ? <div className="value-box"><span className="value-label">Job ID</span>{jobId}</div> : null}
    {progressText != null ? <div className="progress-text">{progressText}</div> : null}
    {reportReady ? (
      <button type="button" disabled={jobId == null || isDownloading} onClick={() => void downloadReport()}>
        {isDownloading ? "Downloading batch report..." : "Download batch report"}
      </button>
    ) : null}
  </div>
) : null}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: End-to-end smoke check**

Run backend (`cd backend && uvicorn app.main:create_app --factory --reload`) and frontend (`npm run dev`). Drop `realistic_clean_lager_f510031.pdf` + rename a copy of `realistic_clean_lager.png` to `realistic_clean_lager_f510031.png` in a temp folder so the prefix matches. Confirm:
- One paired item shows
- Start button enables
- Click → progress updates → Download button appears → file downloads

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BatchUpload.tsx
git commit -m "feat(frontend): batch upload Start gating and multipart submit"
```

---

## Task 9: E2E — adapt happy path; add adversarial orphan-resolution

**Files:**
- Modify: `frontend/tests/e2e/batch-progress.spec.ts`

- [ ] **Step 1: Replace the input upload with multi-file `setInputFiles`**

Open `frontend/tests/e2e/batch-progress.spec.ts`. The current test calls `setInputFiles` on `#batch-mapping-json`, which no longer exists. Replace the upload block (around lines 136–142) with:

```ts
// Click "Pick files" then set the hidden multi-input
const filesInput = page.locator('input[type="file"][multiple]:not([webkitdirectory])');
await filesInput.setInputFiles([
  { name: "widget.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fake\n") },
  { name: "widget-front.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
  { name: "widget-back.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
]);

// Verify the auto-pairing rendered one item with two labels
await expect(page.getByText("1 PDFs, 2 images")).toBeVisible();
await expect(page.getByText("widget.pdf")).toBeVisible();

// Start
await page.getByRole("button", { name: "Start batch check" }).click();
```

(The mocked `/verify/batch` route will return `job-123` regardless of multipart payload, since Playwright's `route.fulfill` doesn't validate the request body. Keep that mock as-is.)

- [ ] **Step 2: Run the existing test — should pass**

Run: `cd frontend && npm run test:e2e -- batch-progress.spec.ts`
Expected: PASS.

- [ ] **Step 3: Add an adversarial orphan-resolution test**

Append to the same file:

```ts
test("orphan PDF and orphan image must be resolved before Start enables", async ({ page }) => {
  await page.route("**/verify/batch", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-orphan" }),
    });
  });

  await page.goto("/");

  const filesInput = page.locator('input[type="file"][multiple]:not([webkitdirectory])');
  await filesInput.setInputFiles([
    { name: "lonely.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fake\n") },
    { name: "stranger.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
  ]);

  // Both should land in the orphan tray; Start is disabled with explanatory tooltip
  await expect(page.getByRole("heading", { name: /Needs review/ })).toBeVisible();
  const startButton = page.getByRole("button", { name: "Start batch check" });
  await expect(startButton).toBeDisabled();
  await expect(startButton).toHaveAttribute("title", /Resolve all items/);

  // Resolve: attach the orphan image to the orphan PDF via the select
  await page
    .getByLabel("Attach images to lonely.pdf")
    .selectOption({ label: "stranger.png" });

  // Now Start should be enabled
  await expect(startButton).toBeEnabled();
});
```

- [ ] **Step 4: Run the full E2E suite**

Run: `cd frontend && npm run test:e2e -- batch-progress.spec.ts`
Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/e2e/batch-progress.spec.ts
git commit -m "test(frontend): E2E for multi-file drop and orphan resolution"
```

---

## Final verification

- [ ] **Step 1: Backend full test suite**

Run: `cd backend && pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 2: Frontend unit tests**

Run: `cd frontend && npm test`
Expected: All PASS.

- [ ] **Step 3: Frontend E2E**

Run: `cd frontend && npm run test:e2e`
Expected: All PASS.

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Manual smoke**

Boot the stack, drop `tests/fixtures/labels/forms/realistic_clean_lager_f510031.pdf` together with a copy of `realistic_clean_lager.png` renamed so the stem matches (`realistic_clean_lager_f510031.png`). Confirm one paired item, Start runs, progress updates, report downloads.

That's the full plan. Each task produces a working, committable increment. The internal `BatchItemPayload` shape stabilizes after Task 1 and Task 2; everything after is frontend.
