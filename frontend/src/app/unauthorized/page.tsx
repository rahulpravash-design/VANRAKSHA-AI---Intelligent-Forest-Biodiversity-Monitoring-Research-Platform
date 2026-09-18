import Link from "next/link";

import { LinkButton } from "@/components/ui/Button";

export default function UnauthorizedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canopy-950 px-4 text-center">
      <span className="text-5xl">🔒</span>
      <h1 className="font-display text-2xl font-semibold text-canopy-50">
        You don&apos;t have access to this page
      </h1>
      <p className="max-w-sm text-sm text-canopy-300">
        This section requires a different role. If you believe this is a
        mistake, contact an administrator.
      </p>
      <div className="mt-2 flex gap-3">
        <LinkButton href="/dashboard" variant="secondary">
          Back to dashboard
        </LinkButton>
        <Link href="/" className="px-4 py-2 text-sm text-canopy-300 hover:text-canopy-50">
          Home
        </Link>
      </div>
    </div>
  );
}
