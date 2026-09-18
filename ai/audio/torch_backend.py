"""Trained acoustic backend — a small CNN over log-mel spectrograms.

The architecture is defined here so the same definition serves training
(:mod:`ai.training.train_audio`) and inference.  A checkpoint stores the weights
alongside its class list, which keeps inference independent of the code's
ordering assumptions.

Importing this module never requires PyTorch; :func:`torch_available` is the
gate, and :func:`ai.audio.pipeline.build_audio_pipeline` falls back to the
template matcher when the gate is closed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ai.preprocessing.audio import DecodedAudio, mel_spectrogram
from ai.schema import Candidate, SpeciesReference

logger = logging.getLogger(__name__)

TARGET_FRAMES = 256


def torch_available() -> bool:
    try:  # pragma: no cover - environment dependent
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def build_model(num_classes: int, n_mels: int = 64):  # pragma: no cover - optional
    """A four-block VGG-style CNN — small enough to train on a single GPU."""
    import torch.nn as nn

    def block(in_channels: int, out_channels: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    return nn.Sequential(
        block(1, 32),
        block(32, 64),
        block(64, 128),
        block(128, 256),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Dropout(0.3),
        nn.Linear(256, num_classes),
    )


def prepare_input(audio: DecodedAudio, *, n_mels: int = 64, target_frames: int = TARGET_FRAMES):
    """Log-mel patch of fixed shape ``(1, n_mels, target_frames)`` in ``[0, 1]``."""
    mel_db, _ = mel_spectrogram(audio.samples, audio.sample_rate, n_mels=n_mels, to_db=True)
    normalised = np.clip((mel_db + 80.0) / 80.0, 0.0, 1.0)
    frames = normalised.shape[1]
    if frames < target_frames:
        normalised = np.pad(normalised, ((0, 0), (0, target_frames - frames)), mode="edge")
    elif frames > target_frames:
        # Centre crop on the most energetic window rather than the start.
        energy = normalised.sum(axis=0)
        window = np.convolve(energy, np.ones(target_frames), mode="valid")
        start = int(np.argmax(window))
        normalised = normalised[:, start : start + target_frames]
    return normalised[None, :, :].astype(np.float32)


class TorchAudioBackend:
    """Inference wrapper around a trained spectrogram CNN."""

    backend = "torch"
    name = "vanraksha-audio-cnn"

    def __init__(
        self,
        references: list[SpeciesReference],
        weights: str,
        *,
        n_mels: int = 64,
        device: str | None = None,
    ) -> None:
        if not torch_available():  # pragma: no cover
            raise RuntimeError("PyTorch is not installed")
        weights_path = Path(weights)
        if not weights_path.exists():  # pragma: no cover
            raise FileNotFoundError(f"audio weights not found: {weights_path}")

        import torch  # pragma: no cover - optional dependency

        checkpoint = torch.load(str(weights_path), map_location="cpu", weights_only=False)
        class_labels: list[str] = list(checkpoint.get("classes") or [])
        if not class_labels:
            raise ValueError("audio checkpoint does not record its class list")

        self._n_mels = int(checkpoint.get("n_mels", n_mels))
        self._device = torch.device(device or "cpu")
        self._model = build_model(len(class_labels), n_mels=self._n_mels)
        self._model.load_state_dict(checkpoint["state_dict"])
        self._model.eval().to(self._device)
        self.version = str(checkpoint.get("version") or weights_path.stem)

        by_name = {self._normalise(r.scientific_name or ""): r for r in references if
                   r.scientific_name}
        by_label = {self._normalise(r.label): r for r in references}
        self._classes = [
            by_name.get(self._normalise(label))
            or by_label.get(self._normalise(label))
            or SpeciesReference(species_id=None, label=label)
            for label in class_labels
        ]

    @staticmethod
    def _normalise(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    @property
    def classes(self) -> list[SpeciesReference]:
        return list(self._classes)

    def classify(  # pragma: no cover - requires a trained checkpoint
        self, audio: DecodedAudio, *, top_k: int = 5
    ) -> list[Candidate]:
        import torch

        patch = prepare_input(audio, n_mels=self._n_mels)
        with torch.no_grad():
            tensor = torch.from_numpy(patch[None, ...]).to(self._device)
            probabilities = torch.softmax(self._model(tensor)[0], dim=-1).cpu().numpy()
        order = np.argsort(probabilities)[::-1][:top_k]
        return [
            Candidate(
                species_id=self._classes[int(i)].species_id,
                label=self._classes[int(i)].label,
                scientific_name=self._classes[int(i)].scientific_name,
                confidence=float(probabilities[int(i)]),
            )
            for i in order
        ]
