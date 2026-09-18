"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { useAuthStore } from "@/lib/auth-store";

import { NavIcon } from "./NavIcon";

const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrator",
  RESEARCHER: "Researcher",
  FOREST_OFFICER: "Forest Officer",
  EXPERT: "Expert",
  VIEWER: "Viewer",
};

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
