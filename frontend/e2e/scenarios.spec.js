import { test, expect } from "@playwright/test";
import { mockSession, mockMe401, clearSession } from "./helpers/session.js";

const scenarios = [
  {
    name: "Logged out -> student dashboard redirects to login",
    setup: clearSession,
    go: "/student/dashboard",
    expectUrl: /\/login/,
  },
  {
    name: "Student -> dashboard allowed",
    setup: (page) => mockSession(page, { role: "student", is_minor: false, consent_verified: true }),
    go: "/student/dashboard",
    expectText: "Student Dashboard",
  },
  {
    name: "Admin -> /admin allowed",
    setup: (page) => mockSession(page, { role: "admin" }),
    go: "/admin",
    expectText: "Admin",
  },
  {
    name: "Admin -> student route redirected to admin",
    setup: (page) => mockSession(page, { role: "admin" }),
    go: "/student/dashboard",
    expectUrl: /\/admin/,
  },
  {
    name: "Minor student without consent forced to consent",
    setup: (page) => mockSession(page, { role: "student", is_minor: true, consent_verified: false }),
    go: "/student/dashboard",
    expectUrl: /\/student\/consent/,
  },
  {
    name: "Expired token -> login",
    setup: mockMe401,
    go: "/student/dashboard",
    expectUrl: /\/login/,
  },
];

for (const s of scenarios) {
  test(s.name, async ({ page }) => {
    await s.setup(page);
    await page.goto(s.go);

    if (s.expectUrl) {
      await expect(page).toHaveURL(s.expectUrl);
    }
    if (s.expectText) {
      await expect(page.getByText(s.expectText)).toBeVisible();
    }
  });
}
