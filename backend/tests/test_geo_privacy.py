"""Location privacy and spatial queries.

These are the tests that matter most for doing no harm: publishing the exact
coordinates of a tiger or a wild sandalwood tree tells a poacher where to go.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_observation

PRECISE_LATITUDE = 11.591234
PRECISE_LONGITUDE = 76.531789


def _record_tiger(client: TestClient, headers: dict[str, str], tiger) -> dict:
    return create_observation(
        client,
        headers,
        species_id=tiger.id,
        latitude=PRECISE_LATITUDE,
        longitude=PRECISE_LONGITUDE,
        location_accuracy_m=8.0,
    )


def test_sensitive_coordinates_are_precise_for_the_recorder(
    client: TestClient, researcher_headers, tiger
) -> None:
    observation = _record_tiger(client, researcher_headers, tiger)
    assert observation["latitude"] == PRECISE_LATITUDE
    assert observation["location_generalised"] is False


def test_sensitive_coordinates_are_generalised_for_anonymous_callers(
    client: TestClient, researcher_headers, tiger
) -> None:
    observation = _record_tiger(client, researcher_headers, tiger)
    public = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert public["location_generalised"] is True
    assert public["latitude"] != PRECISE_LATITUDE
    assert abs(public["latitude"] - PRECISE_LATITUDE) < 0.1
    # The reported accuracy is widened so the map cannot draw a tight marker.
    assert public["location_accuracy_m"] > 1000


def test_sensitive_coordinates_are_generalised_for_viewers(
    client: TestClient, researcher_headers, viewer_headers, tiger
) -> None:
    observation = _record_tiger(client, researcher_headers, tiger)
    seen = client.get(
        f"/api/v1/observations/{observation['id']}", headers=viewer_headers
    ).json()
    assert seen["location_generalised"] is True
    assert seen["latitude"] != PRECISE_LATITUDE


def test_other_researchers_and_experts_see_precise_coordinates(
    client: TestClient, researcher_headers, second_researcher, expert, officer, tiger
) -> None:
    """Field staff need the real position to do their work."""
    observation = _record_tiger(client, researcher_headers, tiger)
    for user in (second_researcher, expert, officer):
        headers = auth_headers(client, user.email)
        seen = client.get(
            f"/api/v1/observations/{observation['id']}", headers=headers
        ).json()
        assert seen["location_generalised"] is False, user.role
        assert seen["latitude"] == PRECISE_LATITUDE, user.role


def test_non_sensitive_species_are_never_generalised(
    client: TestClient, researcher_headers, peafowl
) -> None:
    observation = create_observation(
        client,
        researcher_headers,
        species_id=peafowl.id,
        latitude=PRECISE_LATITUDE,
        longitude=PRECISE_LONGITUDE,
    )
    public = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert public["location_generalised"] is False
    assert public["latitude"] == PRECISE_LATITUDE


def test_threatened_status_alone_triggers_generalisation(
    client: TestClient, researcher_headers, db, peafowl
) -> None:
    """A VU/EN/CR taxon is generalised even without the sensitivity flag."""
    peafowl.conservation_status = "EN"
    peafowl.is_location_sensitive = False
    db.commit()
    observation = create_observation(
        client,
        researcher_headers,
        species_id=peafowl.id,
        latitude=PRECISE_LATITUDE,
        longitude=PRECISE_LONGITUDE,
    )
    public = client.get(f"/api/v1/observations/{observation['id']}").json()
    assert public["location_generalised"] is True


def test_generalisation_snaps_to_a_grid_centre(
    client: TestClient, researcher_headers, tiger
) -> None:
    """Snapping to the cell centre avoids biasing every record south-west."""
    observation = _record_tiger(client, researcher_headers, tiger)
    public = client.get(f"/api/v1/observations/{observation['id']}").json()
    # 0.1 degree grid -> centres land on .x5
    assert round(public["latitude"] % 0.1, 4) == 0.05
    assert round(public["longitude"] % 0.1, 4) == 0.05


def test_list_and_geojson_also_generalise(
    client: TestClient, researcher_headers, tiger
) -> None:
    _record_tiger(client, researcher_headers, tiger)

    listed = client.get("/api/v1/observations").json()["items"][0]
    assert listed["location_generalised"] is True
    assert listed["latitude"] != PRECISE_LATITUDE

    collection = client.get("/api/v1/zones/observations/geojson").json()
    assert collection["location_generalised"] is True
    feature = collection["features"][0]
    assert feature["properties"]["location_generalised"] is True
    assert feature["geometry"]["coordinates"][1] != PRECISE_LATITUDE


def test_csv_export_marks_generalised_rows(
    client: TestClient, researcher_headers, expert_headers, viewer_headers, tiger
) -> None:
    observation = _record_tiger(client, researcher_headers, tiger)
    client.post(
        f"/api/v1/verifications/observation/{observation['id']}",
        json={"decision": "CONFIRM"},
        headers=expert_headers,
    )
    response = client.get("/api/v1/analytics/export.csv", headers=viewer_headers)
    assert response.status_code == 200
    text = response.text
    assert "location_generalised" in text
    assert str(PRECISE_LATITUDE) not in text
    assert "not population estimates" in text


def test_geographic_grid_is_coarse_for_unprivileged_callers(
    client: TestClient, researcher_headers, viewer_headers, tiger
) -> None:
    """A fine grid must not be obtainable by asking for one."""
    _record_tiger(client, researcher_headers, tiger)
    fine_request = client.get(
        "/api/v1/analytics/geographic",
        params={"precision_deg": 0.001},
        headers=viewer_headers,
    ).json()
    assert fine_request["precision_deg"] >= 0.1
    assert fine_request["location_generalised"] is True

    privileged = client.get(
        "/api/v1/analytics/geographic",
        params={"precision_deg": 0.01},
        headers=researcher_headers,
    ).json()
    assert privileged["precision_deg"] <= 0.01
    assert privileged["location_generalised"] is False


# --------------------------------------------------------------------------- #
# spatial queries
# --------------------------------------------------------------------------- #
def test_haversine_matches_a_known_distance() -> None:
    from app.services.geo import haversine_km

    # Mudumalai to Bandipur, roughly 22 km apart.
    distance = haversine_km(11.5900, 76.5300, 11.7000, 76.6300)
    assert 14.0 < distance < 20.0
    assert haversine_km(11.59, 76.53, 11.59, 76.53) == 0.0


def test_bounding_box_contains_the_search_circle() -> None:
    from app.services.geo import bounding_box, haversine_km

    min_lat, max_lat, min_lon, max_lon = bounding_box(11.59, 76.53, 10.0)
    assert min_lat < 11.59 < max_lat
    assert min_lon < 76.53 < max_lon
    # The box corner must be at least the radius away, never less.
    assert haversine_km(11.59, 76.53, max_lat, 76.53) >= 9.9


def test_zone_assignment_picks_the_nearest_containing_zone(
    client: TestClient, researcher_headers, officer_headers, zone, gaur
) -> None:
    """Nested zones: an observation belongs to the smallest one containing it."""
    inner = client.post(
        "/api/v1/zones",
        json={
            "name": "Salt Lick Compartment",
            "code": "MDM-SL",
            "center_latitude": 11.5915,
            "center_longitude": 76.5320,
            "radius_km": 1.0,
        },
        headers=officer_headers,
    )
    assert inner.status_code == 201, inner.text
    observation = create_observation(
        client, researcher_headers, species_id=gaur.id, latitude=11.5916, longitude=76.5321
    )
    assert observation["zone_id"] == inner.json()["id"]


def test_zones_geojson_flags_an_approximate_boundary(client: TestClient, zone) -> None:
    collection = client.get("/api/v1/zones/geojson").json()
    assert collection["total"] == 1
    feature = collection["features"][0]
    assert feature["properties"]["approximate_boundary"] is True
    assert feature["geometry"]["type"] == "Point"
