"""Domain enumerations shared by the ORM, the API schemas and the AI engine."""

from __future__ import annotations

from enum import Enum
from enum import StrEnum as _StdStrEnum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum


class StrEnum(_StdStrEnum):
    """Re-exported so callers only need one import for every domain enum."""


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    RESEARCHER = "RESEARCHER"
    FOREST_OFFICER = "FOREST_OFFICER"
    EXPERT = "EXPERT"
    VIEWER = "VIEWER"


#: Roles a member of the public may choose during self-registration.
PUBLIC_REGISTRATION_ROLES = {UserRole.RESEARCHER, UserRole.VIEWER}

#: Roles that may see un-generalised coordinates of sensitive species.
PRECISE_LOCATION_ROLES = {UserRole.ADMIN, UserRole.RESEARCHER, UserRole.FOREST_OFFICER,
                          UserRole.EXPERT}


class SpeciesCategory(StrEnum):
    MAMMAL = "MAMMAL"
    BIRD = "BIRD"
    PLANT = "PLANT"
    REPTILE = "REPTILE"
    AMPHIBIAN = "AMPHIBIAN"
    INSECT = "INSECT"
    FUNGI = "FUNGI"
    OTHER = "OTHER"


class ConservationStatus(StrEnum):
    """IUCN Red List categories plus an explicit 'not assessed' member."""

    EXTINCT = "EX"
    EXTINCT_IN_THE_WILD = "EW"
    CRITICALLY_ENDANGERED = "CR"
    ENDANGERED = "EN"
    VULNERABLE = "VU"
    NEAR_THREATENED = "NT"
    LEAST_CONCERN = "LC"
    DATA_DEFICIENT = "DD"
    NOT_EVALUATED = "NE"


#: Statuses for which observation coordinates are generalised by default.
THREATENED_STATUSES = {
    ConservationStatus.CRITICALLY_ENDANGERED,
    ConservationStatus.ENDANGERED,
    ConservationStatus.VULNERABLE,
}


class ObservationType(StrEnum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    MULTIMODAL = "MULTIMODAL"
    FIELD_NOTE = "FIELD_NOTE"
    CAMERA_TRAP = "CAMERA_TRAP"
    SENSOR = "SENSOR"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    UNCERTAIN = "UNCERTAIN"


class VerificationDecision(StrEnum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    CORRECT = "CORRECT"
    UNCERTAIN = "UNCERTAIN"


DECISION_TO_STATUS = {
    VerificationDecision.CONFIRM: VerificationStatus.CONFIRMED,
    VerificationDecision.REJECT: VerificationStatus.REJECTED,
    VerificationDecision.CORRECT: VerificationStatus.CORRECTED,
    VerificationDecision.UNCERTAIN: VerificationStatus.UNCERTAIN,
}


class Modality(StrEnum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    SENSOR = "SENSOR"
    FUSED = "FUSED"


class MediaKind(StrEnum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    SPECTROGRAM = "SPECTROGRAM"
    DOCUMENT = "DOCUMENT"


class DeviceKind(StrEnum):
    CAMERA_TRAP = "CAMERA_TRAP"
    ACOUSTIC_RECORDER = "ACOUSTIC_RECORDER"
    ENV_SENSOR = "ENV_SENSOR"
    MULTI_SENSOR_NODE = "MULTI_SENSOR_NODE"


class AlertKind(StrEnum):
    BIODIVERSITY_ANOMALY = "BIODIVERSITY_ANOMALY"
    ACOUSTIC_ANOMALY = "ACOUSTIC_ANOMALY"
    SENSOR_MALFUNCTION = "SENSOR_MALFUNCTION"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    DATA_GAP = "DATA_GAP"
    THREATENED_SPECIES_DETECTION = "THREATENED_SPECIES_DETECTION"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class AnomalyMethod(StrEnum):
    ROBUST_Z = "ROBUST_Z"
    ISOLATION_FOREST = "ISOLATION_FOREST"
    ENSEMBLE = "ENSEMBLE"


class ExperimentStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_E = TypeVar("_E", bound=Enum)


def sa_enum(enum_cls: type[_E], length: int) -> SAEnum:
    """A portable, value-backed enum column.

    ``native_enum=False`` keeps the column a ``VARCHAR`` + ``CHECK`` constraint so
    the same schema works on SQLite and PostgreSQL, and ``values_callable`` stores
    the member *value* (``"CR"``) rather than its name (``"CRITICALLY_ENDANGERED"``),
    which is what the API and the seed data speak.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
    )


__all__ = [
    "DECISION_TO_STATUS",
    "PRECISE_LOCATION_ROLES",
    "PUBLIC_REGISTRATION_ROLES",
    "THREATENED_STATUSES",
    "AlertKind",
    "AlertSeverity",
    "AlertStatus",
    "AnomalyMethod",
    "ConservationStatus",
    "DeviceKind",
    "ExperimentStatus",
    "MediaKind",
    "Modality",
    "ObservationType",
    "SpeciesCategory",
    "UserRole",
    "VerificationDecision",
    "VerificationStatus",
    "sa_enum",
]
