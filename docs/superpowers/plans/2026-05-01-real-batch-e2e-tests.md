# Real Batch E2E Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three Playwright E2E tests that upload real TTB COLA label images through the batch UI and assert that the real Tesseract OCR pipeline extracts the correct fields.

**Architecture:** A separate `playwright.real.config.ts` runs only `real-labels.spec.ts` with two live `webServer` entries (Vite + uvicorn), keeping the mocked suite untouched. Fixtures are downloaded once via a reproducibility script, committed to `tests/fixtures/labels/`, and read at test time from the filesystem — no network calls during tests.

**Tech Stack:** Playwright 1.54+, TypeScript, FastAPI + uvicorn, Tesseract OCR (system install), GitHub Actions

---

## File Map

| Path | Action | Purpose |
|---|---|---|
| `frontend/playwright.real.config.ts` | Create | Real-stack Playwright config (Vite + uvicorn webServers, real-labels only) |
| `frontend/tests/e2e/real-labels.spec.ts` | Create | 3 E2E tests — one per COLA fixture |
| `scripts/download_ttb_fixtures.py` | Create | Reproducibility script — re-downloads committed images from their original TTB URLs |
| `tests/fixtures/labels/images/ttb_beer.png` | Create | Real COLA beer label scan (browser-saved in Task 1) |
| `tests/fixtures/labels/images/ttb_wine.png` | Create | Real COLA wine label scan |
| `tests/fixtures/labels/images/ttb_spirits.png` | Create | Real COLA distilled spirits label scan |
| `tests/fixtures/labels/forms/ttb_beer.json` | Create | Ground truth JSON (identical to truth file; used by backend PDF parser fallback) |
| `tests/fixtures/labels/forms/ttb_wine.json` | Create | Same |
| `tests/fixtures/labels/forms/ttb_spirits.json` | Create | Same |
| `tests/fixtures/labels/truth/ttb_beer.json` | Create | Hand-written ground truth |
| `tests/fixtures/labels/truth/ttb_wine.json` | Create | Same |
| `tests/fixtures/labels/truth/ttb_spirits.json` | Create | Same |
| `tests/fixtures/labels/expected/ttb_beer.json` | Create | Expected outcome (pass) |
| `tests/fixtures/labels/expected/ttb_wine.json` | Create | Same |
| `tests/fixtures/labels/expected/ttb_spirits.json` | Create | Same |
| `tests/fixtures/labels/fixtures_manifest.json` | Modify | Add 3 TTB entries with SHA256 checksums |
| `.github/workflows/ci.yml` | Modify | Add `frontend-e2e-real` job + `workflow_dispatch`/`schedule` triggers |

---

## Task 1: Discover and save 3 TTB COLA label images (manual browser task, ~20 min)

**Files:** `tests/fixtures/labels/images/ttb_beer.png`, `ttb_wine.png`, `ttb_spirits.png`

This task has no code — it is a human browser step. Complete it before any other task.

- [ ] **Step 1: Find a beer/malt beverage COLA**

  Open `https://www.ttbonline.gov/colasonline/publicSearchColasBasic.do` in your browser.
  In "Type of Product" select **MALT BEVERAGES**. Leave other fields blank. Click **Search**.
  Click any result row — a detail popup opens showing the label artwork.
  Right-click the label image → **Save Image As** → save to `tests/fixtures/labels/images/ttb_beer.png`.
  **Important:** While the popup is open, open browser DevTools → Network tab → find the image request → copy its full URL. You will need this URL in Task 2.

- [ ] **Step 2: Find a wine COLA**

  Clear the search. In "Type of Product" select **WINE** (or TABLE WINE). Click **Search**.
  Open any result, save the label image to `tests/fixtures/labels/images/ttb_wine.png`.
  Copy the full image URL for Task 2.

- [ ] **Step 3: Find a distilled spirits COLA**

  Clear the search. In "Type of Product" select **DISTILLED SPIRITS**. Click **Search**.
  Open any result, save the label image to `tests/fixtures/labels/images/ttb_spirits.png`.
  Copy the full image URL for Task 2.

- [ ] **Step 4: Visually inspect all three images**

  Open each saved `.png` in a viewer. Read the label carefully — you will hand-write the ground truth in Task 3. Note down:
  - Brand name (exact capitalisation)
  - Product class / type (e.g. "MALT BEVERAGE", "TABLE WINE", "VODKA")
  - Alcohol content (e.g. "5.0% ALC/VOL")
  - Net contents (e.g. "12 FL OZ (355 mL)")
  - Government warning (the full standard legal text; copy it exactly if present)

---

## Task 2: Write the fixture download script

**Files:** `scripts/download_ttb_fixtures.py`

- [ ] **Step 1: Create the script**

  Create `scripts/download_ttb_fixtures.py`. Fill in the three image URLs you copied in Task 1 into `COLA_SOURCES`.

  ```python
  #!/usr/bin/env python3
  """
  Re-download committed TTB COLA label fixtures from their original sources.

  Only run this if the committed images need to be refreshed.
  URLs were discovered manually via https://www.ttbonline.gov/colasonline/
  """
  import hashlib
  import urllib.request
  from pathlib import Path

  REPO_ROOT = Path(__file__).resolve().parent.parent
  FIXTURES_ROOT = REPO_ROOT / "tests/fixtures/labels/images"

  # Fill in the direct image URLs discovered in Task 1 Step 4 (DevTools → Network).
  COLA_SOURCES: dict[str, str] = {
      "ttb_beer": "<paste URL from Task 1 Step 1>",
      "ttb_wine": "<paste URL from Task 1 Step 2>",
      "ttb_spirits": "<paste URL from Task 1 Step 3>",
  }


  def main() -> None:
      FIXTURES_ROOT.mkdir(parents=True, exist_ok=True)
      for fixture_id, url in COLA_SOURCES.items():
          dest = FIXTURES_ROOT / f"{fixture_id}.png"
          print(f"Downloading {fixture_id} …")
          urllib.request.urlretrieve(url, dest)
          sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
          print(f"  saved  → {dest}")
          print(f"  sha256 → {sha256}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Run the script to verify URLs are correct**

  ```bash
  python3 scripts/download_ttb_fixtures.py
  ```

  Expected output — three lines of `saved → …` and `sha256 → …` (64-char hex each). If you get a 403/404, double-check the image URL from DevTools; TTB session-gated images may require a direct link captured while the popup was open. In that case, keep the Task 1 browser-saved files and skip re-download; the script is a reproducibility aid, not required for CI.

---

## Task 3: Write ground truth JSON files

**Files:** `tests/fixtures/labels/forms/ttb_*.json`, `truth/ttb_*.json`, `expected/ttb_*.json`

Using the notes from Task 1 Step 4, create three sets of JSON files. Repeat the pattern below for each fixture (`ttb_beer`, `ttb_wine`, `ttb_spirits`), substituting the actual values you read off the label.

The standard government warning text (copy exactly if it appears on the label):

```
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
```

- [ ] **Step 1: Create `tests/fixtures/labels/truth/ttb_beer.json`**

  ```json
  {
    "brand_name": "<exact brand name from label>",
    "class_type": "<e.g. MALT BEVERAGE>",
    "alcohol_content": "<e.g. 5.0% ALC/VOL>",
    "net_contents": "<e.g. 12 FL OZ (355 mL)>",
    "government_warning": "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
  }
  ```

  Fill in the angle-bracket fields with what you read from the beer label image.

- [ ] **Step 2: Create `tests/fixtures/labels/forms/ttb_beer.json`**

  Copy `truth/ttb_beer.json` verbatim — the form and truth files must have identical content (and therefore identical SHA256) to match how existing fixtures work.

  ```bash
  cp tests/fixtures/labels/truth/ttb_beer.json tests/fixtures/labels/forms/ttb_beer.json
  ```

- [ ] **Step 3: Create `tests/fixtures/labels/expected/ttb_beer.json`**

  ```json
  {
    "overall_status": "pass",
    "field_statuses": {
      "brand_name": "pass",
      "class_type": "pass",
      "alcohol_content": "pass",
      "net_contents": "pass",
      "government_warning": "pass"
    }
  }
  ```

- [ ] **Step 4: Repeat Steps 1–3 for `ttb_wine` and `ttb_spirits`**

  Same structure; substitute the values you read from the wine and spirits label images.

---

## Task 4: Add fixtures to the manifest and verify

**Files:** `tests/fixtures/labels/fixtures_manifest.json`

- [ ] **Step 1: Compute SHA256 for all new files**

  ```bash
  python3 - <<'EOF'
  import hashlib, pathlib
  root = pathlib.Path("tests/fixtures/labels")
  for fid in ("ttb_beer", "ttb_wine", "ttb_spirits"):
      for subdir in ("images", "forms", "truth", "expected"):
          ext = "png" if subdir == "images" else "json"
          p = root / subdir / f"{fid}.{ext}"
          sha = hashlib.sha256(p.read_bytes()).hexdigest()
          print(f"{subdir}/{fid}.{ext}: {sha}")
  EOF
  ```

  Copy the printed SHA256 values — you need them for the next step.

- [ ] **Step 2: Add three entries to `tests/fixtures/labels/fixtures_manifest.json`**

  Append inside the `"fixtures"` array. Use the SHA256 values from Step 1.

  ```json
  {
    "fixture_id": "ttb_beer",
    "sample_type": "realistic",
    "source": "ttb-cola",
    "scenario": "single_pass",
    "notes": "Real TTB COLA approved beer label downloaded from TTB COLAs Online.",
    "image": "tests/fixtures/labels/images/ttb_beer.png",
    "image_sha256": "<sha256 from Step 1>",
    "form": "tests/fixtures/labels/forms/ttb_beer.json",
    "form_sha256": "<sha256 from Step 1>",
    "truth": "tests/fixtures/labels/truth/ttb_beer.json",
    "truth_sha256": "<sha256 from Step 1>",
    "expected": "tests/fixtures/labels/expected/ttb_beer.json",
    "expected_sha256": "<sha256 from Step 1>"
  }
  ```

  Repeat for `ttb_wine` and `ttb_spirits`.

- [ ] **Step 3: Verify the manifest test passes**

  ```bash
  cd backend && uv run pytest tests/unit/test_fixture_manifest.py -v
  ```

  Expected: `PASSED` for `test_fixture_manifest_references_existing_files`. If it fails with a checksum mismatch, re-run the SHA256 script in Step 1 and fix the manifest entry.

- [ ] **Step 4: Commit fixtures and script**

  ```bash
  git add \
    tests/fixtures/labels/images/ttb_beer.png \
    tests/fixtures/labels/images/ttb_wine.png \
    tests/fixtures/labels/images/ttb_spirits.png \
    tests/fixtures/labels/forms/ttb_beer.json \
    tests/fixtures/labels/forms/ttb_wine.json \
    tests/fixtures/labels/forms/ttb_spirits.json \
    tests/fixtures/labels/truth/ttb_beer.json \
    tests/fixtures/labels/truth/ttb_wine.json \
    tests/fixtures/labels/truth/ttb_spirits.json \
    tests/fixtures/labels/expected/ttb_beer.json \
    tests/fixtures/labels/expected/ttb_wine.json \
    tests/fixtures/labels/expected/ttb_spirits.json \
    tests/fixtures/labels/fixtures_manifest.json \
    scripts/download_ttb_fixtures.py
  git commit -m "test(fixtures): add 3 real TTB COLA label fixtures"
  ```

---

## Task 5: Create the real Playwright config

**Files:** `frontend/playwright.real.config.ts`

- [ ] **Step 1: Create `frontend/playwright.real.config.ts`**

  ```typescript
  import * as path from "path";
  import { defineConfig } from "@playwright/test";

  export default defineConfig({
    testDir: "./tests/e2e",
    testMatch: "**/real-labels.spec.ts",
    timeout: 90_000,
    use: {
      baseURL: "http://127.0.0.1:4173",
    },
    webServer: [
      {
        command: "npm run dev -- --host 127.0.0.1 --port 4173",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: true,
        timeout: 120_000,
      },
      {
        command: "uv run uvicorn app.main:app --host 127.0.0.1 --port 8000",
        url: "http://127.0.0.1:8000/health",
        reuseExistingServer: true,
        timeout: 30_000,
        cwd: path.resolve(__dirname, "../backend"),
      },
    ],
  });
  ```

  `testMatch` restricts this config to `real-labels.spec.ts` only. `timeout: 90_000` gives each test 90 seconds — real Tesseract on a photo-quality image can take 10–30 s.

- [ ] **Step 2: Verify the config is syntactically valid**

  ```bash
  cd frontend && npx playwright test --config playwright.real.config.ts --list
  ```

  Expected: lists three test names like `real COLA batch: ttb_beer` (tests from Task 6 don't exist yet, so you'll get "no tests found" — that is fine at this stage; just confirm there is no TypeScript error).

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/playwright.real.config.ts
  git commit -m "test(e2e): add playwright.real.config.ts for real-stack E2E suite"
  ```

---

## Task 6: Create the real-labels spec

**Files:** `frontend/tests/e2e/real-labels.spec.ts`

- [ ] **Step 1: Create `frontend/tests/e2e/real-labels.spec.ts`**

  ```typescript
  import * as fs from "fs";
  import * as path from "path";
  import { expect, test } from "@playwright/test";

  const FIXTURES_ROOT = path.resolve(__dirname, "../../../tests/fixtures/labels");

  const FIXTURE_IDS = ["ttb_beer", "ttb_wine", "ttb_spirits"] as const;

  for (const fixtureId of FIXTURE_IDS) {
    test(`real COLA batch: ${fixtureId}`, async ({ page }) => {
      const groundTruth: Record<string, string> = JSON.parse(
        fs.readFileSync(path.join(FIXTURES_ROOT, "truth", `${fixtureId}.json`), "utf-8"),
      );
      const imageBytes = fs.readFileSync(
        path.join(FIXTURES_ROOT, "images", `${fixtureId}.png`),
      );

      await page.goto("/");

      const filesInput = page.locator(
        'section[aria-label="Batch upload"] input[type="file"][multiple]:not([webkitdirectory])',
      );
      await filesInput.setInputFiles([
        {
          name: `${fixtureId}.pdf`,
          mimeType: "application/pdf",
          buffer: Buffer.from(JSON.stringify(groundTruth)),
        },
        {
          name: `${fixtureId}-front.png`,
          mimeType: "image/png",
          buffer: imageBytes,
        },
      ]);

      const startButton = page.getByRole("button", { name: "Start batch check" });
      await expect(startButton).toBeEnabled();
      await startButton.click();

      await expect(page.getByText("Batch progress: 1/1")).toBeVisible({
        timeout: 60_000,
      });

      const downloadPromise = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download batch report" }).click();
      const download = await downloadPromise;

      const reportPath = await download.path();
      const report: {
        status: string;
        summary: { total: number };
        items: Array<{
          field_results: Record<
            string,
            { extracted_value: string | null }
          >;
        }>;
      } = JSON.parse(fs.readFileSync(reportPath!, "utf-8"));

      // Smoke: batch completed without crashing
      expect(report.summary.total).toBe(1);
      expect(["pass", "fail", "review_required", "completed_with_failures"]).toContain(
        report.status,
      );

      // Field accuracy: OCR must extract each field with sufficient similarity
      const fr = report.items[0].field_results;
      expect(similarity(groundTruth.brand_name, fr.brand_name?.extracted_value)).toBeGreaterThanOrEqual(0.8);
      expect(similarity(groundTruth.class_type, fr.class_type?.extracted_value)).toBeGreaterThanOrEqual(0.8);
      expect(similarity(groundTruth.alcohol_content, fr.alcohol_content?.extracted_value)).toBeGreaterThanOrEqual(0.6);
      expect(similarity(groundTruth.net_contents, fr.net_contents?.extracted_value)).toBeGreaterThanOrEqual(0.6);
      expect(similarity(groundTruth.government_warning, fr.government_warning?.extracted_value)).toBeGreaterThanOrEqual(0.8);
    });
  }

  function similarity(a: string, b: string | null | undefined): number {
    if (b == null) return 0;
    const aLow = a.toLowerCase();
    const bLow = b.toLowerCase();
    const longer = aLow.length > bLow.length ? aLow : bLow;
    const shorter = aLow.length > bLow.length ? bLow : aLow;
    if (longer.length === 0) return 1;
    return (longer.length - editDistance(longer, shorter)) / longer.length;
  }

  function editDistance(a: string, b: string): number {
    const dp = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let prev = dp[0];
      dp[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const temp = dp[j];
        dp[j] =
          a[i - 1] === b[j - 1] ? prev : Math.min(prev, dp[j], dp[j - 1]) + 1;
        prev = temp;
      }
    }
    return dp[b.length];
  }
  ```

  Key decisions:
  - The "form PDF" bytes are the ground truth JSON — the backend PDF parser detects the absence of the `%PDF-` magic bytes and falls back to JSON parsing (`pdf_parser.py:_ground_truth_from_json_bytes`).
  - Stem matching: `ttb_beer.pdf` + `ttb_beer-front.png` share the stem `ttb_beer`, so the batch UI pairs them automatically.
  - `similarity()` uses Levenshtein edit distance normalised by the longer string length — consistent with the backend's `SequenceMatcher`-based approach.

- [ ] **Step 2: Verify the config now lists 3 tests**

  ```bash
  cd frontend && npx playwright test --config playwright.real.config.ts --list
  ```

  Expected output includes exactly three lines:
  ```
  real COLA batch: ttb_beer
  real COLA batch: ttb_wine
  real COLA batch: ttb_spirits
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/tests/e2e/real-labels.spec.ts
  git commit -m "test(e2e): add real-labels spec for TTB COLA batch E2E"
  ```

---

## Task 7: Run the real E2E tests locally

**Prerequisites:** Tesseract must be installed (`tesseract --version` should print a version number). If not: `brew install tesseract` (macOS) or `sudo apt-get install tesseract-ocr` (Linux).

- [ ] **Step 1: Install backend dependencies**

  ```bash
  cd backend && uv sync && cd ..
  ```

- [ ] **Step 2: Run the real E2E suite**

  ```bash
  cd frontend && npx playwright test --config playwright.real.config.ts
  ```

  Expected: all 3 tests pass. Allow up to 5 minutes for the full run — Playwright starts both servers, runs OCR, and tears down.

- [ ] **Step 3: Interpret failures**

  If a test fails on a similarity assertion, the failure message prints the ground truth string and the extracted value. Compare them visually:
  - If the OCR extraction is clearly wrong (garbled), lower the threshold for that field by 0.05 and document why in a code comment.
  - If the OCR extraction is actually correct but the ground truth JSON has a typo, fix the ground truth JSON and re-run `test_fixture_manifest` to verify the SHA256 still matches. If the SHA256 changed, re-compute it and update the manifest entry.

  If a test fails on the smoke assertion (`report.summary.total`), check the Playwright trace:
  ```bash
  npx playwright test --config playwright.real.config.ts --trace on
  npx playwright show-trace test-results/<test>/trace.zip
  ```

- [ ] **Step 4: Commit any threshold adjustments**

  If you changed thresholds in Step 3, commit the updated spec before moving to Task 8.

  ```bash
  git add frontend/tests/e2e/real-labels.spec.ts
  git commit -m "test(e2e): tune similarity thresholds after real OCR run"
  ```

---

## Task 8: Add the `frontend-e2e-real` CI job

**Files:** `.github/workflows/ci.yml`

- [ ] **Step 1: Add `workflow_dispatch` and `schedule` to the `on` block**

  In `.github/workflows/ci.yml`, change:

  ```yaml
  on:
    push:
    pull_request:
  ```

  to:

  ```yaml
  on:
    push:
    pull_request:
    workflow_dispatch:
    schedule:
      - cron: "0 3 * * *"
  ```

- [ ] **Step 2: Append the new job at the end of the `jobs` block**

  ```yaml
    frontend-e2e-real:
      name: Frontend E2E Real Labels
      runs-on: ubuntu-latest
      if: github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'

      steps:
        - name: Check out repository
          uses: actions/checkout@v4

        - name: Set up uv
          uses: astral-sh/setup-uv@v5
          with:
            enable-cache: true

        - name: Set up Python
          uses: actions/setup-python@v5
          with:
            python-version-file: backend/pyproject.toml

        - name: Install backend dependencies
          run: cd backend && uv sync

        - name: Install Tesseract
          run: sudo apt-get install -y tesseract-ocr

        - name: Set up Node.js
          uses: actions/setup-node@v4
          with:
            node-version: 20
            cache: npm
            cache-dependency-path: frontend/package-lock.json

        - name: Install frontend dependencies
          run: cd frontend && npm ci

        - name: Install Playwright browser dependencies
          run: cd frontend && npx playwright install --with-deps chromium

        - name: Run real E2E tests
          run: cd frontend && npx playwright test --config playwright.real.config.ts
  ```

  Note: no `defaults.run.working-directory` here because different steps need different directories (`backend` for Python, `frontend` for Node/Playwright).

- [ ] **Step 3: Verify existing jobs are unaffected**

  The `if: github.event_name == 'workflow_dispatch' || ...` condition means the new job is skipped on every `push` and `pull_request` event, so existing CI behaviour is unchanged.

- [ ] **Step 4: Commit and push**

  ```bash
  git add .github/workflows/ci.yml
  git commit -m "ci: add nightly real E2E job for TTB COLA batch tests"
  ```
