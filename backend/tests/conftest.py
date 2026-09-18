"""Test configuration.

The environment is configured *before* the application is imported, because
``app.core.config`` builds its settings object at import time. Each test session
gets a throwaway SQLite database and a throwaway media directory, so nothing
touches a developer's real data.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="vanraksha-tests-"))

os.environ.update(
    {
        "VANRAKSHA_ENV": "test",
        "DEBUG": "false",
        "DATABASE_URL": f"sqlite:///{TEST_ROOT / 'test.db'}",
        "JWT_SECRET": "test-secret-key-that-is-long-enough-for-the-suite-0123456789",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "STORAGE_BACKEND": "local",
        "STORAGE_LOCAL_ROOT": str(TEST_ROOT / "media"),
        "STORAGE_PUBLIC_BASE_URL": "http://testserver/media",
        "AUTH_RATE_LIMIT_ATTEMPTS": "100",
        "AI_MIN_CONFIDENCE": "0.45",
        "AI_UNCERTAIN_MARGIN": "0.08",
        "ANOMALY_BASELINE_DAYS": "84",
        "ANOMALY_WINDOW_DAYS": "7",
        "SENSITIVE_LOCATION_PRECISION_DEG": "0.1",
        "PUBLIC_LOCATION_PRECISION_DEG": "0.01",
    }
)

import app.models
import numpy as np
from app.core.rate_limit import auth_limiter
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    ConservationStatus,
    ForestZone,
    Species,
    SpeciesCategory,
    User,
    UserRole,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

PASSWORD = "ForestGaur2026!"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate between tests so each one starts from a known state."""
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    auth_limiter.reset()


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #
def make_user(
    db: Session,
    *,
    email: str,
    role: UserRole,
    full_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        full_name=full_name or email.split("@")[0].replace(".", " ").title(),
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin(db: Session) -> User:
    return make_user(db, email="admin@vanraksha.org", role=UserRole.ADMIN)


@pytest.fixture
def researcher(db: Session) -> User:
    return make_user(db, email="researcher@vanraksha.org", role=UserRole.RESEARCHER)


@pytest.fixture
def second_researcher(db: Session) -> User:
    return make_user(db, email="researcher2@vanraksha.org", role=UserRole.RESEARCHER)


@pytest.fixture
def expert(db: Session) -> User:
    return make_user(db, email="expert@vanraksha.org", role=UserRole.EXPERT)


@pytest.fixture
def officer(db: Session) -> User:
    return make_user(db, email="officer@vanraksha.org", role=UserRole.FOREST_OFFICER)


@pytest.fixture
def viewer(db: Session) -> User:
    return make_user(db, email="viewer@vanraksha.org", role=UserRole.VIEWER)


def auth_headers(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient, admin: User) -> dict[str, str]:
    return auth_headers(client, admin.email)


@pytest.fixture
def researcher_headers(client: TestClient, researcher: User) -> dict[str, str]:
    return auth_headers(client, researcher.email)


@pytest.fixture
def expert_headers(client: TestClient, expert: User) -> dict[str, str]:
    return auth_headers(client, expert.email)


@pytest.fixture
def officer_headers(client: TestClient, officer: User) -> dict[str, str]:
    return auth_headers(client, officer.email)


@pytest.fixture
def viewer_headers(client: TestClient, viewer: User) -> dict[str, str]:
    return auth_headers(client, viewer.email)


# --------------------------------------------------------------------------- #
# reference data
# --------------------------------------------------------------------------- #
@pytest.fixture
def zone(db: Session) -> ForestZone:
    forest_zone = ForestZone(
        name="Mudumalai North Block",
        code="MDM-N",
        description="Moist deciduous forest with grassy clearings.",
        habitat_type="moist deciduous",
        area_hectares=4200.0,
        center_latitude=11.5900,
        center_longitude=76.5300,
        radius_km=12.0,
    )
    db.add(forest_zone)
    db.commit()
    db.refresh(forest_zone)
    return forest_zone


@pytest.fixture
def species_catalogue(db: Session) -> list[Species]:
    """A slice of the real reference catalogue, including a sensitive taxon."""
    from ai.datasets.reference_species import REFERENCE_SPECIES

    wanted = {
        "Indian Gaur",
        "Bengal Tiger",
        "Malabar Whistling Thrush",
        "Indian Peafowl",
        "Great Hornbill",
        "Teak",
        "Indian Sandalwood",
        "Malabar Giant Squirrel",
    }
    rows: list[Species] = []
    for entry in REFERENCE_SPECIES:
        if entry["common_name"] not in wanted:
            continue
        rows.append(
            Species(
                common_name=entry["common_name"],
                scientific_name=entry["scientific_name"],
                category=SpeciesCategory(entry["category"]),
                family=entry.get("family"),
                genus=entry.get("genus"),
                description=entry.get("description"),
                habitat=entry.get("habitat"),
                conservation_status=ConservationStatus(entry["conservation_status"]),
                is_location_sensitive=entry.get("is_location_sensitive", False),
                visual_traits=entry.get("visual_traits") or None,
                acoustic_signature=entry.get("acoustic_signature") or None,
                research_notes=entry.get("research_notes") or None,
            )
        )
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@pytest.fixture
def gaur(species_catalogue: list[Species]) -> Species:
    return next(s for s in species_catalogue if s.common_name == "Indian Gaur")


@pytest.fixture
def tiger(species_catalogue: list[Species]) -> Species:
    """A CR/EN taxon flagged sensitive — used by the location-privacy tests."""
    return next(s for s in species_catalogue if s.common_name == "Bengal Tiger")


@pytest.fixture
def thrush(species_catalogue: list[Species]) -> Species:
    return next(s for s in species_catalogue if s.common_name == "Malabar Whistling Thrush")


@pytest.fixture
def peafowl(species_catalogue: list[Species]) -> Species:
    return next(s for s in species_catalogue if s.common_name == "Indian Peafowl")


# --------------------------------------------------------------------------- #
# media
# --------------------------------------------------------------------------- #
@pytest.fixture
def forest_image_bytes() -> bytes:
    """A small synthetic 'camera trap' JPEG."""
    import io

    from PIL import Image

    rng = np.random.default_rng(11)
    size = 192
    canopy = np.zeros((size, size, 3), dtype=np.float32)
    canopy[..., 0] = 0.16 + 0.06 * rng.random((size, size))
    canopy[..., 1] = 0.42 + 0.12 * rng.random((size, size))
    canopy[..., 2] = 0.14 + 0.05 * rng.random((size, size))
    canopy[60:150, 40:160] = [0.30, 0.19, 0.13]  # dark bovid-like subject
    buffer = io.BytesIO()
    Image.fromarray((canopy * 255).astype(np.uint8)).save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


@pytest.fixture
def thrush_call_bytes() -> bytes:
    """A WAV matching the Malabar Whistling Thrush reference signature."""
    from ai.datasets.reference_species import REFERENCE_SPECIES
    from ai.datasets.synthetic import synthesise_call_wav

    signature = next(
        row["acoustic_signature"]
        for row in REFERENCE_SPECIES
        if row["common_name"] == "Malabar Whistling Thrush"
    )
    return synthesise_call_wav(signature, seconds=6.0, seed=5)


@pytest.fixture
def silent_audio_bytes() -> bytes:
    """Near-silence — the audio pipeline must abstain rather than guess."""
    import io
    import wave

    samples = np.zeros(22_050 * 2, dtype="<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22_050)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def observed_at() -> str:
    return (datetime.now(UTC) - timedelta(hours=3)).isoformat()


def create_observation(
    client: TestClient,
    headers: dict[str, str],
    *,
    species_id: int | None = None,
    latitude: float = 11.5912,
    longitude: float = 76.5318,
    observed_at: str | None = None,
    **extra,
) -> dict:
    payload = {
        "species_id": species_id,
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": observed_at or (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        "observation_type": "FIELD_NOTE",
        **extra,
    }
    response = client.post("/api/v1/observations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
