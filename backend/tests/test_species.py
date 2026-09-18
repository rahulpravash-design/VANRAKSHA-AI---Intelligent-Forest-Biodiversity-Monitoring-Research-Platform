"""Species catalogue endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

NEW_SPECIES = {
    "common_name": "Nilgiri Langur",
    "scientific_name": "semnopithecus johnii",
    "category": "MAMMAL",
    "family": "Cercopithecidae",
    "genus": "Semnopithecus",
    "conservation_status": "VU",
    "habitat": "Western Ghats evergreen forest above 300 m.",
    "visual_traits": {
        "dominant_hues": [0.0],
        "saturation": 0.1,
        "brightness": 0.15,
        "pattern": "uniform",
        "body_aspect": 1.1,
        "subject_fill": 0.25,
        "scene": "canopy",
    },
}


def test_catalogue_is_publicly_readable(client: TestClient, species_catalogue) -> None:
    response = client.get("/api/v1/species")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(species_catalogue)
    assert {item["scientific_name"] for item in body["items"]} >= {"Bos gaurus", "Tectona grandis"}


def test_search_matches_common_and_scientific_names(
    client: TestClient, species_catalogue
) -> None:
    for query in ("gaur", "Bos", "bovidae"):
        body = client.get("/api/v1/species", params={"search": query}).json()
        assert any("Gaur" in item["common_name"] for item in body["items"]), query


def test_filter_by_category(client: TestClient, species_catalogue) -> None:
    body = client.get("/api/v1/species", params={"category": "BIRD"}).json()
    assert body["total"] >= 2
    assert {item["category"] for item in body["items"]} == {"BIRD"}


def test_filter_threatened_only(client: TestClient, species_catalogue) -> None:
    body = client.get("/api/v1/species", params={"threatened_only": True}).json()
    assert body["total"] >= 3
    assert {item["conservation_status"] for item in body["items"]} <= {"CR", "EN", "VU"}


def test_filter_audible_only_excludes_plants(client: TestClient, species_catalogue) -> None:
    """Plants carry no acoustic signature, so the acoustic pipeline cannot match them."""
    body = client.get("/api/v1/species", params={"audible_only": True}).json()
    categories = {item["category"] for item in body["items"]}
    assert "PLANT" not in categories
    assert "BIRD" in categories


def test_pagination_reports_the_unpaged_total(client: TestClient, species_catalogue) -> None:
    body = client.get("/api/v1/species", params={"limit": 2, "offset": 0}).json()
    assert len(body["items"]) == 2
    assert body["total"] == len(species_catalogue)


def test_species_detail_includes_detection_counts(
    client: TestClient, researcher_headers, gaur
) -> None:
    from tests.conftest import create_observation

    create_observation(client, researcher_headers, species_id=gaur.id)
    body = client.get(f"/api/v1/species/{gaur.id}").json()
    assert body["observation_count"] == 1
    assert body["verified_observation_count"] == 0
    assert body["last_observed_at"] is not None


def test_unknown_species_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/species/98765").status_code == 404


def test_create_species_normalises_the_binomial(
    client: TestClient, researcher_headers
) -> None:
    response = client.post("/api/v1/species", json=NEW_SPECIES, headers=researcher_headers)
    assert response.status_code == 201, response.text
    assert response.json()["scientific_name"] == "Semnopithecus johnii"


def test_create_species_rejects_a_duplicate_binomial(
    client: TestClient, researcher_headers, species_catalogue
) -> None:
    response = client.post(
        "/api/v1/species",
        json={**NEW_SPECIES, "scientific_name": "BOS GAURUS"},
        headers=researcher_headers,
    )
    assert response.status_code == 409


def test_create_species_requires_a_curator_role(
    client: TestClient, viewer_headers, officer_headers
) -> None:
    assert client.post("/api/v1/species", json=NEW_SPECIES).status_code == 401
    assert (
        client.post("/api/v1/species", json=NEW_SPECIES, headers=viewer_headers).status_code
        == 403
    )
    assert (
        client.post("/api/v1/species", json=NEW_SPECIES, headers=officer_headers).status_code
        == 403
    )


def test_update_species(client: TestClient, researcher_headers, gaur) -> None:
    response = client.patch(
        f"/api/v1/species/{gaur.id}",
        json={"conservation_status": "EN", "habitat": "Updated habitat note."},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["conservation_status"] == "EN"
    assert response.json()["habitat"] == "Updated habitat note."


def test_delete_species_keeps_the_observations(
    client: TestClient, admin_headers, researcher_headers, gaur
) -> None:
    """Deleting a taxon must never delete the field records collected under it."""
    from tests.conftest import create_observation

    observation = create_observation(client, researcher_headers, species_id=gaur.id)
    assert client.delete(f"/api/v1/species/{gaur.id}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/species/{gaur.id}").status_code == 404

    kept = client.get(f"/api/v1/observations/{observation['id']}")
    assert kept.status_code == 200
    assert kept.json()["species"] is None


def test_delete_species_requires_an_admin(
    client: TestClient, researcher_headers, gaur
) -> None:
    assert (
        client.delete(f"/api/v1/species/{gaur.id}", headers=researcher_headers).status_code == 403
    )


def test_category_and_family_summaries(client: TestClient, species_catalogue) -> None:
    categories = client.get("/api/v1/species/categories").json()
    assert categories["MAMMAL"] >= 3
    families = client.get("/api/v1/species/families").json()
    assert "Bovidae" in families


def test_ai_reference_exposes_the_matching_traits(
    client: TestClient, researcher_headers, thrush
) -> None:
    body = client.get(
        f"/api/v1/species/{thrush.id}/ai-reference", headers=researcher_headers
    ).json()
    assert body["matchable_by_audio"] is True
    assert body["acoustic_signature"]["peak_hz"] == 2200.0
    assert "peak_hz" in body["acoustic_signature_schema"]
    assert "dominant_hues" in body["visual_trait_schema"]


def test_ai_reference_requires_authentication(client: TestClient, thrush) -> None:
    assert client.get(f"/api/v1/species/{thrush.id}/ai-reference").status_code == 401
