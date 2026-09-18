"""Spatial helpers and the location-privacy rules.

Two concerns live here.

**Portable spatial queries.** Distances use the haversine formula expressed in
SQL, which behaves identically on SQLite and PostgreSQL.  A bounding-box
pre-filter runs first so the indexed ``(latitude, longitude)`` columns do the
heavy lifting and the trigonometry only touches candidate rows.  Where PostGIS
is available, ``database/postgis/001_spatial.sql`` adds a real geography column
and GiST index for the same queries at scale — but nothing in the application
depends on it being there.

**Location privacy.** Publishing the exact coordinates of a tiger, a wild
sandalwood tree or a purple frog breeding site tells a poacher exactly where to
go.  Coordinates of sensitive taxa are therefore snapped to a coarse grid for
any caller without precise-location rights, the response says so via
``location_generalised``, and the generalisation happens in the serialisation
layer so no endpoint can leak precise coordinates by forgetting to ask.
"""

from __future__ import annotations

import math

from sqlalchemy import Float, and_, cast, func, literal
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.enums import PRECISE_LOCATION_ROLES, THREATENED_STATUSES, UserRole
from app.models.observation import Observation
from app.models.species import Species
from app.models.user import User

EARTH_RADIUS_KM = 6371.0088


# --------------------------------------------------------------------------- #
# distance
# --------------------------------------------------------------------------- #
def haversine_km(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    """Great-circle distance in kilometres."""
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(longitude_b - longitude_a)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def bounding_box(
    latitude: float, longitude: float, radius_km: float
) -> tuple[float, float, float, float]:
    """``(min_lat, max_lat, min_lon, max_lon)`` enclosing the search circle."""
    latitude_delta = radius_km / 111.32
    cosine = max(math.cos(math.radians(latitude)), 1e-6)
    longitude_delta = radius_km / (111.32 * cosine)
    return (
        max(-90.0, latitude - latitude_delta),
        min(90.0, latitude + latitude_delta),
        max(-180.0, longitude - longitude_delta),
        min(180.0, longitude + longitude_delta),
    )


def haversine_sql(
    latitude_column: ColumnElement,
    longitude_column: ColumnElement,
    latitude: float,
    longitude: float,
) -> ColumnElement:
    """The haversine distance in km as a SQL expression."""
    latitude_radians = func.radians(cast(latitude_column, Float))
    longitude_radians = func.radians(cast(longitude_column, Float))
    target_latitude = literal(math.radians(latitude))
    target_longitude = literal(math.radians(longitude))
    inner = (
        func.pow(func.sin((target_latitude - latitude_radians) / 2), 2)
        + func.cos(latitude_radians)
        * func.cos(target_latitude)
        * func.pow(func.sin((target_longitude - longitude_radians) / 2), 2)
    )
    return 2 * literal(EARTH_RADIUS_KM) * func.asin(func.sqrt(inner))


def within_radius_filter(
    latitude: float, longitude: float, radius_km: float
) -> ColumnElement:
    """Filter observations to a circle, bounding box first for index use."""
    min_lat, max_lat, min_lon, max_lon = bounding_box(latitude, longitude, radius_km)
    return and_(
        Observation.latitude.is_not(None),
        Observation.longitude.is_not(None),
        Observation.latitude.between(min_lat, max_lat),
        Observation.longitude.between(min_lon, max_lon),
        haversine_sql(Observation.latitude, Observation.longitude, latitude, longitude)
        <= radius_km,
    )


# --------------------------------------------------------------------------- #
# location privacy
# --------------------------------------------------------------------------- #
def may_see_precise_locations(user: User | None) -> bool:
    """Only authenticated staff and researchers see sensitive coordinates."""
    if user is None or not user.is_active:
        return False
    return user.role in PRECISE_LOCATION_ROLES


def species_is_sensitive(species: Species | None) -> bool:
    if species is None:
        return False
    return species.is_location_sensitive or species.conservation_status in THREATENED_STATUSES


def snap_to_grid(value: float | None, precision_deg: float) -> float | None:
    """Round a coordinate to the centre of a ``precision_deg`` grid cell.

    Snapping to the cell *centre* rather than truncating avoids biasing every
    generalised record towards the south-west corner of its cell, which would
    otherwise show up as a visible artefact on the map.
    """
    if value is None or precision_deg <= 0:
        return value
    cell = math.floor(value / precision_deg)
    return round((cell + 0.5) * precision_deg, 6)


def generalisation_precision(user: User | None) -> float:
    """Grid size applied to sensitive records for this caller."""
    if user is None:
        return settings.sensitive_location_precision_deg
    if user.role == UserRole.VIEWER:
        return settings.sensitive_location_precision_deg
    return settings.public_location_precision_deg


def apply_location_privacy(
    observation: Observation, viewer: User | None
) -> tuple[float | None, float | None, float | None, bool]:
    """Return ``(latitude, longitude, accuracy_m, was_generalised)`` for a viewer.

    The recorder and any privileged role always see their own precise data; for
    everyone else a sensitive species' coordinates are coarsened and the reported
    accuracy is widened to match, so the UI cannot draw a misleadingly tight
    marker around a generalised point.
    """
    latitude = observation.latitude
    longitude = observation.longitude
    accuracy = observation.location_accuracy_m

    species = observation.verified_species or observation.species
    if not species_is_sensitive(species):
        return latitude, longitude, accuracy, False

    if viewer is not None and (
        viewer.id == observation.researcher_id or may_see_precise_locations(viewer)
    ):
        return latitude, longitude, accuracy, False

    precision = generalisation_precision(viewer)
    generalised_accuracy = max(accuracy or 0.0, precision * 111_320.0 / 2.0)
    return (
        snap_to_grid(latitude, precision),
        snap_to_grid(longitude, precision),
        generalised_accuracy,
        True,
    )
