import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

test("Student assessment intro Start creates run, persists snapshot, and navigates", async ({
  page,
}) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  // Mock backend: POST /v1/assessments/start
  await page.route("**/v1/assessments/start", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        assessment_id: "assess_test_001",
        status: "in_progress",
        started_at: "2026-01-09T12:00:00Z",
        snapshot: { version: 1 },
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

  await expect(page).toHaveURL(/\/student\/assessment\/run\/assess_test_001$/);

  // Snapshot persisted for resume
  const stored = await page.evaluate(() =>
    window.localStorage.getItem("cp:last_assessment_run:v1")
  );
  expect(stored).toBeTruthy();

  const parsed = JSON.parse(stored);
  expect(parsed.assessment_id).toBe("assess_test_001");
});
