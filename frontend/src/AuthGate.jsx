// src/AuthGate.jsx
import { useSession } from "./hooks/useSession";
import LoadingScreen from "./components/LoadingScreen";
import { SessionProvider } from "./session/SessionContext";

export default function AuthGate({ children }) {
  const session = useSession();

  if (session.bootstrapping) {
    return <LoadingScreen label="Loading session…" />;
  }

  return <SessionProvider value={session}>{children}</SessionProvider>;
}
