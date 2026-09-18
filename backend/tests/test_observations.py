"""Observation CRUD, media upload and the AI-assisted capture workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_observation


# --------------------------------------------------------------------------- #
# creation and validation
# --------------------------------------------------------------------------- #
def test_create_observation_starts_pending(
    client: TestClient, researcher_headers, gaur, zone
) -> None:
    body = create_observation(client, researcher_headers, species_id=gaur.id)
    assert body["verification_status"] == "PENDING"
    assert body["species"]["scientific_name"] == "Bos gaurus"
    # The observation falls inside the seeded zone's radius, so it is assigned.
    assert body["zone_id"] == zone.id


def test_create_observation_rejects_a_future_timestamp(
    client: TestClient, researcher_headers
) -> None:
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/observations",
        json={"observed_at": future, "observation_type": "FIELD_NOTE"},
        headers=researcher_headers,
    )
    assert response.status_code == 422
    assert "observed_at" in response.json()["fields"]


def test_create_observation_rejects_invalid_coordinates(
    client: TestClient, researcher_headers, observed_at
) -> None:
    for latitude, longitude in ((95.0, 76.5), (11.5, 200.0)):
        response = client.post(
            "/api/v1/observations",
            json={
                "observed_at": observed_at,
                "latitude": latitude,
                "longitude": longitude,
                "observation_type": "FIELD_NOTE",
            },
            headers=researcher_headers,
        )
        assert response.status_code == 422, (latitude, longitude)


def test_create_observation_rejects_an_unknown_species(
    client: TestClient, researcher_headers, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations",
        json={
            "observed_at": observed_at,
            "species_id": 999_999,
            "observation_type": "FIELD_NOTE",
        },
        headers=researcher_headers,
    )
    assert response.status_code == 422
    assert "999999" in response.json()["detail"]


def test_observation_outside_every_zone_is_unassigned(
    client: TestClient, researcher_headers, zone, gaur
) -> None:
    body = create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=8.0, longitude=77.0
    )
    assert body["zone_id"] is None


# --------------------------------------------------------------------------- #
# listing and filtering
# --------------------------------------------------------------------------- #
def test_list_filters_by_species_and_status(
    client: TestClient, researcher_headers, gaur, peafowl
) -> None:
    create_observation(client, researcher_headers, species_id=gaur.id)
    create_observation(client, researcher_headers, species_id=peafowl.id)
    body = client.get("/api/v1/observations", params={"species_id": gaur.id}).json()
    assert body["total"] == 1
    assert body["items"][0]["species"]["common_name"] == "Indian Gaur"

    pending = client.get(
        "/api/v1/observations", params={"verification_status": "PENDING"}
    ).json()
    assert pending["total"] == 2


def test_list_filters_by_date_window(
    client: TestClient, researcher_headers, gaur
) -> None:
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    create_observation(client, researcher_headers, species_id=gaur.id, observed_at=old)
    create_observation(client, researcher_headers, species_id=gaur.id)
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    body = client.get("/api/v1/observations", params={"observed_from": cutoff}).json()
    assert body["total"] == 1


def test_list_filters_by_radius(client: TestClient, researcher_headers, gaur) -> None:
    create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=11.5912, longitude=76.5318
    )
    create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=12.9, longitude=77.6
    )
    near = client.get(
        "/api/v1/observations",
        params={"latitude": 11.59, "longitude": 76.53, "radius_km": 25},
    ).json()
    assert near["total"] == 1


def test_search_matches_notes_and_species(
    client: TestClient, researcher_headers, gaur
) -> None:
    create_observation(
        client, researcher_headers, species_id=gaur.id, notes="Herd of eight at the salt lick"
    )
    assert client.get("/api/v1/observations", params={"search": "salt lick"}).json()["total"] == 1
    assert client.get("/api/v1/observations", params={"search": "gaurus"}).json()["total"] == 1
    assert client.get("/api/v1/observations", params={"search": "tiger"}).json()["total"] == 0


def test_my_observations_only_returns_your_own(
    client: TestClient, researcher, second_researcher, gaur
) -> None:
    first = auth_headers(client, researcher.email)
    second = auth_headers(client, second_researcher.email)
    create_observation(client, first, species_id=gaur.id)
    create_observation(client, second, species_id=gaur.id)
    create_observation(client, second, species_id=gaur.id)
    assert client.get("/api/v1/observations/me", headers=first).json()["total"] == 1
    assert client.get("/api/v1/observations/me", headers=second).json()["total"] == 2


# --------------------------------------------------------------------------- #
# ownership
# --------------------------------------------------------------------------- #
def test_only_the_recorder_or_an_admin_may_edit(
    client: TestClient, researcher, second_researcher, admin, gaur
) -> None:
    owner = auth_headers(client, researcher.email)
    other = auth_headers(client, second_researcher.email)
    administrator = auth_headers(client, admin.email)
    observation = create_observation(client, owner, species_id=gaur.id)
    url = f"/api/v1/observations/{observation['id']}"

    assert client.patch(url, json={"notes": "hijacked"}, headers=other).status_code == 403
    assert client.patch(url, json={"notes": "mine"}, headers=owner).status_code == 200
    assert client.patch(url, json={"notes": "admin fix"}, headers=administrator).status_code == 200


def test_only_the_recorder_or_an_admin_may_delete(
    client: TestClient, researcher, second_researcher, gaur
) -> None:
    owner = auth_headers(client, researcher.email)
    other = auth_headers(client, second_researcher.email)
    observation = create_observation(client, owner, species_id=gaur.id)
    url = f"/api/v1/observations/{observation['id']}"
    assert client.delete(url, headers=other).status_code == 403
    assert client.delete(url, headers=owner).status_code == 200
    assert client.get(url).status_code == 404


def test_changing_the_species_returns_the_record_to_the_queue(
    client: TestClient, researcher_headers, expert_headers, gaur, peafowl
) -> None:
    """A verified record whose species is edited must be reviewed again."""
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    assert (
        client.get(f"/api/v1/observations/{observation['id']}").json()["verification_status"]
        == "CONFIRMED"
    )
    updated = client.patch(
        f"/api/v1/observations/{observation['id']}",
        json={"species_id": peafowl.id},
        headers=researcher_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["verification_status"] == "PENDING"
    assert updated.json()["verified_species"] is None


# --------------------------------------------------------------------------- #
# media upload
# --------------------------------------------------------------------------- #
def test_capture_with_an_image_runs_ai_identification(
    client: TestClient, researcher_headers, species_catalogue, forest_image_bytes, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={
            "observed_at": observed_at,
            "latitude": "11.5912",
            "longitude": "76.5318",
            "notes": "Camera trap frame at dawn",
        },
        files={"image": ("trap.jpg", forest_image_bytes, "image/jpeg")},
        headers=researcher_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["observation_type"] == "IMAGE"
    assert body["image_url"].endswith(".jpg")
    assert len(body["media"]) == 1
    assert body["media"][0]["width"] == 192

    # An AI prediction was recorded, and it did not become the species.
    assert len(body["predictions"]) == 1
    prediction = body["predictions"][0]
    assert prediction["modality"] == "IMAGE"
    assert 0.0 <= prediction["confidence"] <= 1.0
    assert body["species"] is None, "a model output must never set the reported species"
    assert body["verification_status"] == "PENDING"


def test_capture_with_audio_stores_a_spectrogram(
    client: TestClient, researcher_headers, species_catalogue, thrush_call_bytes, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "latitude": "11.59", "longitude": "76.53"},
        files={"audio": ("call.wav", thrush_call_bytes, "audio/wav")},
        headers=researcher_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["observation_type"] == "AUDIO"
    kinds = {asset["kind"] for asset in body["media"]}
    assert kinds == {"AUDIO", "SPECTROGRAM"}
    audio_asset = next(a for a in body["media"] if a["kind"] == "AUDIO")
    assert audio_asset["sample_rate"] == 22_050
    assert audio_asset["duration_seconds"] > 5.0


def test_capture_identifies_the_thrush_from_its_call(
    client: TestClient, researcher_headers, species_catalogue, thrush_call_bytes, observed_at
) -> None:
    """The acoustic baseline should rank the matching template first."""
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"audio": ("call.wav", thrush_call_bytes, "audio/wav")},
        headers=researcher_headers,
    )
    prediction = response.json()["predictions"][0]
    assert prediction["modality"] == "AUDIO"
    top = (prediction["top_k"] or [{}])[0]
    assert top.get("label") == "Malabar Whistling Thrush", prediction["top_k"]


def test_capture_with_both_media_fuses_the_predictions(
    client: TestClient,
    researcher_headers,
    species_catalogue,
    forest_image_bytes,
    thrush_call_bytes,
    observed_at,
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "latitude": "11.59", "longitude": "76.53"},
        files={
            "image": ("trap.jpg", forest_image_bytes, "image/jpeg"),
            "audio": ("call.wav", thrush_call_bytes, "audio/wav"),
        },
        headers=researcher_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["observation_type"] == "MULTIMODAL"
    modalities = {p["modality"] for p in body["predictions"]}
    assert modalities == {"IMAGE", "AUDIO", "FUSED"}
    # The fused result is the one mirrored onto the observation.
    fused = next(p for p in body["predictions"] if p["modality"] == "FUSED")
    assert body["ai_prediction"] == fused["predicted_label"]
    assert fused["diagnostics"]["modalities_used"] == ["IMAGE", "AUDIO"]
    assert "reliability" in fused["diagnostics"]


def test_silent_recording_produces_an_uncertain_result(
    client: TestClient, researcher_headers, species_catalogue, silent_audio_bytes, observed_at
) -> None:
    """Near-silence must be reported as UNCERTAIN, not as a low-confidence species."""
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"audio": ("silence.wav", silent_audio_bytes, "audio/wav")},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    prediction = response.json()["predictions"][0]
    assert prediction["is_uncertain"] is True
    assert prediction["predicted_label"] == "UNCERTAIN"
    assert "noise floor" in prediction["diagnostics"]["reason"]


def test_capture_rejects_a_file_that_is_not_an_image(
    client: TestClient, researcher_headers, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"image": ("evil.jpg", b"#!/bin/sh\nrm -rf /\n", "image/jpeg")},
        headers=researcher_headers,
    )
    assert response.status_code == 422
    assert "image" in response.json()["detail"].lower()


def test_capture_rejects_a_disallowed_extension(
    client: TestClient, researcher_headers, forest_image_bytes, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"image": ("payload.svg", forest_image_bytes, "image/svg+xml")},
        headers=researcher_headers,
    )
    assert response.status_code == 422
    assert ".jpg" in response.json()["detail"]


def test_capture_rejects_an_oversized_image(
    client: TestClient, researcher_headers, observed_at
) -> None:
    from app.core.config import settings

    oversized = b"\xff\xd8\xff\xe0" + b"\x00" * (settings.max_image_bytes + 1024)
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"image": ("huge.jpg", oversized, "image/jpeg")},
        headers=researcher_headers,
    )
    assert response.status_code == 413


def test_capture_rejects_corrupt_audio(
    client: TestClient, researcher_headers, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        files={"audio": ("broken.wav", b"RIFF\x00\x00\x00\x00WAVEjunk", "audio/wav")},
        headers=researcher_headers,
    )
    assert response.status_code == 422


def test_capture_needs_media_or_a_species(
    client: TestClient, researcher_headers, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at},
        headers=researcher_headers,
    )
    assert response.status_code == 422
    assert "at least" in response.json()["detail"]


def test_identical_uploads_are_stored_once(
    client: TestClient, researcher_headers, species_catalogue, forest_image_bytes, observed_at
) -> None:
    """Media is content-addressed, so the same bytes reuse one stored file."""
    keys = []
    for _ in range(2):
        response = client.post(
            "/api/v1/observations/capture",
            data={"observed_at": observed_at, "run_ai": "false"},
            files={"image": ("trap.jpg", forest_image_bytes, "image/jpeg")},
            headers=researcher_headers,
        )
        assert response.status_code == 201
        keys.append(response.json()["media"][0]["checksum"])
    assert keys[0] == keys[1]


def test_attach_media_to_an_existing_observation(
    client: TestClient, researcher_headers, gaur, forest_image_bytes
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/observations/{observation['id']}/media",
        data={"kind": "IMAGE"},
        files={"file": ("later.png", forest_image_bytes, "image/png")},
        headers=researcher_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # The upload claimed PNG in its filename and content type, but the bytes are
    # a JPEG. The stored file follows the decoder, not the client.
    assert body["mime_type"] == "image/jpeg"
    assert body["public_url"].endswith(".jpg")
    assert body["original_filename"] == "later.png"


def test_reidentify_appends_a_prediction(
    client: TestClient, researcher_headers, species_catalogue, forest_image_bytes, observed_at
) -> None:
    created = client.post(
        "/api/v1/observations/capture",
        data={"observed_at": observed_at, "run_ai": "false"},
        files={"image": ("trap.jpg", forest_image_bytes, "image/jpeg")},
        headers=researcher_headers,
    ).json()
    assert created["predictions"] == []

    response = client.post(
        f"/api/v1/observations/{created['id']}/identify", headers=researcher_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    detail = client.get(f"/api/v1/observations/{created['id']}").json()
    assert len(detail["predictions"]) == 1
    assert detail["predictions"][0]["requires_expert_verification"] is not False


def test_reidentify_without_media_is_422(
    client: TestClient, researcher_headers, gaur
) -> None:
    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    response = client.post(
        f"/api/v1/observations/{observation['id']}/identify", headers=researcher_headers
    )
    assert response.status_code == 422


def test_observation_summary_reports_queue_health(
    client: TestClient, researcher_headers, gaur
) -> None:
    create_observation(client, researcher_headers, species_id=gaur.id)
    body = client.get("/api/v1/observations/stats/summary", headers=researcher_headers).json()
    assert body["pending_review"] == 1
    assert body["pending_over_14_days"] == 0
    assert body["ai_mode"] == "in-process"
