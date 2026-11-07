import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  workers: 1,
  timeout: 45_000,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:8011",
    viewport: { width: 1440, height: 950 },
    launchOptions: {
      executablePath: process.env.HAPIC_TEST_BROWSER || undefined,
      args: ["--enable-unsafe-swiftshader"],
    },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "pnpm build && node tests/office-server.mjs",
    url: "http://127.0.0.1:8011/api/health",
    timeout: 60_000,
    reuseExistingServer: false,
  },
});
