import { defineConfig } from "@playwright/test";
/* E2E for the client SPA (tests/e2e/frontend.spec.mjs) against the LIVE build on :5190,
   which proxies /api to the throwaway test backend on :8610 (kssl_test_serving). No
   webServer block: the backend and vite are started by hand against the test pair, so
   nothing here can touch the servers on :5178/:5180/:8600/:8601.
     bash db/make_test_pair.sh --approve-all
     KSSL_DSN="host=127.0.0.1 port=55432 dbname=kssl_test_serving user=kssl password=kssl" python -m uvicorn backend.app:app --port 8610
     KSSL_API_TARGET=http://127.0.0.1:8610 npx vite --port 5190
     npx playwright test
   The review layer has its own config: playwright.review.config.mjs. */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /frontend\.spec\.mjs/,
  timeout: 45000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 1, // Windows can answer a navigation with ERR_NO_BUFFER_SPACE under a burst of sockets
  reporter: [["list"], ["junit", { outputFile: "reports/e2e-results.xml" }]],
  use: { baseURL: "http://127.0.0.1:5190", headless: true, actionTimeout: 10000 },
});
