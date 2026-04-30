const rawBase = import.meta.env.VITE_API_BASE_URL ?? "";
export const apiBaseUrl = rawBase.replace(/\/+$/, "");

export function apiUrl(pathWithLeadingSlash: string): string {
  return `${apiBaseUrl}${pathWithLeadingSlash}`;
}

export function batchEventsWebSocketUrl(jobId: string): string {
  if (apiBaseUrl) {
    const origin = new URL(apiBaseUrl);
    const scheme = origin.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${origin.host}/verify/batch/${jobId}/events`;
  }
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/verify/batch/${jobId}/events`;
}

/** Shown when `fetch` fails before an HTTP status (offline, refused, CORS, etc.). */
export function unreachableApiHint(): string {
  return (
    "Ensure the backend is listening on port 8000 " +
    "(for example from the backend directory: uv run uvicorn app.main:app --reload --port 8000). " +
    "With npm run dev, requests are proxied from the Vite dev server. " +
    "npm run preview also proxies /verify; or set VITE_API_BASE_URL on the frontend build and ALLOWED_ORIGINS on the API for cross-origin development."
  );
}
