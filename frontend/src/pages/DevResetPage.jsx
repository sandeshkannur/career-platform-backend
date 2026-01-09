// src/pages/DevResetPage.jsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { clearToken } from "../auth";

export default function DevResetPage() {
  const navigate = useNavigate();

  useEffect(() => {
    clearToken();
    navigate("/login", { replace: true });
  }, [navigate]);

  return null;
}
