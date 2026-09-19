"use client";

/**
 * Demo-build affordances: a persistent label so nobody mistakes the sample
 * catalogue for real records, and a sign-in helper listing the demo accounts.
 *
 * Both render nothing until after mount. `isDemoMode()` reads
 * `window.location`, which does not exist while the server renders, so
 * deciding during the first client paint instead of at render time keeps the
 * markup identical on both sides.
 */

import { useState, useSyncExternalStore } from "react";

import { isDemoMode } from "@/lib/config";

export const DEMO_ACCOUNTS = [
  { role: "Researcher", email: "arjun.k@wri-india.org", password: "Researcher#2026a" },
  { role: "Expert", email: "anjali.menon@wii.res.in", password: "Expert#2026a" },
  { role: "Forest officer", email: "kavitha.raman@forest.gov.in", password: "ForestOfficer#2026" },
  { role: "Administrator", email: "admin@vanraksha.ai", password: "ChangeMe#Admin2026" },
] as const;

/** Never changes after load, so the subscription is a no-op; the point is the
 * separate server snapshot, which keeps the first paint matching the markup. */
const noSubscription = () => () => {};

function useIsDemo(): boolean {
  return useSyncExternalStore(noSubscription, isDemoMode, () => false);
}

export function DemoBanner() {
  const demo = useIsDemo();
  const [dismissed, setDismissed] = useState(false);
  if (!demo || dismissed) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-amber-glow-soft/30 bg-canopy-950/95 px-4 py-2 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center gap-3 text-[11px] text-canopy-200">
        <span className="rounded bg-amber-glow-soft/15 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-amber-glow-soft">
          Demo
        </span>
        <span className="flex-1">
          Sample data from a seeded catalogue — not real field observations. The API is not
          running, so nothing you change here is saved.
        </span>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 rounded px-1.5 py-0.5 text-canopy-400 transition hover:text-canopy-100"
          aria-label="Dismiss demo notice"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function DemoAccounts({
  onPick,
}: {
  onPick: (email: string, password: string) => void;
}) {
  const demo = useIsDemo();
  if (!demo) return null;

  return (
    <div className="mt-6 rounded-lg border border-canopy-700/60 bg-canopy-950/60 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-glow-soft">
        Demo accounts
      </p>
      <p className="mt-1 text-[11px] text-canopy-400">
        Pick one to fill the form. Each role sees a different set of features.
      </p>
      <ul className="mt-2 space-y-1">
        {DEMO_ACCOUNTS.map((account) => (
          <li key={account.email}>
            <button
              type="button"
              onClick={() => onPick(account.email, account.password)}
              className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-[11px] text-canopy-200 transition hover:bg-canopy-800/60"
            >
              <span className="font-medium">{account.role}</span>
              <span className="truncate text-canopy-400">{account.email}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
