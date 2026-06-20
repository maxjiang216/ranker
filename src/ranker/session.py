"""Session orchestrator — the main public entry point.

``Ranker`` ties together the Bradley-Terry model, active pair selection, stopping,
tiers, and the HodgeRank diagnostic, and persists the raw answer log. The Glicko
implementation is still available as a legacy engine via ``engine="glicko"``.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from . import hodge, stopping, tiers
from .model import BTModel
from .select import Selector

STATE_VERSION = 2


class Ranker:
    def __init__(
        self,
        names: List[str],
        *,
        scale: int = 7,
        eta: float = 0.05,
        prior_sd: float = 1.5,
        seed: Optional[int] = None,
    ):
        self.model = BTModel(names, scale=scale, eta=eta, prior_sd=prior_sd)
        self.seed = seed
        self.selector = Selector(self.model, seed=seed)
        self._eig_history: List[float] = []

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_list(cls, names: List[str], *, engine: str = "bt", **kwargs):
        """Create a ranker. ``engine="bt"`` (default) is the Bayesian Bradley-Terry
        engine; ``engine="glicko"`` returns the legacy Glicko ranker."""
        if engine == "glicko":
            from .legacy import Ranker as GlickoRanker

            return GlickoRanker.from_list(names)
        if engine != "bt":
            raise ValueError(f"Unknown engine: {engine!r}")
        return cls(names, **kwargs)

    @classmethod
    def from_file(cls, filename: str, *, engine: str = "bt", **kwargs):
        with open(filename, "r") as f:
            names = [line.strip() for line in f if line.strip()]
        return cls.from_list(names, engine=engine, **kwargs)

    # -- interaction ----------------------------------------------------------

    def next_pair(self) -> Optional[Tuple[str, str]]:
        """Suggest the next (left, right) items to compare, or None when done.

        Side-effect-free: safe to call repeatedly (e.g. once per UI poll)."""
        return self.selector.next_pair(self.model)

    def record(self, left: str, right: str, answer: float) -> None:
        """Record an answer on the 1..scale preference scale (1=left, scale=right)."""
        self.model.add(left, right, answer)
        # Track the best remaining information gain for the progress estimate.
        self._eig_history.append(stopping.max_eig(self.model))

    def undo(self) -> Optional[Tuple[str, str, float]]:
        """Undo the most recent comparison."""
        if self._eig_history:
            self._eig_history.pop()
        return self.model.pop()

    def edit(self, index: int, answer: float) -> None:
        """Rewrite a past comparison's answer (by position in the log) and refit."""
        self.model.edit(index, answer)

    # -- outputs --------------------------------------------------------------

    def ranking(self) -> List[Tuple[str, float, float]]:
        return self.model.ranking()

    def prob(self, i: str, j: str) -> float:
        return self.model.prob_pref(i, j)

    def tiers(self, method: str = "graph", **kwargs) -> List[List[str]]:
        if method == "graph":
            return tiers.graph_tiers(self.model, **kwargs)
        if method == "kmeans":
            return tiers.kmeans_tiers(self.model, **kwargs)
        raise ValueError(f"Unknown tier method: {method!r}")

    def progress(self, tau: float = 0.01) -> Dict[str, object]:
        return stopping.progress(self.model, eig_history=self._eig_history, tau=tau)

    def should_stop(self, **kwargs) -> bool:
        return stopping.should_stop(self.model, **kwargs)

    def report_cycles(self) -> Dict[str, object]:
        return hodge.decompose(self.model)

    # -- persistence ----------------------------------------------------------

    def save_state(self, filename: str) -> None:
        m = self.model
        state = {
            "version": STATE_VERSION,
            "engine": "bt",
            "scale": m.scale,
            "eta": m.eta,
            "prior_sd": m.prior_sd,
            "seed": self.seed,
            "items": list(m.items),
            "comparisons": [
                [m.items[a], m.items[b], ans] for a, b, ans in m.comparisons
            ],
        }
        with open(filename, "w") as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state(cls, filename: str):
        with open(filename, "r") as f:
            state = json.load(f)
        # Untagged state was only ever written by the legacy engine.
        if state.get("engine", "glicko") == "glicko":
            from .legacy import Ranker as GlickoRanker

            return GlickoRanker.load_state(filename)
        obj = cls(
            state["items"],
            scale=state.get("scale", 7),
            eta=state.get("eta", 0.05),
            prior_sd=state.get("prior_sd", 1.5),
            seed=state.get("seed"),
        )
        for left, right, answer in state["comparisons"]:
            obj.model.add(left, right, answer)
        return obj
