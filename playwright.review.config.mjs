import { defineConfig } from "@playwright/test";
/* Review-layer e2e (tests/e2e/review.spec.mjs). No webServer block: the review vite
   (:5191, --mode review, KSSL_API_TARGET=:8611) and the live vite (:5190, KSSL_API_TARGET=:8610)
   are started by hand against the throwaway test pair, so nothing here can touch
   the servers on :5178/:5180. */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /review\.spec\.mjs/,
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  retries: 1, // Windows can answer a navigation with ERR_NO_BUFFER_SPACE under a burst of sockets
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5191", headless: true, actionTimeout: 10000 },
});
