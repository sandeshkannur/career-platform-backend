// src/pages/StudentConsentPage.jsx
import { useEffect, useMemo, useState } from "react";
import SkeletonPage from "../ui/SkeletonPage";
import Button from "../ui/Button";
import Input from "../ui/Input";
import { useSession } from "../hooks/useSession";
import { useNavigate } from "react-router-dom";

import { requestConsent, getConsentStatus, verifyConsent } from "../api/consent";

const DEV_BYPASS_KEY = "__DEV_BYPASS_CONSENT__";

export default function StudentConsentPage() {
  const { logout, sessionUser, refreshSession } = useSession();
  const navigate = useNavigate();

  // DEV guard (Vite)
  const DEV_ONLY = !import.meta.env.PROD;

  const [devCode, setDevCode] = useState("");
  const devBypassOn =
    DEV_ONLY && sessionStorage.getItem(DEV_BYPASS_KEY) === "1";

  // Consent data
  const [statusLoading, setStatusLoading] = useState(false);
  const [requestLoading, setRequestLoading] = useState(false);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [error, setError] = useState(null);

  const [statusData, setStatusData] = useState(null);
  const [requestData, setRequestData] = useState(null);

  // Student-side verification helper (optional). Primary flow remains the public guardian page.
  const [showVerifyPanel, setShowVerifyPanel] = useState(false);
  const [verifyToken, setVerifyToken] = useState("");
  const [verifyOtp, setVerifyOtp] = useState("");

  const guardianEmail = useMemo(() => {
    return sessionUser?.guardian_email || null;
  }, [sessionUser]);

  /**
   * Treat consent as verified if either:
   * - session says consent_verified true (authoritative for routing)
   * - status endpoint says "verified"
   */
  const consentVerified = useMemo(() => {
    // Support both backend snake_case and frontend camelCase (depends on useSession normalization)
    const v = sessionUser?.consent_verified ?? sessionUser?.consentVerified ?? false;

    if (v === true) return true;
    if (statusData?.state === "verified") return true;
    return false;
  }, [sessionUser, statusData]);

  /**
   * Guardian public verify URL (DEV/TEST convenience).
   * - Only present when backend returns requestData.dev.token
   * - Uses encodeURIComponent to keep the URL safe
   */
  const guardianVerifyUrl = useMemo(() => {
    const token = requestData?.dev?.token;
    if (!token) return null;
    return `${window.location.origin}/guardian/verify?token=${encodeURIComponent(token)}`;
  }, [requestData]);

  function enableDevBypass() {
    if (!DEV_ONLY) return;

    if (devCode.trim() !== "DEV") {
      alert('Enter "DEV" to enable bypass');
      return;
    }
    sessionStorage.setItem(DEV_BYPASS_KEY, "1");
    navigate("/student/dashboard", { replace: true });
  }

  function disableDevBypass() {
    if (!DEV_ONLY) return;

    sessionStorage.removeItem(DEV_BYPASS_KEY);
    alert("Dev bypass disabled. You will be gated again as a minor.");
  }

  async function refreshStatus() {
    setStatusLoading(true);
    setError(null);
    try {
      const data = await getConsentStatus();
      setStatusData(data);
    } catch (e) {
      setError({
        status: e?.status,
        message: e?.message || "Failed to load consent status.",
        raw: e,
      });
    } finally {
      setStatusLoading(false);
    }
  }

  async function handleRequestConsent() {
    setRequestLoading(true);
    setError(null);
    setRequestData(null);

    try {
      if (!guardianEmail) {
        throw new Error("guardian_email is missing in session. Cannot request consent.");
      }

      // If already verified, don't allow new requests (clean UX)
      if (consentVerified) {
        setError({
          status: 400,
          message: "Consent is already verified. No need to request again.",
        });
        return;
      }

      // Backend derives guardian_email from the authenticated student session (no payload needed).
      const data = await requestConsent();
      setRequestData(data);

      // After requesting, refresh derived status
      await refreshStatus();
    } catch (e) {
      setError({
        status: e?.status,
        message: e?.message || "Failed to request consent.",
        raw: e,
      });
    } finally {
      setRequestLoading(false);
    }
  }

  /**
   * Optional helper: allow student/dev tester to verify using token + OTP.
   * - Primary flow remains guardian public verify page.
   * - On success, refresh status + session and redirect to dashboard.
   */
  async function handleVerifyConsent() {
    setVerifyLoading(true);
    setError(null);

    try {
      if (consentVerified) {
        setError({
          status: 400,
          message: "Consent is already verified.",
        });
        return;
      }

      if (!verifyToken.trim()) throw new Error("Token is required.");
      if (!verifyOtp.trim()) throw new Error("OTP is required.");

      await verifyConsent({
        token: verifyToken.trim(),
        otp: verifyOtp.trim(),
      });

      await refreshStatus();

      // Refresh session so consent_verified reflects immediately in routing.
      if (typeof refreshSession === "function") {
        await refreshSession();
        navigate("/student/dashboard", { replace: true });
      } else {
        // Safe fallback if the hook doesn't expose refreshSession
        window.location.reload();
      }
    } catch (e) {
      setError({
        status: e?.status,
        message: e?.message || "Failed to verify consent.",
        raw: e,
      });
    } finally {
      setVerifyLoading(false);
    }
  }

  // Load status once on entry
  useEffect(() => {
    refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // DEV convenience: auto-fill verify inputs from dev payload, if present.
  useEffect(() => {
    if (requestData?.dev?.token) setVerifyToken(requestData.dev.token);
    if (requestData?.dev?.otp) setVerifyOtp(requestData.dev.otp);
  }, [requestData]);

  // If consent becomes verified, hide the helper panel (clean UX)
  useEffect(() => {
    if (consentVerified) setShowVerifyPanel(false);
  }, [consentVerified]);

  return (
    <SkeletonPage
      title="Parental Consent Required"
      subtitle="You must complete guardian consent before continuing."
      actions={<Button onClick={logout}>Logout</Button>}
    >
      <p>
        Student email: <b>{sessionUser?.email}</b>
      </p>

      <p style={{ marginTop: 12 }}>
        This student account is marked as a <b>minor</b>. Before assessments can
        begin, parental or guardian consent must be verified.
      </p>

      {/* Verified banner (UX polish) */}
      {consentVerified ? (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            border: "1px solid #b7e3c0",
            background: "#f3fff6",
            borderRadius: 8,
          }}
        >
          <div style={{ fontWeight: 800 }}>Consent verified ✅</div>
          <div style={{ marginTop: 6, fontSize: 14, color: "#2b6b3f" }}>
            You may continue to the dashboard.
          </div>
          <div style={{ marginTop: 10 }}>
            <Button onClick={() => navigate("/student/dashboard", { replace: true })}>
              Go to Dashboard
            </Button>
          </div>
        </div>
      ) : null}

      {/* Status panel */}
      <div style={{ marginTop: 14, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div style={{ fontWeight: 800 }}>Consent Status</div>
          <Button variant="secondary" onClick={refreshStatus} disabled={statusLoading}>
            {statusLoading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        <div style={{ marginTop: 8, fontSize: 14, color: "#555" }}>
          Guardian email on file:{" "}
          <b>{guardianEmail ? guardianEmail : "— missing —"}</b>
        </div>

        {error ? (
          <div
            style={{
              marginTop: 10,
              padding: 10,
              border: "1px solid #f3b4b4",
              background: "#fff6f6",
              borderRadius: 8,
            }}
          >
            <div style={{ fontWeight: 800 }}>
              Error{error.status ? ` (HTTP ${error.status})` : ""}
            </div>
            <div style={{ fontSize: 14 }}>{error.message}</div>
          </div>
        ) : null}

        {statusData ? (
          <pre style={{ marginTop: 10, marginBottom: 0, padding: 10, overflowX: "auto" }}>
            {JSON.stringify(statusData, null, 2)}
          </pre>
        ) : (
          <div style={{ marginTop: 10, color: "#777" }}>
            {statusLoading ? "Loading…" : "No status loaded yet."}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button
          onClick={handleRequestConsent}
          disabled={requestLoading || !guardianEmail || consentVerified}
        >
          {requestLoading ? "Sending…" : "Send Consent Request"}
        </Button>

        <Button
          variant="secondary"
          onClick={() => setShowVerifyPanel((v) => !v)}
          disabled={consentVerified}
        >
          Verify OTP / Token
        </Button>
      </div>

      {/* Optional student-side verify helper */}
      {showVerifyPanel ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>Verify Consent (Helper)</div>

          <div style={{ display: "grid", gap: 10, maxWidth: 520 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Token</div>
              <Input
                value={verifyToken}
                onChange={(e) => setVerifyToken(e.target.value)}
                placeholder="Paste consent token"
              />
            </div>

            <div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>OTP</div>
              <Input
                value={verifyOtp}
                onChange={(e) => setVerifyOtp(e.target.value)}
                placeholder="Enter OTP"
              />
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button onClick={handleVerifyConsent} disabled={verifyLoading}>
                {verifyLoading ? "Verifying…" : "Verify"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowVerifyPanel(false)}
                disabled={verifyLoading}
              >
                Close
              </Button>
            </div>

            <div style={{ fontSize: 12, color: "#666" }}>
              Note: Primary flow is the public guardian page. This helper is for DEV/testing only.
            </div>
          </div>
        </div>
      ) : null}

      {/* Request response debug (DEV/TEST only) */}
      {DEV_ONLY && requestData ? (
        <div style={{ marginTop: 14, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>
            Consent Request Response (temporary debug)
          </div>

          <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
            {JSON.stringify(requestData, null, 2)}
          </pre>

          {/* Guardian Verify Link helper (DEV/TEST convenience) */}
          {guardianVerifyUrl ? (
            <div style={{ marginTop: 10, fontSize: 14 }}>
              <div style={{ fontWeight: 800, marginBottom: 6 }}>Guardian Verify Link</div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <a href={guardianVerifyUrl} target="_blank" rel="noreferrer">
                  Open guardian verification page
                </a>

                <Button
                  variant="secondary"
                  onClick={async () => {
                    await navigator.clipboard.writeText(guardianVerifyUrl);
                    alert("Guardian link copied to clipboard");
                  }}
                >
                  Copy link
                </Button>
              </div>

              {requestData?.dev?.otp ? (
                <div style={{ marginTop: 8 }}>
                  OTP (DEV): <b>{requestData.dev.otp}</b>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ---------------- DEV ONLY OVERRIDE ---------------- */}
      {DEV_ONLY ? (
        <div
          style={{
            marginTop: 18,
            paddingTop: 16,
            borderTop: "1px dashed #ddd",
          }}
        >
          <p style={{ margin: 0, fontWeight: 700 }}>DEV ONLY</p>
          <p style={{ margin: "6px 0 0", color: "#666" }}>
            Temporary bypass to continue development without OTP flow. Remove later.
          </p>

          <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <div style={{ minWidth: 220 }}>
              <Input
                value={devCode}
                onChange={(e) => setDevCode(e.target.value)}
                placeholder='Type "DEV"'
              />
            </div>

            <Button onClick={enableDevBypass}>Enable Dev Bypass & Continue</Button>

            {devBypassOn ? (
              <Button variant="secondary" onClick={disableDevBypass}>
                Disable Bypass
              </Button>
            ) : null}
          </div>

          {devBypassOn ? (
            <p style={{ marginTop: 10, color: "green" }}>
              Dev bypass is ON ✅ (sessionStorage)
            </p>
          ) : (
            <p style={{ marginTop: 10, color: "#999" }}>Dev bypass is OFF</p>
          )}
        </div>
      ) : null}
      {/* --------------------------------------------------- */}
    </SkeletonPage>
  );
}
