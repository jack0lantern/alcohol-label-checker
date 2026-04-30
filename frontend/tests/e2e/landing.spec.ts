import { expect, test } from "@playwright/test";

test("home page loads with single and batch sections", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("main")).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: /alcohol.*label.*checker/i }),
  ).toBeVisible();
  await expect(page.getByText(/automated ttb compliance verification system/i)).toBeVisible();

  await expect(page.getByRole("region", { name: "Single upload" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Batch upload" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Single Check" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Batch Check" })).toBeVisible();
});
