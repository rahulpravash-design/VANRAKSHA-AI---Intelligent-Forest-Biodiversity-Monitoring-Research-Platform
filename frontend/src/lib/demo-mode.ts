/**
 * Demo mode — serves captured API responses so the frontend works with no
 * backend behind it.
 *
 * The payloads in `public/demo/data.json` are snapshots of real responses from
 * a seeded instance (see scripts/seed.py, which builds a synthetic catalogue —
 * these are not real field sightings), captured rather than hand-written so
 * they cannot drift from the API's actual shapes.
 *
 * Reads are answered from the snapshot; writes are refused with an explanation,
 * because there is nowhere to persist them.
 */

import { ApiError, readStoredTokens } from "./api";

const DEMO_TOKEN_PREFIX = "demo:";

interface DemoBundle {
  get: Record<string, unknown>;
  byId: Record<string, Record<string, unknown>>;
  roles: Record<string, { me: unknown; observationsMine: unknown }>;
  logins: Record<string, { password: string; role: string }>;
}

interface PageShape {
  items: Record<string, unknown>[];
  total: number;
  limit?: number;
  offset?: number;
}

let bundlePromise: Promise<DemoBundle> | null = null;

function loadBundle(): Promise<DemoBundle> {
  bundlePromise ??= fetch("/demo/data.json")
    .then((response) => {
      if (!response.ok) throw new Error(`demo data ${response.status}`);
      return response.json() as Promise<DemoBundle>;
    })
    .catch((error) => {
      bundlePromise = null;
      throw error;
    });
  return bundlePromise;
}

function currentEmail(): string | null {
  const token = readStoredTokens()?.access_token;
  return token?.startsWith(DEMO_TOKEN_PREFIX)
    ? token.slice(DEMO_TOKEN_PREFIX.length)
    : null;
}

function isPage(value: unknown): value is PageShape {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as PageShape).items) &&
    typeof (value as PageShape).total === "number"
  );
}

type Params = Record<string, string | number | boolean | undefined | null> | undefined;

function matches(row: Record<string, unknown>, key: string, wanted: unknown): boolean {
  const actual = row[key];
  if (actual == null) return false;
  if (typeof actual === "object") {
    // Nested reference (e.g. a row's `species`): compare on its id.
    const id = (actual as Record<string, unknown>).id;
    return String(id) === String(wanted);
  }
  return String(actual) === String(wanted);
}

/** Apply the filters and slicing the UI actually sends, so lists stay interactive. */
function applyParams(page: PageShape, params: Params): PageShape {
  let items = page.items;

  const search = params?.search;
  if (typeof search === "string" && search.trim()) {
    const needle = search.trim().toLowerCase();
    items = items.filter((row) =>
      ["common_name", "scientific_name", "family", "genus", "notes", "name", "full_name", "email"]
        .map((field) => row[field])
        .some((value) => typeof value === "string" && value.toLowerCase().includes(needle))
    );
  }

  for (const [key, column] of [
    ["category", "category"],
    ["conservation_status", "conservation_status"],
    ["verification_status", "verification_status"],
    ["observation_type", "observation_type"],
    ["role", "role"],
    ["status", "status"],
    ["zone_id", "zone_id"],
    ["species_id", "species"],
  ] as const) {
    const wanted = params?.[key];
    if (wanted !== undefined && wanted !== null && wanted !== "") {
      items = items.filter((row) => matches(row, column, wanted));
    }
  }

  if (params?.threatened_only === true || params?.threatened_only === "true") {
    const threatened = new Set(["CR", "EN", "VU"]);
    items = items.filter((row) => threatened.has(String(row.conservation_status)));
  }

  const total = items.length;
  const offset = Number(params?.offset ?? 0) || 0;
  const rawLimit = Number(params?.limit ?? total);
  const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? rawLimit : total;

  return { ...page, items: items.slice(offset, offset + limit), total, limit, offset };
}

const ID_ROUTES: [RegExp, string][] = [
  [/^\/species\/(\d+)$/, "/species/:id"],
  [/^\/observations\/(\d+)$/, "/observations/:id"],
];

function resolveRead(bundle: DemoBundle, path: string, params: Params): unknown {
  if (path === "/auth/me") {
    const email = currentEmail();
    const profile = email ? bundle.roles[email] : undefined;
    if (!profile) throw new ApiError(401, { detail: "Not authenticated." });
    return profile.me;
  }

  if (path === "/observations/me") {
    const email = currentEmail();
    const profile = email ? bundle.roles[email] : undefined;
    if (!profile) throw new ApiError(401, { detail: "Not authenticated." });
    const mine = profile.observationsMine;
    return isPage(mine) ? applyParams(mine, params) : mine;
  }

  const direct = bundle.get[path];
  if (direct !== undefined) {
    return isPage(direct) ? applyParams(direct, params) : direct;
  }

  for (const [pattern, key] of ID_ROUTES) {
    const id = path.match(pattern)?.[1];
    if (id !== undefined) {
      const record = bundle.byId[key]?.[id];
      if (record === undefined) {
        throw new ApiError(404, { detail: "Not included in the demo dataset." });
      }
      return record;
    }
  }

  throw new ApiError(404, {
    detail: "This view needs the live API, which is not running in the demo.",
  });
}

async function login(bundle: DemoBundle, body: unknown): Promise<unknown> {
  const { email, password } = (body ?? {}) as { email?: string; password?: string };
  const account = email ? bundle.logins[email.trim().toLowerCase()] : undefined;
  if (!account || account.password !== password) {
    throw new ApiError(401, {
      detail: "Incorrect email or password. The demo accounts are listed below the form.",
    });
  }
  const expires = new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString();
  return {
    access_token: `${DEMO_TOKEN_PREFIX}${email!.trim().toLowerCase()}`,
    refresh_token: `${DEMO_TOKEN_PREFIX}${email!.trim().toLowerCase()}`,
    token_type: "bearer",
    expires_at: expires,
  };
}

const WRITE_REFUSAL =
  "The demo runs without a backend, so changes cannot be saved. " +
  "Deploy the API (see docs/guides/deployment.md) to enable this.";

export async function demoRequest<T>(
  path: string,
  method: string,
  body: unknown,
  params: Params
): Promise<T> {
  const bundle = await loadBundle();

  if (method === "GET") {
    return resolveRead(bundle, path, params) as T;
  }
  if (path === "/auth/login") {
    return (await login(bundle, body)) as T;
  }
  if (path === "/auth/logout") {
    return undefined as T;
  }
  if (path === "/auth/register") {
    throw new ApiError(403, {
      detail: "Registration is disabled in the demo. Use one of the demo accounts below.",
    });
  }
  throw new ApiError(403, { detail: WRITE_REFUSAL });
}
