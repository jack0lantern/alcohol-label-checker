import { expect, test } from "@playwright/test";

const standardFields = [
  "brand_name",
  "class_type",
  "alcohol_content",
  "net_contents",
  "government_warning",
] as const;

type FieldKey = (typeof standardFields)[number];

function fieldPass(
  field: FieldKey,
  expected: string,
  extracted: string,
): Record<string, { status: "pass"; expected_value: string; extracted_value: string }> {
  return {
    [field]: { status: "pass", expected_value: expected, extracted_value: extracted },
  };
}

function fieldFail(
  field: FieldKey,
  expected: string,
  extracted: string,
): Record<string, { status: "fail"; expected_value: string; extracted_value: string }> {
  return {
    [field]: { status: "fail", expected_value: expected, extracted_value: extracted },
  };
}

test.describe("single check with multiple label images", () => {
  test("shows Images Processed count matching uploaded images", async ({ page }) => {
    await page.route("**/verify/single", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "pass",
          field_results: Object.fromEntries(
            standardFields.map((f) => [
              f,
              {
                status: "pass",
                expected_value: "x",
                extracted_value: "x",
              },
            ]),
          ),
          image_results: [{ status: "pass", field_results: {} }, { status: "pass", field_results: {} }, { status: "pass", field_results: {} }],
        }),
      });
    });

    await page.goto("/");

    await page.locator("#single-form-pdf").setInputFiles({
      name: "form.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4"),
    });
    await page.locator("#single-label-images").setInputFiles([
      { name: "a.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "b.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "c.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
    ]);

    await page.getByRole("button", { name: "Run single check" }).click();

    await expect(page.locator(".value-box").filter({ hasText: "Images Processed" })).toContainText("3");
  });

  test("aggregate row shows best extraction when fields come from different images", async ({ page }) => {
    const expected = {
      brand_name: "Ridgeline IPA",
      class_type: "MALT BEVERAGE",
      alcohol_content: "6.2% alc/vol",
      net_contents: "16 fl oz",
      government_warning: "GOV_WARN_MULTI_IMG_E2E",
    };

    const image0Fields = {
      ...fieldPass("brand_name", expected.brand_name, "IMG0_BRAND_Ridgeline IPA"),
      ...fieldPass("class_type", expected.class_type, expected.class_type),
      ...fieldFail("alcohol_content", expected.alcohol_content, "xx"),
      ...fieldFail("net_contents", expected.net_contents, "xx"),
      ...fieldFail("government_warning", expected.government_warning, "xx"),
    };

    const image1Fields = {
      ...fieldFail("brand_name", expected.brand_name, "Wrong Brand"),
      ...fieldFail("class_type", expected.class_type, "WINE"),
      ...fieldPass("alcohol_content", expected.alcohol_content, expected.alcohol_content),
      ...fieldPass("net_contents", expected.net_contents, expected.net_contents),
      ...fieldPass("government_warning", expected.government_warning, expected.government_warning),
    };

    const aggregateFields = {
      brand_name: { status: "pass" as const, expected_value: expected.brand_name, extracted_value: "IMG0_BRAND_Ridgeline IPA" },
      class_type: { status: "pass" as const, expected_value: expected.class_type, extracted_value: expected.class_type },
      alcohol_content: { status: "pass" as const, expected_value: expected.alcohol_content, extracted_value: expected.alcohol_content },
      net_contents: { status: "pass" as const, expected_value: expected.net_contents, extracted_value: expected.net_contents },
      government_warning: { status: "pass" as const, expected_value: expected.government_warning, extracted_value: expected.government_warning },
    };

    await page.route("**/verify/single", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "pass",
          field_results: aggregateFields,
          image_results: [
            { status: "fail", field_results: image0Fields },
            { status: "fail", field_results: image1Fields },
          ],
        }),
      });
    });

    await page.goto("/");

    await page.locator("#single-form-pdf").setInputFiles({
      name: "form.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4"),
    });
    await page.locator("#single-label-images").setInputFiles([
      { name: "front.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "back.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
    ]);

    await page.getByRole("button", { name: "Run single check" }).click();

    await expect(page.getByTestId("single-extracted-brand_name")).toContainText("IMG0_BRAND_Ridgeline IPA");
    await expect(page.getByTestId("single-extracted-class_type")).toContainText("MALT BEVERAGE");
    await expect(page.getByTestId("single-extracted-alcohol_content")).toContainText("6.2%");
    await expect(page.getByTestId("single-extracted-net_contents")).toContainText("16 fl oz");
    await expect(page.getByTestId("single-extracted-government_warning")).toContainText("GOV_WARN_MULTI_IMG_E2E");
  });

  test("aggregate prefers passing brand from second image when first image brand fails", async ({ page }) => {
    await page.route("**/verify/single", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "pass",
          field_results: {
            brand_name: {
              status: "pass",
              expected_value: "Acme Brewing",
              extracted_value: "Acme Brewing",
            },
            class_type: {
              status: "pass",
              expected_value: "MALT BEVERAGE",
              extracted_value: "MALT BEVERAGE",
            },
            alcohol_content: {
              status: "pass",
              expected_value: "5% alc/vol",
              extracted_value: "5% alc/vol",
            },
            net_contents: {
              status: "pass",
              expected_value: "12 fl oz",
              extracted_value: "12 fl oz",
            },
            government_warning: {
              status: "pass",
              expected_value: "WARN",
              extracted_value: "WARN",
            },
          },
          image_results: [
            {
              status: "fail",
              field_results: {
                brand_name: {
                  status: "fail",
                  expected_value: "Acme Brewing",
                  extracted_value: "Other Brewing",
                },
                class_type: {
                  status: "pass",
                  expected_value: "MALT BEVERAGE",
                  extracted_value: "MALT BEVERAGE",
                },
                alcohol_content: {
                  status: "pass",
                  expected_value: "5% alc/vol",
                  extracted_value: "5% alc/vol",
                },
                net_contents: {
                  status: "pass",
                  expected_value: "12 fl oz",
                  extracted_value: "12 fl oz",
                },
                government_warning: {
                  status: "pass",
                  expected_value: "WARN",
                  extracted_value: "WARN",
                },
              },
            },
            {
              status: "pass",
              field_results: {
                brand_name: {
                  status: "pass",
                  expected_value: "Acme Brewing",
                  extracted_value: "Acme Brewing",
                },
                class_type: {
                  status: "pass",
                  expected_value: "MALT BEVERAGE",
                  extracted_value: "MALT BEVERAGE",
                },
                alcohol_content: {
                  status: "pass",
                  expected_value: "5% alc/vol",
                  extracted_value: "5% alc/vol",
                },
                net_contents: {
                  status: "pass",
                  expected_value: "12 fl oz",
                  extracted_value: "12 fl oz",
                },
                government_warning: {
                  status: "pass",
                  expected_value: "WARN",
                  extracted_value: "WARN",
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
      buffer: Buffer.from("%PDF-1.4"),
    });
    await page.locator("#single-label-images").setInputFiles([
      { name: "bad.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "good.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
    ]);

    await page.getByRole("button", { name: "Run single check" }).click();

    await expect(page.getByTestId("single-extracted-brand_name")).toContainText("Acme Brewing");
    await expect(page.locator(".value-box").filter({ hasText: "Images Processed" })).toContainText("2");
  });

  test("three images: extracted fields can each align with a different mock image in aggregate row", async ({
    page,
  }) => {
    await page.route("**/verify/single", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "pass",
          field_results: {
            brand_name: { status: "pass", expected_value: "B", extracted_value: "E2E_BRAND_FROM_IMG1" },
            class_type: { status: "pass", expected_value: "C", extracted_value: "E2E_CLASS_FROM_IMG2" },
            alcohol_content: { status: "pass", expected_value: "A", extracted_value: "E2E_ABV_FROM_IMG3" },
            net_contents: { status: "pass", expected_value: "N", extracted_value: "E2E_NET_FROM_IMG1" },
            government_warning: { status: "pass", expected_value: "G", extracted_value: "E2E_GOV_FROM_IMG2" },
          },
          image_results: [
            {
              status: "review_required",
              field_results: {
                brand_name: { status: "pass", expected_value: "B", extracted_value: "E2E_BRAND_FROM_IMG1" },
                net_contents: { status: "pass", expected_value: "N", extracted_value: "E2E_NET_FROM_IMG1" },
                class_type: { status: "fail", expected_value: "C", extracted_value: "x" },
                alcohol_content: { status: "fail", expected_value: "A", extracted_value: "x" },
                government_warning: { status: "fail", expected_value: "G", extracted_value: "x" },
              },
            },
            {
              status: "review_required",
              field_results: {
                class_type: { status: "pass", expected_value: "C", extracted_value: "E2E_CLASS_FROM_IMG2" },
                government_warning: { status: "pass", expected_value: "G", extracted_value: "E2E_GOV_FROM_IMG2" },
                brand_name: { status: "fail", expected_value: "B", extracted_value: "x" },
                alcohol_content: { status: "fail", expected_value: "A", extracted_value: "x" },
                net_contents: { status: "fail", expected_value: "N", extracted_value: "x" },
              },
            },
            {
              status: "pass",
              field_results: {
                alcohol_content: { status: "pass", expected_value: "A", extracted_value: "E2E_ABV_FROM_IMG3" },
                brand_name: { status: "fail", expected_value: "B", extracted_value: "x" },
                class_type: { status: "fail", expected_value: "C", extracted_value: "x" },
                net_contents: { status: "fail", expected_value: "N", extracted_value: "x" },
                government_warning: { status: "fail", expected_value: "G", extracted_value: "x" },
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
      buffer: Buffer.from("%PDF-1.4"),
    });
    await page.locator("#single-label-images").setInputFiles([
      { name: "1.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "2.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
      { name: "3.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n") },
    ]);

    await page.getByRole("button", { name: "Run single check" }).click();

    await expect(page.locator(".value-box").filter({ hasText: "Images Processed" })).toContainText("3");
    await expect(page.getByTestId("single-extracted-brand_name")).toContainText("E2E_BRAND_FROM_IMG1");
    await expect(page.getByTestId("single-extracted-class_type")).toContainText("E2E_CLASS_FROM_IMG2");
    await expect(page.getByTestId("single-extracted-alcohol_content")).toContainText("E2E_ABV_FROM_IMG3");
    await expect(page.getByTestId("single-extracted-net_contents")).toContainText("E2E_NET_FROM_IMG1");
    await expect(page.getByTestId("single-extracted-government_warning")).toContainText("E2E_GOV_FROM_IMG2");
  });
});
