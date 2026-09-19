"""Snapshot the live API's own responses into the demo fixture bundle.

Run against a freshly seeded local instance. Capturing real responses (rather
than hand-writing fixtures) keeps the demo payloads structurally identical to
what the API actually returns, so the demo cannot drift from the contract.
"""

import json
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"

ACCOUNTS = [
    ("admin@vanraksha.ai", "ChangeMe#Admin2026", "ADMIN"),
    ("kavitha.raman@forest.gov.in", "ForestOfficer#2026", "FOREST_OFFICER"),
    ("arjun.k@wri-india.org", "Researcher#2026a", "RESEARCHER"),
    ("meera.pillai@atree.org", "Researcher#2026b", "RESEARCHER"),
    ("anjali.menon@wii.res.in", "Expert#2026a", "EXPERT"),
    ("suresh.nair@ncbs.res.in", "Expert#2026b", "EXPERT"),
    ("viewer@vanraksha.ai", "Viewer#2026", "VIEWER"),
]


def call(path, token=None, params=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"  !! {path} -> HTTP {exc.code} {exc.read()[:160]!r}")
        return None


def login(email, password):
    body = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(
        f"{BASE}/auth/login", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["access_token"]


tokens = {}
for email, password, role in ACCOUNTS:
    tokens[email] = login(email, password)
print(f"logged in {len(tokens)} accounts")

admin = tokens["admin@vanraksha.ai"]
expert = tokens["anjali.menon@wii.res.in"]

bundle = {"get": {}, "byId": {}, "roles": {}, "logins": {}}


def grab(key, path, token=None, params=None):
    data = call(path, token, params)
    if data is None:
        return None
    bundle["get"][key] = data
    size = len(json.dumps(data))
    print(f"  {key:44s} {size:>8,}b")
    return data


print("\npublic + shared reads")
species_page = grab("/species", "/species", params={"limit": 200})
grab("/species/categories", "/species/categories")
observations_page = grab("/observations", "/observations", params={"limit": 60})
grab("/ai/status", "/ai/status")
grab("/zones", "/zones")
grab("/zones/geojson", "/zones/geojson")
grab("/zones/observations/geojson", "/zones/observations/geojson", params={"limit": 500})

print("\nanalytics")
grab("/analytics/overview", "/analytics/overview")
grab("/analytics/trends", "/analytics/trends")
grab("/analytics/species-frequency", "/analytics/species-frequency")
grab("/analytics/diversity", "/analytics/diversity")
grab("/analytics/zones", "/analytics/zones")
grab("/analytics/seasonal", "/analytics/seasonal")
grab("/analytics/geographic", "/analytics/geographic")
grab("/analytics/ai-performance", "/analytics/ai-performance", admin)

print("\nauthenticated reads (admin view)")
grab("/observations/stats/summary", "/observations/stats/summary", admin)
queue_page = grab("/verifications/queue", "/verifications/queue", expert, {"limit": 50})
grab("/verifications/stats", "/verifications/stats", expert)
grab("/alerts", "/alerts", admin, {"limit": 50})
grab("/sensors/devices", "/sensors/devices", admin)
grab("/sensors/devices/health", "/sensors/devices/health", admin)
grab("/research/variants", "/research/variants", admin)
grab("/research", "/research", admin)
grab("/users", "/users", admin, {"limit": 100})

print("\nper-id detail")
species_ids = [row["id"] for row in (species_page or {}).get("items", [])]
bundle["byId"]["/species/:id"] = {}
for sid in species_ids:
    detail = call(f"/species/{sid}")
    if detail:
        bundle["byId"]["/species/:id"][str(sid)] = detail
print(f"  species details: {len(bundle['byId']['/species/:id'])}")

obs_ids = {row["id"] for row in (observations_page or {}).get("items", [])}
# Queue rows nest the observation rather than carrying a bare id.
obs_ids |= {row["observation"]["id"] for row in (queue_page or {}).get("items", [])}
bundle["byId"]["/observations/:id"] = {}
for oid in sorted(obs_ids):
    detail = call(f"/observations/{oid}", expert)
    if detail:
        bundle["byId"]["/observations/:id"][str(oid)] = detail
print(f"  observation details: {len(bundle['byId']['/observations/:id'])}")

print("\nper-role identity")
for email, password, role in ACCOUNTS:
    token = tokens[email]
    me = call("/auth/me", token)
    mine = call("/observations/me", token, {"limit": 30})
    bundle["roles"][email] = {"me": me, "observationsMine": mine}
    bundle["logins"][email] = {"password": password, "role": role}
    caps = sum(1 for v in (me or {}).get("capabilities", {}).values() if v is True)
    print(f"  {email:34s} {role:16s} caps={caps}")

out = sys.argv[1]
media_root = pathlib.Path(sys.argv[2])
storage_root = pathlib.Path(sys.argv[3])

# Media URLs are absolute against the capture host, which cannot resolve from a
# deployed demo. Rewrite them to paths served next to the bundle, and copy only
# the files the fixtures actually reference.
serialised = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
referenced = sorted(
    set(re.findall(r"http://(?:127\.0\.0\.1|localhost):8000/media/([^\"]+)", serialised))
)
serialised = serialised.replace("http://127.0.0.1:8000/media/", "/demo/media/")
serialised = serialised.replace("http://localhost:8000/media/", "/demo/media/")

# Audio is excluded: the 82 synthetic WAVs are 24MB, which is not worth
# committing for a demo. Spectrograms (PNG) are kept, so acoustic observations
# still show their evidence — the detail page renders one whenever it exists.
serialised = re.sub(r'"audio_url":"[^"]*"', '"audio_url":null', serialised)

copied = skipped = excluded = 0
copied_bytes = 0
for rel in referenced:
    if rel.endswith(".wav"):
        excluded += 1
        continue
    source = storage_root / rel
    if not source.is_file():
        skipped += 1
        continue
    target = media_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    copied += 1
    copied_bytes += target.stat().st_size
print(f"audio excluded: {excluded} files")

print(f"\nmedia referenced={len(referenced)} copied={copied} missing={skipped}")
print(f"media bytes: {copied_bytes:,} ({copied_bytes / 1_048_576:.1f} MB)")

with open(out, "w") as handle:
    handle.write(serialised)
print(f"wrote {out}  ({len(serialised):,} bytes)")

if "127.0.0.1:8000" in serialised or "localhost:8000" in serialised:
    print("ERROR: capture-host URLs survived the rewrite")
    sys.exit(1)
missing = [k for k, v in bundle["get"].items() if v is None]
if missing:
    print(f"MISSING: {missing}")
    sys.exit(1)
