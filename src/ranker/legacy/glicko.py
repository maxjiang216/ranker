from __future__ import annotations
from typing import List, Tuple, Dict, Optional
import json
import random
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

from .player import Player


class Ranker:
    """
    Pairwise comparison ranking system (Glicko/Elo-style) with tier list support.
    """

    def __init__(self, players: List[Player]):
        self.players: Dict[str, Player] = {p.name: p for p in players}  # Name → Player
        self.comparisons: Dict[Tuple[str, str], List[float]] = (
            {}
        )  # (name1, name2): [result, ...]
        self.rng = random.SystemRandom()
        self.names_to_avoid: List[str] = []

    @classmethod
    def from_file(cls, filename: str) -> "Ranker":
        """Loads players from a file (one per line)."""
        players = []
        with open(filename, "r") as f:
            for line in f:
                name = line.strip()
                if name:
                    players.append(Player(name))
        return cls(players)

    @classmethod
    def from_list(cls, names: List[str]) -> "Ranker":
        """Loads players from a list of strings."""
        return cls([Player(name) for name in names])

    def save_state(self, filename: str) -> None:
        """Saves current state to a JSON file."""
        state = {
            "players": [p.to_dict() for p in self.players.values()],
            "comparisons": {
                json.dumps([a, b]): results
                for (a, b), results in self.comparisons.items()
            },
        }
        with open(filename, "w") as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state(cls, filename: str) -> "Ranker":
        """Loads state from a JSON file."""
        with open(filename, "r") as f:
            state = json.load(f)
        players = [Player.from_dict(d) for d in state["players"]]
        comparisons = {}
        # Load and convert stringified list back to tuple
        for k, v in state["comparisons"].items():
            a, b = json.loads(k)
            comparisons[(a, b)] = v
        obj = cls(players)
        obj.comparisons = comparisons
        return obj

    def add_result(
        self, name1: str, name2: str, result: float, *, avoid_next: bool = True
    ) -> None:
        """
        Updates the ranking system based on the outcome of a comparison.
        'result' is a float from 0 to 1 representing the preference for name2.
        """
        if name1 == name2:
            raise ValueError("Cannot compare an item to itself.")
        if not (0.0 <= result <= 1.0):
            raise ValueError("Comparison result must be between 0 and 1.")
        if name1 not in self.players or name2 not in self.players:
            raise ValueError("Both compared items must exist.")

        # Sort pair for canonical order
        a, b = sorted([name1, name2])
        canonical_result = result if (name1, name2) == (a, b) else 1.0 - result
        pair = (a, b)
        if pair not in self.comparisons:
            self.comparisons[pair] = []
        self.comparisons[pair].append(canonical_result)

        # Update both players (deep copy so order doesn't matter)
        player1 = self.players[name1]
        player2 = self.players[name2]
        player1_copy = Player(
            player1.name, rating=player1.rating, deviation=player1.deviation
        )
        player1.update(1.0 - result, player2.rating, player2.deviation)
        player2.update(result, player1_copy.rating, player1_copy.deviation)

        if avoid_next:
            self.names_to_avoid = [name1, name2]

    def get_ranking(self) -> List[Player]:
        """
        Returns the current ranking of all players, sorted by rating (descending).
        """
        return sorted(self.players.values(), key=lambda x: x.rating, reverse=True)

    def get_performance(
        self,
        opponent_ratings: List[float],
        score: float,
        *,
        epsilon: float = 1e-6,
        rating_min: float = -4000.0,
        rating_max: float = 4000.0,
    ) -> float:
        """
        Computes the performance rating needed to achieve the given score
        against opponents with the provided ratings.
        Uses binary search. Caps the result for stability.
        """
        low, high = rating_min, rating_max

        while high - low > epsilon:
            mid = (high + low) / 2
            expected_score = sum(
                1 / (1 + 10 ** ((r - mid) / 400)) for r in opponent_ratings
            )
            if expected_score < score:
                low = mid
            else:
                high = mid

        # Clamp to min/max
        return max(rating_min, min(rating_max, mid))

    def compile_results(
        self, *, epsilon: float = 1e-3, shrink_factor: float = 0.95
    ) -> None:
        """
        Refines rankings based on all pairwise comparisons, using a performance-based model.
        Normalizes the ratings at the end.
        """
        # List of player names (to fix order)
        names = list(self.players.keys())
        ratings = [self.players[name].rating for name in names]

        while True:
            new_ratings = ratings.copy()
            for idx, name in enumerate(names):
                item = self.players[name]
                opponent_ratings: List[float] = []
                score = 0.0

                # Find all matches this player participated in
                for (a, b), results in self.comparisons.items():
                    if name == a:
                        opp_idx = names.index(b)
                        num = len(results)
                        opponent_ratings.extend([ratings[opp_idx]] * num)
                        # Each result in [0,1]: higher result = more wins for b
                        # So, for a, score in this comparison is (num - sum(results))
                        score += (num / 2 - sum(results)) * shrink_factor + num / 2
                    elif name == b:
                        opp_idx = names.index(a)
                        num = len(results)
                        opponent_ratings.extend([ratings[opp_idx]] * num)
                        # For b, sum(results) is its score
                        score += (sum(results) - num / 2) * shrink_factor + num / 2

                if not opponent_ratings:
                    new_ratings[idx] = item.rating
                    continue

                new_rating = self.get_performance(
                    opponent_ratings, score, epsilon=epsilon
                )
                new_ratings[idx] = (item.rating + new_rating) / 2

            # Convergence check
            if all(abs(new - old) < epsilon for new, old in zip(new_ratings, ratings)):
                break
            ratings = new_ratings

        # Normalize ratings
        avg_rating = sum(ratings) / len(ratings)
        for idx, name in enumerate(names):
            self.players[name].rating = ratings[idx] - avg_rating

    def get_tiers(self, n: int) -> Dict[int, List[str]]:
        """
        Groups players into n tiers using KMeans clustering on ratings.
        Returns a dictionary mapping tier index to a list of player names.
        """
        ratings = [player.rating for player in self.players.values()]
        names = [player.name for player in self.players.values()]
        data = np.array(ratings).reshape(-1, 1)

        kmeans = KMeans(n_clusters=n, n_init=10)
        labels = kmeans.fit_predict(data)

        # Build mapping from tier index to player names
        tiers: Dict[int, List[str]] = {i: [] for i in range(n)}
        for name, label in zip(names, labels):
            tiers[label].append(name)

        # Optional: sort tiers by average rating descending (so tier 0 is best)
        sorted_tiers = sorted(
            tiers.items(),
            key=lambda kv: -np.mean([self.players[name].rating for name in kv[1]]),
        )
        return {i: names for i, (_, names) in enumerate(sorted_tiers)}

    def dump_tiers(self, filename: str, n_tiers: int = 5) -> None:
        """
        Compiles the ratings, computes the tiers, and outputs the tiered ranking to a file.
        Each tier is labeled and includes the names and final ratings.
        """
        # Compile the results to update all ratings
        self.compile_results()
        # Compute tiers (returns Dict[int, List[str]])
        tiers = self.get_tiers(n_tiers)
        # Build a reverse lookup: name -> rating
        ratings = {player.name: player.rating for player in self.players.values()}

        with open(filename, "w", encoding="utf-8") as f:
            for tier_idx in sorted(tiers):
                f.write(f"Tier {tier_idx + 1}:\n")
                # Sort names in tier by descending rating
                for name in sorted(tiers[tier_idx], key=lambda n: -ratings[n]):
                    f.write(f"  {name}: {ratings[name]:.2f}\n")
                f.write("\n")
