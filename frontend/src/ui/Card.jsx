// src/ui/Card.jsx
export default function Card({ children }) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 8,
        padding: 24,
        boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
      }}
    >
      {children}
    </div>
  );
}
