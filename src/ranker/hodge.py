"""HodgeRank intransitivity diagnostic.

Treat the averaged pairwise preferences as an edge flow on the comparison graph and
project it onto the space of consistent (gradient) flows by weighted least squares.
The leftover residual measures how much of the user's data cannot be explained by *any*
single ranking; large triangle curls localize the cycles (e.g. A>B>C>A).

Policy in this package: report, don't auto-fix.
"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Tuple

import numpy as np

from .model import BTModel


def _edge_flows(model: BTModel) -> Dict[Tuple[int, int], Tuple[float, int]]:
    """For each undirected edge ``(i, j)`` with ``i < j`` return ``(g, weight)`` where
    ``g = 2*mean_pref_for_j - 1 in [-1, 1]`` and ``weight`` is the comparison count."""
    acc: Dict[Tuple[int, int], List[float]] = {}
    for a, b, ans in model.comparisons:
        y = model.answer_to_y(ans)  # preference for the right item b
        if a < b:
            key, pref_for_high = (a, b), y
        else:
            key, pref_for_high = (b, a), 1.0 - y
        acc.setdefault(key, []).append(pref_for_high)
    return {k: (2.0 * float(np.mean(v)) - 1.0, len(v)) for k, v in acc.items()}


def decompose(model: BTModel) -> Dict[str, object]:
    """Return HodgeRank diagnostics.

    Keys: ``scores`` (consistent global score per item), ``inconsistency_ratio`` (in
    [0, 1]; share of weighted flow energy not explained by a ranking), and ``cycles``
    (triangles sorted by absolute curl, worst first).
    """
    n = len(model.items)
    edges = _edge_flows(model)
    if not edges:
        return {
            "scores": {name: 0.0 for name in model.items},
            "inconsistency_ratio": 0.0,
            "cycles": [],
        }

    keys = list(edges.keys())
    m = len(keys)
    D = np.zeros((m, n))
    g = np.zeros(m)
    w = np.zeros(m)
    for r, (i, j) in enumerate(keys):
        gij, cnt = edges[(i, j)]
        D[r, j] = 1.0
        D[r, i] = -1.0
        g[r] = gij
        w[r] = cnt

    sw = np.sqrt(w)
    s, *_ = np.linalg.lstsq(D * sw[:, None], g * sw, rcond=None)
    s = s - s.mean()  # fix the additive gauge

    resid = D @ s - g
    energy = float(w @ (g * g))
    resid_energy = float(w @ (resid * resid))
    ratio = resid_energy / energy if energy > 0 else 0.0

    # Triangle curls localize 3-cycles.
    flow = {k: edges[k][0] for k in keys}
    cycles: List[Dict[str, object]] = []
    for i, j, k in combinations(range(n), 3):
        if (i, j) in flow and (j, k) in flow and (i, k) in flow:
            curl = flow[(i, j)] + flow[(j, k)] - flow[(i, k)]
            if abs(curl) > 1e-9:
                cycles.append(
                    {
                        "items": (model.items[i], model.items[j], model.items[k]),
                        "curl": float(curl),
                    }
                )
    cycles.sort(key=lambda c: -abs(c["curl"]))

    return {
        "scores": {model.items[i]: float(s[i]) for i in range(n)},
        "inconsistency_ratio": float(np.clip(ratio, 0.0, 1.0)),
        "cycles": cycles,
    }
