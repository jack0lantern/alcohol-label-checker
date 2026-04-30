import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/verify": {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
