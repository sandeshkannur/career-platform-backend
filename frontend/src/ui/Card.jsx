// src/ui/Card.jsx
export default function Card({ children, className = "" }) {
  return (
    <div
      className={[
        "rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm",
        className,
      ].join(" ")}
    >
      {children}
    </div>
  );
}