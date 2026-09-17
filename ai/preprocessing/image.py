"""Image validation and descriptor extraction.

The descriptor is the feature space shared by the baseline vision classifier and
the reference traits stored on each species, so both sides must agree on its
layout.  It is deliberately hand-designed and interpretable:

===================  ======  ==========================================
block                 size   content
===================  ======  ==========================================
hue histogram            12   circular hue distribution, saliency-weighted
saturation histogram      6   colour purity distribution
value histogram           6   brightness distribution
gradient orientation      8   HOG-style texture orientation profile
texture statistics        4   edge density, edge contrast, roughness, entropy
region geometry           4   subject aspect, fill, centre offset, spread
vegetation cues           4   greenness, brownness, sky/water share, bark share
===================  ======  ==========================================

Total: 44 dimensions (:data:`DESCRIPTOR_LENGTH`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:  # pragma: no cover - Pillow is a hard requirement in practice
    from PIL import Image, ImageFile, UnidentifiedImageError

    ImageFile.LOAD_TRUNCATED_IMAGES = False
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[misc,assignment]

HUE_BINS = 12
SAT_BINS = 6
VAL_BINS = 6
ORIENTATION_BINS = 8
TEXTURE_STATS = 4
REGION_STATS = 4
VEGETATION_CUES = 4
DESCRIPTOR_LENGTH = (
    HUE_BINS + SAT_BINS + VAL_BINS + ORIENTATION_BINS + TEXTURE_STATS + REGION_STATS
    + VEGETATION_CUES
)

#: Slice of the descriptor each block occupies — used by the trait prototypes.
BLOCKS: dict[str, slice] = {}
_offset = 0
for _name, _size in (
    ("hue", HUE_BINS),
    ("saturation", SAT_BINS),
    ("value", VAL_BINS),
    ("orientation", ORIENTATION_BINS),
    ("texture", TEXTURE_STATS),
    ("region", REGION_STATS),
    ("vegetation", VEGETATION_CUES),
):
    BLOCKS[_name] = slice(_offset, _offset + _size)
    _offset += _size
del _offset, _name, _size

MIN_DIMENSION = 32
MAX_DIMENSION = 12_000


class ImageValidationError(ValueError):
    """Raised when an upload is not a usable image."""


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    format: str
    mode: str
    size_bytes: int


def inspect_image(data: bytes) -> ImageInfo:
    """Verify image integrity without trusting the client's filename or MIME type.

    Pillow's ``verify()`` consumes the file, so the image is opened twice: once
    to validate the container and once to read its real dimensions.
    """
    if Image is None:  # pragma: no cover
        raise ImageValidationError("Pillow is not installed; cannot validate images")
    if not data:
        raise ImageValidationError("empty file")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            fmt = (img.format or "UNKNOWN").upper()
            mode = img.mode
    except UnidentifiedImageError as exc:
        raise ImageValidationError("file is not a recognised image") from exc
    except OSError as exc:
        raise ImageValidationError(f"image could not be decoded: {exc}") from exc

    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageValidationError(
            f"image is too small ({width}x{height}); minimum is "
            f"{MIN_DIMENSION}x{MIN_DIMENSION}"
        )
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ImageValidationError(f"image is too large ({width}x{height})")
    return ImageInfo(width=width, height=height, format=fmt, mode=mode, size_bytes=len(data))


def load_image(source: bytes | str | Path, size: int = 224) -> np.ndarray:
    """Load an image as an ``(size, size, 3)`` float array in ``[0, 1]``."""
    if Image is None:  # pragma: no cover
        raise ImageValidationError("Pillow is not installed")
    if isinstance(source, bytes):
        inspect_image(source)
        handle = io.BytesIO(source)
    else:
        handle = Path(source).open("rb")  # noqa: SIM115 - closed by the with below
    try:
        with Image.open(handle) as img:
            rgb = img.convert("RGB").resize((size, size), Image.BILINEAR)
            array = np.asarray(rgb, dtype=np.float32) / 255.0
    finally:
        handle.close()
    return array


# --------------------------------------------------------------------------- #
# colour space
# --------------------------------------------------------------------------- #
def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Vectorised RGB→HSV for an ``(H, W, 3)`` array in ``[0, 1]``."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    delta = maxc - minc

    hue = np.zeros_like(maxc)
    safe = delta > 1e-8
    # Standard piecewise hue definition, in turns (0..1).
    with np.errstate(invalid="ignore", divide="ignore"):
        rc = np.where(safe, (maxc - r) / np.where(safe, delta, 1.0), 0.0)
        gc = np.where(safe, (maxc - g) / np.where(safe, delta, 1.0), 0.0)
        bc = np.where(safe, (maxc - b) / np.where(safe, delta, 1.0), 0.0)
    hue = np.where(maxc == r, bc - gc, hue)
    hue = np.where((maxc == g) & (maxc != r), 2.0 + rc - bc, hue)
    hue = np.where((maxc == b) & (maxc != r) & (maxc != g), 4.0 + gc - rc, hue)
    hue = np.where(safe, (hue / 6.0) % 1.0, 0.0)

    saturation = np.where(maxc > 1e-8, delta / np.where(maxc > 1e-8, maxc, 1.0), 0.0)
    return np.stack([hue, saturation, maxc], axis=-1)


def _sobel(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sobel gradients computed with plain NumPy slicing (no SciPy needed)."""
    padded = np.pad(gray, 1, mode="edge")
    kx = np.array([[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]])
    ky = kx.T
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    for i in range(3):
        for j in range(3):
            window = padded[i : i + gray.shape[0], j : j + gray.shape[1]]
            gx += kx[i, j] * window
            gy += ky[i, j] * window
    return gx, gy


def _histogram(values: np.ndarray, weights: np.ndarray, bins: int) -> np.ndarray:
    hist, _ = np.histogram(values, bins=bins, range=(0.0, 1.0), weights=weights)
    total = hist.sum()
    return (hist / total) if total > 0 else np.full(bins, 1.0 / bins)


def _saliency(hsv: np.ndarray, edge_magnitude: np.ndarray) -> np.ndarray:
    """A cheap subject-versus-background weight map.

    Field photographs are dominated by foliage, so weighting by local contrast
    and by distance from the image's median colour biases the descriptor towards
    the animal or the leaf being photographed rather than the background.
    """
    median_colour = np.median(hsv.reshape(-1, 3), axis=0)
    colour_distance = np.linalg.norm(hsv - median_colour, axis=-1)
    colour_distance /= colour_distance.max() + 1e-8
    edges = edge_magnitude / (edge_magnitude.max() + 1e-8)
    # Centre prior: subjects are usually near the middle of a deliberate shot.
    height, width = hsv.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    centre = np.exp(
        -(((yy / height - 0.5) ** 2 + ((xx / width - 0.5) ** 2)) / (2 * 0.32**2))
    )
    weights = 0.45 * colour_distance + 0.3 * edges + 0.25 * centre
    return weights / (weights.mean() + 1e-8)


def image_descriptor(image: np.ndarray) -> np.ndarray:
    """Compute the 44-dimensional descriptor for a loaded image.

    Each block is individually normalised so that no single block can dominate
    the distance metric, which keeps the baseline classifier stable across
    exposure and white-balance differences between camera traps.
    """
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("expected an (H, W, 3) RGB image")
    image = np.clip(image.astype(np.float32), 0.0, 1.0)
    hsv = rgb_to_hsv(image)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]

    gx, gy = _sobel(gray)
    magnitude = np.hypot(gx, gy)
    weights = _saliency(hsv, magnitude)

    # -- colour -------------------------------------------------------------
    hue_hist = _histogram(hue, weights * sat, HUE_BINS)
    sat_hist = _histogram(sat, weights, SAT_BINS)
    val_hist = _histogram(val, weights, VAL_BINS)

    # -- texture ------------------------------------------------------------
    orientation = (np.arctan2(gy, gx) / np.pi + 1.0) / 2.0  # 0..1
    orient_hist = _histogram(orientation, magnitude, ORIENTATION_BINS)

    norm_mag = magnitude / (magnitude.max() + 1e-8)
    edge_density = float((norm_mag > 0.12).mean())
    edge_contrast = float(norm_mag.std())
    # Roughness: high-frequency residual after a 3x3 box blur.
    blurred = _box_blur(gray, 3)
    roughness = float(np.abs(gray - blurred).mean() * 6.0)
    hist_for_entropy = np.histogram(gray, bins=32, range=(0.0, 1.0))[0].astype(np.float64)
    probabilities = hist_for_entropy / (hist_for_entropy.sum() + 1e-12)
    entropy = float(
        -(probabilities[probabilities > 0] * np.log2(probabilities[probabilities > 0])).sum() / 5.0
    )
    texture = np.array(
        [edge_density, min(edge_contrast * 3.0, 1.0), min(roughness, 1.0), min(entropy, 1.0)]
    )

    # -- subject geometry ---------------------------------------------------
    mask = weights > np.quantile(weights, 0.72)
    if mask.any():
        ys, xs = np.nonzero(mask)
        height_span = (ys.max() - ys.min() + 1) / mask.shape[0]
        width_span = (xs.max() - xs.min() + 1) / mask.shape[1]
        aspect = width_span / (height_span + 1e-8)
        fill = float(mask.mean())
        centre_offset = float(
            np.hypot(xs.mean() / mask.shape[1] - 0.5, ys.mean() / mask.shape[0] - 0.5) * 2.0
        )
        spread = float(np.hypot(xs.std() / mask.shape[1], ys.std() / mask.shape[0]) * 2.0)
    else:  # pragma: no cover - only for degenerate flat images
        aspect, fill, centre_offset, spread = 1.0, 0.0, 0.0, 0.0
    region = np.array(
        [min(aspect / 3.0, 1.0), min(fill * 2.0, 1.0), min(centre_offset, 1.0), min(spread, 1.0)]
    )

    # -- scene / vegetation cues -------------------------------------------
    greenness = float(((hue > 0.20) & (hue < 0.45) & (sat > 0.18)).mean())
    brownness = float(((hue > 0.03) & (hue < 0.13) & (sat > 0.15) & (val < 0.75)).mean())
    sky_water = float(((hue > 0.5) & (hue < 0.72) & (val > 0.45)).mean())
    bark_gray = float(((sat < 0.16) & (val > 0.15) & (val < 0.7)).mean())
    vegetation = np.array([greenness, brownness, sky_water, bark_gray])

    descriptor = np.concatenate(
        [hue_hist, sat_hist, val_hist, orient_hist, texture, region, vegetation]
    ).astype(np.float32)
    assert descriptor.shape[0] == DESCRIPTOR_LENGTH, descriptor.shape
    return np.clip(descriptor, 0.0, 1.0)


def _box_blur(array: np.ndarray, size: int) -> np.ndarray:
    pad = size // 2
    padded = np.pad(array, pad, mode="edge")
    accumulator = np.zeros_like(array)
    for i in range(size):
        for j in range(size):
            accumulator += padded[i : i + array.shape[0], j : j + array.shape[1]]
    return accumulator / (size * size)
