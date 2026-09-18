"""ORM models.

Importing this package registers every table on ``Base.metadata`` — Alembic and
``create_all`` both rely on that, so new model modules must be imported here.
"""

from app.db.base import Base
from app.models.ai import AIPrediction
from app.models.alert import Alert, AnomalyScore
from app.models.audit import AuditLog
from app.models.auth import RevokedToken
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AlertStatus,
    AnomalyMethod,
    ConservationStatus,
    DeviceKind,
    ExperimentStatus,
    MediaKind,
    Modality,
    ObservationType,
    SpeciesCategory,
    UserRole,
    VerificationDecision,
    VerificationStatus,
)
from app.models.experiment import Experiment, ExperimentRun
from app.models.iot import Device, SensorReading
from app.models.observation import MediaAsset, Observation
from app.models.species import Species
from app.models.user import User
from app.models.verification import ExpertVerification
from app.models.zone import ForestZone

__all__ = [
    "AIPrediction",
    "Alert",
    "AlertKind",
    "AlertSeverity",
    "AlertStatus",
    "AnomalyMethod",
    "AnomalyScore",
    "AuditLog",
    "Base",
    "ConservationStatus",
    "Device",
    "DeviceKind",
    "Experiment",
    "ExperimentRun",
    "ExperimentStatus",
    "ExpertVerification",
    "ForestZone",
    "MediaAsset",
    "MediaKind",
    "Modality",
    "Observation",
    "ObservationType",
    "RevokedToken",
    "SensorReading",
    "Species",
    "SpeciesCategory",
    "User",
    "UserRole",
    "VerificationDecision",
    "VerificationStatus",
]
