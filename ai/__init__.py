"""VANRAKSHA AI engine.

Three independent pipelines plus a fusion layer:

* :mod:`ai.vision`     – animal detection and plant/species classification
* :mod:`ai.audio`      – bird and animal sound classification from recordings
* :mod:`ai.anomaly`    – unusual observation-pattern detection
* :mod:`ai.multimodal` – late fusion of image + audio (+ contextual priors)

Every pipeline has two backends: a *trained* backend (Ultralytics/PyTorch, used
when weights are present) and a *baseline* backend that depends only on NumPy
and Pillow.  The baseline is not a stub — it is a classical descriptor /
template-matching classifier — which keeps the whole platform runnable and
testable on any machine while the forest-specific models are being trained.

No pipeline ever returns a bare species name: results carry a confidence, the
top-k alternatives, an ``UNCERTAIN`` outcome when the model should not commit,
and the model version that produced them.
"""

from ai.config import AIConfig, get_config
from ai.schema import (
    UNCERTAIN_LABEL,
    Candidate,
    Detection,
    Prediction,
    SpeciesReference,
)

__all__ = [
    "AIConfig",
    "Candidate",
    "Detection",
    "Prediction",
    "SpeciesReference",
    "UNCERTAIN_LABEL",
    "get_config",
]

__version__ = "1.0.0"
