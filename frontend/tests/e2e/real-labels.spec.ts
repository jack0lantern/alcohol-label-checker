import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
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
