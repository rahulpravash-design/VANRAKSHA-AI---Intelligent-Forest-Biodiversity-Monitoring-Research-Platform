"""Analytics endpoints and the diversity mathematics behind them."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import create_observation


def _spread_observations(client, headers, species, *, days: int, per_day: int = 1) -> None:
    for day in range(days):
        stamp = (datetime.now(UTC) - timedelta(days=day, hours=2)).isoformat()
        for _ in range(per_day):
            create_observation(client, headers, species_id=species.id, observed_at=stamp)


def test_overview_counts(
    client: TestClient, researcher_headers, expert_headers, species_catalogue, gaur, zone
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    body = client.get("/api/v1/analytics/overview").json()
    assert body["species_total"] == len(species_catalogue)
    assert body["species_observed"] == 1
    assert body["observations_total"] == 2
    assert body["observations_verified"] == 1
    assert body["observations_pending"] == 1
    assert body["zones_total"] == 1
    assert body["species_by_category"]["MAMMAL"] >= 3
    assert "not population estimates" in body["disclaimer"]


def test_overview_counts_a_new_species_only_on_first_record(
    client: TestClient, researcher_headers, gaur
) -> None:
    last_year = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    create_observation(client, researcher_headers, species_id=gaur.id, observed_at=last_year)
    create_observation(client, researcher_headers, species_id=gaur.id)
    body = client.get("/api/v1/analytics/overview").json()
    # First recorded a year ago, so it is not "new this month" despite today's record.
    assert body["new_species_this_month"] == 0


def test_trends_bucket_by_month_and_day(
    client: TestClient, researcher_headers, gaur
) -> None:
    _spread_observations(client, researcher_headers, gaur, days=3)
    monthly = client.get("/api/v1/analytics/trends", params={"granularity": "month"}).json()
    assert monthly["granularity"] == "month"
    assert sum(point["observations"] for point in monthly["points"]) == 3

    daily = client.get("/api/v1/analytics/trends", params={"granularity": "day"}).json()
    assert len(daily["points"]) == 3
    assert all(len(point["period"]) == 10 for point in daily["points"])


def test_species_frequency_shares_sum_to_one(
    client: TestClient, researcher_headers, gaur, peafowl
) -> None:
    _spread_observations(client, researcher_headers, gaur, days=3)
    _spread_observations(client, researcher_headers, peafowl, days=1)
    body = client.get("/api/v1/analytics/species-frequency").json()
    assert len(body) == 2
    assert body[0]["common_name"] == "Indian Gaur"
    assert body[0]["detections"] == 3
    assert math.isclose(sum(item["share"] for item in body), 1.0, abs_tol=1e-6)


def test_diversity_indices_on_an_even_community(
    client: TestClient, researcher_headers, species_catalogue
) -> None:
    """Four species with equal detections: Shannon = ln(4), evenness = 1."""
    from app.models import Species

    chosen = species_catalogue[:4]
    for species in chosen:
        assert isinstance(species, Species)
        _spread_observations(client, researcher_headers, species, days=5)

    body = client.get("/api/v1/analytics/diversity").json()
    assert body["species_richness"] == 4
    assert body["sample_count"] == 20
    assert math.isclose(body["shannon_index"], math.log(4), abs_tol=1e-3)
    assert math.isclose(body["shannon_evenness"], 1.0, abs_tol=1e-3)
    assert math.isclose(body["simpson_index"], 0.75, abs_tol=1e-3)
    assert math.isclose(body["inverse_simpson"], 4.0, abs_tol=1e-2)


def test_diversity_flags_a_window_that_is_not_comparable(
    client: TestClient, researcher_headers, gaur
) -> None:
    """Two sampling days cannot be compared against a full season."""
    _spread_observations(client, researcher_headers, gaur, days=2)
    body = client.get("/api/v1/analytics/diversity").json()
    assert body["comparable"] is False
    assert "sampling effort" in body["caveat"]


def test_diversity_becomes_comparable_with_enough_effort(
    client: TestClient, researcher_headers, gaur
) -> None:
    _spread_observations(client, researcher_headers, gaur, days=20)
    assert client.get("/api/v1/analytics/diversity").json()["comparable"] is True


def test_chao1_accounts_for_singletons(
    client: TestClient, researcher_headers, species_catalogue
) -> None:
    """Chao1 exceeds observed richness when rare species dominate."""
    common, rare_one, rare_two = species_catalogue[:3]
    _spread_observations(client, researcher_headers, common, days=10)
    create_observation(client, researcher_headers, species_id=rare_one.id)
    create_observation(client, researcher_headers, species_id=rare_two.id)
    body = client.get("/api/v1/analytics/diversity").json()
    assert body["species_richness"] == 3
    assert body["singletons"] == 2
    assert body["chao1_estimate"] > 3


def test_diversity_on_an_empty_dataset(client: TestClient) -> None:
    body = client.get("/api/v1/analytics/diversity").json()
    assert body["species_richness"] == 0
    assert body["sample_count"] == 0
    assert body["comparable"] is False


def test_zone_comparison_normalises_by_effort(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    far = client.post(
        "/api/v1/zones",
        json={
            "name": "Bandipur East",
            "code": "BND-E",
            "center_latitude": 11.7000,
            "center_longitude": 76.6300,
            "radius_km": 5.0,
        },
        headers=officer_headers,
    ).json()

    # Zone A: 6 detections over 6 days. Zone B: 6 detections in one day.
    for day in range(6):
        stamp = (datetime.now(UTC) - timedelta(days=day, hours=1)).isoformat()
        create_observation(
            client, researcher_headers, species_id=gaur.id, observed_at=stamp
        )
    same_day = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    for _ in range(6):
        create_observation(
            client,
            researcher_headers,
            species_id=gaur.id,
            latitude=11.7001,
            longitude=76.6301,
            observed_at=same_day,
        )

    body = {row["zone_code"]: row for row in client.get("/api/v1/analytics/zones").json()}
    assert body[zone.code]["observations"] == 6
    assert body["BND-E"]["observations"] == 6
    # Same totals, very different effort — the per-active-day rate shows it.
    assert body["BND-E"]["detections_per_active_day"] > body[zone.code][
        "detections_per_active_day"
    ]
    assert far["id"]


def test_seasonal_pattern_covers_twelve_months(
    client: TestClient, researcher_headers, gaur
) -> None:
    create_observation(client, researcher_headers, species_id=gaur.id)
    body = client.get("/api/v1/analytics/seasonal").json()
    assert len(body["buckets"]) == 12
    assert [bucket["month"] for bucket in body["buckets"]] == list(range(1, 13))
    assert sum(bucket["observations"] for bucket in body["buckets"]) == 1
    current_month = datetime.now(UTC).month
    bucket = next(b for b in body["buckets"] if b["month"] == current_month)
    assert bucket["observations"] == 1
    assert bucket["dominant_category"] == "MAMMAL"


def test_ai_performance_report(
    client: TestClient,
    researcher_headers,
    expert_headers,
    species_catalogue,
    thrush_call_bytes,
    thrush,
    observed_at,
) -> None:
    capture = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "species_id": str(thrush.id)},
        files={"audio": ("call.wav", thrush_call_bytes, "audio/wav")},
        headers=researcher_headers,
    ).json()
    client.post(
        f"/api/v1/verifications/observation/{capture['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    body = client.get("/api/v1/analytics/ai-performance", headers=expert_headers).json()
    assert body["predictions_total"] == 1
    assert len(body["confidence_bins"]) == 10
    assert body["reviewed_total"] == 1
    assert "review-conditional" in body["caveat"]


def test_geographic_grid_counts_cells(
    client: TestClient, researcher_headers, gaur
) -> None:
    create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=11.5912, longitude=76.5318
    )
    create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=11.5913, longitude=76.5319
    )
    body = client.get(
        "/api/v1/analytics/geographic",
        params={"precision_deg": 0.01},
        headers=researcher_headers,
    ).json()
    assert len(body["cells"]) == 1
    assert body["cells"][0]["observations"] == 2
    assert body["cells"][0]["distinct_species"] == 1


def test_csv_export_defaults_to_verified_records(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    pending = create_observation(client, researcher_headers, species_id=gaur.id)
    confirmed = create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{confirmed['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    text = client.get("/api/v1/analytics/export.csv", headers=researcher_headers).text
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_lines) == 2  # header + one verified row
    assert str(confirmed["id"]) in text
    assert f",{pending['id']}," not in text

    everything = client.get(
        "/api/v1/analytics/export.csv",
        params={"verified_only": False},
        headers=researcher_headers,
    ).text
    assert len([line for line in everything.splitlines() if line and not line.startswith("#")]) == 3


def test_csv_export_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/analytics/export.csv").status_code == 401


def test_environment_summary_uses_sensor_readings(
    client: TestClient, officer_headers, researcher_headers, zone
) -> None:
    registered = client.post(
        "/api/v1/sensors/devices",
        json={
            "device_code": "node-env-1",
            "name": "Stream node",
            "kind": "ENV_SENSOR",
            "zone_id": zone.id,
        },
        headers=officer_headers,
    ).json()
    now = datetime.now(UTC)
    client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": registered["device_code"],
            "ingest_key": registered["ingest_key"],
            "readings": [
                {
                    "recorded_at": (now - timedelta(minutes=30)).isoformat(),
                    "temperature_c": 21.5,
                    "humidity_pct": 88.0,
                    "sound_level_db": 42.0,
                    "motion_events": 3,
                },
                {
                    "recorded_at": (now - timedelta(minutes=10)).isoformat(),
                    "temperature_c": 23.5,
                    "humidity_pct": 84.0,
                    "sound_level_db": 46.0,
                    "motion_events": 5,
                },
            ],
        },
    )
    body = client.get("/api/v1/analytics/environment", headers=researcher_headers).json()
    assert body["reading_count"] == 2
    assert math.isclose(body["temperature_c"]["mean"], 22.5, abs_tol=0.01)
    assert body["temperature_c"]["min"] == 21.5
    assert body["motion_events_total"] == 8
