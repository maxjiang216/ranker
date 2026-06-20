import math
from typing import Any, Dict


class Player:
    """
    Represents an object to be ranked.
    Contains rating and rating deviation (Glicko-style).
    """

    Q: float = math.log(10) / 400

    def __init__(self, name: str, *, rating: float = 1500.0, deviation: float = 350.0):
        """
        Initialize a Player.
        :param name: Name of the item/player.
        :param rating: Initial rating (default 1500).
        :param deviation: Initial rating deviation (default 350).
        """
        self.name: str = name
        self.rating: float = rating
        self.deviation: float = deviation
        self.num_matches: int = 0

    def __repr__(self) -> str:
        return (
            f"Player(name={self.name!r}, rating={self.rating:.2f}, "
            f"deviation={self.deviation:.2f}, matches={self.num_matches})"
        )

    def update(self, score: float, opp_rating: float, opp_deviation: float) -> None:
        """
        Update this player's rating and deviation based on the result against an opponent.
        :param score: 1 for win, 0 for loss, 0.5 for tie, or partial values.
        :param opp_rating: Opponent's rating.
        :param opp_deviation: Opponent's deviation.
        """
        d2 = self.get_d2(opp_rating, opp_deviation)
        self.rating = self.get_new_rating(score, opp_rating, opp_deviation, d2)
        self.deviation = self.get_new_deviation(d2)
        self.num_matches += 1

    def get_new_rating(
        self, score: float, opp_rating: float, opp_deviation: float, d2: float
    ) -> float:
        """
        Calculate new rating after a match.
        """
        expected = self.get_expected_score(opp_rating, opp_deviation)
        denom = (1 / (opp_deviation**2)) + (1 / d2)
        return self.rating + self.Q / denom * (score - expected)

    def get_new_deviation(self, d2: float) -> float:
        """
        Calculate new deviation after a match.
        """
        return math.sqrt(1 / (1 / (self.deviation**2) + 1 / d2))

    def get_d2(self, opp_rating: float, opp_deviation: float) -> float:
        """
        Calculate d², a Glicko factor.
        """
        g = self.get_g(opp_deviation)
        expected = self.get_expected_score(opp_rating, opp_deviation)
        return 1 / (self.Q**2 * g**2 * expected * (1 - expected))

    def get_expected_score(self, opp_rating: float, opp_deviation: float) -> float:
        """
        Expected score against an opponent.
        """
        g = self.get_g(opp_deviation)
        return 1 / (1 + 10 ** (g * (opp_rating - self.rating) / 400))

    def get_g(self, deviation: float) -> float:
        """
        Glicko scale factor for a deviation.
        """
        return 1 / math.sqrt(1 + (3 * (self.Q**2) * (deviation**2)) / math.pi**2)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict."""
        return {
            "name": self.name,
            "rating": self.rating,
            "deviation": self.deviation,
            "num_matches": self.num_matches,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        """Deserialize from a dict."""
        obj = cls(data["name"], rating=data["rating"], deviation=data["deviation"])
        obj.num_matches = data.get("num_matches", 0)
        return obj
