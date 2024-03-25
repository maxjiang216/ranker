import math

class Item:
    """
    Represents an item to be ranked.
    """

    Q = math.log(10) / 400

    def __init__(self, name, rating=0, variance=350):
        """
        Initializes an item with a name and a rating.
        """
        self.name = name
        self.rating = rating
        self.variance = variance

    def __repr__(self):
        return f"Item({self.name}, {self.rating})"

    def __str__(self):
        return self.name
    
    def __eq__(self, other):
        return self.name == other.name
    
    def get_g(self):
        """
        Computes g(RD)
        g(RD) = 1/sqrt(1 + (3q^2(RD)^2)/pi^2)
        """

        return 1 / math.sqrt(1 + (3 * (self.Q**2) * (self.variance**2)) / math.pi**2)
    
    def get_d2(self, other):
        """
        Computes d^2 = 1/(q^2(g(RD)^2 + g(RD')^2))
        """

        return 1 / (self.Q**2 * (self.get_g()**2 + other.get_g()**2))
    
    def get_expected_score(self, other):
        """
        Computes the expected score of the player against the opponent
        E = 1/(1 + 10^(g(RD')(opp_rating - rating)/400))
        """

        return 1 / (
            1 + 10 ** (self.get_g() * (other.rating - self.rating) / 400)
        )
    
    def get_new_rating(self, score, other):
        """
        Computes the new rating of the player after a match against the opponent
        R' = R + q/(1/(RD^2 + d^2) * (score - E))
        """

        return self.rating + self.Q / (1 / (self.variance**2 + self.get_d2(other)) * (score - self.get_expected_score(other)))
    
    def get_new_variance(self, other):
        """
        Computes the new variance of the player after a match
        RD' = 1/sqrt(1/(RD^2 + d^2))
        """

        return 1 / math.sqrt(1 / self.variance**2 + self.get_d2(other))
    
    def update(self, score, other):
        """
        Updates the item's rating and deviation based on the score against an opponent.
        """
        
        new_rating = self.get_new_rating(score, other)
        new_variance = self.get_new_variance(other)
        self.rating = new_rating
        self.variance = new_variance