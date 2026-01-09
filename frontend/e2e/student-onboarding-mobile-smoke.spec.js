import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Student onboarding mobile shows 1-question stepper", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  // iPhone-ish viewport (mobile breakpoint <= 640px)
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/student/onboarding");

  // Page title should still render
  await expect(page.getByRole("heading", { name: "Student Onboarding" })).toBeVisible();

  // Mobile stepper should show Step counter
  await expect(page.getByText(/Step 1 of/i)).toBeVisible();

  // "Next" should be disabled until required input is provided
  const nextBtn = page.getByRole("button", { name: "Next" });
  await expect(nextBtn).toBeDisabled();

  // Fill first required question (Grade) and proceed
  await page.getByPlaceholder("e.g. 9").fill("9");
  await expect(nextBtn).toBeEnabled();
  await nextBtn.click();

  // Step 2 should now be visible (Primary Goal)
  await expect(page.getByText(/Step 2 of/i)).toBeVisible();

  const goalInput = page.getByPlaceholder(
    "e.g. choose a stream, explore careers, plan higher studies"
  );
  await expect(goalInput).toBeVisible();

  // Next should again be disabled until Primary Goal is filled
  await expect(nextBtn).toBeDisabled();
  await goalInput.fill("Explore careers");
  await expect(nextBtn).toBeEnabled();
});
