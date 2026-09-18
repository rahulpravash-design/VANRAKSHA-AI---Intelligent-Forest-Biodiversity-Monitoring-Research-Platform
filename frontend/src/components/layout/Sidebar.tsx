"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuthStore } from "@/lib/auth-store";

import { NAV_ITEMS } from "./nav";
import { NavIcon } from "./NavIcon";

export function Sidebar() {
  const pathname = usePathname();
  const capabilities = useAuthStore((state) => state.capabilities);

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-canopy-800 bg-canopy-950/80 py-6 lg:flex">
      <Link href="/dashboard" className="mb-8 flex items-center gap-2 px-6">
        <span className="text-xl">🌳</span>
        <span className="font-display text-lg font-semibold text-canopy-50">VANRAKSHA</span>
      </Link>
      <nav className="flex flex-1 flex-col gap-1 px-3">
        {NAV_ITEMS.filter((item) => !item.requires || capabilities?.[item.requires]).map(
          (item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-canopy-800 text-amber-glow-soft"
                    : "text-canopy-300 hover:bg-canopy-900 hover:text-canopy-50"
                )}
              >
                <NavIcon name={item.icon} className="h-4.5 w-4.5" />
                {item.label}
              </Link>
            );
          }
        )}
      </nav>
      <div className="px-6 pt-4 text-[11px] leading-relaxed text-canopy-500">
        Detections, not population estimates. AI identifications require
        expert verification.
      </div>
    </aside>
  );
}
