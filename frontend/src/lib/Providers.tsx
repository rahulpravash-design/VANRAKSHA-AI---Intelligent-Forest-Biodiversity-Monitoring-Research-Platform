"use client";

import { useEffect } from "react";

import { useAuthStore } from "@/lib/auth-store";

/** Runs the one-time auth bootstrap (check localStorage → validate against
 * /auth/me) as soon as the app mounts on the client. */
export function Providers({ children }: { children: React.ReactNode }) {
  const bootstrap = useAuthStore((state) => state.bootstrap);
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);
  return <>{children}</>;
}
