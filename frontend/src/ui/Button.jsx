export default function Button({ children, style, ...props }) {
  return (
    <button
      {...props}
      style={{
        padding: "10px 12px",
        fontWeight: 600,
        cursor: "pointer",
        borderRadius: 10,
        border: "1px solid #ddd",
        background: "#fff",
        ...style,
      }}
    >
      {children}
    </button>
  );
}
