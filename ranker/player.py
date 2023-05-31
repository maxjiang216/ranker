import math


class Player:
    """
    Represents a player or object that is to be ranked
    Contains information about rating and rating deviation
    """

    Q = math.log(10) / 400

    def __init__(self, name, *, rating=0, deviation=350):
        """
        Initializes a player with a name, rating, and deviation
        """
        self.name = name
        self.rating = rating
        self.deviation = deviation
        self.num_matches = 0

    def __repr__(self):
        return f"Player({self.name}, {self.rating}, {self.deviation}, {self.num_matches})"

    def update(self, score, opp_rating, opp_devation):
        """
        Updates the player's rating and deviation
        based on the score again an opponent
        """

        d2 = self.get_d2(opp_rating, opp_devation)
        new_rating = self.get_new_rating(score, opp_rating, opp_devation, d2)
        new_deviation = self.get_new_deviation(d2)
        self.rating = new_rating
        self.deviation = new_deviation
        self.num_matches += 1

    def get_new_rating(self, score, opp_rating, opp_deviation, d2):
        """
        Get player's new rating based on the score
        against an opponent
        """

        return self.rating + self.Q / (1 / opp_deviation**2 + 1 / d2) * (
            score - self.get_expected_score(opp_rating, opp_deviation)
        )

    def get_new_deviation(self, d2):
        """
        Get player's new deviation based on the score
        against an opponent
        """

        return math.sqrt(1 / (1 / self.deviation**2 + 1 / d2))

    def get_d2(self, opp_rating, opp_deviation):
        """
        Computes
        d^2 = 1/(q^2(g(RD')^2E(1-E)))
        where
        q = ln(10)/400
        g(RD') = 1/sqrt(1 + (3q^2(RD')^2)/pi^2)
        RD' is the rating deviation of the opponent
        E is the expected score against the opponent
        """

        expected_score = self.get_expected_score(opp_rating, opp_deviation)

        return 1 / (
            self.Q**2
            * (self.get_g(opp_deviation) ** 2)
            * expected_score
            * (1 - expected_score)
        )

    def get_expected_score(self, opp_rating, opp_deviation):
        """
        Computes the expected score of the player against the opponent
        E = 1/(1 + 10^(g(RD')(opp_rating - rating)/400))
        """

        return 1 / (
            1 + 10 ** (self.get_g(opp_deviation) * (opp_rating - self.rating) / 400)
        )

    def get_g(self, deviation):
        """
        Computes g(RD)
        g(RD) = 1/sqrt(1 + (3q^2(RD)^2)/pi^2)
        """

        return 1 / math.sqrt(1 + (3 * (self.Q**2) * (deviation**2)) / math.pi**2)
