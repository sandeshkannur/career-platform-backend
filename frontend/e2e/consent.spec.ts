import { test } from "@playwright/test";
import { ensureConsentVerified } from "./helpers/consent";

test("minor student completes consent flow", async ({ request }) => {
  await ensureConsentVerified({
    request,
    baseUrl: "http://localhost:8000",
    studentEmail: "dashboard.test2@example.com",
    studentPassword: "Test@12345",
    guardianEmail: "guardian.test2@example.com",
    guardianPassword: "Guardian@123",
  });
});
