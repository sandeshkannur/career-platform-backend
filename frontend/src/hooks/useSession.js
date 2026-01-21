// src/hooks/useSession.js
import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

import { getToken, setToken, clearToken, routeFromSession } from "../auth";
import { apiGet, apiPost } from "../apiClient";
import { toastSuccess } from "../toast";

/**
 * In-memory session cache + in-flight de-dupe.
 * Goal: prevent multiple components calling useSession() from triggering multiple /v1/auth/me calls.
 *
 * - __sessionUserCache holds the last known /me payload for the current token.
 * - __meInFlightPromise ensures concurrent bootstraps share the same request.
 * - __cachedToken lets us invalidate cache when token changes.
 */
let __sessionUserCache = null;
let __meInFlightPromise = null;
let __cachedToken = null;

async function fetchMeDeduped() {
  const token = getToken();

  // No token => no session
  if (!token) {
    __sessionUserCache = null;
    __meInFlightPromise = null;
    __cachedToken = null;
    return null;
  }

  // Token changed => invalidate cache and in-flight promise
  if (__cachedToken !== token) {
    __sessionUserCache = null;
    __meInFlightPromise = null;
    __cachedToken = token;
  }

  // Serve from cache
  if (__sessionUserCache) return __sessionUserCache;

  // Share in-flight request across all hook instances
  if (!__meInFlightPromise) {
    __meInFlightPromise = (async () => {
      const me = await apiGet("/v1/auth/me");
      __sessionUserCache = me;
      return me;
    })().finally(() => {
      // Allow future refresh attempts after this completes
      __meInFlightPromise = null;
    });
  }

  return __meInFlightPromise;
}

export function useSession() {
  const navigate = useNavigate();
  const _location = useLocation();

  const [sessionUser, setSessionUser] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);

  /**
   * Bootstrap session on refresh
   * IMPORTANT:
   * - Run once on mount (do NOT re-run on every location change)
   * - Only auto-route when user is on public pages (/ or /login)
   * - Do NOT override navigation inside /student/* or /admin/*
   */
  async function bootstrapSession() {
    const token = getToken();

    // No token => no session
    if (!token) {
      setSessionUser(null);
      setBootstrapping(false);
      return;
    }

    try {
      // ✅ De-duped /me call across multiple hook instances
      const me = await fetchMeDeduped();
      setSessionUser(me);

      const currentPath = window.location.pathname;

      // ✅ only auto-route on public pages
      const isPublic = currentPath === "/" || currentPath === "/login";

      if (isPublic && me) {
        const target = routeFromSession(me, currentPath);
        if (target && target !== currentPath) {
          navigate(target, { replace: true });
        }
      }
    } catch {
      clearToken();
      __sessionUserCache = null;
      __cachedToken = null;
      setSessionUser(null);
      navigate("/login", { replace: true });
    } finally {
      setBootstrapping(false);
    }
  }

  /**
   * Login flow (supports login(email, password, redirectTo))
   */
  const login = async (arg1, arg2, redirectTo) => {
    let email;
    let password;

    if (typeof arg1 === "string") {
      email = arg1;
      password = arg2;
    } else {
      email = arg1?.email ?? arg1?.username;
      password = arg1?.password;
    }

    if (!email || !password) {
      throw new Error("Email/username and password are required.");
    }

    const data = await apiPost("/v1/auth/login", { email, password });
    setToken(data.access_token);

    // Token changed => invalidate cache explicitly
    __sessionUserCache = null;
    __meInFlightPromise = null;
    __cachedToken = getToken();

    const me = await fetchMeDeduped();
    setSessionUser(me);

    // one-time redirect guard (safe no-op)
    sessionStorage.removeItem("__AUTH_REDIRECTING__");

    const target = redirectTo || routeFromSession(me, window.location.pathname);
    navigate(target, { replace: true });
  };

  /**
   * Logout flow
   */
  const logout = async () => {
    try {
      await apiPost("/v1/auth/logout", {});
    } catch {
      // ignore
    }

    clearToken();

    // Clear cache on logout
    __sessionUserCache = null;
    __meInFlightPromise = null;
    __cachedToken = null;

    setSessionUser(null);
    toastSuccess("Logged out");
    navigate("/login", { replace: true });
  };

  // ✅ Bootstrap ONCE (do not depend on location.pathname)
  useEffect(() => {
    bootstrapSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    sessionUser,
    bootstrapping,
    login,
    logout,
  };
}
