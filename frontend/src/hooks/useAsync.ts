"use client";

/**
 * A small data-fetching hook: runs `fn` on mount and whenever `deps` change,
 * tracking loading/error/data. Exists so every page does not hand-roll the
 * same three `useState` calls — see components/ui/AsyncBoundary.tsx for the
 * matching render helper.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";

interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: React.DependencyList): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  // Keep the ref pointed at the latest `fn` from an effect rather than during
  // render — mutating a ref synchronously in the render body is what React's
  // stricter hooks rules (aimed at React Compiler compatibility) flag, even
  // though this specific "always call the latest closure" idiom is safe.
  useEffect(() => {
    fnRef.current = fn;
  });

  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    // Reset to the loading state for this run before the request starts.
    // This is the standard shape for a manual data-fetching hook and does not
    // feed back into this effect's own dependencies, so it cannot cascade.
    setLoading(true);
    setError(null);
    fnRef
      .current()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Something went wrong.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload };
}
