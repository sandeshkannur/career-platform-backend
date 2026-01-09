import { test, expect } from "@playwright/test";

test("Public module smoke: home -> pricing -> login", async ({ page }) => {
  // Home
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  await expect(
    page.getByText("Page not found. (NOTFOUND_FROM_APPROUTES)")
  ).toHaveCount(0);

  // Confirm header exists (helps stability)
  await expect(page.getByRole("link", { name: "CareerPlatform", exact: true })).toBeVisible();

  // Header navigation: click Pricing
  await page.getByRole("link", { name: "Pricing", exact: true }).click();
  await expect(page).toHaveURL(/\/pricing$/);
  await expect(page.getByRole("heading", { name: "Pricing" })).toBeVisible();
  await expect(
    page.getByText("Page not found. (NOTFOUND_FROM_APPROUTES)")
  ).toHaveCount(0);

  // Header navigation: click Login
  await page.getByRole("link", { name: "Login", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Login" })).toBeVisible();
  await expect(
    page.getByText("Page not found. (NOTFOUND_FROM_APPROUTES)")
  ).toHaveCount(0);
});
