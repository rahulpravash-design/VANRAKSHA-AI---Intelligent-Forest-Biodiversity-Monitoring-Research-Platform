"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui/Button";
import { useAuthStore } from "@/lib/auth-store";
import type { UserCapabilities } from "@/lib/types";

/** Gate an entire route group behind sign-in. Reads `status` (not just
 * whether `user` is set) so a page never flashes its signed-out state while
 * the token check from `bootstrap()` is still in flight. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((state) => state.status);
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canopy-950 text-canopy-300">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  return <>{children}</>;
}

/** Gate a page behind one capability flag (see UserCapabilities), redirecting
 * to /unauthorized rather than silently rendering nothing. */
export function RequireCapability({
  capability,
  children,
}: {
  capability: keyof UserCapabilities;
  children: React.ReactNode;
}) {
  const capabilities = useAuthStore((state) => state.capabilities);
  const router = useRouter();

  useEffect(() => {
    if (capabilities && !capabilities[capability]) router.replace("/unauthorized");
  }, [capabilities, capability, router]);

  if (!capabilities || !capabilities[capability]) return null;
  return <>{children}</>;
}
