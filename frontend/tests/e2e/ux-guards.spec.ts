import { expect, test } from "@playwright/test";

test.describe("submit guards", () => {
  test("run single check stays disabled until form PDF and label image are chosen", async ({
    page,
  }) => {
    await page.goto("/");

    const runSingle = page.getByRole("button", { name: "Run single check" });
    await expect(runSingle).toBeDisabled();

    await page.locator("#single-form-pdf").setInputFiles({
      name: "form.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 minimal"),
    });
    await expect(runSingle).toBeDisabled();

    await page.locator("#single-label-images").setInputFiles({
      name: "label.png",
      mimeType: "image/png",
      buffer: Buffer.from("\x89PNG\r\n\x1a\n"),
    });
    await expect(runSingle).toBeEnabled();
  });

  test("start batch check stays disabled until a paired item exists with no orphans", async ({ page }) => {
    await page.goto("/");

    const startBatch = page.getByRole("button", { name: "Start batch check" });
    await expect(startBatch).toBeDisabled();

    // Drop a PDF + a stem-prefixed image so they auto-pair into one item
    const filesInput = page.locator('section[aria-label="Batch upload"] input[type="file"][multiple]:not([webkitdirectory])');
    await filesInput.setInputFiles([
      { name: "widget.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fake\n") },
      { name: "widget-front.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
    ]);

    await expect(startBatch).toBeEnabled();
  });
});

test.describe("single verify failure", () => {
  test("shows error alert when single verify request fails", async ({ page }) => {
    await page.route("**/verify/single", async (route) => {
      await route.fulfill({ status: 502, body: "Bad Gateway" });
    });

    await page.goto("/");

    await page.locator("#single-form-pdf").setInputFiles({
      name: "form.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 minimal"),
    });
    await page.locator("#single-label-images").setInputFiles({
      name: "label.png",
      mimeType: "image/png",
      buffer: Buffer.from("\x89PNG\r\n\x1a\n"),
    });

    await page.getByRole("button", { name: "Run single check" }).click();

    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Single verification failed");
    await expect(page.getByRole("heading", { name: "Verification Result" })).toHaveCount(0);
  });
});
