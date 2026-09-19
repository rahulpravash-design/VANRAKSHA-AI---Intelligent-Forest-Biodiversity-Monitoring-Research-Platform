export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_PREFIX = process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1";
export const API_BASE = `${API_URL}${API_PREFIX}`;

/**
 * True when the app should answer from the bundled demo snapshot instead of a
 * live API (see lib/demo-mode.ts).
 *
 * NEXT_PUBLIC_API_URL is inlined at build time, so a deployment built without
 * it keeps the localhost default — an address no visitor can reach. That
 * combination, a loopback API on a page served from somewhere else, is what
 * marks a demo build, and inferring it means the demo needs no build-time
 * variable to enable itself. Set NEXT_PUBLIC_DEMO_MODE to "1" or "0" to force
 * the decision.
 */
export function isDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "1") return true;
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "0") return false;
  const apiIsLoopback = /^https?:\/\/(localhost|127\.0\.0\.1)([:/]|$)/i.test(API_URL);
  const pageIsLoopback = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
  return apiIsLoopback && !pageIsLoopback;
}

export const MAP_TILE_URL =
  process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
export const MAP_ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ?? "© OpenStreetMap contributors";

const [defaultLat, defaultLon] = (
  process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER ?? "11.4102,76.6950"
)
  .split(",")
  .map(Number);
export const DEFAULT_MAP_CENTER: [number, number] = [defaultLat ?? 11.4102, defaultLon ?? 76.695];
export const DEFAULT_MAP_ZOOM = Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_ZOOM ?? 8);
