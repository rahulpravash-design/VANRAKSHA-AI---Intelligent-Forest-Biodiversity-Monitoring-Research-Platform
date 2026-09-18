import type { UserCapabilities } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  icon: string;
  /** Omit to show for every signed-in role. */
  requires?: keyof UserCapabilities;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "layout" },
  { href: "/observations", label: "Observations", icon: "camera" },
  { href: "/species", label: "Species", icon: "leaf" },
  { href: "/map", label: "Map", icon: "map" },
  { href: "/analytics", label: "Analytics", icon: "chart" },
  { href: "/verification", label: "Verification", icon: "check", requires: "can_verify" },
  { href: "/alerts", label: "Alerts", icon: "bell" },
  { href: "/sensors", label: "Sensors", icon: "radio" },
  { href: "/research", label: "Research", icon: "flask", requires: "can_run_experiments" },
  { href: "/admin/users", label: "Users", icon: "users", requires: "can_manage_users" },
];
