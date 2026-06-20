"""Ranker — rank many items from sparse, noisy pairwise comparisons.

The default :class:`Ranker` is a Bayesian Bradley-Terry engine with active pair
selection. The original Glicko engine is preserved under :mod:`ranker.legacy` and is
selectable via ``Ranker.from_list(..., engine="glicko")``.
"""

from .session import Ranker

__all__ = ["Ranker"]
