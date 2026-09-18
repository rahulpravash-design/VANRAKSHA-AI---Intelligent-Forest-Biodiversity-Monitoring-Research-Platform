"""Anomaly detection and alert handling.

The behavioural contract under test is as much about *language* as about
statistics: a flagged window must be described as unusual and offered for
investigation, never diagnosed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import create_observation

FORBIDDEN_CLAIMS = ("poach", "poaching", "illegal", "crime", "damage confirmed")


def _seed_history(client, headers, species, *, weeks: int, per_day: int) -> None:
    """A steady baseline of detections over several weeks."""
    for day in range(weeks * 7):
        stamp = (datetime.now(UTC) - timedelta(days=day + 7, hours=6)).isoformat()
        for _ in range(per_day):
            create_observation(client, headers, species_id=species.id, observed_at=stamp)


# --------------------------------------------------------------------------- #
# the detector
# --------------------------------------------------------------------------- #
def test_steady_history_raises_nothing(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    # Keep the most recent week at the same level.
    for day in range(7):
        stamp = (datetime.now(UTC) - timedelta(days=day, hours=6)).isoformat()
        for _ in range(3):
            create_observation(
                client, researcher_headers, species_id=gaur.id, observed_at=stamp
            )
    response = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evaluated_windows"] > 0
    assert body["anomalies_found"] == 0
    assert body["alerts_created"] == 0


def test_a_collapse_in_detections_is_flagged(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    """Ten weeks at 3/day, then a week at zero: the drop must be noticed."""
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    response = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    )
    body = response.json()
    assert body["anomalies_found"] >= 1
    assert body["alerts_created"] >= 1

    alert = body["alerts"][0]
    assert alert["kind"] in {"BIODIVERSITY_ANOMALY", "SENSOR_MALFUNCTION"}
    assert alert["status"] == "OPEN"
    assert "Unusual biodiversity observation pattern" in alert["title"]
    assert "human investigation" in alert["message"]
    assert alert["candidate_causes"]
    assert alert["confirmed_cause"] is None


def test_an_alert_never_asserts_a_cause(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    """The system flags the pattern; it does not accuse anyone of anything."""
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=4)
    body = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()
    assert body["alerts"], "expected the drop to be flagged"
    for alert in body["alerts"]:
        text = f"{alert['title']} {alert['message']}".lower()
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in text, f"alert asserted a cause: {claim}"
        # Human activity may appear as a *hypothesis*, never as a conclusion.
        assert any("Human activity" in cause for cause in alert["candidate_causes"])
    assert "does not infer a cause" in body["note"]


def test_detection_can_score_without_raising_alerts(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    body = client.post(
        "/api/v1/alerts/detect",
        json={"zone_id": zone.id, "create_alerts": False},
        headers=officer_headers,
    ).json()
    assert body["anomalies_found"] >= 1
    assert body["alerts_created"] == 0
    assert client.get("/api/v1/alerts", headers=officer_headers).json()["total"] == 0


def test_the_same_window_is_not_flagged_twice(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    first = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()
    second = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()
    assert first["alerts_created"] >= 1
    assert second["alerts_created"] == 0


def test_too_little_history_produces_no_findings(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    """Three days of data cannot support a baseline, so nothing is claimed."""
    for day in range(3):
        stamp = (datetime.now(UTC) - timedelta(days=day)).isoformat()
        create_observation(client, researcher_headers, species_id=gaur.id, observed_at=stamp)
    body = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()
    assert body["anomalies_found"] == 0


def test_scores_endpoint_returns_unflagged_windows_too(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    client.post("/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers)
    everything = client.get(
        "/api/v1/alerts/anomaly/scores", headers=officer_headers
    ).json()
    flagged = client.get(
        "/api/v1/alerts/anomaly/scores",
        params={"anomalies_only": True},
        headers=officer_headers,
    ).json()
    assert everything["total"] > flagged["total"] >= 1
    score = flagged["items"][0]
    assert score["baseline_value"] is not None
    assert score["method"] in {"ROBUST_Z", "ISOLATION_FOREST", "ENSEMBLE"}


# --------------------------------------------------------------------------- #
# alert lifecycle
# --------------------------------------------------------------------------- #
def test_alert_lifecycle_records_the_human_conclusion(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    alert = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()["alerts"][0]

    investigating = client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"status": "INVESTIGATING"},
        headers=officer_headers,
    ).json()
    assert investigating["status"] == "INVESTIGATING"
    assert investigating["acknowledged_at"] is not None

    resolved = client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={
            "status": "RESOLVED",
            "resolution_notes": "Survey team was on leave; no fieldwork took place.",
            "confirmed_cause": "Gap in data collection",
        },
        headers=officer_headers,
    ).json()
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"] is not None
    assert resolved["confirmed_cause"] == "Gap in data collection"


def test_closing_an_alert_requires_notes(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    """An alert closed with no explanation teaches the platform nothing."""
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    alert = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()["alerts"][0]
    response = client.patch(
        f"/api/v1/alerts/{alert['id']}", json={"status": "DISMISSED"}, headers=officer_headers
    )
    assert response.status_code == 422
    assert "resolution notes" in response.json()["detail"]


def test_a_researcher_cannot_close_an_alert(
    client: TestClient, researcher_headers, officer_headers, gaur, zone
) -> None:
    _seed_history(client, researcher_headers, gaur, weeks=10, per_day=3)
    alert = client.post(
        "/api/v1/alerts/detect", json={"zone_id": zone.id}, headers=officer_headers
    ).json()["alerts"][0]
    response = client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"status": "RESOLVED", "resolution_notes": "nothing to see"},
        headers=researcher_headers,
    )
    assert response.status_code == 403


def test_device_sweep_flags_a_silent_node(
    client: TestClient, officer_headers, zone
) -> None:
    registered = client.post(
        "/api/v1/sensors/devices",
        json={
            "device_code": "node-quiet-1",
            "name": "Ridge camera",
            "kind": "CAMERA_TRAP",
            "zone_id": zone.id,
            "report_interval_minutes": 30,
        },
        headers=officer_headers,
    ).json()
    created = client.post("/api/v1/alerts/device-sweep", headers=officer_headers).json()
    assert len(created) == 1
    alert = created[0]
    assert alert["kind"] == "DEVICE_OFFLINE"
    assert registered["device_code"] in alert["title"]
    assert "Battery depleted or power failure" in alert["candidate_causes"]
    # Sweeping again must not duplicate an open alert.
    assert client.post("/api/v1/alerts/device-sweep", headers=officer_headers).json() == []


# --------------------------------------------------------------------------- #
# the detector in isolation
# --------------------------------------------------------------------------- #
def test_robust_baseline_resists_outliers() -> None:
    import numpy as np

    from ai.anomaly.robust_z import fit_robust_baseline

    steady = np.array([20.0] * 20 + [500.0])  # one wild spike
    baseline = fit_robust_baseline(steady)
    assert baseline.median == 20.0
    # A mean/std baseline would have sigma ~100 here and hide everything after.
    assert baseline.sigma < 20.0


def test_robust_baseline_handles_a_constant_series() -> None:
    import numpy as np

    from ai.anomaly.robust_z import fit_robust_baseline

    baseline = fit_robust_baseline(np.array([9.0] * 12))
    assert baseline.median == 9.0
    # Poisson dispersion assumption, so a real jump is still detectable.
    assert baseline.sigma == 3.0


def test_isolation_forest_ranks_an_outlier_highest() -> None:
    import numpy as np

    from ai.anomaly.isolation_forest import IsolationForest, average_path_length

    rng = np.random.default_rng(3)
    normal = rng.normal(0.0, 1.0, size=(200, 3))
    outlier = np.array([[12.0, -11.0, 13.0]])
    forest = IsolationForest(n_trees=64, subsample_size=128, random_state=7).fit(normal)
    scores = forest.score_samples(np.vstack([normal[:50], outlier]))
    assert scores[-1] == scores.max()
    assert scores[-1] > np.percentile(scores[:-1], 99)
    assert average_path_length(1) == 0.0
    assert average_path_length(2) == 1.0


def test_isolation_forest_threshold_follows_contamination() -> None:
    import numpy as np

    from ai.anomaly.isolation_forest import IsolationForest

    rng = np.random.default_rng(5)
    data = rng.normal(size=(300, 2))
    forest = IsolationForest(n_trees=64, subsample_size=128, random_state=1).fit(data)
    strict = forest.threshold_for(0.01)
    loose = forest.threshold_for(0.25)
    assert strict > loose
    assert forest.predict(data, contamination=0.1).mean() < 0.2


def test_detector_reports_direction_and_candidate_causes() -> None:
    from ai.anomaly.detector import BiodiversityAnomalyDetector, candidate_causes
    from ai.config import AIConfig

    counts: dict[date, float] = {}
    today = date.today()
    for day in range(70, 7, -1):
        counts[today - timedelta(days=day)] = 20.0
    for day in range(7, 0, -1):
        counts[today - timedelta(days=day)] = 1.0

    findings = BiodiversityAnomalyDetector(
        AIConfig(window_days=7, baseline_days=56, z_threshold=3.0)
    ).detect("detections.total", counts)
    flagged = [f for f in findings if f.is_anomaly]
    assert flagged, "a 20x drop should be flagged"
    latest = flagged[-1]
    assert latest.direction == "drop"
    assert latest.robust_z < -3.0

    causes = candidate_causes(latest, device_gap=True)
    assert causes[0] == "Sensor or camera malfunction"
    assert "Seasonal migration or phenology" in causes
    # Never a conclusion, only hypotheses.
    assert all("poach" not in cause.lower() for cause in causes)


def test_detector_distinguishes_a_data_gap_from_a_decline() -> None:
    """An incomplete window promotes the collection-gap hypothesis."""
    from ai.anomaly.detector import BiodiversityAnomalyDetector, candidate_causes
    from ai.config import AIConfig

    counts: dict[date, float] = {}
    today = date.today()
    for day in range(70, 6, -1):
        counts[today - timedelta(days=day)] = 15.0
    # Surveying continued, but only two days in the last week produced records.
    counts[today - timedelta(days=4)] = 2.0
    counts[today] = 1.0

    findings = BiodiversityAnomalyDetector(
        AIConfig(window_days=7, baseline_days=56, z_threshold=3.0)
    ).detect("detections.total", counts, end_date=today)
    latest = findings[-1]
    assert latest.active_days == 2
    assert latest.is_anomaly
    causes = candidate_causes(latest)
    assert causes[0] == "Gap in data collection or connectivity"


def test_detector_evaluates_the_period_after_data_stops() -> None:
    """A zone that went silent is the signal that matters most."""
    from ai.anomaly.detector import BiodiversityAnomalyDetector
    from ai.config import AIConfig

    counts: dict[date, float] = {}
    today = date.today()
    for day in range(70, 13, -1):  # data ends a fortnight ago
        counts[today - timedelta(days=day)] = 12.0

    detector = BiodiversityAnomalyDetector(
        AIConfig(window_days=7, baseline_days=56, z_threshold=3.0)
    )
    anchored_to_data = detector.detect("detections.total", counts)
    anchored_to_today = detector.detect("detections.total", counts, end_date=today)

    assert not any(f.is_anomaly for f in anchored_to_data), (
        "windowing only to the last populated day hides the silence"
    )
    assert any(f.is_anomaly for f in anchored_to_today)
    assert anchored_to_today[-1].observed == 0.0
    assert anchored_to_today[-1].active_days == 0
