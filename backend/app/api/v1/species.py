"""Species knowledge-base endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request, status

from app.core.deps import AdminUser, CuratorUser, CurrentUser, DbSession
from app.models.enums import ConservationStatus, SpeciesCategory
from app.schemas.common import Message, Page
from app.schemas.species import (
    SpeciesCreate,
    SpeciesRead,
    SpeciesUpdate,
    SpeciesWithStats,
)
from app.services import species_service

router = APIRouter(prefix="/species", tags=["species"])


@router.get("", response_model=Page[SpeciesRead], summary="Search the species catalogue")
def list_species(
    db: DbSession,
    search: str | None = Query(default=None, max_length=160, description="Name or family"),
    category: SpeciesCategory | None = Query(default=None),
    conservation_status: ConservationStatus | None = Query(default=None),
    family: str | None = Query(default=None, max_length=120),
    threatened_only: bool = Query(default=False, description="CR, EN and VU taxa only"),
    audible_only: bool = Query(
        default=False, description="Only taxa the acoustic pipeline can match"
    ),
    sort: str = Query(default="common_name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[SpeciesRead]:
    """Public read access: the catalogue is reference data, not observation data."""
    return species_service.list_species(
        db,
        search=search,
        category=category,
        conservation_status=conservation_status,
        family=family,
        threatened_only=threatened_only,
        audible_only=audible_only,
        limit=limit,
        offset=offset,
        sort=sort,
    )


@router.get("/categories", response_model=dict[str, int], summary="Species count per category")
def categories(db: DbSession) -> dict[str, int]:
    return species_service.category_counts(db)


@router.get("/families", response_model=list[str], summary="Distinct families in the catalogue")
def families(db: DbSession) -> list[str]:
    return species_service.families(db)


@router.get(
    "/{species_id}",
    response_model=SpeciesWithStats,
    summary="A species with its detection counts",
    responses={404: {"description": "Species not found"}},
)
def get_species(db: DbSession, species_id: int) -> SpeciesWithStats:
    return species_service.species_with_stats(db, species_id)


@router.post(
    "",
    response_model=SpeciesRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a species to the catalogue",
    responses={409: {"description": "Scientific name already in the catalogue"}},
)
def create_species(
    db: DbSession, request: Request, actor: CuratorUser, payload: SpeciesCreate = Body(...)
) -> SpeciesRead:
    """Adding a species immediately widens what the AI baselines can match: the
    reference set is read from this table on every inference call."""
    species = species_service.create_species(db, payload, actor=actor, request=request)
    return SpeciesRead.model_validate(species)


@router.patch(
    "/{species_id}",
    response_model=SpeciesRead,
    summary="Update a species record",
    responses={404: {"description": "Species not found"}},
)
def update_species(
    db: DbSession,
    request: Request,
    actor: CuratorUser,
    species_id: int,
    payload: SpeciesUpdate = Body(...),
) -> SpeciesRead:
    species = species_service.update_species(
        db, species_id, payload, actor=actor, request=request
    )
    return SpeciesRead.model_validate(species)


@router.delete(
    "/{species_id}",
    response_model=Message,
    summary="Remove a species (administrators only)",
)
def delete_species(
    db: DbSession, request: Request, admin: AdminUser, species_id: int
) -> Message:
    """Observations recorded under this taxon are kept and detached, never deleted."""
    species_service.delete_species(db, species_id, actor=admin, request=request)
    return Message(
        detail="Species removed. Observations recorded under it were kept and detached."
    )


@router.get(
    "/{species_id}/ai-reference",
    response_model=dict,
    summary="The reference traits the AI baselines match against",
)
def ai_reference(db: DbSession, _user: CurrentUser, species_id: int) -> dict:
    """Exposes the descriptors behind an identification, so a reviewer can see
    *why* a species was ranked highly rather than only that it was."""
    from ai.audio.baseline import ACOUSTIC_SCHEMA
    from ai.vision.baseline import TRAIT_SCHEMA

    species = species_service.get_species(db, species_id)
    return {
        "species_id": species.id,
        "common_name": species.common_name,
        "visual_traits": species.visual_traits or {},
        "acoustic_signature": species.acoustic_signature or {},
        "visual_trait_schema": TRAIT_SCHEMA,
        "acoustic_signature_schema": ACOUSTIC_SCHEMA,
        "matchable_by_image": bool(species.visual_traits),
        "matchable_by_audio": bool(species.acoustic_signature),
    }
