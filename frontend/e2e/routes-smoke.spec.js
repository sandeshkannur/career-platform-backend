import { test, expect } from "@playwright/test";
import { mockSession } from "./helpers/session.js";

const studentRoutes = [
  "/student/dashboard",
  "/student/consent",
  "/student/onboarding",
  "/student/assessment",
  "/student/assessment/run/123",
  "/student/assessment/submit/123",
  "/student/results/latest",
  "/student/results/history",
  "/student/careers/1",
  "/student/reports/1",
];

const adminRoutes = [
  "/admin",
  "/admin/career-clusters",
  "/admin/careers",
  "/admin/key-skills",
  "/admin/mappings",
  "/admin/bulk-upload",
];

test("Student route smoke test (all pages load)", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: false, consent_verified: true });

  for (const path of studentRoutes) {
    await page.goto(path);
    // Basic sanity checks: not 404, not blank
    await expect(page.getByText("404")).toHaveCount(0);
    await expect(page.locator("h1")).toHaveCount(1);
  }
});

test("Admin route smoke test (all pages load)", async ({ page }) => {
  await mockSession(page, { role: "admin" });

  for (const path of adminRoutes) {
    await page.goto(path);
    await expect(page.getByText("404")).toHaveCount(0);
    await expect(page.locator("h1")).toHaveCount(1);
  }
});
