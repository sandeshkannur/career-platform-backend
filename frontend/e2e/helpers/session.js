// e2e/helpers/session.js

export async function mockSession(
  page,
  { role = "student", is_minor = false, consent_verified = true } = {}
) {
  // Put a fake token in sessionStorage before app loads
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "FAKE_TEST_TOKEN");
  });

  // Mock /v1/auth/me
  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 1,
        email: "test@example.com",
        role,
        is_minor,
        consent_verified,
      }),
    });
  });
}
export async function enableDevConsentBypass(page) {
  await page.addInitScript(() => {
    sessionStorage.setItem("__DEV_BYPASS_CONSENT__", "1");
  });
}

export async function disableDevConsentBypass(page) {
  await page.addInitScript(() => {
    sessionStorage.removeItem("__DEV_BYPASS_CONSENT__");
  });
}
export async function mockMe401(page) {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "EXPIRED_TOKEN");
  });

  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Expired token" }),
    });
  });
}

export async function clearSession(page) {
  await page.addInitScript(() => {
    sessionStorage.removeItem("access_token");
  });

  // Optional: if your app hits /me anyway, respond 401
  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not authenticated" }),
    });
  });
}
