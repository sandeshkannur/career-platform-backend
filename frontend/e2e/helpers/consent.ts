// helpers/consent.ts
import { APIRequestContext, expect } from "@playwright/test";

type LoginResponse = {
  access_token: string;
  token_type: "bearer";
};

type ConsentRequestResponse = {
  consent_id: string;
  delivery: string;
  expires_at: string;
  dev?: {
    token: string;
    otp: string;
  };
};

type ConsentVerifyResponse = {
  verified: boolean;
  status: "verified" | "rejected";
  student_id: number;
  student_user_id: number;
  guardian_email: string;
  verified_at?: string;
  expires_at: string;
};

type MeResponse = {
  id: number;
  email: string;
  is_minor: boolean;
  guardian_email?: string | null;
  consent_verified: boolean;
  message?: string | null;
};

async function login(
  request: APIRequestContext,
  baseUrl: string,
  email: string,
  password: string
): Promise<string> {
  const res = await request.post(`${baseUrl}/v1/auth/login`, {
    data: { email, password },
  });

  expect(res.ok()).toBeTruthy();

  const json = (await res.json()) as LoginResponse;
  expect(json.access_token).toBeTruthy();

  return json.access_token;
}

/**
 * Automates consent flow in DEV/TEST mode (Option A).
 *
 * Requirements:
 * - backend ENV=dev|test so /v1/consent/request returns dev.token + dev.otp
 * - student user is_minor=true and has guardian_email set
 * - guardian user exists and can login
 */
export async function ensureConsentVerified(params: {
  request: APIRequestContext;
  baseUrl?: string; // default http://localhost:8000
  studentEmail: string;
  studentPassword: string;
  guardianEmail: string;
  guardianPassword: string;
}): Promise<void> {
  const {
    request,
    baseUrl = "http://localhost:8000",
    studentEmail,
    studentPassword,
    guardianEmail,
    guardianPassword,
  } = params;

  // 1) Student login
  const studentToken = await login(request, baseUrl, studentEmail, studentPassword);

  // 2) Student requests consent (DEV returns token+otp)
  const reqRes = await request.post(`${baseUrl}/v1/consent/request`, {
    headers: { Authorization: `Bearer ${studentToken}` },
    data: {}, // endpoint accepts {}
  });

  expect(reqRes.ok()).toBeTruthy();

  const reqJson = (await reqRes.json()) as ConsentRequestResponse;

  // DEV/TEST requirement
  if (!reqJson.dev?.token || !reqJson.dev?.otp) {
    throw new Error(
      `Expected dev.token/dev.otp from /v1/consent/request. ` +
        `Make sure ENV=dev|test. Got: ${JSON.stringify(reqJson)}`
    );
  }

  // 3) Guardian login
  const guardianToken = await login(request, baseUrl, guardianEmail, guardianPassword);

  // 4) Guardian verifies consent
  const verifyRes = await request.post(`${baseUrl}/v1/consent/verify`, {
    headers: {
      Authorization: `Bearer ${guardianToken}`,
      "Content-Type": "application/json",
    },
    data: {
      token: reqJson.dev.token,
      otp: reqJson.dev.otp,
    },
  });

  expect(verifyRes.ok()).toBeTruthy();

  const verifyJson = (await verifyRes.json()) as ConsentVerifyResponse;
  expect(verifyJson.verified).toBeTruthy();
  expect(verifyJson.status).toBe("verified");
  expect(verifyJson.guardian_email.toLowerCase()).toBe(guardianEmail.toLowerCase());

  // 5) Student session bootstrap should now show consent_verified=true
  const meRes = await request.get(`${baseUrl}/v1/auth/me`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });

  expect(meRes.ok()).toBeTruthy();

  const meJson = (await meRes.json()) as MeResponse;
  expect(meJson.consent_verified).toBeTruthy();
}
