import { defineConfig } from "@playwright/test";
import path from "node:path";

const BACKEND_PORT = 8100;
const FRONTEND_PORT = 3100;
const backendDir = path.resolve(__dirname, "../backend");
const db = path.resolve(__dirname, "e2e/.tmp/e2e.db");

/**
 * Starts its own throwaway stack, so the tests never touch your dev data:
 *  - the FastAPI backend on a fresh SQLite file, migrated with Alembic
 *  - the frontend as a real production build
 * Every setting a test could depend on is pinned (real env vars beat the backend's .env file),
 * so no real API key is ever used and the SSRF guard is on.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${FRONTEND_PORT}`, trace: "retain-on-failure" },
  webServer: [
    {
      command: `sh -c 'rm -f "${db}"; mkdir -p "${path.dirname(db)}"; .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --port ${BACKEND_PORT}'`,
      cwd: backendDir,
      url: `http://localhost:${BACKEND_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: `sqlite:///${db}`,
        SECRET_KEY: "e2e-secret-key-that-is-at-least-32-bytes-long",
        ENCRYPTION_KEY: "e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2g=",
        GEMINI_API_KEY: "",
        GOOGLE_PLACES_API_KEY: "",
        ALLOW_PRIVATE_SMTP: "false",
        PUBLIC_BASE_URL: `http://localhost:${FRONTEND_PORT}`,
      },
    },
    {
      command: `sh -c 'npm run build && npx next start --port ${FRONTEND_PORT}'`,
      url: `http://localhost:${FRONTEND_PORT}/login`,
      reuseExistingServer: false,
      timeout: 240_000,
      env: { BACKEND_URL: `http://localhost:${BACKEND_PORT}`, NEXT_DIST_DIR: ".next-e2e", NODE_ENV: "production" },
    },
  ],
});
