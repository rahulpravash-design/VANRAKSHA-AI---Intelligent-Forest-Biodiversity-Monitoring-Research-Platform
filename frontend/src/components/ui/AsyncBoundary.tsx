"use client";

import type { ReactNode } from "react";

import { Spinner } from "./Button";

export function AsyncBoundary<T>({
  loading,
  error,
  data,
  children,
  empty,
}: {
  loading: boolean;
  error: string | null;
  data: T | null;
  children: (data: T) => ReactNode;
  empty?: ReactNode;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-canopy-300">
        <Spinner /> Loading…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-alert-critical/40 bg-alert-critical/10 px-4 py-3 text-sm text-red-200">
        {error}
      </div>
    );
  }
  if (data === null || (Array.isArray(data) && data.length === 0)) {
    return <>{empty ?? <p className="py-8 text-center text-sm text-canopy-400">Nothing here yet.</p>}</>;
  }
  return <>{children(data)}</>;
}
