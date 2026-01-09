// src/pages/guardian/GuardianVerifyPage.jsx
import React, { useMemo, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Best-effort decode JWT payload (for display only).
 * Not trusted. Backend verification is source of truth.
 */
function tryDecodeJwtPayload(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    const payload = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");

    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/**
 * Build API URL without auth/session dependencies.
 * - Uses VITE_API_BASE_URL if set (prod)
 * - Otherwise relies on Vite proxy (dev)
 */
function buildApiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL || "";
  return `${base}${path}`;
}

export default function GuardianVerifyPage() {
  const [searchParams] = useSearchParams();
  const tokenFromUrl = searchParams.get("token") || "";

  // ✅ NEW: allow token to be pasted manually (prevents URL truncation issues)
  const [token, setToken] = useState(tokenFromUrl);

  // Keep token in sync if page is opened with a token in URL
  useEffect(() => {
    setToken(tokenFromUrl);
  }, [tokenFromUrl]);

  const decoded = useMemo(() => (token ? tryDecodeJwtPayload(token) : null), [token]);

  const guardianEmail =
    decoded?.guardian_email ||
    decoded?.guardianEmail ||
    decoded?.email ||
    "(will confirm after verification)";

  const [otp, setOtp] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [status, setStatus] = useState("idle"); // idle | success | error
  const [message, setMessage] = useState("");

  // Quick client-side sanity (not authoritative)
  const tokenLooksValid = useMemo(() => {
    if (!token) return false;
    const parts = token.split(".");
    return parts.length === 3 && token.length > 30; // basic heuristic
  }, [token]);

  async function onSubmit(e) {
    e.preventDefault();

    if (!tokenLooksValid) {
      setStatus("error");
      setMessage(
        "Token looks missing or incomplete. Please paste the full token (it may have been truncated in the URL)."
      );
      return;
    }
    if (!otp.trim()) {
      setStatus("error");
      setMessage("Please enter the OTP.");
      return;
    }

    setSubmitting(true);
    setStatus("idle");
    setMessage("");

    try {
      const res = await fetch(buildApiUrl("/v1/consent/verify"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // IMPORTANT: no Authorization header here (public guardian flow)
        body: JSON.stringify({ token, otp: otp.trim() }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const errMsg = data?.detail || data?.message || "Verification failed.";
        setStatus("error");
        setMessage(errMsg);
        return;
      }

      if (data?.verified === true || data?.status === "verified") {
        setStatus("success");
        setMessage("Consent verified successfully. You may now close this tab.");
      } else {
        setStatus("error");
        setMessage(data?.message || "Verification rejected.");
      }
    } catch (err) {
      setStatus("error");
      setMessage(err?.message || "Network error. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ maxWidth: 620, margin: "40px auto", padding: 16 }}>
      <h1 style={{ fontSize: 22, marginBottom: 8 }}>Guardian Consent Verification</h1>
      <p style={{ marginTop: 0, opacity: 0.85 }}>
        Enter the OTP you received to verify consent for the student.
      </p>

      <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8, marginBottom: 16 }}>
        <div style={{ fontSize: 13, opacity: 0.8 }}>Guardian</div>
        <div style={{ fontWeight: 600 }}>{guardianEmail}</div>

        <div style={{ fontSize: 13, opacity: 0.8, marginTop: 12 }}>
          Verification link
        </div>
        <div style={{ fontSize: 13, marginTop: 6 }}>
          {tokenLooksValid ? (
            <span>Token present ✅</span>
          ) : (
            <span style={{ color: "#b23" }}>
              Token missing or incomplete ❌ (paste token below)
            </span>
          )}
        </div>

        <div style={{ fontSize: 13, opacity: 0.8, marginTop: 12 }}>
          Token (paste full token if needed)
        </div>
        <textarea
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste the full consent token here (if the URL token is missing/truncated)"
          rows={4}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #ccc",
            marginTop: 6,
            fontSize: 12,
            fontFamily: "monospace",
          }}
        />
      </div>

      <form onSubmit={onSubmit}>
        <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>OTP</label>
        <input
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
          placeholder="Enter OTP"
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #ccc",
            marginBottom: 12,
          }}
        />

        <button
          type="submit"
          disabled={submitting}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 8,
            border: "none",
            cursor: submitting ? "not-allowed" : "pointer",
          }}
        >
          {submitting ? "Verifying..." : "Verify Consent"}
        </button>
      </form>

      {status === "success" && (
        <div style={{ marginTop: 16, padding: 12, borderRadius: 8, border: "1px solid #cfe9cf" }}>
          ✅ {message}
          <div style={{ marginTop: 8, fontSize: 13, opacity: 0.9 }}>
            You can safely close this tab/window now.
          </div>
        </div>
      )}

      {status === "error" && (
        <div style={{ marginTop: 16, padding: 12, borderRadius: 8, border: "1px solid #f3c2c2" }}>
          ❌ {message}
          <div style={{ marginTop: 8, fontSize: 13, opacity: 0.9 }}>
            Tip: If you copied a long link, the token might be truncated. Paste the full token above and try again.
          </div>
        </div>
      )}
    </div>
  );
}
