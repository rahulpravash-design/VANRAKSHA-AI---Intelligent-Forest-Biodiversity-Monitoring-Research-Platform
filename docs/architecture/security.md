# Security

## Authentication

* Passwords: bcrypt when available, a pure-stdlib PBKDF2-HMAC-SHA256
  fallback otherwise (`app/core/security.py`) — the API works even without
  native wheels, and a stored hash is transparently upgraded to the
  preferred scheme on the user's next successful login.
* JWT access (30 min default) + refresh (14 days default) token pair.
  Refresh rotates: presenting a refresh token issues a new pair *and* revokes
  the one just used, so a stolen refresh token is usable once before the
  legitimate client's own next refresh invalidates it (`RevokedToken`).
* Login and registration failures return identical wording for "wrong
  password" and "unknown email" so the endpoint cannot be used to enumerate
  accounts, and login is rate-limited per IP and per email
  (`app/core/rate_limit.py` — in-process; move to a shared store behind more
  than one worker).

## Authorization

Five roles (`ADMIN`, `RESEARCHER`, `FOREST_OFFICER`, `EXPERT`, `VIEWER`).
Public self-registration is restricted to `RESEARCHER` and `VIEWER` at the
schema level (`RegisterRequest`) *and* again in the service
(`auth_service.register`), so a caller that somehow bypasses the schema still
cannot mint an administrator. Every other role is created by an administrator
via `POST /users`.

Route guards are dependency functions built by
`app/core/deps.py::require_roles(*roles)` — a closure, not a callable class,
because FastAPI resolves a dependency's type annotations through its
`__globals__`, which a class *instance* does not carry; combined with
`from __future__ import annotations`, a callable-class guard leaves
`CurrentUser` an unresolved forward reference and breaks OpenAPI generation
outright. Worth knowing if you add a new guard.

## Location privacy

See `docs/architecture/overview.md#location-privacy`. In short: coordinates
of CR/EN/VU or explicitly flagged species are snapped to a coarse grid
(`app/services/geo.py::snap_to_grid`, cell-centre snapped to avoid a visible
south-west bias) for any viewer without precise-location rights, at the
serialisation layer so no endpoint can forget. Every affected payload —
observation reads, lists, the map GeoJSON feed, the CSV export, the gridded
geographic-distribution analytics — carries a `location_generalised: true`
flag rather than silently substituting a fake-precise coordinate.

## Uploads

Every image and audio upload is validated by decoding it, not by trusting
the filename or `Content-Type` header (`app/services/storage.py`,
`ai/preprocessing/{image,audio}.py`). Stored filenames are derived from the
*detected* format and a SHA-256 digest of the content — never from the
client-supplied name — which removes path traversal and filename spoofing as
a class of problem and makes identical uploads storage-free to repeat.

## Devices

A field node authenticates with a per-device ingest key
(`vrk_<random>`), issued once at registration and stored only as a hash
(`app/services/sensor_service.py`). A captured node can write its own sensor
readings and nothing else — it never holds a user token.

## Audit trail

`app/services/audit.py` records authentication events, permission denials,
every data-changing action, and alert lifecycle changes to `audit_logs`,
including the actor's IP and user agent. It is intentionally the mechanism
that would answer "who looked up where the tigers are?" after the fact.

## What is out of scope for this version

* Rate limiting is per-process; a multi-worker/multi-replica deployment needs
  a shared store (Redis, or a database-backed limiter).
* No email verification or password-reset flow yet — an administrator resets
  a locked-out account via `PATCH /users/{id}`.
* CORS origins, the JWT secret, and the bootstrap admin password all have
  insecure defaults meant only for local development;
  `Settings.warn_insecure()` checks these and logs on startup when
  `VANRAKSHA_ENV=production`, but does not refuse to start — a deployment
  should treat those warnings as blocking.
