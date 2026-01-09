import { test, expect } from "@playwright/test";
import { clearSession, mockSession } from "./helpers/session.js";

test("Student dashboard is protected: unauthenticated -> /login", async ({ page }) => {
  await clearSession(page);
  await page.goto("/student/dashboard");
  await expect(page).toHaveURL(/\/login/);
});

test("Verified minor sees consent verified banner on dashboard", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: true, consent_verified: true });

  await page.goto("/student/dashboard");

  // Banner we added/kept in StudentDashboardPage.jsx
  await expect(page.getByText("Parental consent verified ✅")).toBeVisible();
});

test("Unverified minor is gated to consent page and sees consent header", async ({ page }) => {
  await mockSession(page, { role: "student", is_minor: true, consent_verified: false });

  await page.goto("/student/dashboard");

  // ProtectedRoute should force consent page
  await expect(page).toHaveURL(/\/student\/consent/);

  // StudentConsentPage title prop should render as H1
  await expect(
    page.getByRole("heading", { name: "Parental Consent Required" })
  ).toBeVisible();
});
