import { expect, test } from "@playwright/test";

test("batch upload shows progress and performs report download action", async ({
  page,
}) => {
  let reportReads = 0;

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

  await expect(page.getByText("Batch progress: 3/3")).toBeVisible();

  const reportAction = page.getByRole("button", { name: "Download batch report" });
  await expect(reportAction).toBeEnabled();
  await expect.poll(() => reportReads).toBe(0);

  const downloadPromise = page.waitForEvent("download");
  await reportAction.click();
  const download = await downloadPromise;
  await expect(download.suggestedFilename()).toBe("job-123-report.json");
  await expect.poll(() => reportReads).toBe(1);
});
