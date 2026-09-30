import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${process.env.WEB_PORT ?? "3000"}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    locale: "tr-TR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Önceden kurulu bir Chromium kullanmak için (ör. kısıtlı ağlı ortamlar).
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "tablet", use: { ...devices["Galaxy Tab S4"], defaultBrowserType: "chromium" } },
  ],
});
