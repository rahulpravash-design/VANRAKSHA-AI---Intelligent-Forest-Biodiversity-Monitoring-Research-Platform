"""Device registration and sensor ingest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

DEVICE = {
    "device_code": "vrk-node-01",
    "name": "Salt lick multi-sensor node",
    "kind": "MULTI_SENSOR_NODE",
    "latitude": 11.5915,
    "longitude": 76.5320,
    "firmware_version": "1.2.0",
    "report_interval_minutes": 30,
}


def _register(client: TestClient, headers: dict[str, str], zone_id: int | None = None) -> dict:
    payload = {**DEVICE, "zone_id": zone_id}
    response = client.post("/api/v1/sensors/devices", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_returns_the_ingest_key_once(
    client: TestClient, officer_headers, zone
) -> None:
    device = _register(client, officer_headers, zone.id)
    assert device["ingest_key"].startswith("vrk_")
    assert device["device_code"] == "VRK-NODE-01"

    # Reading the device back never exposes the key again.
    listed = client.get("/api/v1/sensors/devices", headers=officer_headers).json()
    assert "ingest_key" not in listed[0]


def test_registration_requires_an_officer(client: TestClient, researcher_headers) -> None:
    assert client.post("/api/v1/sensors/devices", json=DEVICE).status_code == 401
    assert (
        client.post(
            "/api/v1/sensors/devices", json=DEVICE, headers=researcher_headers
        ).status_code
        == 403
    )


def test_duplicate_device_code_is_rejected(client: TestClient, officer_headers) -> None:
    _register(client, officer_headers)
    assert (
        client.post("/api/v1/sensors/devices", json=DEVICE, headers=officer_headers).status_code
        == 409
    )


def test_ingest_accepts_a_batch(client: TestClient, officer_headers, zone) -> None:
    device = _register(client, officer_headers, zone.id)
    now = datetime.now(UTC)
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [
                {
                    "recorded_at": (now - timedelta(minutes=offset)).isoformat(),
                    "temperature_c": 22.0 + offset / 60,
                    "humidity_pct": 80.0,
                    "sound_level_db": 40.0,
                    "motion_events": offset % 3,
                    "battery_volts": 3.9,
                }
                for offset in (60, 30, 5)
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 3
    assert body["rejected"] == 0

    stored = client.get("/api/v1/sensors/readings", headers=officer_headers).json()
    assert stored["total"] == 3
    assert stored["items"][0]["zone_id"] == zone.id


def test_ingest_rejects_a_wrong_key(client: TestClient, officer_headers) -> None:
    device = _register(client, officer_headers)
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": "vrk_not-the-real-key",
            "readings": [{"recorded_at": datetime.now(UTC).isoformat(), "temperature_c": 20.0}],
        },
    )
    assert response.status_code == 401


def test_ingest_rejects_an_unknown_device_with_the_same_message(
    client: TestClient, officer_headers
) -> None:
    """Identical wording, so the endpoint cannot enumerate deployed node codes."""
    device = _register(client, officer_headers)
    reading = [{"recorded_at": datetime.now(UTC).isoformat(), "temperature_c": 20.0}]
    unknown = client.post(
        "/api/v1/sensors/readings",
        json={"device_code": "NO-SUCH-NODE", "ingest_key": "vrk_x", "readings": reading},
    )
    wrong_key = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": "vrk_wrong",
            "readings": reading,
        },
    )
    assert unknown.status_code == wrong_key.status_code == 401
    assert unknown.json()["detail"] == wrong_key.json()["detail"]


def test_ingest_rejects_a_future_timestamp(client: TestClient, officer_headers) -> None:
    """A node with a wrong clock would otherwise corrupt the anomaly baseline."""
    device = _register(client, officer_headers)
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [
                {
                    "recorded_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    "temperature_c": 20.0,
                }
            ],
        },
    ).json()
    assert response["accepted"] == 0
    assert response["rejected"] == 1
    assert "clock" in response["warnings"][0]


def test_ingest_rejects_an_old_backfill(client: TestClient, officer_headers) -> None:
    device = _register(client, officer_headers)
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [
                {
                    "recorded_at": (datetime.now(UTC) - timedelta(days=90)).isoformat(),
                    "temperature_c": 20.0,
                }
            ],
        },
    ).json()
    assert response["rejected"] == 1
    assert "backfill" in response["warnings"][0]


def test_ingest_is_idempotent_on_the_same_timestamp(
    client: TestClient, officer_headers
) -> None:
    """A node retrying after a lost acknowledgement must not double-count."""
    device = _register(client, officer_headers)
    stamp = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    payload = {
        "device_code": device["device_code"],
        "ingest_key": device["ingest_key"],
        "readings": [{"recorded_at": stamp, "temperature_c": 21.0}],
    }
    first = client.post("/api/v1/sensors/readings", json=payload).json()
    second = client.post("/api/v1/sensors/readings", json=payload).json()
    assert first["accepted"] == 1
    assert second["accepted"] == 0
    assert second["rejected"] == 1


def test_ingest_validates_physical_ranges(client: TestClient, officer_headers) -> None:
    device = _register(client, officer_headers)
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "humidity_pct": 250.0,  # impossible
                }
            ],
        },
    )
    assert response.status_code == 422


def test_device_health_reports_status(client: TestClient, officer_headers) -> None:
    device = _register(client, officer_headers)
    health = client.get("/api/v1/sensors/devices/health", headers=officer_headers).json()
    assert health[0]["status"] == "never_reported"

    client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [
                {"recorded_at": datetime.now(UTC).isoformat(), "battery_volts": 3.7}
            ],
        },
    )
    health = client.get("/api/v1/sensors/devices/health", headers=officer_headers).json()
    assert health[0]["status"] == "online"
    assert health[0]["battery_volts"] == 3.7
    assert health[0]["reading_count"] == 1


def test_device_marked_late_then_offline(client: TestClient, officer_headers) -> None:
    device = _register(client, officer_headers)
    now = datetime.now(UTC)
    # Interval is 30 minutes: 90 minutes silent is "late", 5 hours is "offline".
    client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [{"recorded_at": (now - timedelta(minutes=90)).isoformat()}],
        },
    )
    assert (
        client.get("/api/v1/sensors/devices/health", headers=officer_headers).json()[0]["status"]
        == "late"
    )


def test_rotating_the_key_invalidates_the_old_one(
    client: TestClient, admin_headers, officer_headers
) -> None:
    device = _register(client, officer_headers)
    rotated = client.post(
        f"/api/v1/sensors/devices/{device['id']}/rotate-key", headers=admin_headers
    ).json()
    assert rotated["ingest_key"] != device["ingest_key"]

    reading = [{"recorded_at": datetime.now(UTC).isoformat(), "temperature_c": 20.0}]
    old = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": reading,
        },
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": rotated["ingest_key"],
            "readings": reading,
        },
    )
    assert new.status_code == 200


def test_a_deactivated_device_cannot_ingest(
    client: TestClient, officer_headers
) -> None:
    device = _register(client, officer_headers)
    client.patch(
        f"/api/v1/sensors/devices/{device['id']}",
        json={"is_active": False},
        headers=officer_headers,
    )
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "device_code": device["device_code"],
            "ingest_key": device["ingest_key"],
            "readings": [{"recorded_at": datetime.now(UTC).isoformat()}],
        },
    )
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"]
