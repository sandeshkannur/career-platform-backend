// src/ui/Page.jsx
export default function Page({ children, maxWidth = 960 }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        padding: "32px 16px",
        display: "flex",
        justifyContent: "center",
        background: "#fafafa",
      }}
    >
      <div style={{ width: "100%", maxWidth }}>{children}</div>
    </div>
  );
}
