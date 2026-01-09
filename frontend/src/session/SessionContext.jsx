// src/session/SessionContext.jsx
import { createContext, useContext } from "react";

const SessionContext = createContext(null);

export function SessionProvider({ value, children }) {
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSessionContext() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSessionContext must be used inside SessionProvider");
  return ctx;
}
