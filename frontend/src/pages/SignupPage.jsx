// src/pages/SignupPage.jsx
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Page from "../ui/Page";
import Card from "../ui/Card";
import AuthHeader from "../ui/AuthHeader";

export default function SignupPage() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const canSubmit = useMemo(() => {
    return (
      String(fullName).trim().length >= 2 &&
      String(email).includes("@") &&
      String(password).length >= 8
    );
  }, [fullName, email, password]);

  function onSubmit(e) {
    e.preventDefault();
    navigate("/login", { replace: true });
  }

  return (
    <Page>
      <AuthHeader />
      <Card>
        <h1>Signup</h1>
        <p>Create an account to continue.</p>

        <form onSubmit={onSubmit} style={{ marginTop: 12, display: "grid", gap: 10 }}>
          <div>
            <label style={{ display: "block", fontSize: 12, marginBottom: 6 }}>
              Full name
            </label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              autoComplete="name"
              style={{ width: "100%", padding: 10, border: "1px solid #ddd", borderRadius: 8 }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, marginBottom: 6 }}>
              Email
            </label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              style={{ width: "100%", padding: 10, border: "1px solid #ddd", borderRadius: 8 }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, marginBottom: 6 }}>
              Password
            </label>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters"
              type="password"
              autoComplete="new-password"
              style={{ width: "100%", padding: 10, border: "1px solid #ddd", borderRadius: 8 }}
            />
          </div>

          <button
            type="submit"
            disabled={!canSubmit}
            style={{
              padding: 10,
              borderRadius: 10,
              border: "1px solid #ddd",
              background: canSubmit ? "#111" : "#f2f2f2",
              color: canSubmit ? "#fff" : "#777",
              cursor: canSubmit ? "pointer" : "not-allowed",
              fontWeight: 600,
            }}
          >
            Create account
          </button>

          <p style={{ fontSize: 12 }}>
            Already have an account? <Link to="/login">Login</Link>
          </p>

          <p style={{ fontSize: 12, color: "#666" }}>
            Note: Signup is UI-only in this step. We will wire the backend later.
          </p>
        </form>
      </Card>
    </Page>
  );
}
