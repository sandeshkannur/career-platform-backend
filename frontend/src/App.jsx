// src/App.jsx
import { Toaster } from "sonner";
import AuthGate from "./AuthGate";
import AppRoutes from "./AppRoutes";

export default function App() {
  return (
    <>
      <Toaster richColors position="top-right" />
      <AuthGate>
        <AppRoutes />
      </AuthGate>
    </>
  );
}
