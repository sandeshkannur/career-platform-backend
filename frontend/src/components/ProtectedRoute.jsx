// src/components/ProtectedRoute.jsx
import { Navigate, useLocation } from "react-router-dom";
import LoadingScreen from "./LoadingScreen";
import { useSession } from "../hooks/useSession";
import { getToken, routeFromSession } from "../auth";

/**
 * ProtectedRoute
 * - Requires token + sessionUser
 * - Enforces role allowlist
 * - Enforces minor consent gate (student only)
 *   -> if is_minor === true AND consent_verified === false => force /student/consent
 *
 * DEV ONLY:
 * - "__DEV_BYPASS_CONSENT__" = "1" bypasses the consent gate
 * - "__DEV_ALLOW_CONSENT_PAGE__" = "1" allows staying on /student/consent even if verified
 */
export default function ProtectedRoute({ allowRoles, children }) {
  const { bootstrapping, sessionUser } = useSession();
  const location = useLocation();
  const token = getToken();

  // DEV guard (Vite)
  const DEV_ONLY = !import.meta.env.PROD;

  // Wait for bootstrap
  if (bootstrapping) return <LoadingScreen label="Loading session…" />;

  // No token -> login
  if (!token) return <Navigate to="/login" replace state={{ from: location }} />;

  // Token exists but no session user -> login (avoid 401 loops)
  if (!sessionUser) return <Navigate to="/login" replace state={{ from: location }} />;

  // Role mismatch -> send to correct landing
  if (allowRoles?.length && !allowRoles.includes(sessionUser.role)) {
    const target = routeFromSession(sessionUser, location.pathname);
    if (target !== location.pathname) return <Navigate to={target} replace />;
  }

  // -------- Minor consent gate (student only) --------
  const isStudent = sessionUser.role === "student";
  const isMinor = sessionUser.is_minor === true;

  // IMPORTANT: use EXACT field name "consent_verified"
  const consentVerified = sessionUser.consent_verified === true;

  const onConsentPage = location.pathname === "/student/consent";

  // ✅ DEV bypass flag (remove later) — MUST NOT work in production
  const devBypassConsent =
    DEV_ONLY && sessionStorage.getItem("__DEV_BYPASS_CONSENT__") === "1";

  // ✅ DEV helper: allow staying on /student/consent to validate UI state even if verified
  // MUST NOT work in production
  const devAllowConsentPage =
    DEV_ONLY && sessionStorage.getItem("__DEV_ALLOW_CONSENT_PAGE__") === "1";

  // If minor and consent not verified -> force consent page (unless DEV bypass enabled)
  if (isStudent && isMinor && !consentVerified && !onConsentPage && !devBypassConsent) {
    return <Navigate to="/student/consent" replace state={{ from: location }} />;
  }

  // If verified (or bypass enabled or not minor) and they are on consent page -> push to dashboard
  // unless devAllowConsentPage is enabled
  if (
    isStudent &&
    (!isMinor || consentVerified || devBypassConsent) &&
    onConsentPage &&
    !devAllowConsentPage
  ) {
    return <Navigate to="/student/dashboard" replace />;
  }

  return children;
}
