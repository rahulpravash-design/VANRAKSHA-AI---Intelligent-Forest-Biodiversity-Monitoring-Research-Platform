"""Expert verification workflow and AI-versus-expert agreement."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_observation


def test_queue_contains_pending_observations_oldest_first(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    from datetime import UTC, datetime, timedelta

    older = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    first = create_observation(
        client, researcher_headers, species_id=gaur.id, observed_at=older
    )
    second = create_observation(client, researcher_headers, species_id=gaur.id)

    queue = client.get("/api/v1/verifications/queue", headers=expert_headers).json()
    assert queue["total"] == 2
    ids = [item["observation"]["id"] for item in queue["items"]]
    assert ids == [first["id"], second["id"]]
    assert queue["items"][0]["waiting_days"] >= 0


def test_confirm_sets_the_verified_species(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM", "comments": "Clear dorsal ridge and white stockings."},
        headers=expert_headers,
    )
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert detail["verification_status"] == "CONFIRMED"
    assert detail["verified_species"]["id"] == gaur.id
    assert detail["verified_at"] is not None
    assert detail["final_species"]["id"] == gaur.id


def test_correct_replaces_the_species_and_keeps_the_original(
    client: TestClient, researcher_headers, expert_headers, gaur, peafowl
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={
            "decision": "CORRECT",
            "corrected_species_id": peafowl.id,
            "comments": "Misidentified: this is a peafowl.",
        },
        headers=expert_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["corrected_species"]["id"] == peafowl.id
    assert body["previous_species"]["id"] == gaur.id

    detail = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert detail["verification_status"] == "CORRECTED"
    assert detail["verified_species"]["id"] == peafowl.id
    # The recorder's original report is preserved for provenance.
    assert detail["species"]["id"] == gaur.id
    assert detail["final_species"]["id"] == peafowl.id


def test_reject_leaves_no_verified_species(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "REJECT", "comments": "Image too blurred to identify."},
        headers=expert_headers,
    )
    detail = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert detail["verification_status"] == "REJECTED"
    assert detail["verified_species"] is None
    assert detail["final_species"] is None


def test_uncertain_decision_is_recorded_as_such(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "UNCERTAIN", "comments": "Could be gaur or a feral bovid."},
        headers=expert_headers,
    )
    detail = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert detail["verification_status"] == "UNCERTAIN"
    assert detail["verified_species"] is None


def test_correct_requires_a_species(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CORRECT"},
        headers=expert_headers,
    )
    assert response.status_code == 422
    assert "corrected_species_id" in str(response.json()["fields"])


def test_correcting_to_the_same_species_is_rejected(
    client: TestClient, researcher_headers, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CORRECT", "corrected_species_id": gaur.id},
        headers=expert_headers,
    )
    assert response.status_code == 422
    assert "CONFIRM" in response.json()["detail"]


def test_confirming_an_observation_without_a_species_is_rejected(
    client: TestClient, researcher_headers, expert_headers
) -> None:
    observation = create_observation(client, researcher_headers, species_id=None)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    assert response.status_code == 422
    assert "no reported species" in response.json()["detail"]


def test_a_researcher_cannot_verify(
    client: TestClient, researcher_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=researcher_headers,
    )
    assert response.status_code == 403


def test_verification_history_is_append_only(
    client: TestClient, researcher_headers, expert_headers, gaur, peafowl
) -> None:
    """A second review is added, not substituted, so the trail stays auditable."""
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    url = f"/api/v1/verifications/observation/{observation['id']}"
    client.post(url, json={"decision": "CONFIRM"}, headers=expert_headers)
    client.post(
        url,
        json={"decision": "CORRECT", "corrected_species_id": peafowl.id},
        headers=expert_headers,
    )
    history = client.get(url, headers=expert_headers).json()
    assert len(history) == 2
    assert {entry["decision"] for entry in history} == {"CONFIRM", "CORRECT"}


def test_agreement_stats_compare_ai_with_the_expert(
    client: TestClient,
    researcher_headers,
    expert_headers,
    species_catalogue,
    thrush_call_bytes,
    thrush,
    observed_at,
) -> None:
    """The AI's label at review time is snapshotted, which is what makes this work."""
    capture = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "species_id": str(thrush.id)},
        files={"audio": ("call.wav", thrush_call_bytes, "audio/wav")},
        headers=researcher_headers,
    ).json()
    assert capture["ai_prediction"] is not None

    client.post(
        f"/api/v1/verifications/observation/{capture['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    stats = client.get("/api/v1/verifications/stats", headers=expert_headers).json()
    assert stats["reviewed_count"] == 1
    assert stats["confirmed"] == 1
    if capture["ai_prediction"] == thrush.common_name:
        assert stats["ai_agreement_rate"] == 1.0
        assert stats["mean_confidence_when_agreed"] is not None
    assert "review coverage" in stats["note"]


def test_agreement_stats_record_a_confusion(
    client: TestClient,
    researcher_headers,
    expert_headers,
    species_catalogue,
    thrush_call_bytes,
    gaur,
    peafowl,
    observed_at,
) -> None:
    capture = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "species_id": str(gaur.id)},
        files={"audio": ("call.wav", thrush_call_bytes, "audio/wav")},
        headers=researcher_headers,
    ).json()
    client.post(
        f"/api/v1/verifications/observation/{capture['id']}",
        json={"decision": "CORRECT", "corrected_species_id": peafowl.id},
        headers=expert_headers,
    )
    stats = client.get("/api/v1/verifications/stats", headers=expert_headers).json()
    assert stats["corrected"] == 1
    if capture["ai_prediction"] not in (None, "UNCERTAIN", peafowl.common_name):
        assert stats["ai_agreement_rate"] == 0.0
        assert stats["top_confusions"]
        assert stats["top_confusions"][0]["expert_label"] == peafowl.common_name


def test_confirming_a_threatened_species_raises_an_informational_alert(
    client: TestClient, researcher_headers, expert_headers, officer_headers, tiger
) -> None:
    """Officers are told a CR/EN/VU taxon was confirmed — never on a model guess alone."""
    observation = create_observation(client, researcher_headers, species_id=tiger.id)
    alerts_before = client.get("/api/v1/alerts", headers=officer_headers).json()["total"]
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    alerts = client.get("/api/v1/alerts", headers=officer_headers).json()
    assert alerts["total"] == alerts_before + 1
    alert = alerts["items"][0]
    assert alert["kind"] == "THREATENED_SPECIES_DETECTION"
    assert alert["severity"] == "INFO"
    assert "restricted" in alert["message"]
    assert alert["evidence"]["location_restricted"] is True


def test_no_alert_for_a_pending_threatened_record(
    client: TestClient, researcher_headers, officer_headers, tiger
) -> None:
    create_observation(client, researcher_headers, species_id=tiger.id)
    assert client.get("/api/v1/alerts", headers=officer_headers).json()["total"] == 0


def test_expert_workload_summary(
    client: TestClient, researcher_headers, expert, expert_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    board = client.get("/api/v1/verifications/experts", headers=expert_headers).json()
    assert board[0]["expert_id"] == expert.id
    assert board[0]["reviews"] == 1


def test_queue_filters_by_media_and_zone(
    client: TestClient,
    researcher_headers,
    expert_headers,
    species_catalogue,
    forest_image_bytes,
    gaur,
    zone,
    observed_at,
) -> None:
    create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        "/api/v1/observations/capture",
        data={
            "observed_at": observed_at,
            "latitude": "11.5912",
            "longitude": "76.5318",
            "run_ai": "false",
        },
        files={"image": ("trap.jpg", forest_image_bytes, "image/jpeg")},
        headers=researcher_headers,
    )
    with_media = client.get(
        "/api/v1/verifications/queue",
        params={"only_with_media": True},
        headers=expert_headers,
    ).json()
    assert with_media["total"] == 1
    assert with_media["items"][0]["has_image"] is True

    in_zone = client.get(
        "/api/v1/verifications/queue", params={"zone_id": zone.id}, headers=expert_headers
    ).json()
    assert in_zone["total"] == 2


def test_admin_can_also_verify(client: TestClient, researcher_headers, admin, gaur) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    headers = auth_headers(client, admin.email)
    response = client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=headers,
    )
    assert response.status_code == 201
