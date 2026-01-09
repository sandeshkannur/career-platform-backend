// src/auth.js

export const TOKEN_KEY = "access_token";

/** Safe JSON parse helper */
export function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Token helpers (default to sessionStorage) */
export function getToken(storage = sessionStorage) {
  return storage.getItem(TOKEN_KEY);
}

export function setToken(token, storage = sessionStorage) {
  storage.setItem(TOKEN_KEY, token);
}

export function clearToken(storage = sessionStorage) {
  storage.removeItem(TOKEN_KEY);
}

/**
 * API base URL
 * - If VITE_API_BASE_URL is set (prod), use it
 * - Otherwise return "" (dev proxy mode: /v1/... will work)
 */
export function apiBase() {
  const base = import.meta.env.VITE_API_BASE_URL;
  return base ? String(base).replace(/\/+$/, "") : "";
}

/** Single source of truth for "where should this user land?" */
export function routeFromSession(user, currentPath = "") {
  if (!user) return "/login";

  if (user.role === "admin") {
    // stay on admin pages if already there
    if (currentPath.startsWith("/admin")) return currentPath;
    return "/admin";
  }

  if (user.role === "student") {
    // stay on student pages if already there
    if (currentPath.startsWith("/student")) return currentPath;
    return "/student/dashboard";
  }

  return "/login";
}

/** Fetch /v1/auth/me for a token (returns {ok, meData?, error?}) */
export async function fetchMe(token) {
  try {
    const res = await fetch(`${apiBase()}/v1/auth/me`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include", // keeps refresh-cookie compatibility
    });

    const raw = await res.text();
    const data = raw ? safeJsonParse(raw) : null;

    if (!res.ok) {
      return {
        ok: false,
        error: (data && data.detail) || raw || `HTTP ${res.status}`,
      };
    }

    return { ok: true, meData: data };
  } catch (err) {
    console.error("fetchMe failed:", err);
    return { ok: false, error: "Unable to reach backend for session bootstrap." };
  }
}
