import { expect, test } from "@playwright/test";

test("shows app heading on home page", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Alcohol Label Checker" }),
  ).toBeVisible();
});
