/**
 * A thin fetch wrapper around the VANRAKSHA API.
 *
 * Handles: the Authorization header, JSON encoding/decoding, multipart
 * uploads, and turning a non-2xx response into a typed `ApiError` the UI can
 * read `.detail` / `.fields` / `.context` off of directly — the same shape
 * `app/core/errors.py` produces on the backend.
 */

import { API_BASE, isDemoMode } from "./config";
import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  status: number;
  fields?: Record<string, string>;
  context?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.fields = body.fields;
    this.context = body.context;
  }
}

const TOKEN_STORAGE_KEY = "vanraksha.tokens";

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
  expires_at: string;
}

/** Read/write the token pair. Wrapped in try/catch: a private-browsing tab
 * or a blocked-storage environment must not crash the app, only degrade it
 * to "signed out". */
export function readStoredTokens(): StoredTokens | null {
  try {
    const raw = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

export function writeStoredTokens(tokens: StoredTokens | null): void {
  try {
    if (tokens) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    /* ignore — storage may be unavailable */
  }
}

let refreshPromise: Promise<StoredTokens | null> | null = null;

async function refreshTokens(): Promise<StoredTokens | null> {
  const current = readStoredTokens();
  if (!current?.refresh_token) return null;
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: current.refresh_token }),
    });
    if (!response.ok) {
      writeStoredTokens(null);
      return null;
    }
    const data = await response.json();
    const tokens: StoredTokens = {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at: data.expires_at,
    };
    writeStoredTokens(tokens);
    return tokens;
  } catch {
    return null;
  }
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: FormData;
  params?: Record<string, string | number | boolean | undefined | null>;
  auth?: boolean;
  /** Set true for a request whose 401 must not trigger a refresh (e.g. login itself). */
  skipRefreshOn401?: boolean;
}

function buildQuery(params?: RequestOptions["params"]): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = { detail: `Request failed with status ${response.status}` };
  try {
    body = await response.json();
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(response.status, body);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, form, params, auth = true, skipRefreshOn401 = false } = options;

  if (isDemoMode()) {
    // Imported here rather than at module scope so the snapshot loader stays
    // out of the bundle for builds that talk to a real API.
    const { demoRequest } = await import("./demo-mode");
    return demoRequest<T>(path, method, json, params);
  }

  const url = `${API_BASE}${path}${buildQuery(params)}`;
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (form) {
    body = form;
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  if (auth) {
    const tokens = readStoredTokens();
    if (tokens?.access_token) headers.Authorization = `Bearer ${tokens.access_token}`;
  }

  let response = await fetch(url, { method, headers, body });

  if (response.status === 401 && auth && !skipRefreshOn401) {
    refreshPromise ??= refreshTokens().finally(() => {
      refreshPromise = null;
    });
    const refreshed = await refreshPromise;
    if (refreshed) {
      headers.Authorization = `Bearer ${refreshed.access_token}`;
      response = await fetch(url, { method, headers, body });
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/csv")) return (await response.text()) as unknown as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"], options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET", params }),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", json }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
  postForm: <T>(path: string, form: FormData, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", form }),
  raw: request,
};

export function mediaUrl(path: string): string {
  if (path.startsWith("http")) return path;
  // Demo snapshots carry site-relative media paths; prefixing them with the
  // (unreachable) API origin would break every image.
  if (isDemoMode()) return path;
  return `${API_BASE.replace(/\/api\/v1$/, "")}${path}`;
}
