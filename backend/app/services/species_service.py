"""Species knowledge-base queries and mutations."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import String, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import ConservationStatus, SpeciesCategory, VerificationStatus
from app.models.observation import Observation
from app.models.species import Species
from app.models.user import User
from app.schemas.common import Page
from app.schemas.species import (
    SpeciesCreate,
    SpeciesRead,
    SpeciesUpdate,
    SpeciesWithStats,
)
from app.services import audit


def normalise_scientific_name(name: str) -> str:
    """Trim and capitalise to the binomial convention (``Genus species``)."""
    parts = " ".join(name.strip().split()).split(" ")
    if not parts or not parts[0]:
        return name.strip()
    parts[0] = parts[0].capitalize()
    return " ".join([parts[0]] + [p.lower() for p in parts[1:]])


def get_species(db: Session, species_id: int) -> Species:
    species = db.get(Species, species_id)
    if species is None:
        raise NotFoundError(f"No species with id {species_id}.")
    return species


def list_species(
    db: Session,
    *,
    search: str | None = None,
    category: SpeciesCategory | None = None,
    conservation_status: ConservationStatus | None = None,
    family: str | None = None,
    threatened_only: bool = False,
    audible_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: str = "common_name",
) -> Page[SpeciesRead]:
    """Search and filter the catalogue."""
    statement = select(Species)
    if search:
        pattern = f"%{search.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(Species.common_name).like(pattern),
                func.lower(Species.scientific_name).like(pattern),
                func.lower(func.coalesce(Species.family, "")).like(pattern),
                func.lower(func.coalesce(Species.genus, "")).like(pattern),
            )
        )
    if category is not None:
        statement = statement.where(Species.category == category)
    if conservation_status is not None:
        statement = statement.where(Species.conservation_status == conservation_status)
    if family:
        statement = statement.where(func.lower(Species.family) == family.strip().lower())
    if threatened_only:
        statement = statement.where(
            Species.conservation_status.in_(
                [
                    ConservationStatus.CRITICALLY_ENDANGERED,
                    ConservationStatus.ENDANGERED,
                    ConservationStatus.VULNERABLE,
                ]
            )
        )
    if audible_only:
        # Species the acoustic pipeline can actually match against. An empty JSON
        # object is stored, not NULL, so the emptiness test is on the serialised
        # text — which behaves the same on SQLite and PostgreSQL.
        statement = statement.where(
            Species.acoustic_signature.is_not(None),
            func.cast(Species.acoustic_signature, String).notin_(("{}", "null")),
        )

    total = db.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar_one()

    sort_columns = {
        "common_name": Species.common_name,
        "scientific_name": Species.scientific_name,
        "category": Species.category,
        "conservation_status": Species.conservation_status,
        "created_at": Species.created_at.desc(),
    }
    statement = statement.order_by(sort_columns.get(sort, Species.common_name))
    rows = db.execute(statement.limit(limit).offset(offset)).scalars().all()
    return Page[SpeciesRead](
        items=[SpeciesRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def species_with_stats(db: Session, species_id: int) -> SpeciesWithStats:
    """A species plus its detection counts."""
    species = get_species(db, species_id)
    total, verified, last_seen = db.execute(
        select(
            func.count(Observation.id),
            func.sum(
                case(
                    (
                        Observation.verification_status.in_(
                            [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.max(Observation.observed_at),
        ).where(
            or_(
                Observation.species_id == species_id,
                Observation.verified_species_id == species_id,
            )
        )
    ).one()
    payload = SpeciesRead.model_validate(species).model_dump()
    return SpeciesWithStats(
        **payload,
        observation_count=int(total or 0),
        verified_observation_count=int(verified or 0),
        last_observed_at=last_seen,
    )


def create_species(
    db: Session, payload: SpeciesCreate, *, actor: User, request: Request | None = None
) -> Species:
    scientific_name = normalise_scientific_name(payload.scientific_name)
    existing = db.execute(
        select(Species).where(func.lower(Species.scientific_name) == scientific_name.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"'{scientific_name}' is already in the catalogue (id {existing.id})."
        )
    data = payload.model_dump()
    data["scientific_name"] = scientific_name
    data["common_name"] = payload.common_name.strip()
    species = Species(**data)
    db.add(species)
    db.flush()
    audit.record(
        db,
        "species.create",
        user=actor,
        entity="species",
        entity_id=species.id,
        request=request,
        context={"scientific_name": species.scientific_name},
    )
    db.commit()
    db.refresh(species)
    return species


def update_species(
    db: Session,
    species_id: int,
    payload: SpeciesUpdate,
    *,
    actor: User,
    request: Request | None = None,
) -> Species:
    species = get_species(db, species_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("scientific_name"):
        changes["scientific_name"] = normalise_scientific_name(changes["scientific_name"])
        clash = db.execute(
            select(Species).where(
                func.lower(Species.scientific_name) == changes["scientific_name"].lower(),
                Species.id != species_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError(
                f"'{changes['scientific_name']}' is already used by species {clash.id}."
            )
    for field, value in changes.items():
        setattr(species, field, value)
    audit.record(
        db,
        "species.update",
        user=actor,
        entity="species",
        entity_id=species.id,
        request=request,
        context={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(species)
    return species


def delete_species(
    db: Session, species_id: int, *, actor: User, request: Request | None = None
) -> None:
    """Remove a species.

    Observations keep their row — ``species_id`` is set to NULL by the foreign
    key — because deleting a taxon from the catalogue must never silently delete
    field records collected under it.
    """
    species = get_species(db, species_id)
    linked = db.execute(
        select(func.count(Observation.id)).where(
            or_(
                Observation.species_id == species_id,
                Observation.verified_species_id == species_id,
            )
        )
    ).scalar_one()
    audit.record(
        db,
        "species.delete",
        user=actor,
        entity="species",
        entity_id=species_id,
        request=request,
        context={
            "scientific_name": species.scientific_name,
            "detached_observations": int(linked or 0),
        },
    )
    db.delete(species)
    db.commit()


def category_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Species.category, func.count(Species.id)).group_by(Species.category)
    ).all()
    return {str(category): int(count) for category, count in rows}


def families(db: Session) -> list[str]:
    rows = db.execute(
        select(Species.family)
        .where(Species.family.is_not(None))
        .distinct()
        .order_by(Species.family)
    ).scalars().all()
    return [row for row in rows if row]
