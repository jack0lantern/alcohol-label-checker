import * as path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/real-labels.spec.ts",
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: [
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "uv run uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 30_000,
      cwd: path.resolve(__dirname, "../backend"),
    },
  ],
});
