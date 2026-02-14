// src/pages/LoginPage.jsx
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Input from "../ui/Input";
import Button from "../ui/Button";
import Page from "../ui/Page";
import Card from "../ui/Card";
import { useSession } from "../hooks/useSession";
import AuthHeader from "../ui/AuthHeader";
import useContent from "../hooks/useContent";

export default function LoginPage() {
  const { login } = useSession();
  const location = useLocation();
  const { t } = useContent("auth.login");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!email || !password) {
      setError(t("missingFields", "Email and password are required"));
      return;
    }

    // ProtectedRoute puts attempted URL into location.state.from
    const redirectTo = location.state?.from?.pathname;

    try {
      await login(email, password, redirectTo);
    } catch (err) {
      setError(err?.message || t("loginFailed", "Login failed"));
    }
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <Page maxWidth="920px">
        <div className="mx-auto grid min-h-screen items-center gap-10 py-10 md:grid-cols-[1fr_420px]">
          <div className="hidden md:block">
            <AuthHeader variant="minimal" />
            <div className="mt-6 space-y-2">
              <h1 className="text-2xl font-semibold text-[var(--text)]">
                {t("headline", "Welcome back")}
              </h1>
              <p className="text-sm text-[var(--text-muted)]">
                {t("blurb", "Sign in to continue your assessment journey.")}
              </p>
            </div>
          </div>

          <div className="w-full max-w-[420px] justify-self-center md:justify-self-end">
            <div className="md:hidden">
              <AuthHeader variant="minimal" />
            </div>

            <Card>
              <div className="space-y-1">
                <h1 className="m-0 text-xl font-semibold text-[var(--text)]">
                  {t("title", "Login")}
                </h1>
                <p className="text-sm text-[var(--text-muted)]">
                  {t("subtitle", "Sign in to continue")}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="mt-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--text)]">
                    {t("emailLabel", "Email")}
                  </label>
                  <div className="mt-2">
                    <Input
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={t("emailPlaceholder", "you@example.com")}
                      autoComplete="email"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--text)]">
                    {t("passwordLabel", "Password")}
                  </label>
                  <div className="mt-2">
                    <Input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={t("passwordPlaceholder", "••••••••")}
                      autoComplete="current-password"
                    />
                  </div>
                </div>

                {error ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {error}
                  </div>
                ) : null}

                <Button type="submit" style={{ width: "100%" }}>
                  {t("submit", "Login")}
                </Button>

                <div className="text-sm text-[var(--text-muted)]">
                  {t("noAccount", "Don’t have an account?")}{" "}
                  <Link className="text-[var(--brand)] hover:underline" to="/signup">
                    {t("createOne", "Create one")}
                  </Link>
                </div>

                <div className="pt-2">
                  <Link className="text-sm text-[var(--text-muted)] hover:underline" to="/">
                    {t("backHome", "← Back to Home")}
                  </Link>
                </div>
              </form>
            </Card>
          </div>
        </div>
      </Page>
    </div>
  );
}
