"""Computer-vision pipeline: detect the subject, then identify the species."""

from ai.vision.baseline import (
    TRAIT_SCHEMA,
    BaselineVisionClassifier,
    discriminative_scale,
    prototype_from_traits,
)
from ai.vision.detect import saliency_detections
from ai.vision.pipeline import VisionPipeline, build_vision_pipeline

__all__ = [
    "BaselineVisionClassifier",
    "TRAIT_SCHEMA",
    "VisionPipeline",
    "discriminative_scale",
    "build_vision_pipeline",
    "prototype_from_traits",
    "saliency_detections",
]
