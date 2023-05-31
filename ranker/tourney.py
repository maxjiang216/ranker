from player import Player
import math
import random


class Tourney:
    """
    Keeps track of many players
    Will retrieve the best pair to compare at any given point
    """

    def __init__(self, players):
        """
        Initializes a tourney with a list of players
        """
        self.players = players
        self.matches = []

    def get_best_pair(self):
        """
        Gets the best pair to compare
        """

        # Choose player with highest rating deviation
        best_id = self.get_best_player()

        # Choose best opponent for that player
        best_opp_id = self.get_best_opp(best_id)

        return (best_id, best_opp_id)

    def receive_comparison(self, id1, id2, score):
        """
        Receives a comparison between two players
        player with id1 scored score against player with id2
        """

        # Update the players' ratings
        player1_rating = self.players[id1].rating
        player1_deviation = self.players[id1].deviation
        self.players[id1].update(
            score, self.players[id2].rating, self.players[id2].deviation
        )
        self.players[id2].update(1 - score, player1_rating, player1_deviation)

        # Record the match
        self.matches.append((id1, id2, score))

    def get_best_player(self):
        """
        Returns the player with the highest rating deviation
        In case of ties, returns the player with the fewest matches
        In case of ties, returns the player with the highest rating
        In case of ties, chooses randomly
        """

        highest_deviation = 0
        candidates = []

        for i, player in enumerate(self.players):
            if player.deviation > highest_deviation:
                highest_deviation = player.deviation
                candidates = [(i, player)]
            elif player.deviation == highest_deviation:
                candidates.append((i, player))

        if len(candidates) == 1:
            print(f"Best player: {candidates[0][1]} with deviation {highest_deviation}")
            return candidates[0][0]

        fewest_matches = math.inf
        new_candidates = []

        for i, candidate in candidates:
            if candidate.num_matches < fewest_matches:
                fewest_matches = candidate.num_matches
                new_candidates = [(i, candidate)]
            elif candidate.num_matches == fewest_matches:
                new_candidates.append((i, candidate))

        candidates = new_candidates

        if len(candidates) == 1:
            print(f"Best player: {candidates[0][1]} with fewest matches {fewest_matches}")
            return candidates[0][0]

        highest_rating = -math.inf
        new_candidates = []

        for i, candidate in candidates:
            if candidate.rating > highest_rating:
                highest_rating = candidate.rating
                new_candidates = [(i, candidate)]
            elif candidate.rating == highest_rating:
                new_candidates.append((i, candidate))

        candidates = new_candidates

        if len(candidates) == 1:
            print(f"Best player: {candidates[0][1]} with rating {highest_rating}")
            return candidates[0][0]

        print(f"Choosing randomly from candidates {[candidate[1] for candidate in candidates]}")
        return random.choice(candidates)[0]

    def get_best_opp(self, player_id):
        """
        Chooses the opponent with least matches with the given player
        In case of ties, choose the opponent whose expected score is closest to 0.5
        In case of ties, choose opponent with least matches
        In case of ties, choose randomly
        """

        previous_matches = [0] * len(self.players)
        for match in self.matches:
            if match[0] == player_id:
                previous_matches[match[1]] += 1
            elif match[1] == player_id:
                previous_matches[match[0]] += 1
        
        # Choose opponent with least matches
        least_matches = math.inf
        candidates = []

        for i, opponent in enumerate(self.players):
            if i == player_id:
                continue
            if previous_matches[i] < least_matches:
                least_matches = previous_matches[i]
                candidates = [(i, opponent)]
            elif previous_matches[i] == least_matches:
                candidates.append((i, opponent))

        if len(candidates) == 1:
            print(f"Best opponent for {self.players[player_id]}: {candidates[0][1]} with {least_matches} matches")
            return candidates[0][0]
        
        # Choose opponent with expected score closest to 0.5

        player = self.players[player_id]
        closest_distance = 0.5
        new_candidates = []

        for i, opponent in candidates:
            if i == player_id:
                continue
            distance = abs(
                player.get_expected_score(opponent.rating, opponent.deviation) - 0.5
            )
            if distance < closest_distance:
                closest_distance = distance
                new_candidates = [(i, opponent)]
            elif distance == closest_distance:
                new_candidates.append((i, opponent))

        candidates = new_candidates

        if len(candidates) == 1:
            print(f"Best opponent for {self.players[player_id]}: {candidates[0][1]} with distance {closest_distance}")
            return candidates[0][0]
        
        # Choose opponent with least matches
        least_matches = math.inf
        new_candidates = []

        for i, opponent in candidates:
            if i == player_id:
                continue
            if opponent.num_matches < least_matches:
                least_matches = opponent.num_matches
                new_candidates = [(i, opponent)]
            elif opponent.num_matches == least_matches:
                new_candidates.append((i, opponent))

        candidates = new_candidates

        if len(candidates) == 1:
            print(f"Best opponent for {self.players[player_id]}: {candidates[0][1]} with {least_matches} matches")
            return candidates[0][0]

        print(f"For {self.players[player_id]}, choosing randomly from candidates {[candidates[i][1] for i in range(len(candidates))]}")
        return random.choice(candidates)[0]

    def run(self, filename="results.txt"):
        """
        Runs the tourney
        Writes the results to a file
        """

        response = ""
        while response != "q":
            best_pair = self.get_best_pair()
            response = input(
                f"{self.players[best_pair[0]].name} vs {self.players[best_pair[1]].name} (1-5), q to quit:\n"
            )
            if response == "q":
                self.write_results(filename)
                self.write_ratings()
                break
            try:
                score = int(response)
                if score < 1 or score > 5:
                    raise ValueError
                self.receive_comparison(best_pair[0], best_pair[1], (5 - score) / 4)
            except ValueError:
                print("Invalid input")
                continue
    

    def write_results(self, filename="results.txt"):
        """
        Writes the results of all matches to a file
        """

        with open(filename, "w") as f:
            for match in self.matches:
                f.write(f"{match[0]} {match[1]} {match[2]}\n")

    def write_ratings(self, *, filename="ratings.txt", epsilon=0.01):
        """
        Writes the ratings of all players to a file
        """

        ratings = self.get_true_ratings(epsilon=epsilon)

        results = [(ratings[i], self.players[i].name) for i in range(len(ratings))]
        results.sort(reverse=True, key=lambda x: x[0])

        with open(filename, "w") as f:
            for result in results:
                f.write(f"{result[1]} {result[0]}\n")

    def get_true_ratings(self, *, epsilon=0.01):
        """
        Returns a list of ratings
        Iteratively calculate performance of players
        Take average of old and new ratings to avoid divergence
        """

        ratings = [1500] * len(self.players)

        while True:

            new_ratings = [0] * len(self.players)

            for i, rating in enumerate(ratings):
                opponents = []
                score = 0
                for match in self.matches:
                    if match[0] == i:
                        opponents.append(ratings[match[1]])
                        score += match[2]
                    elif match[1] == i:
                        opponents.append(ratings[match[0]])
                        score += 1 - match[2]
                if opponents:
                    new_ratings[i] = (rating + self.get_performance(score, opponents, epsilon=epsilon)) / 2
                else:
                    new_ratings[i] = rating

            if all(
                abs(new_ratings[i] - ratings[i]) < epsilon for i in range(len(ratings))
            ):
                break

            ratings = new_ratings
                
        return ratings
    
    @staticmethod
    def get_performance(score, opponents, *, epsilon=0.01):
        """
        Returns the performance rating of a player
        """

        low = 0
        high = 4000

        while high - low > epsilon:
            mid = (low + high) / 2
            expected_score = 0
            for opponent in opponents:
                expected_score += 1 / (1 + 10 ** ((opponent - mid) / 400))
            if expected_score > score:
                high = mid
            else:
                low = mid

        return (low + high) / 2
