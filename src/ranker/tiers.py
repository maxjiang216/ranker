"""Tier (grouping) output.

Two methods:
- ``graph`` (default): group items whose order is uncertain. Build an undirected graph
  with an edge whenever ``low < P(i>j) < high``, then take connected components. The
  number of tiers emerges from the posterior; near-tied items stay together.
- ``kmeans``: 1-D k-means over the posterior mean scores with a fixed ``k`` (the original
  behavior, kept for comparison).

Both return a list of tiers, best first, each a list of item names ordered best-first.
"""

from __future__ import annotations

from typing import List

import numpy as np

from .model import BTModel


def _order_by_mean(model: BTModel, groups: List[List[int]]) -> List[List[str]]:
    mu = model.posterior().mu
    groups_sorted = sorted(groups, key=lambda g: -float(np.mean([mu[i] for i in g])))
    out = []
    for g in groups_sorted:
        out.append([model.items[i] for i in sorted(g, key=lambda i: -mu[i])])
    return out


def graph_tiers(model: BTModel, *, low: float = 0.2, high: float = 0.8) -> List[List[str]]:
    n = len(model.items)
    P = model.prob_matrix()
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            if low < P[i, j] < high:
                union(i, j)

    comps: dict = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    return _order_by_mean(model, list(comps.values()))


def kmeans_tiers(model: BTModel, k: int) -> List[List[str]]:
    from sklearn.cluster import KMeans

    n = len(model.items)
    if k < 1:
        raise ValueError("k must be >= 1.")
    k = min(k, n)
    mu = model.posterior().mu
    labels = KMeans(n_clusters=k, n_init=10).fit_predict(mu.reshape(-1, 1))
    groups: dict = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)
    return _order_by_mean(model, list(groups.values()))
