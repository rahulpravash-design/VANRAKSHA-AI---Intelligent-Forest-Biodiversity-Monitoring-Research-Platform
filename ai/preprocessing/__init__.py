"""Input validation and feature extraction for images and audio."""

from ai.preprocessing.audio import (
    AudioFeatures,
    AudioValidationError,
    DecodedAudio,
    decode_audio,
    extract_audio_features,
    mel_spectrogram,
    spectral_gate,
    write_spectrogram_png,
)
from ai.preprocessing.image import (
    DESCRIPTOR_LENGTH,
    ImageInfo,
    ImageValidationError,
    image_descriptor,
    inspect_image,
    load_image,
)

__all__ = [
    "DESCRIPTOR_LENGTH",
    "AudioFeatures",
    "AudioValidationError",
    "DecodedAudio",
    "ImageInfo",
    "ImageValidationError",
    "decode_audio",
    "extract_audio_features",
    "image_descriptor",
    "inspect_image",
    "load_image",
    "mel_spectrogram",
    "spectral_gate",
    "write_spectrogram_png",
]
