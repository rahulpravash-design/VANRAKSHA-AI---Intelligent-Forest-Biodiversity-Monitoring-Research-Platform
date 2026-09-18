"""Late fusion of image, audio and contextual evidence."""

from ai.multimodal.fusion import (
    FusionWeights,
    context_prior_from_history,
    fuse_predictions,
)

__all__ = ["FusionWeights", "context_prior_from_history", "fuse_predictions"]
