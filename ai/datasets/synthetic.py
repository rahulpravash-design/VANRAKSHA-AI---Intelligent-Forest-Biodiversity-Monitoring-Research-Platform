"""A seeded, reproducible evaluation dataset.

Comparing image-only, audio-only and fused identification honestly needs a
labelled set where *both* modalities exist for the same individual, each is
independently noisy, and the difficulty is controllable.  Field data of that
shape takes a season to collect; this generator produces it deterministically
from the reference catalogue so the research comparison can be re-run by anyone
with the same seed and inspected line by line.

What it is: a synthetic benchmark that renders each species' documented visual
traits and acoustic signature with controlled corruption — hue drift, exposure
and blur on the image side; frequency, rhythm and band-energy jitter on the
audio side — plus a configurable rate of *confusable* samples whose appearance
is blended towards a different species.

What it is not: a substitute for field validation.  Absolute numbers from this
benchmark say nothing about accuracy on real camera-trap frames, and
``docs/research/ai-methodology.md`` states that plainly.  What it does support
is the comparison the research question actually asks — whether combining the
two modalities beats either one alone under identical conditions.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ai.preprocessing.audio import AudioFeatures
from ai.schema import SpeciesReference

#: Hour-of-day sampling windows implied by a species' documented activity.
ACTIVITY_WINDOWS: dict[str, tuple[int, int]] = {
    "diurnal": (7, 17),
    "nocturnal": (20, 5),
    "crepuscular": (5, 8),
    "dawn-dusk": (5, 8),
    "diurnal-crepuscular": (6, 18),
    "monsoon-nocturnal": (19, 4),
}


@dataclass(frozen=True)
class SyntheticSample:
    """One labelled observation with optional image and audio evidence."""

    label: str
    species_id: int | None
    image: np.ndarray | None
    audio_features: AudioFeatures | None
    #: 0 = textbook example, 1 = heavily corrupted / confusable
    difficulty: float
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def has_image(self) -> bool:
        return self.image is not None

    @property
    def has_audio(self) -> bool:
        return self.audio_features is not None


# --------------------------------------------------------------------------- #
# colour helpers
# --------------------------------------------------------------------------- #
def hsv_to_rgb(hue: np.ndarray, saturation: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Vectorised HSV→RGB for arrays in ``[0, 1]``."""
    hue = np.asarray(hue, dtype=np.float64) % 1.0
    saturation = np.clip(saturation, 0.0, 1.0)
    value = np.clip(value, 0.0, 1.0)
    i = np.floor(hue * 6.0)
    f = hue * 6.0 - i
    p = value * (1.0 - saturation)
    q = value * (1.0 - f * saturation)
    t = value * (1.0 - (1.0 - f) * saturation)
    i = i.astype(int) % 6
    options = np.stack(
        [
            np.stack([value, t, p], axis=-1),
            np.stack([q, value, p], axis=-1),
            np.stack([p, value, t], axis=-1),
            np.stack([p, q, value], axis=-1),
            np.stack([t, p, value], axis=-1),
            np.stack([value, p, q], axis=-1),
        ]
    )
    return np.take_along_axis(options, i[None, ..., None], axis=0)[0]


_SCENE_BACKGROUND: dict[str, tuple[float, float, float]] = {
    "canopy": (0.28, 0.55, 0.38),
    "understory": (0.25, 0.42, 0.26),
    "grassland": (0.14, 0.45, 0.60),
    "wetland": (0.55, 0.30, 0.52),
    "bark": (0.09, 0.22, 0.40),
    "rock": (0.10, 0.10, 0.52),
    "sky": (0.58, 0.28, 0.80),
}


def _pattern_overlay(
    pattern: str, height: int, width: int, rng: np.random.Generator
) -> np.ndarray:
    """A multiplicative brightness overlay that mimics a coat or leaf pattern."""
    yy, xx = np.mgrid[0:height, 0:width]
    if pattern == "striped":
        overlay = 0.72 + 0.34 * (np.sin(xx / max(width, 1) * np.pi * 9) > 0)
    elif pattern == "barred":
        overlay = 0.74 + 0.32 * (np.sin(yy / max(height, 1) * np.pi * 8) > 0)
    elif pattern == "spotted":
        overlay = np.ones((height, width))
        for _ in range(max(4, (height * width) // 700)):
            cy, cx = rng.integers(0, height), rng.integers(0, width)
            radius = max(2, int(min(height, width) * rng.uniform(0.05, 0.12)))
            mask = (yy - cy) ** 2 + (xx - cx) ** 2 < radius**2
            overlay[mask] *= rng.uniform(0.55, 0.75)
    elif pattern == "mottled":
        blocks_y, blocks_x = max(2, height // 8), max(2, width // 8)
        coarse = rng.uniform(0.78, 1.18, size=(blocks_y, blocks_x))
        # Nearest-neighbour upsample by index lookup so the result is exactly
        # (height, width) for any subject size.
        rows = np.arange(height) * blocks_y // height
        columns = np.arange(width) * blocks_x // width
        overlay = coarse[np.ix_(rows, columns)]
    elif pattern == "leafy":
        overlay = 0.85 + 0.25 * np.sin(yy / 5.0) * np.cos(xx / 7.0)
    elif pattern == "feathered":
        overlay = 0.88 + 0.2 * np.sin((yy + xx) / 4.0)
    else:  # uniform
        overlay = np.full((height, width), 1.0)
    overlay = np.broadcast_to(np.asarray(overlay, dtype=np.float64), (height, width))
    return np.clip(overlay, 0.3, 1.5)


def _blur(image: np.ndarray, radius: int) -> np.ndarray:
    if radius < 1:
        return image
    size = 2 * radius + 1
    padded = np.pad(image, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
    accumulator = np.zeros_like(image)
    for i in range(size):
        for j in range(size):
            accumulator += padded[i : i + image.shape[0], j : j + image.shape[1], :]
    return accumulator / (size * size)


def render_image(
    traits: dict[str, Any],
    rng: np.random.Generator,
    *,
    size: int = 160,
    difficulty: float = 0.0,
    blend_traits: dict[str, Any] | None = None,
) -> np.ndarray:
    """Render a synthetic field photograph from a species' visual traits.

    ``blend_traits`` produces a *confusable* sample: the subject's colour and
    pattern are pulled part-way towards another species, which is how the
    benchmark creates the hard cases that separate the modalities.
    """
    traits = traits or {}
    scene = str(traits.get("scene", "understory")).lower()
    hue_background, saturation_background, value_background = _SCENE_BACKGROUND.get(
        scene, _SCENE_BACKGROUND["understory"]
    )

    # -- background -------------------------------------------------------
    texture = rng.uniform(-0.06, 0.06, size=(size, size))
    hue_map = np.full((size, size), hue_background) + texture * 0.35
    saturation_map = np.clip(
        np.full((size, size), saturation_background) + texture, 0.0, 1.0
    )
    value_map = np.clip(np.full((size, size), value_background) + texture * 1.6, 0.0, 1.0)
    # Dappled forest light.
    yy, xx = np.mgrid[0:size, 0:size]
    value_map *= 0.85 + 0.3 * np.abs(np.sin(xx / 11.0) * np.cos(yy / 13.0))
    image = hsv_to_rgb(hue_map, saturation_map, value_map)

    # -- subject ----------------------------------------------------------
    hues = traits.get("dominant_hues") or [0.3]
    if isinstance(hues, (int, float)):
        hues = [float(hues)]
    subject_hue = float(hues[rng.integers(0, len(hues))])
    subject_saturation = float(traits.get("saturation", 0.4))
    subject_value = float(traits.get("brightness", 0.45))
    pattern = str(traits.get("pattern", "uniform")).lower()

    if blend_traits:
        other_hues = blend_traits.get("dominant_hues") or [subject_hue]
        blend = 0.35 + 0.35 * difficulty
        subject_hue = (1 - blend) * subject_hue + blend * float(other_hues[0])
        subject_saturation = (1 - blend) * subject_saturation + blend * float(
            blend_traits.get("saturation", subject_saturation)
        )
        if rng.random() < 0.5:
            pattern = str(blend_traits.get("pattern", pattern)).lower()

    fill = float(np.clip(traits.get("subject_fill", 0.3), 0.05, 0.9))
    aspect = float(np.clip(traits.get("body_aspect", 1.2), 0.3, 3.0))
    area = fill * size * size
    subject_height = int(np.clip(np.sqrt(area / aspect), 8, size - 4))
    subject_width = int(np.clip(subject_height * aspect, 8, size - 4))
    top = int(rng.integers(0, max(1, size - subject_height)))
    left = int(rng.integers(0, max(1, size - subject_width)))

    # Elliptical mask so the subject has a natural silhouette.
    sub_yy, sub_xx = np.mgrid[0:subject_height, 0:subject_width]
    ellipse = (
        ((sub_yy - subject_height / 2) / (subject_height / 2 + 1e-9)) ** 2
        + ((sub_xx - subject_width / 2) / (subject_width / 2 + 1e-9)) ** 2
    ) <= 1.0

    overlay = _pattern_overlay(pattern, subject_height, subject_width, rng)
    edge_density = float(np.clip(traits.get("edge_density", 0.3), 0.0, 1.0))
    detail = rng.uniform(1.0 - 0.35 * edge_density, 1.0 + 0.35 * edge_density,
                         size=(subject_height, subject_width))

    subject_hue_map = np.full((subject_height, subject_width), subject_hue)
    subject_hue_map += rng.uniform(-0.02, 0.02, size=subject_hue_map.shape)
    subject_saturation_map = np.clip(
        subject_saturation * overlay * detail, 0.0, 1.0
    )
    subject_value_map = np.clip(subject_value * overlay * detail, 0.0, 1.0)
    subject_rgb = hsv_to_rgb(subject_hue_map, subject_saturation_map, subject_value_map)

    region = image[top : top + subject_height, left : left + subject_width, :]
    region[ellipse] = subject_rgb[ellipse]

    # -- corruption -------------------------------------------------------
    exposure = 1.0 + rng.uniform(-0.28, 0.28) * (0.4 + difficulty)
    image = np.clip(image * exposure, 0.0, 1.0)
    image = np.clip(
        image + rng.normal(0.0, 0.02 + 0.06 * difficulty, size=image.shape), 0.0, 1.0
    )
    if difficulty > 0.5 and rng.random() < 0.5:
        image = _blur(image, radius=1)
    return image.astype(np.float32)


# --------------------------------------------------------------------------- #
# audio
# --------------------------------------------------------------------------- #
def sample_audio_features(
    signature: dict[str, Any], rng: np.random.Generator, *, difficulty: float = 0.0
) -> AudioFeatures:
    """Draw a plausible measured feature set for one call of this species."""
    from ai.datasets.reference_species import band_profile_for

    jitter = 0.10 + 0.28 * difficulty
    peak = float(signature.get("peak_hz", 2000.0)) * float(
        np.exp(rng.normal(0.0, jitter))
    )
    bandwidth = max(
        60.0,
        float(signature.get("bandwidth_hz", 600.0)) * float(np.exp(rng.normal(0.0, jitter))),
    )
    reference_pulse = float(signature.get("pulse_rate_hz", 0.0))
    if reference_pulse <= 0:
        pulse = max(0.0, rng.normal(0.0, 0.35))
    else:
        pulse = max(0.0, reference_pulse * float(np.exp(rng.normal(0.0, jitter * 1.25))))
    tonality = float(
        np.clip(signature.get("tonality", 0.5) + rng.normal(0.0, 0.08 + 0.14 * difficulty),
                0.0, 1.0)
    )
    duration = max(
        0.4, float(signature.get("call_duration_s", 1.0)) * rng.uniform(1.5, 6.0)
    )

    profile = np.asarray(band_profile_for(peak, bandwidth), dtype=np.float64)
    # Dirichlet noise around the expected profile: the lower the concentration,
    # the noisier the measured band energies.
    concentration = np.maximum(profile, 1e-3) * (140.0 / (1.0 + 3.0 * difficulty))
    band_energies = rng.dirichlet(concentration)

    snr = float(np.clip(rng.normal(18.0 - 12.0 * difficulty, 4.0), -3.0, 40.0))
    return AudioFeatures(
        duration_seconds=round(duration, 3),
        rms_db=float(np.clip(rng.normal(-22.0, 5.0), -60.0, -3.0)),
        peak_frequency_hz=peak,
        spectral_centroid_hz=peak * rng.uniform(0.92, 1.18),
        bandwidth_hz=bandwidth,
        rolloff_95_hz=peak + bandwidth * rng.uniform(1.4, 2.4),
        pulse_rate_hz=pulse,
        tonality=tonality,
        activity_ratio=float(np.clip(rng.normal(0.45 - 0.2 * difficulty, 0.12), 0.03, 0.95)),
        snr_db=snr,
        band_energies=tuple(float(v) for v in band_energies),
    )


def synthesise_call_wav(
    signature: dict[str, Any],
    *,
    seconds: float = 4.0,
    sample_rate: int = 22_050,
    seed: int = 0,
    noise_level: float = 0.04,
) -> bytes:
    """Render a 16-bit mono WAV that matches an acoustic signature.

    Used by the integration tests to exercise the real decode → spectrogram →
    classify path, rather than injecting pre-computed features.
    """
    rng = np.random.default_rng(seed)
    peak = float(signature.get("peak_hz", 2000.0))
    bandwidth = float(signature.get("bandwidth_hz", 500.0))
    pulse = float(signature.get("pulse_rate_hz", 0.0))
    tonality = float(signature.get("tonality", 0.6))

    t = np.arange(int(sample_rate * seconds)) / sample_rate
    # Tonal core plus a broadband component scaled by (1 - tonality).
    tone = np.sin(2 * np.pi * peak * t + rng.uniform(0, 2 * np.pi))
    tone += 0.35 * np.sin(2 * np.pi * (peak * 2) * t)  # first harmonic
    noise = rng.normal(0.0, 1.0, size=t.size)
    # Shape the noise around the call's band with a simple resonator.
    freqs = np.fft.rfftfreq(t.size, d=1.0 / sample_rate)
    shaped = np.fft.irfft(
        np.fft.rfft(noise) * np.exp(-0.5 * ((freqs - peak) / max(bandwidth, 60.0)) ** 2),
        n=t.size,
    )
    shaped /= np.abs(shaped).max() + 1e-9
    signal = tonality * tone / (np.abs(tone).max() + 1e-9) + (1 - tonality) * shaped

    if pulse > 0:
        envelope = (np.sin(2 * np.pi * pulse * t) > 0.15).astype(np.float64)
        # Soften the gate so the onsets are not clicks.
        kernel = np.hanning(max(3, int(sample_rate * 0.01)))
        envelope = np.convolve(envelope, kernel / kernel.sum(), mode="same")
    else:
        envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 0.2 * t)
    signal = signal * envelope * 0.7 + rng.normal(0.0, noise_level, size=t.size)

    peak_amplitude = np.abs(signal).max() + 1e-9
    pcm = (np.clip(signal / peak_amplitude * 0.9, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# dataset
# --------------------------------------------------------------------------- #
def _sample_hour(reference: SpeciesReference, notes: dict, rng: np.random.Generator) -> int:
    window = ACTIVITY_WINDOWS.get(str(notes.get("activity", "diurnal")), (6, 18))
    start, end = window
    if start <= end:
        return int(rng.integers(start, end + 1))
    span = (24 - start) + end + 1
    return int((start + rng.integers(0, span)) % 24)


def generate_dataset(
    references: list[SpeciesReference],
    *,
    sample_count: int = 240,
    seed: int = 20260917,
    image_size: int = 160,
    confusion_rate: float = 0.30,
    missing_image_rate: float = 0.10,
    missing_audio_rate: float = 0.25,
    notes_by_label: dict[str, dict] | None = None,
) -> list[SyntheticSample]:
    """Build a balanced, reproducible evaluation set.

    Samples are drawn round-robin over the reference species so every class has
    comparable support, and each sample independently loses its image or its
    audio at the configured rates — which is what makes the fusion comparison
    meaningful rather than a formality.
    """
    if not references:
        return []
    rng = np.random.default_rng(seed)
    notes_by_label = notes_by_label or {}
    samples: list[SyntheticSample] = []

    for index in range(sample_count):
        reference = references[index % len(references)]
        difficulty = float(np.clip(rng.beta(2.0, 3.0), 0.0, 1.0))

        blend_traits = None
        if reference.visual_traits and rng.random() < confusion_rate:
            others = [
                r for r in references if r.label != reference.label and r.visual_traits
            ]
            if others:
                blend_traits = others[int(rng.integers(0, len(others)))].visual_traits

        image = None
        if reference.visual_traits and rng.random() >= missing_image_rate:
            image = render_image(
                reference.visual_traits,
                rng,
                size=image_size,
                difficulty=difficulty,
                blend_traits=blend_traits,
            )

        audio_features = None
        if reference.acoustic_signature and rng.random() >= missing_audio_rate:
            audio_features = sample_audio_features(
                reference.acoustic_signature, rng, difficulty=difficulty
            )

        if image is None and audio_features is None:
            # Never emit an evidence-free sample: restore the stronger modality.
            if reference.visual_traits:
                image = render_image(
                    reference.visual_traits, rng, size=image_size, difficulty=difficulty
                )
            elif reference.acoustic_signature:
                audio_features = sample_audio_features(
                    reference.acoustic_signature, rng, difficulty=difficulty
                )
            else:
                continue

        notes = notes_by_label.get(reference.label, {})
        samples.append(
            SyntheticSample(
                label=reference.label,
                species_id=reference.species_id,
                image=image,
                audio_features=audio_features,
                difficulty=difficulty,
                context={
                    "hour": _sample_hour(reference, notes, rng),
                    "category": reference.category,
                    "confusable": blend_traits is not None,
                },
            )
        )
    return samples
