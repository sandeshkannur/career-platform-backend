import { test, expect } from "@playwright/test";
import { mockSession, mockMe401, clearSession } from "./helpers/session.js";
import { enableDevConsentBypass } from "./helpers/session";

test("Logged out user accessing student dashboard is redirected to /login", async ({ page }) => {
  await clearSession(page);
  await page.goto("/student/dashboard");
  await expect(page).toHaveURL(/\/login/);
});

test("Student can access /student/dashboard", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: false });
  await page.goto("/student/dashboard");
  await expect(page.getByText("Student Dashboard")).toBeVisible();
});

test("Admin can access /admin", async ({ page }) => {
  await mockSession(page, { role: "admin" });
  await page.goto("/admin");
  await expect(page.getByText(/Admin/i)).toBeVisible();
});

test("Role mismatch: admin visiting student route redirects away", async ({ page }) => {
  await mockSession(page, { role: "admin" });
  await page.goto("/student/dashboard");
  await expect(page).toHaveURL(/\/admin/);
});

test("Minor student without consent is forced to /student/consent", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: true, consent_verified: false });
  await page.goto("/student/dashboard");
  await expect(page).toHaveURL(/\/student\/consent/);
});

test("Expired token causes redirect to /login", async ({ page }) => {
  await mockMe401(page);
  await page.goto("/student/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
test("DEV bypass allows minor student to access dashboard", async ({ page }) => {
  await enableDevConsentBypass(page);

  await mockSession(page, {
    role: "student",
    is_minor: true,
    consent_verified: false,
  });

  await page.goto("/student/dashboard");

  await expect(page).toHaveURL("/student/dashboard");
  await expect(page.getByText("Student Dashboard")).toBeVisible();
});