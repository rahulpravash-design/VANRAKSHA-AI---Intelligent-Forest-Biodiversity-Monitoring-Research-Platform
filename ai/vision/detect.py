"""Subject localisation without a trained detector.

Connected-component analysis over the saliency map produced by
:mod:`ai.preprocessing.image` yields usable bounding boxes for deliberate field
photographs and camera-trap frames.  It is not a substitute for a trained
detector on cluttered scenes — which is exactly why
:mod:`ai.vision.ultralytics_backend` takes over whenever weights are available.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from ai.preprocessing.image import rgb_to_hsv
from ai.schema import Detection


def _saliency_map(image: np.ndarray) -> np.ndarray:
    hsv = rgb_to_hsv(image)
    gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
    gy, gx = np.gradient(gray)
    magnitude = np.hypot(gx, gy)
    median_colour = np.median(hsv.reshape(-1, 3), axis=0)
    colour_distance = np.linalg.norm(hsv - median_colour, axis=-1)
    colour_distance /= colour_distance.max() + 1e-8
    edges = magnitude / (magnitude.max() + 1e-8)
    return 0.6 * colour_distance + 0.4 * edges


def _label_components(mask: np.ndarray, min_pixels: int) -> list[np.ndarray]:
    """4-connected component labelling via breadth-first flood fill."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[np.ndarray] = []
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or visited[start_y, start_x]:
                continue
            queue = deque([(start_y, start_x)])
            visited[start_y, start_x] = True
            pixels: list[tuple[int, int]] = []
            while queue:
                y, x = queue.popleft()
                pixels.append((y, x))
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if not (0 <= ny < height and 0 <= nx < width):
                        continue
                    if mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            if len(pixels) >= min_pixels:
                components.append(np.array(pixels))
    return components


def saliency_detections(
    image: np.ndarray,
    *,
    max_detections: int = 12,
    quantile: float = 0.88,
    min_area_share: float = 0.004,
    downsample_to: int = 96,
) -> list[Detection]:
    """Return normalised ``[x, y, w, h]`` boxes ranked by mean saliency."""
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("expected an (H, W, 3) RGB image")

    # Label on a small copy: component analysis is O(pixels) and the boxes are
    # returned in normalised coordinates anyway.
    step = max(1, min(image.shape[0], image.shape[1]) // downsample_to)
    small = image[::step, ::step]
    saliency = _saliency_map(small)
    threshold = float(np.quantile(saliency, quantile))
    mask = saliency >= threshold
    if not mask.any():
        return []

    height, width = mask.shape
    min_pixels = max(4, int(min_area_share * height * width))
    detections: list[Detection] = []
    for pixels in _label_components(mask, min_pixels):
        ys, xs = pixels[:, 0], pixels[:, 1]
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        component_saliency = float(saliency[ys, xs].mean())
        # Compactness rewards blob-like subjects over thin foliage edges.
        compactness = len(pixels) / float(max((y1 - y0) * (x1 - x0), 1))
        score = float(np.clip(0.55 * component_saliency + 0.45 * compactness, 0.0, 1.0))
        detections.append(
            Detection(
                bbox=(x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height),
                score=round(score, 4),
                label="subject",
            )
        )
    detections.sort(key=lambda d: d.score, reverse=True)
    return detections[:max_detections]


def crop_to_detection(image: np.ndarray, detection: Detection, pad: float = 0.08) -> np.ndarray:
    """Crop an image to a detection box with a small context margin."""
    height, width = image.shape[:2]
    x, y, w, h = detection.bbox
    x0 = int(max(0, (x - pad) * width))
    y0 = int(max(0, (y - pad) * height))
    x1 = int(min(width, (x + w + pad) * width))
    y1 = int(min(height, (y + h + pad) * height))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return image
    return image[y0:y1, x0:x1]
