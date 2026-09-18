"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { useAuthStore } from "@/lib/auth-store";
import { formatDateTime } from "@/lib/format";
import { useOfflineStore } from "@/lib/offline-store";

import { NavIcon } from "./NavIcon";

const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrator",
  RESEARCHER: "Researcher",
  FOREST_OFFICER: "Forest Officer",
  EXPERT: "Expert",
  VIEWER: "Viewer",
};

function SyncStatus() {
  const supported = useOfflineStore((state) => state.supported);
  const isOnline = useOfflineStore((state) => state.isOnline);
  const pendingCount = useOfflineStore((state) => state.pendingCount);
  const items = useOfflineStore((state) => state.items);
  const syncing = useOfflineStore((state) => state.syncing);
  const syncNow = useOfflineStore((state) => state.syncNow);
  const discard = useOfflineStore((state) => state.discard);
  const [open, setOpen] = useState(false);

  if (!supported || (isOnline && pendingCount === 0)) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 rounded-full border border-canopy-700 bg-canopy-900 px-3 py-1.5 text-xs font-medium text-canopy-100 hover:bg-canopy-800"
      >
        <span
          className={`h-2 w-2 rounded-full ${isOnline ? "bg-amber-glow" : "bg-alert-critical"}`}
          aria-hidden
        />
        {isOnline ? `Syncing ${pendingCount}` : `Offline · ${pendingCount} queued`}
      </button>
      {open ? (
        <div className="absolute right-0 top-12 z-30 w-72 overflow-hidden rounded-lg border border-canopy-700 bg-canopy-900 shadow-canopy">
          <div className="flex items-center justify-between border-b border-canopy-800 px-4 py-2.5">
            <p className="text-xs text-canopy-300">
              {isOnline
                ? "Back online — observations captured offline upload automatically."
                : "No connection. Observations are saved on this device and upload once you're back online."}
            </p>
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-3 text-xs text-canopy-400">Nothing queued.</p>
          ) : (
            <ul className="max-h-64 overflow-y-auto">
              {items.map((item) => (
                <li key={item.id} className="border-b border-canopy-800 px-4 py-2.5 last:border-0">
                  <p className="text-xs text-canopy-200">
                    Queued {formatDateTime(item.queuedAt)}
                  </p>
                  {item.lastError ? (
                    <p className="mt-0.5 text-xs text-red-300">{item.lastError}</p>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void discard(item.id)}
                    className="mt-1 text-xs text-canopy-400 hover:text-canopy-100 hover:underline"
                  >
                    Discard
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            disabled={!isOnline || syncing}
            onClick={() => void syncNow()}
            className="w-full border-t border-canopy-800 px-4 py-2.5 text-left text-xs font-medium text-amber-glow-soft hover:bg-canopy-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function Topbar({ title }: { title?: string }) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="flex h-16 items-center justify-between border-b border-canopy-800 bg-canopy-950/70 px-4 backdrop-blur-sm lg:px-8">
      <div>
        {title ? (
          <h1 className="font-display text-lg font-semibold text-canopy-50">{title}</h1>
        ) : null}
      </div>
      <div className="relative flex items-center gap-3">
        <SyncStatus />
        {user ? <Badge tone="green">{ROLE_LABEL[user.role] ?? user.role}</Badge> : null}
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="flex items-center gap-2 rounded-full border border-canopy-700 bg-canopy-900 px-3 py-1.5 text-sm text-canopy-100 hover:bg-canopy-800"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-canopy-600 text-xs font-semibold uppercase">
            {user?.full_name?.charAt(0) ?? "?"}
          </span>
          {user?.full_name}
        </button>
        {menuOpen ? (
          <div className="absolute right-0 top-12 z-30 w-48 overflow-hidden rounded-lg border border-canopy-700 bg-canopy-900 shadow-canopy">
            <Link
              href="/profile"
              className="flex items-center gap-2 px-4 py-2.5 text-sm text-canopy-100 hover:bg-canopy-800"
              onClick={() => setMenuOpen(false)}
            >
              <NavIcon name="settings" className="h-4 w-4" /> Profile
            </Link>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-canopy-100 hover:bg-canopy-800"
              onClick={async () => {
                setMenuOpen(false);
                await logout();
                router.replace("/login");
              }}
            >
              <NavIcon name="logout" className="h-4 w-4" /> Sign out
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
