import type { ReactNode } from "react";

export function InlineAlert({ tone = "info", children }: { tone?: "info" | "error"; children: ReactNode }) {
  const classes =
    tone === "error"
      ? "border-alert-critical/40 bg-alert-critical/10 text-red-200"
      : "border-amber-glow/40 bg-amber-glow/10 text-amber-glow-soft";
  return <div className={`rounded-lg border px-3 py-2 text-sm ${classes}`}>{children}</div>;
}
