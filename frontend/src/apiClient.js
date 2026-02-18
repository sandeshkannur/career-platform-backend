// src/apiClient.js
import { getToken, setToken, clearToken } from "./auth";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

// ✅ one-time redirect guard (prevents repeated redirects / race conditions)
const AUTH_REDIRECT_FLAG = "__AUTH_REDIRECTING__";
const LANG_STORAGE_KEY = "CP_LANG";
const DEFAULT_LANG = "en";

// Exported so UI can call it later (language dropdown/toggle)
export function getPreferredLang() {
  const raw = (localStorage.getItem(LANG_STORAGE_KEY) || "").trim().toLowerCase();
  return raw || DEFAULT_LANG;
}

export function setPreferredLang(lang) {
  const value = (lang || "").trim().toLowerCase();
  if (!value) return;
  localStorage.setItem(LANG_STORAGE_KEY, value);
}
function buildUrl(url) {
  if (/^https?:\/\//i.test(url)) return url;
  if (!API_BASE) return url; // proxy mode
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}
function applyLangParamIfNeeded(finalUrl, method = "GET") {
  const m = (method || "GET").toUpperCase();
  if (m !== "GET") return finalUrl;

  const lang = getPreferredLang();
  if (!lang) return finalUrl;

  const isAbsolute = /^https?:\/\//i.test(finalUrl);

  try {
    const u = new URL(finalUrl, window.location.origin);

    const p = u.pathname;
    const isQuestionEndpoint =
      p === "/v1/questions" || p === "/v1/questions/pool" || p === "/v1/questions/random";

    if (isQuestionEndpoint && !u.searchParams.has("lang")) {
      u.searchParams.set("lang", lang);
    }

    // Preserve relative URLs in proxy mode
    if (!isAbsolute && !API_BASE) {
      return `${u.pathname}${u.search}${u.hash}`;
    }

    return u.toString();
  } catch {
    return finalUrl;
  }
}

async function safeParseBody(res) {
  const contentType = res.headers.get("content-type") || "";
  if (res.status === 204) return null;

  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }

  try {
    const text = await res.text();
    return text ? text : null;
  } catch {
    return null;
  }
}

/**
 * Refresh flow:
 * POST /v1/auth/refresh
 * - Uses HttpOnly cookie refresh token (recommended)
 * - Returns: { access_token }
 */
async function refreshAccessToken() {
  try {
    const res = await fetch(buildUrl("/v1/auth/refresh"), {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "include", // ✅ allow HttpOnly cookie
    });

    if (!res.ok) return null;

    const data = await safeParseBody(res);
    const newToken = data?.access_token;
    if (!newToken) return null;

    setToken(newToken);
    return newToken;
  } catch {
    return null;
  }
}

// ✅ centralized hard-logout + redirect (safe to call multiple times)
function hardLogoutToLogin() {
  clearToken();

  // prevent repeated redirects in fast loops
  if (sessionStorage.getItem(AUTH_REDIRECT_FLAG) === "1") return;
  sessionStorage.setItem(AUTH_REDIRECT_FLAG, "1");

  // Avoid redirect loop if already on /login
  if (window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

export async function apiRequest(url, options = {}) {
  const builtUrl = buildUrl(url);
  const finalUrl = applyLangParamIfNeeded(builtUrl, options.method);
  const token = getToken();

  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");

  const isFormData = options.body instanceof FormData;
  if (!isFormData && options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (token) headers.set("Authorization", `Bearer ${token}`);

  const requestOptions = {
    ...options,
    headers,
    credentials: options.credentials ?? "include", // ✅ AWS friendly (cookie refresh)
  };

  let res = await fetch(finalUrl, requestOptions);

  // ✅ If unauthorized:
  // - For /v1/auth/me: do NOT refresh; immediately logout (bootstrap must be strict)
  // - Otherwise: try refresh once, then retry original request
  if (res.status === 401) {
    const isMeEndpoint = url === "/v1/auth/me" || finalUrl.endsWith("/v1/auth/me");

    if (isMeEndpoint) {
      hardLogoutToLogin();
    } else {
      const newToken = await refreshAccessToken();

      if (newToken) {
        const retryHeaders = new Headers(headers);
        retryHeaders.set("Authorization", `Bearer ${newToken}`);
        res = await fetch(finalUrl, { ...requestOptions, headers: retryHeaders });
      } else {
        hardLogoutToLogin();
      }
    }
  }

  const data = await safeParseBody(res);

  if (!res.ok) {
    const message =
      (data && typeof data === "object" && (data.detail || data.message)) ||
      (typeof data === "string" ? data : null) ||
      `Request failed (${res.status})`;

    const err = new Error(
      typeof message === "string" ? message : JSON.stringify(message)
    );
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

export const apiGet = (url, options = {}) =>
  apiRequest(url, { ...options, method: "GET" });

export const apiPost = (url, body, options = {}) =>
  apiRequest(url, {
    ...options,
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body),
  });

export const apiPut = (url, body, options = {}) =>
  apiRequest(url, {
    ...options,
    method: "PUT",
    body: body instanceof FormData ? body : JSON.stringify(body),
  });

export const apiDelete = (url, options = {}) =>
  apiRequest(url, { ...options, method: "DELETE" });
