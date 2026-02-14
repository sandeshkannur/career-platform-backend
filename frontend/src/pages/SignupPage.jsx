// src/pages/SignupPage.jsx
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Page from "../ui/Page";
import Card from "../ui/Card";
import AuthHeader from "../ui/AuthHeader";
import useContent from "../hooks/useContent";
import Input from "../ui/Input";
import Button from "../ui/Button";

export default function SignupPage() {
  const navigate = useNavigate();
  const { t } = useContent("auth.signup");
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
    <div className="min-h-screen bg-[var(--bg)]">
      <Page maxWidth="920px">
        <div className="mx-auto grid min-h-screen items-center gap-10 py-10 md:grid-cols-[1fr_420px]">
          <div className="hidden md:block">
            <AuthHeader variant="minimal" />
            <div className="mt-6 space-y-2">
              <h1 className="text-2xl font-semibold text-[var(--text)]">
                {t("headline", "Create your account")}
              </h1>
              <p className="text-sm text-[var(--text-muted)]">
                {t("blurb", "Signup is UI-only for now. Backend wiring will come later.")}
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
                  {t("title", "Signup")}
                </h1>
                <p className="text-sm text-[var(--text-muted)]">
                  {t("subtitle", "Create an account to continue.")}
                </p>
              </div>

              <form onSubmit={onSubmit} className="mt-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--text)]">
                    {t("fullNameLabel", "Full name")}
                  </label>
                  <div className="mt-2">
                    <Input
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder={t("fullNamePlaceholder", "Your name")}
                      autoComplete="name"
                    />
                  </div>
                </div>

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
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={t("passwordPlaceholder", "Min 8 characters")}
                      type="password"
                      autoComplete="new-password"
                    />
                  </div>
                </div>

                <Button type="submit" disabled={!canSubmit} style={{ width: "100%" }}>
                  {t("submit", "Create account")}
                </Button>

                <div className="text-sm text-[var(--text-muted)]">
                  {t("alreadyHave", "Already have an account?")}{" "}
                  <Link className="text-[var(--brand)] hover:underline" to="/login">
                    {t("loginLink", "Login")}
                  </Link>
                </div>

                <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--text-muted)]">
                  {t("note", "Note: Signup is UI-only in this step. We will wire the backend later.")}
                </div>
              </form>
            </Card>
          </div>
        </div>
      </Page>
    </div>
  );
}
