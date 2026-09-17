"""Turning raw model scores into comparable confidences.

Both baseline backends produce an un-normalised score per candidate species: a
distance for vision, a template-match score for audio.  Turning those into a
confidence is a calibration problem, and getting it wrong has a specific
consequence in this platform — the confidence gate either abstains on everything
or commits to everything, and the expert review queue becomes useless either
way.

Two helpers are shared by both backends:

* :func:`standardised_softmax` removes the score scale before the softmax, so a
  temperature keeps its meaning when the descriptor, the weighting or the number
  of reference species changes.
* :func:`reliability` measures how peaked a distribution is, which is what the
  fusion layer uses to decide how much a modality's opinion is worth.
"""

from __future__ import annotations

import numpy as np


def standardised_softmax(
    values: np.ndarray, temperature: float, *, higher_is_better: bool
) -> np.ndarray:
    """Softmax over z-scored values.

    ``higher_is_better`` distinguishes a similarity (audio template match) from a
    distance (vision descriptor).  The result depends only on how far the best
    candidate stands out from its rivals, in units of the candidate set's own
    spread — never on the absolute score scale.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return values
    if values.size == 1:
        return np.ones(1)
    spread = float(values.std())
    centred = values - float(values.mean())
    standardised = centred / spread if spread > 1e-9 else centred
    if not higher_is_better:
        standardised = -standardised
    logits = standardised / max(float(temperature), 1e-3)
    logits -= logits.max()
    weights = np.exp(logits)
    return weights / max(weights.sum(), 1e-12)


def normalised_entropy(probabilities: np.ndarray) -> float:
    """Shannon entropy scaled to ``[0, 1]`` by the uniform distribution's entropy."""
    probabilities = np.asarray(probabilities, dtype=np.float64)
    probabilities = probabilities[probabilities > 0]
    if probabilities.size <= 1:
        return 0.0
    entropy = float(-(probabilities * np.log(probabilities)).sum())
    return float(np.clip(entropy / np.log(probabilities.size), 0.0, 1.0))


def reliability(probabilities: np.ndarray) -> float:
    """How much a modality's opinion is worth, in ``[0, 1]``.

    ``1 - normalised_entropy``: a modality that concentrates its mass on a few
    species is informative, while one spreading it evenly across the catalogue is
    saying "I don't know" and should not be able to outvote a confident partner
    just because its fixed weight happens to be larger.
    """
    return 1.0 - normalised_entropy(probabilities)
