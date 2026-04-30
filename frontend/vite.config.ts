import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";

const verifyProxy = {
  "/verify": {
    target: API_TARGET,
    changeOrigin: true,
    ws: true,
  },
} satisfies Record<string, { target: string; changeOrigin: boolean; ws: boolean }>;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: verifyProxy,
  },
  preview: {
    proxy: verifyProxy,
  },
});
