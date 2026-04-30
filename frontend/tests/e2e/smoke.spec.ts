import { expect, test } from "@playwright/test";

test("single upload flow shows verification result", async ({ page }) => {
  await page.route("**/verify/single", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "pass",
        field_results: {
          brand_name: { status: "pass", expected_value: "Acme", extracted_value: "Acme" },
        },
      }),
    });
  });

  await page.goto("/");

  await page.getByLabel("TTB Form PDF").setInputFiles({
    name: "form.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("test-form"),
  });
  await page.getByLabel("Label Image").setInputFiles({
    name: "label.png",
    mimeType: "image/png",
    buffer: Buffer.from("test-label"),
  });

  await page.getByRole("button", { name: "Run single check" }).click();

  await expect(page.getByText("Single verification result")).toBeVisible();
  await expect(page.getByText("Overall status: pass")).toBeVisible();
});
