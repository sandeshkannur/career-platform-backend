import { test, expect } from "@playwright/test";
import { clearSession } from "./helpers/session.js";

test("Auth UI smoke: login <-> signup navigation", async ({ page }) => {
  await clearSession(page);

  // --- Login page ---
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Login" })).toBeVisible();
  await expect(page.getByText("Page not found. (NOTFOUND_FROM_APPROUTES)")).toHaveCount(0);

  // Header should be present
  await expect(page.getByRole("link", { name: "Signup", exact: true })).toBeVisible();

  // --- Navigate to Signup via header ---
  await page.getByRole("link", { name: "Signup", exact: true }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("heading", { name: "Signup" })).toBeVisible();
  await expect(page.getByText("Page not found. (NOTFOUND_FROM_APPROUTES)")).toHaveCount(0);

  // --- Navigate back to Login via header (scope to first match) ---
  await page.getByRole("link", { name: "Login", exact: true }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Login" })).toBeVisible();
});
