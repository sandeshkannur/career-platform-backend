// src/pages/LoginPage.jsx
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Input from "../ui/Input";
import Button from "../ui/Button";
import Page from "../ui/Page";
import Card from "../ui/Card";
import { useSession } from "../hooks/useSession";
import AuthHeader from "../ui/AuthHeader";

export default function LoginPage() {
  const { login } = useSession();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!email || !password) {
      setError("Email and password are required");
      return;
    }

    // ProtectedRoute puts attempted URL into location.state.from
    const redirectTo = location.state?.from?.pathname;

    try {
      await login(email, password, redirectTo);
    } catch (err) {
      setError(err?.message || "Login failed");
    }
  }

  return (
    <Page maxWidth="520px">
      <AuthHeader />
      <Card>
        <h1 style={{ marginTop: 0 }}>Login</h1>
        <p style={{ color: "#666" }}>Sign in to continue</p>

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", marginTop: 12 }}>Email</label>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />

          <label style={{ display: "block", marginTop: 12 }}>Password</label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
          />

          {error ? (
            <p style={{ color: "red", marginTop: 10, marginBottom: 0 }}>{error}</p>
          ) : null}

          <div style={{ marginTop: 14 }}>
            <Button type="submit" style={{ width: "100%" }}>
              Login
            </Button>
          </div>
        </form>

        <div style={{ marginTop: 12 }}>
          <p style={{ margin: 0 }}>
            Don’t have an account? <Link to="/signup">Create one</Link>
          </p>
        </div>

        <div style={{ marginTop: 12 }}>
          <Link to="/">← Back to Home</Link>
        </div>
      </Card>
    </Page>
  );
}
