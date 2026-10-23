import { defineConfig } from "@playwright/test";
/* QA suite, UI layer (tests/qa/ui.spec.mjs) against the RUNNING sites -- read-only, tracker muted. Local by default;
   point it elsewhere with KSSL_QA_LIVE_UI / KSSL_QA_REVIEW_UI (+ KSSL_QA_REVIEW_AUTH="user:password" for basic auth).
   Run everything with: python tests/qa/run_qa.py */
const auth = process.env.KSSL_QA_REVIEW_AUTH ? process.env.KSSL_QA_REVIEW_AUTH.split(":") : null;
export default defineConfig({
  testDir: "./tests/qa",
  testMatch: /ui\.spec\.mjs/,
  timeout: 120000,
  expect: { timeout: 15000 },
  workers: 2,
  retries: 1,
  reporter: [["list"], ["json", { outputFile: "tests/qa/out/ui_results.json" }]],
  use: { headless: true, viewport: { width: 1600, height: 1000 }, actionTimeout: 15000 },
  projects: [
    { name: "live", use: { baseURL: process.env.KSSL_QA_LIVE_UI || "http://127.0.0.1:5178" } },
    { name: "review", use: { baseURL: process.env.KSSL_QA_REVIEW_UI || "http://127.0.0.1:5180",
      ...(auth ? { httpCredentials: { username: auth[0], password: auth.slice(1).join(":") } } : {}) } },
  ],
});
