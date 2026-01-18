import { test, expect } from "@playwright/test";

/**
 * Minimal smoke test for automation gate.
 * - Must not depend on backend availability or seeded data
 * - Only verifies the Vite app boots and renders something
 * - Keeps the automation pipeline stable while deeper E2E evolves
 */
test("app boots and serves HTML", async ({ page }) => {
  await page.goto("/");

  // We expect some HTML to exist and page not to be blank.
  await expect(page.locator("body")).toBeVisible();

  // At minimum, React/Vite should have mounted some content.
  // This is intentionally loose: we don't want to couple to copy/UX yet.
  const bodyText = await page.locator("body").innerText();
  expect(bodyText.length).toBeGreaterThan(0);
});
