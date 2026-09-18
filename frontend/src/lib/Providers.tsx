"use client";

import { useEffect } from "react";

import { useAuthStore } from "@/lib/auth-store";
import { useOfflineStore } from "@/lib/offline-store";

/** Runs the one-time auth bootstrap (check localStorage → validate against
 * /auth/me) and the offline-queue bootstrap (connectivity listeners + an
 * initial drain attempt) as soon as the app mounts on the client. */
export function Providers({ children }: { children: React.ReactNode }) {
  const bootstrap = useAuthStore((state) => state.bootstrap);
  const initOffline = useOfflineStore((state) => state.init);
  useEffect(() => {
    void bootstrap();
    initOffline();
  }, [bootstrap, initOffline]);
  return <>{children}</>;
}
