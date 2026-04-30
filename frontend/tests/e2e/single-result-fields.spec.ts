import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoFixturesRoot = path.join(__dirname, "../../../tests/fixtures/labels");

/** Mirrors `/verify/single` aggregate output shape for `realistic_clean_lager` (OCR may vary slightly). */
const realisticCleanLagerVerifyBody = {
  status: "fail" as const,
  field_results: {
    alcohol_content: {
      expected_value: "5.0% alc/vol",
      extracted_value: "50%alevol",
      status: "fail" as const,
    },
    brand_name: {
      expected_value: "North Coast Lager",
      extracted_value: "North Cast Lager",
      status: "fail" as const,
    },
    class_type: {
      expected_value: "MALT BEVERAGE",
      extracted_value: "MALT BEVERAGE",
      status: "pass" as const,
    },
    government_warning: {
      expected_value:
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
      extracted_value:
        "GOVERNMENT WARNING: (1) According tothe Surgeon General women should notdrinkaleaholic beverages during pregnancy because ofthe risk of bith defects (2) Consumption of aleaholic beverag",
      status: "fail" as const,
    },
    net_contents: {
      expected_value: "12 fl oz",
      extracted_value: "12 loz",
      status: "fail" as const,
    },
  },
  image_results: [
    {
      status: "fail" as const,
      field_results: {
        alcohol_content: {
          expected_value: "5.0% alc/vol",
          extracted_value: "50%alevol",
          status: "fail" as const,
        },
        brand_name: {
          expected_value: "North Coast Lager",
          extracted_value: "North Cast Lager",
          status: "fail" as const,
        },
        class_type: {
          expected_value: "MALT BEVERAGE",
          extracted_value: "MALT BEVERAGE",
          status: "pass" as const,
        },
        government_warning: {
          expected_value:
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
          extracted_value:
            "GOVERNMENT WARNING: (1) According tothe Surgeon General women should notdrinkaleaholic beverages during pregnancy because ofthe risk of bith defects (2) Consumption of aleaholic beverag",
          status: "fail" as const,
        },
        net_contents: {
          expected_value: "12 fl oz",
          extracted_value: "12 loz",
          status: "fail" as const,
        },
      },
    },
  ],
};

test("single result shows realistic_clean_lager extracted text (not clipped or blank)", async ({ page }) => {
  await page.route("**/verify/single", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(realisticCleanLagerVerifyBody),
    });
  });

  await page.goto("/");

  const formBuffer = await readFile(path.join(repoFixturesRoot, "forms/realistic_clean_lager.json"));
  await page.locator("#single-form-pdf").setInputFiles({
    name: "form.pdf",
    mimeType: "application/pdf",
    buffer: formBuffer,
  });

  await page.locator("#single-label-images").setInputFiles(
    path.join(repoFixturesRoot, "images/realistic_clean_lager.png"),
  );

  await page.getByRole("button", { name: "Run single check" }).click();

  await expect(page.getByTestId("single-extracted-brand_name")).toContainText("North");
  await expect(page.getByTestId("single-extracted-class_type")).toContainText("MALT BEVERAGE");
  await expect(page.getByTestId("single-extracted-net_contents")).toContainText("12");
  await expect(page.getByTestId("single-extracted-government_warning")).toContainText("GOVERNMENT WARNING");
});

test("extracted column stays visible beside very long expected text (narrow viewport)", async ({ page }) => {
  const longExpected = `GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems. ${"x".repeat(400)}`;
  const uniqueExtracted = "E2E_EXTRACTED_MARKER_ZZ9";

  await page.setViewportSize({ width: 380, height: 900 });

  await page.route("**/verify/single", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "fail",
        field_results: {
          brand_name: {
            status: "pass",
            expected_value: "Short",
            extracted_value: "Short",
          },
          class_type: {
            status: "pass",
            expected_value: "MALT",
            extracted_value: "MALT",
          },
          alcohol_content: {
            status: "pass",
            expected_value: "5%",
            extracted_value: "5%",
          },
          net_contents: {
            status: "pass",
            expected_value: "12 oz",
            extracted_value: "12 oz",
          },
          government_warning: {
            status: "fail",
            expected_value: longExpected,
            extracted_value: uniqueExtracted,
          },
        },
        image_results: [
          {
            status: "fail",
            field_results: {
              brand_name: {
                status: "pass",
                expected_value: "Short",
                extracted_value: "Short",
              },
              class_type: {
                status: "pass",
                expected_value: "MALT",
                extracted_value: "MALT",
              },
              alcohol_content: {
                status: "pass",
                expected_value: "5%",
                extracted_value: "5%",
              },
              net_contents: {
                status: "pass",
                expected_value: "12 oz",
                extracted_value: "12 oz",
              },
              government_warning: {
                status: "fail",
                expected_value: longExpected,
                extracted_value: uniqueExtracted,
              },
            },
          },
        ],
      }),
    });
  });

  await page.goto("/");

  await page.locator("#single-form-pdf").setInputFiles({
    name: "form.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("{}"),
  });
  await page.locator("#single-label-images").setInputFiles({
    name: "label.png",
    mimeType: "image/png",
    buffer: Buffer.from("x"),
  });

  await page.getByRole("button", { name: "Run single check" }).click();

  const extractedCell = page.getByTestId("single-extracted-government_warning");
  await expect(extractedCell).toContainText(uniqueExtracted);

  const box = await extractedCell.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThan(80);
});
