import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Student assessment intro loads and shows CTAs", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  await page.goto("/student/assessment");

  await expect(page.getByRole("heading", { name: "Assessment" })).toBeVisible();

  // Stable CTA text
  await expect(page.getByRole("button", { name: "Start Assessment" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
});
