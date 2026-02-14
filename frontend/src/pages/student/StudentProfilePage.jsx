// frontend/src/pages/student/StudentProfilePage.jsx
import useContent from "../../hooks/useContent";

export default function StudentProfilePage() {
  const { t } = useContent("student.profile");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">
          {t("title", "Profile")}
        </h1>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          {t("subtitle", "Manage your account and preferences.")}
        </p>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-white p-5">
        <div className="text-sm font-medium">
          {t("comingSoonTitle", "Coming soon")}
        </div>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          {t(
            "comingSoonBody",
            "Profile settings will be available in a future release."
          )}
        </p>
      </div>
    </div>
  );
}