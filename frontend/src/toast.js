// src/toast.js
import { toast } from "sonner";

export function toastError(err, fallback = "Something went wrong") {
  const msg =
    err?.message ||
    (typeof err === "string" ? err : null) ||
    fallback;

  toast.error(msg);
}

export function toastSuccess(message) {
  toast.success(message);
}

export function toastInfo(message) {
  toast(message);
}
