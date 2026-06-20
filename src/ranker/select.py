"""Active pair selection: cold-start matchings, then expected-information-gain.

Phase A (cold start): a couple of random *matchings* (each a shuffle paired up as
``(0,1),(2,3),...``) so every item is seen ~twice early, spread across the set. Pairs are
then ordered so no two consecutive questions share an item — comparing the same item
back-to-back feels repetitive. (Strict connectivity isn't needed: the Gaussian prior
anchors every score, and Phase B bridges any gaps.)

Phase B (refinement): pick the un-asked pair with the largest expected information
gain (see ``BTModel.eig_matrix``).

``next_pair`` is side-effect-free: it derives the suggestion purely from the current
answer log, so it is safe to call repeatedly (e.g. once per UI poll).
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from .model import BTModel


class Selector:
    def __init__(self, model: BTModel, *, seed: Optional[int] = None, cold_rounds: int = 2):
        rng = random.Random(seed)
        n = len(model.items)
        seen = set()
        pairs: List[Tuple[int, int]] = []
        for _ in range(cold_rounds):
            perm = list(range(n))
            rng.shuffle(perm)
            for k in range(0, n - 1, 2):
                a, b = perm[k], perm[k + 1]
                key = frozenset((a, b))
                if key not in seen:
                    seen.add(key)
                    pairs.append((a, b))
        self._chain = self._spread(pairs)

    @staticmethod
    def _spread(pairs: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Reorder so adjacent pairs don't share an item (best effort, deterministic)."""
        remaining = list(pairs)
        ordered: List[Tuple[int, int]] = []
        prev: Optional[Tuple[int, int]] = None
        while remaining:
            idx = 0
            for i, p in enumerate(remaining):
                if prev is None or not (set(p) & set(prev)):
                    idx = i
                    break
            prev = remaining.pop(idx)
            ordered.append(prev)
        return ordered

    def next_pair(self, model: BTModel) -> Optional[Tuple[str, str]]:
        """Return the next (left, right) item names to ask, or None if none useful.

        Strict no-repeat rule: never suggest a pair that shares an item with the
        immediately preceding comparison — unless avoidance is impossible (e.g. too few
        items left). Applies in both phases.
        """
        asked = model.asked_pairs()
        avoid = set()
        if model.comparisons:
            la, lb, _ = model.comparisons[-1]
            avoid = {la, lb}

        cold = [(a, b) for a, b in self._chain if frozenset((a, b)) not in asked]

        # Phase A: first un-answered cold-start pair that avoids the last items.
        for a, b in cold:
            if a not in avoid and b not in avoid:
                return model.items[a], model.items[b]

        # Phase B (or cold pairs all blocked): best EIG pair that avoids the last items.
        eig = model.eig_matrix()
        masked = eig.copy()
        for i in avoid:
            masked[i, :] = 0.0
            masked[:, i] = 0.0
        if masked.max() > 0.0:
            a, b = divmod(int(masked.argmax()), eig.shape[0])
            return model.items[a], model.items[b]

        # Avoidance impossible — fall back rather than get stuck.
        if cold:
            a, b = cold[0]
            return model.items[a], model.items[b]
        if eig.max() > 0.0:
            a, b = divmod(int(eig.argmax()), eig.shape[0])
            return model.items[a], model.items[b]
        return None
