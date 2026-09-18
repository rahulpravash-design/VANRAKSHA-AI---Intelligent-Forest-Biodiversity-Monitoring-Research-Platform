export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_PREFIX = process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1";
export const API_BASE = `${API_URL}${API_PREFIX}`;

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
