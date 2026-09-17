"""Acoustic pipeline: bird and animal sound classification."""

from ai.audio.baseline import (
    ACOUSTIC_SCHEMA,
    BaselineAudioClassifier,
    feature_match_scores,
)
from ai.audio.pipeline import AudioPipeline, build_audio_pipeline

__all__ = [
    "ACOUSTIC_SCHEMA",
    "AudioPipeline",
    "BaselineAudioClassifier",
    "build_audio_pipeline",
    "feature_match_scores",
]
