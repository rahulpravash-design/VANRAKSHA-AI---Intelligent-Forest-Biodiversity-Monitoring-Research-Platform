"""Isolation Forest, implemented on NumPy.

Faithful to Liu, Ting & Zhou (2008): each tree is grown on a subsample by
choosing a random feature and a random split value inside that feature's range,
to a maximum depth of ``ceil(log2(subsample_size))``.  The anomaly score of a
point is ``2 ** (-E[h(x)] / c(n))`` where ``h`` is its path length and ``c(n)``
is the average path length of an unsuccessful search in a binary search tree.

Written out rather than pulled in from scikit-learn for two reasons: the
platform's only numerical dependency stays NumPy, and the scoring is fully
inspectable for the methodology write-up.  Scores match scikit-learn's ranking
behaviour on the same subsample settings; the absolute values follow the paper's
convention (0.5 ≈ ordinary, → 1 anomalous), not scikit-learn's shifted
``score_samples``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EULER_GAMMA = 0.5772156649015329


def average_path_length(n: int) -> float:
    """``c(n)`` — expected path length of an unsuccessful BST search."""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (np.log(n - 1) + EULER_GAMMA) - 2.0 * (n - 1) / n


@dataclass
class _Node:
    """Either an internal split or a leaf holding its subsample size."""

    size: int
    depth: int
    feature: int | None = None
    threshold: float | None = None
    left: "_Node | None" = None
    right: "_Node | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.feature is None


@dataclass
class _Tree:
    root: _Node
    subsample_size: int

    def path_length(self, point: np.ndarray) -> float:
        node = self.root
        depth = 0
        while not node.is_leaf:
            assert node.feature is not None and node.threshold is not None
            node = node.left if point[node.feature] < node.threshold else node.right  # type: ignore[assignment]
            depth += 1
            if node is None:  # pragma: no cover - defensive
                break
        # Add the expected remaining depth of the unsplit leaf population.
        return depth + average_path_length(node.size if node else 1)


@dataclass
class IsolationForest:
    """An unsupervised outlier scorer for small tabular windows."""

    n_trees: int = 128
    subsample_size: int = 256
    random_state: int = 0
    _trees: list[_Tree] = field(default_factory=list, repr=False)
    _n_features: int = field(default=0, repr=False)
    _training_scores: np.ndarray | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ fit
    def fit(self, X: np.ndarray) -> "IsolationForest":
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        if X.ndim != 2 or X.shape[0] == 0:
            raise ValueError("expected a non-empty 2-D array of shape (samples, features)")
        rng = np.random.default_rng(self.random_state)
        n_samples, self._n_features = X.shape
        subsample = int(min(self.subsample_size, n_samples))
        max_depth = max(1, int(np.ceil(np.log2(max(subsample, 2)))))

        self._trees = []
        for _ in range(self.n_trees):
            indices = rng.choice(n_samples, size=subsample, replace=subsample > n_samples)
            root = self._grow(X[indices], depth=0, max_depth=max_depth, rng=rng)
            self._trees.append(_Tree(root=root, subsample_size=subsample))

        # Keep the in-sample score distribution so callers can turn a
        # contamination rate into a concrete decision threshold.
        self._training_scores = self.score_samples(X)
        return self

    def _grow(self, X: np.ndarray, *, depth: int, max_depth: int, rng) -> _Node:  # noqa: ANN001
        n_samples = X.shape[0]
        if depth >= max_depth or n_samples <= 1:
            return _Node(size=n_samples, depth=depth)

        # Only features with a non-degenerate range can produce a split.
        minima, maxima = X.min(axis=0), X.max(axis=0)
        splittable = np.flatnonzero(maxima - minima > 1e-12)
        if splittable.size == 0:
            return _Node(size=n_samples, depth=depth)

        feature = int(rng.choice(splittable))
        threshold = float(rng.uniform(minima[feature], maxima[feature]))
        mask = X[:, feature] < threshold
        if not mask.any() or mask.all():  # pragma: no cover - numerical edge
            return _Node(size=n_samples, depth=depth)
        return _Node(
            size=n_samples,
            depth=depth,
            feature=feature,
            threshold=threshold,
            left=self._grow(X[mask], depth=depth + 1, max_depth=max_depth, rng=rng),
            right=self._grow(X[~mask], depth=depth + 1, max_depth=max_depth, rng=rng),
        )

    # ---------------------------------------------------------------- score
    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Anomaly scores in ``(0, 1)``; higher means more isolated."""
        if not self._trees:
            raise RuntimeError("call fit() before scoring")
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        if X.shape[1] != self._n_features:
            raise ValueError(
                f"expected {self._n_features} features, received {X.shape[1]}"
            )
        normaliser = average_path_length(self._trees[0].subsample_size) or 1.0
        scores = np.empty(X.shape[0], dtype=np.float64)
        for index, point in enumerate(X):
            mean_path = float(np.mean([tree.path_length(point) for tree in self._trees]))
            scores[index] = 2.0 ** (-mean_path / normaliser)
        return scores

    def threshold_for(self, contamination: float) -> float:
        """The in-sample score above which a point counts as an outlier."""
        if self._training_scores is None:
            raise RuntimeError("call fit() before requesting a threshold")
        contamination = float(np.clip(contamination, 1e-4, 0.5))
        return float(np.quantile(self._training_scores, 1.0 - contamination))

    def predict(self, X: np.ndarray, contamination: float = 0.1) -> np.ndarray:
        """``True`` for points scoring above the contamination threshold."""
        return self.score_samples(X) >= self.threshold_for(contamination)
