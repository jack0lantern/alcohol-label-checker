import { expect, test } from "@playwright/test";

test("batch upload shows progress and performs report download action", async ({
  page,
}) => {
  let reportReads = 0;

  await page.route("**/verify/batch", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-123" }),
    });
  });

  await page.route("**/verify/batch/job-123/report", async (route) => {
    reportReads += 1;
    if (reportReads === 1) {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-123",
          status: "running",
          summary: { processed: 1, total: 3, pass: 1, fail: 0, review_required: 0 },
          items: [],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "job-123",
        status: "completed_with_failures",
        summary: { processed: 3, total: 3, pass: 1, fail: 1, review_required: 1 },
        items: [],
      }),
    });
  });

  await page.goto("/");

  await page.getByLabel("Batch Mapping JSON").setInputFiles({
    name: "batch.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"items":[]}'),
  });

  await page.getByRole("button", { name: "Start batch check" }).click();

  await expect(page.getByText("Batch progress: 1/3")).toBeVisible();
  await expect(page.getByText("Batch progress: 3/3")).toBeVisible();

  const reportAction = page.getByRole("button", { name: "Download batch report" });
  await expect(reportAction).toBeEnabled();

  const downloadPromise = page.waitForEvent("download");
  await reportAction.click();
  const download = await downloadPromise;
  await expect(download.suggestedFilename()).toBe("job-123-report.json");
});
