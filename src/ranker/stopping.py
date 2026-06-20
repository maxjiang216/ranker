"""Stopping criteria and live progress estimate."""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from .model import BTModel


def decided_fraction(model: BTModel, *, hi: float = 0.9) -> float:
    """Fraction of adjacent pairs (in the current ranking) whose order is clear,
    i.e. ``P(i>j) > hi`` or ``P(i>j) < 1 - hi`` (decided either way)."""
    ranking = model.ranking()
    if len(ranking) < 2:
        return 1.0
    P = model.prob_matrix()
    names = [name for name, _, _ in ranking]
    idx = model.index
    decided = 0
    for k in range(len(names) - 1):
        p = P[idx[names[k]], idx[names[k + 1]]]
        if p > hi or p < 1.0 - hi:
            decided += 1
    return decided / (len(names) - 1)


def max_eig(model: BTModel) -> float:
    return float(model.eig_matrix().max())


def target_budget(model: BTModel, target_per_item: float = 3.0) -> int:
    """Suggested (not enforced) comparison budget = ``target_per_item * N`` (default 3N —
    the empirical sweet spot from benchmarks/accuracy_vs_budget.py: ~0.9 Kendall-tau with
    graded answers, with diminishing returns beyond). Used only for the progress display;
    it does not trigger stopping."""
    import math

    return int(math.ceil(target_per_item * len(model.items)))


def should_stop(
    model: BTModel,
    *,
    tau: float = 0.01,
    decided_hi: float = 0.9,
    decided_frac: float = 0.9,
    min_q: Optional[int] = None,
    max_q: Optional[int] = None,
) -> bool:
    """True only when the ranking is genuinely settled (or the hard cap is hit). The 3N
    budget is a recommendation surfaced via ``progress``, not a stop condition."""
    n = len(model.items)
    q = len(model.comparisons)
    min_q = n if min_q is None else min_q
    max_q = 5 * n if max_q is None else max_q

    if q >= max_q:
        return True
    if q < min_q:
        return False
    if max_eig(model) >= tau:
        return False
    return decided_fraction(model, hi=decided_hi) >= decided_frac


def _unsettled_adjacent(model: BTModel, *, lo: float = 0.25, hi: float = 0.75) -> int:
    ranking = model.ranking()
    if len(ranking) < 2:
        return 0
    P = model.prob_matrix()
    idx = model.index
    names = [name for name, _, _ in ranking]
    return sum(
        1
        for k in range(len(names) - 1)
        if lo < P[idx[names[k]], idx[names[k + 1]]] < hi
    )


def estimate_remaining(eig_history: List[float], tau: float) -> Optional[int]:
    """Estimate questions remaining by fitting ``eig_t ~ I0 * exp(-lambda t)`` to the
    history of best-pair EIG values. Order-of-magnitude only; None if indeterminate."""
    ys = [e for e in eig_history if e > 0]
    if len(ys) < 3:
        return None
    t = np.arange(len(ys), dtype=float)
    logy = np.log(ys)
    # Least-squares slope of log(eig) vs t.
    slope, intercept = np.polyfit(t, logy, 1)
    if slope >= -1e-9:  # not decaying
        return None
    cur = len(ys) - 1
    t_stop = (math.log(tau) - intercept) / slope
    return max(0, int(math.ceil(t_stop - cur)))


def progress(
    model: BTModel,
    *,
    eig_history: Optional[List[float]] = None,
    tau: float = 0.01,
    target_per_item: float = 3.0,
) -> Dict[str, object]:
    """Live progress summary for display."""
    post = model.posterior()
    n = len(model.items)
    trace0 = n * model.prior_sd * model.prior_sd  # prior total variance
    trace = float(np.trace(post.cov))
    confidence = float(np.clip(1.0 - trace / trace0, 0.0, 1.0)) if trace0 > 0 else 0.0
    asked = len(model.comparisons)
    target = target_budget(model, target_per_item)
    est = estimate_remaining(eig_history, tau) if eig_history is not None else None
    return {
        "confidence": confidence,
        "questions_asked": asked,
        "unsettled_pairs": _unsettled_adjacent(model),
        "est_remaining": est,
        "target": target,
        "remaining_to_target": max(0, target - asked),
    }
