#!/usr/bin/env python3
"""Seed the VANRAKSHA AI database with reference data and a demo dataset.

Writes, in order:

1. the 32-species reference catalogue shared with the AI engine
   (``ai/datasets/reference_species.py``), so seeded species IDs line up with
   the AI baselines' reference set exactly;
2. an administrator, a forest officer, two researchers and two experts;
3. six Western Ghats forest zones with real-ish centroids and radii;
4. four monitoring nodes (camera traps / acoustic recorders / an env sensor);
5. a season of observations — synthetic photographs and recordings rendered
   from the same reference traits/signatures the AI engine matches against,
   so the demo dataset is internally consistent: running AI-assisted
   identification on a seeded observation's media is expected to *usually*
   agree with the species it was generated from;
6. a run of expert verification on a sample of those observations, so the
   review queue, the AI-vs-expert agreement stats and the analytics
   endpoints all have something real to show;
7. a week of environmental sensor readings.

Usage::

    python scripts/seed.py                 # add to what's there
    python scripts/seed.py --reset         # wipe and reseed
    python scripts/seed.py --minimal       # reference data + users only, fast
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("seed")

RANDOM_SEED = 20260917

# --------------------------------------------------------------------------- #
# reference data
# --------------------------------------------------------------------------- #
ZONES = [
    {
        "name": "Mudumalai North Block",
        "code": "MDM-N",
        "description": "Moist deciduous forest with grassy clearings along the Moyar river.",
        "habitat_type": "moist deciduous",
        "area_hectares": 4200.0,
        "center_latitude": 11.5900,
        "center_longitude": 76.5300,
        "radius_km": 9.0,
    },
    {
        "name": "Bandipur East Range",
        "code": "BND-E",
        "description": "Dry deciduous forest and teak plantation on the Karnataka side "
        "of the corridor.",
        "habitat_type": "dry deciduous",
        "area_hectares": 5600.0,
        "center_latitude": 11.7000,
        "center_longitude": 76.6300,
        "radius_km": 10.0,
    },
    {
        "name": "Silent Valley Core",
        "code": "SLV-C",
        "description": "Undisturbed Western Ghats evergreen rainforest; lion-tailed macaque range.",
        "habitat_type": "evergreen rainforest",
        "area_hectares": 8950.0,
        "center_latitude": 11.0800,
        "center_longitude": 76.4400,
        "radius_km": 7.0,
    },
    {
        "name": "Nilgiri Shola-Grassland Complex",
        "code": "NLG-S",
        "description": "Montane shola forest and grassland above 1,800 m near the Nilgiri plateau.",
        "habitat_type": "shola-grassland",
        "area_hectares": 3100.0,
        "center_latitude": 11.4000,
        "center_longitude": 76.7000,
        "radius_km": 6.0,
    },
    {
        "name": "Periyar Lakeside Zone",
        "code": "PYR-L",
        "description": "Forest bordering the Periyar reservoir; elephant and gaur corridor.",
        "habitat_type": "moist deciduous",
        "area_hectares": 3800.0,
        "center_latitude": 9.4600,
        "center_longitude": 77.2400,
        "radius_km": 8.0,
    },
    {
        "name": "Anamalai Buffer",
        "code": "ANM-B",
        "description": "Buffer zone of plantation and secondary forest bordering Anamalai "
        "Tiger Reserve.",
        "habitat_type": "mixed / secondary forest",
        "area_hectares": 2600.0,
        "center_latitude": 10.3300,
        "center_longitude": 76.9300,
        "radius_km": 5.0,
    },
]

USERS = [
    {
        "full_name": "VANRAKSHA Administrator",
        "email": "admin@vanraksha.ai",
        "password": "ChangeMe#Admin2026",
        "role": "ADMIN",
    },
    {
        "full_name": "Kavitha Raman",
        "email": "kavitha.raman@forest.gov.in",
        "password": "ForestOfficer#2026",
        "role": "FOREST_OFFICER",
        "organization": "Tamil Nadu Forest Department",
    },
    {
        "full_name": "Arjun Krishnamurthy",
        "email": "arjun.k@wri-india.org",
        "password": "Researcher#2026a",
        "role": "RESEARCHER",
        "organization": "Wildlife Research Institute",
    },
    {
        "full_name": "Meera Pillai",
        "email": "meera.pillai@atree.org",
        "password": "Researcher#2026b",
        "role": "RESEARCHER",
        "organization": "ATREE",
    },
    {
        "full_name": "Dr. Anjali Menon",
        "email": "anjali.menon@wii.res.in",
        "password": "Expert#2026a",
        "role": "EXPERT",
        "organization": "Wildlife Institute of India",
        "expertise": "Mammals and large carnivores",
    },
    {
        "full_name": "Dr. Suresh Nair",
        "email": "suresh.nair@ncbs.res.in",
        "password": "Expert#2026b",
        "role": "EXPERT",
        "organization": "National Centre for Biological Sciences",
        "expertise": "Birds and bioacoustics",
    },
    {
        "full_name": "Public Viewer",
        "email": "viewer@vanraksha.ai",
        "password": "Viewer#2026",
        "role": "VIEWER",
    },
]

DEVICES = [
    {
        "device_code": "CAM-MDM-01",
        "name": "Mudumalai salt-lick camera trap",
        "kind": "CAMERA_TRAP",
        "zone_code": "MDM-N",
        "report_interval_minutes": 60,
    },
    {
        "device_code": "MIC-SLV-01",
        "name": "Silent Valley canopy recorder",
        "kind": "ACOUSTIC_RECORDER",
        "zone_code": "SLV-C",
        "report_interval_minutes": 30,
    },
    {
        "device_code": "ENV-BND-01",
        "name": "Bandipur multi-sensor node",
        "kind": "MULTI_SENSOR_NODE",
        "zone_code": "BND-E",
        "report_interval_minutes": 15,
    },
    {
        "device_code": "MIC-NLG-01",
        "name": "Nilgiri shola-edge recorder",
        "kind": "ACOUSTIC_RECORDER",
        "zone_code": "NLG-S",
        "report_interval_minutes": 30,
    },
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reset", action="store_true", help="drop and recreate every table first"
    )
    parser.add_argument(
        "--minimal", action="store_true", help="species, zones and users only — no observations"
    )
    parser.add_argument(
        "--observations",
        type=int,
        default=260,
        help="number of synthetic observations to generate (default: 260)",
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    import app.models  # noqa: F401 - registers every table
    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import engine
    from sqlalchemy.orm import Session

    if args.reset:
        logger.info("dropping and recreating the schema")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        species_by_name = _seed_species(db)
        users_by_email = _seed_users(db, hash_password)
        zones_by_code = _seed_zones(db)
        devices_by_code = _seed_devices(db, zones_by_code)

        if not args.minimal:
            _seed_observations(
                db,
                species_by_name=species_by_name,
                users_by_email=users_by_email,
                zones_by_code=zones_by_code,
                count=args.observations,
                seed=args.seed,
            )
            _seed_sensor_readings(db, devices_by_code, seed=args.seed)

    logger.info("done")
    return 0


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #
def _seed_species(db) -> dict[str, object]:
    from app.models import ConservationStatus, Species, SpeciesCategory
    from sqlalchemy import select

    from ai.datasets.reference_species import REFERENCE_SPECIES

    existing = {row.scientific_name: row for row in db.execute(select(Species)).scalars()}
    created = 0
    for entry in REFERENCE_SPECIES:
        if entry["scientific_name"] in existing:
            continue
        row = Species(
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
        db.add(row)
        existing[row.scientific_name] = row
        created += 1
    db.commit()
    logger.info("species: %d created, %d already present", created, len(existing) - created)
    return {row.common_name: row for row in existing.values()}


def _seed_users(db, hash_password) -> dict[str, object]:
    from app.models import User, UserRole
    from sqlalchemy import select

    existing = {row.email: row for row in db.execute(select(User)).scalars()}
    created = 0
    for entry in USERS:
        if entry["email"] in existing:
            continue
        row = User(
            full_name=entry["full_name"],
            email=entry["email"],
            password_hash=hash_password(entry["password"]),
            role=UserRole(entry["role"]),
            organization=entry.get("organization"),
            expertise=entry.get("expertise"),
            is_active=True,
        )
        db.add(row)
        existing[row.email] = row
        created += 1
    db.commit()
    logger.info("users: %d created, %d already present", created, len(existing) - created)
    if created:
        logger.info("seeded credentials (development only — change before any real deployment):")
        for entry in USERS:
            logger.info("  %-32s %-16s %s", entry["email"], entry["role"], entry["password"])
    return {row.email: row for row in existing.values()}


def _seed_zones(db) -> dict[str, object]:
    from app.models import ForestZone
    from sqlalchemy import select

    existing = {row.code: row for row in db.execute(select(ForestZone)).scalars()}
    created = 0
    for entry in ZONES:
        if entry["code"] in existing:
            continue
        row = ForestZone(**entry)
        db.add(row)
        existing[row.code] = row
        created += 1
    db.commit()
    logger.info("zones: %d created, %d already present", created, len(existing) - created)
    return {row.code: row for row in existing.values()}


def _seed_devices(db, zones_by_code) -> dict[str, object]:
    from app.core.security import hash_password
    from app.models import Device, DeviceKind
    from sqlalchemy import select

    existing = {row.device_code: row for row in db.execute(select(Device)).scalars()}
    created = 0
    for entry in DEVICES:
        if entry["device_code"] in existing:
            continue
        zone = zones_by_code.get(entry["zone_code"])
        row = Device(
            device_code=entry["device_code"],
            name=entry["name"],
            kind=DeviceKind(entry["kind"]),
            zone_id=zone.id if zone else None,
            latitude=zone.center_latitude if zone else None,
            longitude=zone.center_longitude if zone else None,
            report_interval_minutes=entry["report_interval_minutes"],
            is_active=True,
            # Development-only fixed key so the seed script's own demo
            # ingest calls (and anyone following the docs) can use it.
            ingest_key_hash=hash_password(f"vrk_seed_{entry['device_code'].lower()}"),
        )
        db.add(row)
        existing[row.device_code] = row
        created += 1
    db.commit()
    logger.info("devices: %d created, %d already present", created, len(existing) - created)
    return {row.device_code: row for row in existing.values()}


def _seed_observations(
    db,
    *,
    species_by_name: dict,
    users_by_email: dict,
    zones_by_code: dict,
    count: int,
    seed: int,
) -> None:
    from app.core.config import settings
    from app.models import (
        MediaAsset,
        MediaKind,
        Observation,
        ObservationType,
        UserRole,
        VerificationStatus,
    )
    from app.services import observation_service
    from app.services.ai_client import AIEngine
    from sqlalchemy import func, select

    from ai.datasets.reference_species import REFERENCE_SPECIES
    from ai.datasets.synthetic import (
        ACTIVITY_WINDOWS,
        render_image,
        synthesise_call_wav,
    )
    from ai.preprocessing.audio import write_spectrogram_png

    already = db.execute(select(func.count(Observation.id))).scalar_one()
    if already:
        logger.info("observations: %d already present, skipping generation", already)
        return

    rng = random.Random(seed)
    recorders = [u for u in users_by_email.values() if u.role in {UserRole.RESEARCHER,
                                                                    UserRole.FOREST_OFFICER}]
    experts = [u for u in users_by_email.values() if u.role == UserRole.EXPERT]
    zones = list(zones_by_code.values())
    notes_by_label = {row["common_name"]: row.get("research_notes") or {} for row in
                       REFERENCE_SPECIES}
    labels = list(species_by_name)

    storage_root = settings.storage_root
    storage_root.mkdir(parents=True, exist_ok=True)

    engine = AIEngine(db)
    created = 0
    now = datetime.now(UTC)

    for index in range(count):
        label = labels[index % len(labels)]
        species = species_by_name[label]
        zone = zones[index % len(zones)]
        recorder = recorders[index % len(recorders)]
        day_offset = rng.randint(0, 179)
        window = ACTIVITY_WINDOWS.get(
            str((notes_by_label.get(label) or {}).get("activity", "diurnal")), (6, 18)
        )
        hour = rng.randint(window[0], window[1]) if window[0] <= window[1] else rng.randint(0, 23)
        observed_at = (now - timedelta(days=day_offset)).replace(
            hour=hour, minute=rng.randint(0, 59), second=0, microsecond=0
        )
        latitude = zone.center_latitude + rng.uniform(-0.04, 0.04)
        longitude = zone.center_longitude + rng.uniform(-0.04, 0.04)

        has_image = bool(species.visual_traits) and rng.random() > 0.15
        has_audio = bool(species.acoustic_signature) and rng.random() > 0.55
        if not has_image and not has_audio:
            has_image = bool(species.visual_traits) or not species.acoustic_signature

        observation_type = ObservationType.FIELD_NOTE
        if has_image and has_audio:
            observation_type = ObservationType.MULTIMODAL
        elif has_image:
            observation_type = ObservationType.IMAGE
        elif has_audio:
            observation_type = ObservationType.AUDIO

        observation = Observation(
            researcher_id=recorder.id,
            species_id=species.id,
            zone_id=zone.id,
            observation_type=observation_type,
            latitude=round(latitude, 6),
            longitude=round(longitude, 6),
            location_accuracy_m=rng.uniform(3.0, 25.0),
            observed_at=observed_at,
            individual_count=rng.choice([1, 1, 1, 2, 3]) if species.category == "MAMMAL"
            else None,
            notes=None,
            verification_status=VerificationStatus.PENDING,
        )
        db.add(observation)
        db.flush()

        image_prediction = None
        audio_prediction = None

        if has_image:
            import numpy as np

            image = render_image(
                species.visual_traits,
                np.random.default_rng(seed + index),
                size=200,
                difficulty=rng.uniform(0.0, 0.4),
            )
            import hashlib

            from PIL import Image as PILImage

            buf_path = storage_root / "images" / f"{observed_at:%Y/%m}"
            buf_path.mkdir(parents=True, exist_ok=True)
            arr = (image * 255).astype("uint8")
            pil_image = PILImage.fromarray(arr)
            checksum = hashlib.sha256(arr.tobytes()).hexdigest()
            key = f"images/{observed_at:%Y/%m}/{checksum[:16]}.jpg"
            path = storage_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            pil_image.save(path, format="JPEG", quality=88)
            url = f"{settings.storage_public_base_url.rstrip('/')}/{key}"
            asset = MediaAsset(
                observation_id=observation.id,
                kind=MediaKind.IMAGE,
                storage_key=key,
                public_url=url,
                mime_type="image/jpeg",
                size_bytes=path.stat().st_size,
                checksum=checksum,
                width=image.shape[1],
                height=image.shape[0],
            )
            db.add(asset)
            observation.image_url = url
            try:
                image_prediction = engine.predict_image(path.read_bytes())
            except Exception:  # pragma: no cover - seeding must not hard-fail
                logger.warning("vision prediction failed for observation %s", observation.id)

        if has_audio:
            import hashlib

            wav_bytes = synthesise_call_wav(
                species.acoustic_signature, seconds=rng.uniform(3.0, 7.0), seed=seed + index
            )
            checksum = hashlib.sha256(wav_bytes).hexdigest()
            key = f"audio/{observed_at:%Y/%m}/{checksum[:16]}.wav"
            path = storage_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(wav_bytes)
            url = f"{settings.storage_public_base_url.rstrip('/')}/{key}"
            from ai.preprocessing.audio import decode_audio

            decoded = decode_audio(wav_bytes, filename="call.wav")
            asset = MediaAsset(
                observation_id=observation.id,
                kind=MediaKind.AUDIO,
                storage_key=key,
                public_url=url,
                mime_type="audio/wav",
                size_bytes=len(wav_bytes),
                checksum=checksum,
                duration_seconds=round(decoded.duration_seconds, 3),
                sample_rate=decoded.sample_rate,
            )
            db.add(asset)
            observation.audio_url = url
            try:
                spectrogram_key = f"spectrograms/{observed_at:%Y/%m}/{checksum[:16]}.png"
                spectrogram_path = storage_root / spectrogram_key
                spectrogram_path.parent.mkdir(parents=True, exist_ok=True)
                write_spectrogram_png(decoded, spectrogram_path)
                db.add(
                    MediaAsset(
                        observation_id=observation.id,
                        kind=MediaKind.SPECTROGRAM,
                        storage_key=spectrogram_key,
                        public_url=f"{settings.storage_public_base_url.rstrip('/')}/"
                        f"{spectrogram_key}",
                        mime_type="image/png",
                        size_bytes=spectrogram_path.stat().st_size,
                        checksum=hashlib.sha256(spectrogram_path.read_bytes()).hexdigest(),
                    )
                )
                audio_prediction = engine.predict_audio(wav_bytes, filename="call.wav")
            except Exception:  # pragma: no cover - seeding must not hard-fail
                logger.warning("audio prediction failed for observation %s", observation.id)

        if image_prediction is not None and audio_prediction is not None:
            fused = engine.fuse(image_prediction, audio_prediction)
            observation_service.record_prediction(
                db, observation, image_prediction, commit=False, set_primary=False
            )
            observation_service.record_prediction(
                db, observation, audio_prediction, commit=False, set_primary=False
            )
            observation_service.record_prediction(
                db, observation, fused, commit=False, set_primary=True
            )
        elif image_prediction is not None or audio_prediction is not None:
            single = image_prediction or audio_prediction
            observation_service.record_prediction(
                db, observation, single, commit=False, set_primary=True
            )

        created += 1
        if created % 50 == 0:
            db.commit()
            logger.info("observations: %d/%d", created, count)

    db.commit()
    logger.info("observations: %d created", created)

    # A realistic review pass: experts confirm/correct roughly 40% of records,
    # weighted toward the oldest so the queue looks like ongoing work rather
    # than an all-or-nothing backlog.
    if experts:
        _seed_verifications(db, experts=experts, rng=rng)


def _seed_verifications(db, *, experts: list, rng: random.Random) -> None:
    from app.models import Observation, VerificationDecision, VerificationStatus
    from app.schemas.verification import VerificationCreate
    from app.services.verification_service import submit_verification
    from sqlalchemy import select

    pending = list(
        db.execute(
            select(Observation)
            .where(Observation.verification_status == VerificationStatus.PENDING)
            .order_by(Observation.observed_at)
        )
        .scalars()
        .all()
    )
    to_review = pending[: int(len(pending) * 0.4)]
    reviewed = 0
    for observation in to_review:
        expert = experts[reviewed % len(experts)]
        roll = rng.random()
        try:
            if roll < 0.82:
                submit_verification(
                    db,
                    observation.id,
                    VerificationCreate(decision=VerificationDecision.CONFIRM),
                    expert=expert,
                )
            elif roll < 0.94 and observation.ai_predicted_species_id:
                submit_verification(
                    db,
                    observation.id,
                    VerificationCreate(
                        decision=VerificationDecision.CORRECT,
                        corrected_species_id=observation.ai_predicted_species_id,
                    ),
                    expert=expert,
                )
            else:
                submit_verification(
                    db,
                    observation.id,
                    VerificationCreate(decision=VerificationDecision.UNCERTAIN),
                    expert=expert,
                )
            reviewed += 1
        except Exception:  # pragma: no cover - seeding must not hard-fail
            logger.warning("verification failed for observation %s", observation.id)
    logger.info("verifications: %d observations reviewed", reviewed)


def _seed_sensor_readings(db, devices_by_code: dict, *, seed: int) -> None:
    from app.models import SensorReading
    from sqlalchemy import func, select

    already = db.execute(select(func.count(SensorReading.id))).scalar_one()
    if already:
        logger.info("sensor readings: %d already present, skipping", already)
        return

    rng = random.Random(seed + 1)
    now = datetime.now(UTC)
    created = 0
    for device in devices_by_code.values():
        base_temp = rng.uniform(19.0, 26.0)
        for hours_ago in range(0, 24 * 14, 2):  # two weeks, every 2 hours
            stamp = now - timedelta(hours=hours_ago)
            diurnal = 3.0 * (0.5 - abs((stamp.hour - 14) / 24.0))
            db.add(
                SensorReading(
                    device_id=device.id,
                    zone_id=device.zone_id,
                    recorded_at=stamp,
                    temperature_c=round(base_temp + diurnal + rng.uniform(-0.8, 0.8), 2),
                    humidity_pct=round(rng.uniform(55.0, 95.0), 1),
                    illuminance_lux=round(max(0.0, rng.uniform(-500, 12000)), 1),
                    sound_level_db=round(rng.uniform(28.0, 62.0), 1),
                    motion_events=rng.choice([0, 0, 0, 1, 1, 2]),
                    battery_volts=round(rng.uniform(3.4, 4.1), 2),
                )
            )
            created += 1
        device.last_seen_at = now - timedelta(hours=2)
    db.commit()
    logger.info("sensor readings: %d created", created)


if __name__ == "__main__":
    sys.exit(main())
