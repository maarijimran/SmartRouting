import { defineConfig } from "@playwright/test";

// Expects the stack to be running: backend on :8000 with FAKE_PROVIDERS=true and `make seed`
// applied, frontend on :3000. See SETUP.md ("End-to-end test").
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3000" },
});
