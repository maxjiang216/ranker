"""Bradley-Terry model state: items, the graded answer log, and derived quantities.

Holds the items being ranked and the raw answer log (the source of truth), maps the
user-facing 1..S preference scale to ``y in [0, 1]``, and exposes everything derived
from the Laplace posterior: rankings, pairwise probabilities, and expected information
gain for active selection.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .inference import Posterior, _sigmoid, fit


class BTModel:
    def __init__(
        self,
        items: Sequence[str],
        *,
        scale: int = 7,
        eta: float = 0.05,
        prior_sd: float = 1.5,
    ):
        if len(set(items)) != len(items):
            raise ValueError("Item names must be unique.")
        if scale < 2:
            raise ValueError("scale must be >= 2.")
        if not (0.0 <= eta < 0.5):
            raise ValueError("eta must be in [0, 0.5).")
        self.items: List[str] = list(items)
        self.index: Dict[str, int] = {name: i for i, name in enumerate(self.items)}
        self.scale = scale
        self.eta = eta
        self.prior_sd = prior_sd
        # Answer log: (left_idx, right_idx, raw_answer on the 1..scale scale).
        self.comparisons: List[Tuple[int, int, float]] = []
        self._posterior: Optional[Posterior] = None

    # -- answer scale ---------------------------------------------------------

    def answer_to_y(self, answer: float) -> float:
        """Map a raw 1..scale answer to preference-for-right ``y in [0, 1]``."""
        if not (1.0 <= answer <= self.scale):
            raise ValueError(f"answer must be in [1, {self.scale}].")
        return (answer - 1.0) / (self.scale - 1.0)

    # -- mutation (invalidates the cached posterior) --------------------------

    def _idx(self, name: str) -> int:
        if name not in self.index:
            raise ValueError(f"Unknown item: {name!r}")
        return self.index[name]

    def add(self, left: str, right: str, answer: float) -> None:
        if left == right:
            raise ValueError("Cannot compare an item to itself.")
        a, b = self._idx(left), self._idx(right)
        self.answer_to_y(answer)  # validate range
        self.comparisons.append((a, b, float(answer)))
        self._posterior = None

    def pop(self) -> Optional[Tuple[str, str, float]]:
        """Remove and return the last comparison as (left, right, answer)."""
        if not self.comparisons:
            return None
        a, b, ans = self.comparisons.pop()
        self._posterior = None
        return self.items[a], self.items[b], ans

    def edit(self, index: int, answer: float) -> None:
        a, b, _ = self.comparisons[index]
        self.answer_to_y(answer)  # validate range
        self.comparisons[index] = (a, b, float(answer))
        self._posterior = None

    # -- inference ------------------------------------------------------------

    def posterior(self) -> Posterior:
        if self._posterior is None:
            comps_y = [(a, b, self.answer_to_y(ans)) for a, b, ans in self.comparisons]
            self._posterior = fit(
                len(self.items), comps_y, eta=self.eta, prior_sd=self.prior_sd
            )
        return self._posterior

    # -- derived quantities ---------------------------------------------------

    def ranking(self) -> List[Tuple[str, float, float]]:
        """Items sorted best-first as (name, score, sd)."""
        post = self.posterior()
        order = np.argsort(-post.mu)
        sd = post.sd
        return [(self.items[i], float(post.mu[i]), float(sd[i])) for i in order]

    def prob_matrix(self) -> np.ndarray:
        """``P[i, j] = P(item i preferred over item j)`` under the posterior."""
        post = self.posterior()
        mu, cov = post.mu, post.cov
        n = len(self.items)
        diff = mu[:, None] - mu[None, :]
        var = np.diag(cov)[:, None] + np.diag(cov)[None, :] - 2.0 * cov
        var = np.clip(var, 0.0, None)
        scaled = diff / np.sqrt(1.0 + math.pi * var / 8.0)
        A = 1.0 - 2.0 * self.eta
        P = self.eta + A * _sigmoid(scaled)
        np.fill_diagonal(P, 0.5)
        return P

    def prob_pref(self, i: str, j: str) -> float:
        return float(self.prob_matrix()[self._idx(i), self._idx(j)])

    def asked_pairs(self) -> set:
        """Set of frozensets of item indices that already have an answer."""
        return {frozenset((a, b)) for a, b, _ in self.comparisons}

    def eig_matrix(self) -> np.ndarray:
        """Expected information gain (nats) for asking each pair.

        Closed form for a Laplace posterior: adding one comparison contributes
        Fisher information ``kappa`` along ``v = e_i - e_j``, so by the matrix
        determinant lemma the entropy drop is ``0.5 * log(1 + kappa * v^T Sigma v)``.
        The expected Fisher information does not depend on the (unknown) outcome, so
        the expectation over answers collapses. Already-asked pairs are set to 0.
        """
        post = self.posterior()
        mu, cov = post.mu, post.cov
        n = len(self.items)
        A = 1.0 - 2.0 * self.eta
        diff = mu[:, None] - mu[None, :]
        s = _sigmoid(diff)
        p = np.clip(self.eta + A * s, 1e-12, 1.0 - 1e-12)
        kappa = (A * s * (1.0 - s)) ** 2 / (p * (1.0 - p))
        var = np.diag(cov)[:, None] + np.diag(cov)[None, :] - 2.0 * cov
        var = np.clip(var, 0.0, None)
        eig = 0.5 * np.log1p(kappa * var)
        np.fill_diagonal(eig, 0.0)
        for pair in self.asked_pairs():
            a, b = tuple(pair)
            eig[a, b] = 0.0
            eig[b, a] = 0.0
        return eig
