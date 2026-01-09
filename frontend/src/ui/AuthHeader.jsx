// src/ui/AuthHeader.jsx
import { Link, useLocation } from "react-router-dom";

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  const isActive = pathname === to;

  return (
    <Link
      to={to}
      style={{
        textDecoration: "none",
        fontWeight: isActive ? 700 : 600,
        borderBottom: isActive ? "2px solid #111" : "2px solid transparent",
        paddingBottom: 2,
        color: "#111",
      }}
    >
      {children}
    </Link>
  );
}

export default function AuthHeader() {
  return (
    <div style={{ borderBottom: "1px solid #eee", background: "#fff" }}>
      <div
        style={{
          maxWidth: 980,
          margin: "0 auto",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <Link to="/" style={{ textDecoration: "none", color: "#111" }}>
          <span style={{ fontWeight: 800 }}>CareerPlatform</span>
        </Link>

        <div style={{ display: "flex", gap: 14, marginLeft: 12 }}>
          <NavLink to="/login">Login</NavLink>
          <NavLink to="/signup">Signup</NavLink>
        </div>

        <div style={{ marginLeft: "auto" }}>
          <Link
            to="/pricing"
            style={{
              textDecoration: "none",
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid #ddd",
              color: "#111",
              fontWeight: 600,
            }}
          >
            Pricing
          </Link>
        </div>
      </div>
    </div>
  );
}
