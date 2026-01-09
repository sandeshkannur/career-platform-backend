import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Student onboarding page loads (student session)", async ({ page }) => {
  // Use the same session mocking convention as your other tests
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  await page.goto("/student/onboarding");

  // Stable assertions (matches your page title)
  await expect(page.getByRole("heading", { name: "Student Onboarding" })).toBeVisible();

  // Basic UI sanity checks (buttons exist)
  await expect(page.getByText("Save & Continue")).toBeVisible();
  await expect(page.getByText("Back to Dashboard")).toBeVisible();
});
