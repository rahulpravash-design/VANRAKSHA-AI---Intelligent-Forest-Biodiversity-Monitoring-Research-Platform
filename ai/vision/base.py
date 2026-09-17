"""The contract every vision backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from ai.schema import Candidate, Detection, SpeciesReference


@runtime_checkable
class VisionBackend(Protocol):
    """A species classifier over images.

    Backends return *ranked candidates*, not a decision.  Thresholding and the
    ``UNCERTAIN`` outcome are applied once, centrally, by
    :class:`ai.vision.pipeline.VisionPipeline`, so every backend is calibrated
    and gated the same way.
    """

    name: str
    version: str
    backend: str

    def classify(self, image: np.ndarray, *, top_k: int = 5) -> list[Candidate]:
        """Rank species for a loaded ``(H, W, 3)`` float image in ``[0, 1]``."""
        ...

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Locate subjects in the image. May return an empty list."""
        ...

    @property
    def classes(self) -> list[SpeciesReference]:
        """The species this backend can currently distinguish."""
        ...
