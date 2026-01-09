import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Assessment runner loads and enforces answer before next", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  await page.goto("/student/assessment/run/123");

  await expect(page.getByRole("heading", { name: "Assessment in Progress" })).toBeVisible();
  await expect(page.getByText(/Question 1 of/i)).toBeVisible();

  // Next should be disabled until an option is selected
  const nextBtn = page.getByRole("button", { name: "Next" });
  await expect(nextBtn).toBeDisabled();

  // Select an option
  await page.getByRole("button", { name: "Neutral" }).click();
  await expect(nextBtn).toBeEnabled();

  // Move to question 2
  await nextBtn.click();
  await expect(page.getByText(/Question 2 of/i)).toBeVisible();
});
