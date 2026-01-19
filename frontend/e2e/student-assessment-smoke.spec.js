import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Student assessment intro Start creates run, persists snapshot, and navigates", async ({
  page,
}) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  // Mock backend: POST /v1/assessments/
	await page.route("**/v1/assessments/", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
		  id: 1,
		  assessment_id: 1, // normalized by our wrapper contract
		  submitted_at: null,
      }),
    });
  });
// Mock backend: GET /v1/assessments/active (intro page loads this and disables buttons until it returns)
await page.route("**/v1/assessments/active", async (route) => {
  if (route.request().method() !== "GET") return route.fallback();

  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      active: false,
      is_complete: false,
      assessment_id: null,
      answered_count: 0,
      total_questions: 30,
      next_question_id: null,
    }),
  });
});

  await page.goto("/student/assessment");

  await expect(page.getByRole("heading", { name: "Assessment" })).toBeVisible();

  // Stable CTA text
  const startBtn = page.getByRole("button", { name: "Start Assessment" });
  const resumeBtn = page.getByRole("button", { name: "Resume" });

  await expect(startBtn).toBeVisible();
  await expect(resumeBtn).toBeVisible();

  // Start -> creates real assessment_id and navigates to run route
  await startBtn.click();

  await expect(page).toHaveURL(/\/student\/assessment\/run\/1$/);

  // Snapshot persisted for resume
  const stored = await page.evaluate(() =>
    window.localStorage.getItem("cp:last_assessment_run:v1")
  );
  expect(stored).toBeTruthy();

  const parsed = JSON.parse(stored);
  expect(parsed.assessment_id).toBe(1);
});
