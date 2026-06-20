"""Legacy ranking engine (original author's work, kept for posterity).

Glicko-style online updates + a performance-rating batch solver + k-means tiers.
Preserved unchanged; not the default. Use the new Bradley-Terry engine
(``ranker.Ranker``) for active, uncertainty-aware ranking.
"""

from .glicko import Ranker
from .player import Player

__all__ = ["Ranker", "Player"]
