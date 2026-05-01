import { expect, test } from "@playwright/test";

test("batch upload shows progress and performs report download action", async ({
  page,
}) => {
  let reportReads = 0;
  let sawPurgeQuery = false;

  await page.addInitScript(() => {
    class FakeWebSocket {
      static OPEN = 1;

      url: string;
      readyState = FakeWebSocket.OPEN;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      listeners: Record<string, EventListenerOrEventListenerObject[]> = {};

      constructor(url: string) {
        this.url = url;

        window.setTimeout(() => {
          this.emit("open", new Event("open"));
        }, 0);

        if (url.includes("/verify/batch/job-123/events")) {
          window.setTimeout(() => {
            this.emit(
              "message",
              new MessageEvent("message", {
                data: JSON.stringify({
                  event_type: "item_processed",
                  job_id: "job-123",
                  processed: 1,
                  total: 3,
                  status: "running",
                }),
              }),
            );
          }, 50);

          window.setTimeout(() => {
            this.emit(
              "message",
              new MessageEvent("message", {
                data: JSON.stringify({
                  event_type: "job_completed",
                  job_id: "job-123",
                  processed: 3,
                  total: 3,
                  status: "completed_with_failures",
                }),
              }),
            );
            this.emit("close", new Event("close"));
          }, 100);
        }
      }

      emit(type: string, event: Event) {
        if (type === "open") {
          this.onopen?.(event);
        }
        if (type === "message" && event instanceof MessageEvent) {
          this.onmessage?.(event);
        }
        if (type === "error") {
          this.onerror?.(event);
        }
        if (type === "close") {
          this.onclose?.(event);
        }

        const eventListeners = this.listeners[type] ?? [];
        for (const listener of eventListeners) {
          if (typeof listener === "function") {
            listener(event);
            continue;
          }
          listener.handleEvent(event);
        }
      }

      addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        const existing = this.listeners[type] ?? [];
        this.listeners[type] = [...existing, listener];
      }

      removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        const existing = this.listeners[type] ?? [];
        this.listeners[type] = existing.filter((entry) => entry !== listener);
      }

      send(_data: string) {}

      close() {
        this.emit("close", new Event("close"));
      }
    }

    Object.defineProperty(window, "WebSocket", {
      writable: true,
      value: FakeWebSocket,
    });
  });

  await page.route("**/verify/batch", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-123" }),
    });
  });

  await page.route("**/verify/batch/job-123/report*", async (route) => {
    reportReads += 1;
    const requestUrl = new URL(route.request().url());
    sawPurgeQuery = requestUrl.searchParams.get("purge") === "true";

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

  // Click "Pick files" then set the hidden multi-input
  const filesInput = page.locator('section[aria-label="Batch upload"] input[type="file"][multiple]:not([webkitdirectory])');
  await filesInput.setInputFiles([
    { name: "widget.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fake\n") },
    { name: "widget-front.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
    { name: "widget-back.png", mimeType: "image/png", buffer: Buffer.from("fake-png-bytes") },
  ]);

  // Verify the auto-pairing rendered one item with two labels
  await expect(page.getByText(/1 PDFs, 2 images/)).toBeVisible();
  await expect(page.getByText("widget.pdf")).toBeVisible();

  // Start
  await page.getByRole("button", { name: "Start batch check" }).click();

  await expect(page.getByText("Batch progress: 3/3")).toBeVisible();

  const reportAction = page.getByRole("button", { name: "Download batch report" });
  await expect(reportAction).toBeEnabled();
  await expect.poll(() => reportReads).toBe(0);

  const downloadPromise = page.waitForEvent("download");
  await reportAction.click();
  const download = await downloadPromise;
  await expect(download.suggestedFilename()).toBe("job-123-report.json");
  await expect.poll(() => reportReads).toBe(1);
  await expect.poll(() => sawPurgeQuery).toBe(true);
});

test("orphan PDF and orphan image must be resolved before Start enables", async ({ page }) => {
  await page.route("**/verify/batch", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-orphan" }),
    });
  });

  await page.goto("/");

  const filesInput = page.locator('section[aria-label="Batch upload"] input[type="file"][multiple]:not([webkitdirectory])');
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
