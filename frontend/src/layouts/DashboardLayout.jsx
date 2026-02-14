// frontend/src/layouts/DashboardLayout.jsx
import React, { useMemo, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

function classNames(...xs) {
  return xs.filter(Boolean).join(" ");
}

function NavItem({ to, label, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        classNames(
          "block rounded-lg px-3 py-2 text-sm font-medium transition",
          isActive
            ? "bg-[var(--brand-primary)] text-white"
            : "text-[var(--text-primary)] hover:bg-white hover:border hover:border-[var(--border)]"
        )
      }
    >
      {label}
    </NavLink>
  );
}

export default function DashboardLayout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close drawer on route change (mobile)
  React.useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const nav = useMemo(
    () => [
      { to: "/student/dashboard", label: "Dashboard" },
      { to: "/student/assessment", label: "Assessment" },
      { to: "/student/results", label: "Results" },
      { to: "/student/profile", label: "Profile" },
    ],
    []
  );

  return (
    <div className="min-h-screen bg-[var(--bg-app)] text-[var(--text-primary)]">
      {/* Mobile top bar */}
      <div className="sticky top-0 z-30 border-b border-[var(--border)] bg-white md:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center justify-center rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm"
          >
            ☰
          </button>

          <div className="text-sm font-semibold">Student Portal</div>

          <div className="w-[42px]" />
        </div>
      </div>

      {/* Layout grid */}
      <div className="mx-auto flex max-w-[1400px]">
        {/* Desktop sidebar */}
        <aside className="hidden h-screen w-[260px] shrink-0 border-r border-[var(--border)] bg-white md:flex md:flex-col">
          <div className="px-5 py-4">
            <div className="text-sm font-semibold">Student Portal</div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              Clean & safe experience
            </div>
          </div>

          <nav className="flex-1 space-y-1 px-3">
            {nav.map((item) => (
              <NavItem key={item.to} to={item.to} label={item.label} />
            ))}
          </nav>

          {/* Footer / profile stub (future: show user name + tier) */}
          <div className="border-t border-[var(--border)] px-5 py-4">
            <div className="text-xs text-[var(--text-muted)]">Signed in</div>
            <div className="text-sm font-medium">Student</div>
          </div>
        </aside>

        {/* Mobile drawer */}
        {open ? (
          <div className="fixed inset-0 z-40 md:hidden">
            <div
              className="absolute inset-0 bg-black/30"
              onClick={() => setOpen(false)}
            />
            <div className="absolute left-0 top-0 h-full w-[280px] bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
                <div className="text-sm font-semibold">Student Portal</div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm"
                >
                  ✕
                </button>
              </div>

              <nav className="space-y-1 px-3 py-3">
                {nav.map((item) => (
                  <NavItem
                    key={item.to}
                    to={item.to}
                    label={item.label}
                    onClick={() => setOpen(false)}
                  />
                ))}
              </nav>

              <div className="absolute bottom-0 w-full border-t border-[var(--border)] px-4 py-4">
                <div className="text-xs text-[var(--text-muted)]">Signed in</div>
                <div className="text-sm font-medium">Student</div>
              </div>
            </div>
          </div>
        ) : null}

        {/* Main content */}
        <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
          <div className="mx-auto w-full max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}