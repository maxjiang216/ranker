from item import Item
import math
import random

class Ranker:
    def __init__(self):
        """
        Initialize the Ranker with an empty list of items and an empty dictionary of comparisons.
        """
        self.items = []
        self.comparisons = {}

    def import_items(self, filename):
        """
        Reads items from a text file and initializes their ratings.
        Each line in the file represents one item.
        """
        with open(filename, 'r') as file:
            for line in file:
                name = line.strip()
                item = Item(name)
                if item not in self.items:
                    self.items.append(item)

    def import_state(self, filename):
        self.items = []
        self.comparisons = {}
        with open(filename, 'r') as file:
            import_items = True
            for line in file:
                if line.strip() == "Comparisons":
                    import_items = False
                    continue
    
                if import_items:
                    name, rating, variance = line.strip().split(',')
                    self.items.append(Item(name, float(rating), float(variance)))
                else:
                    pair, results = line.strip().split(':')
                    id1, id2 = map(int, pair.split(','))
                    self.comparisons[(id1, id2)] = [float(result) for result in results.split(',')]

    def export_state(self, filename, compile_results=True):
        if compile_results:
            self.compile_results()
        with open(filename, 'w') as file:
            for item in self.items:
                file.write(f"{item.name},{item.rating},{item.variance}\n")
            file.write("Comparisons\n")
            for (id1, id2), results in self.comparisons.items():
                comparisons_string = ','.join(str(result) for result in results)
                file.write(f"{id1},{id2}:{comparisons_string}\n")
    

    def get_best_item(self, *, choose_random=True):
        """
        Chooses the item with the highest rating variance.
        In case of ties, the item with the highest rating is chosen.
        """

        max_variance_index = []
        # Note that variance is always positive, so we don't need to check for negative values.
        max_variance = (0, 0)

        for i in range(0, len(self.items)):
            if (self.items[i].variance, self.items[i].rating) > max_variance:
                max_variance = (self.items[i].variance, self.items[i].rating)
                max_variance_index = [i]
            elif (self.items[i].variance, self.items[i].rating) == max_variance:
                max_variance_index.append(i)
        if choose_random:
            return random.choice(max_variance_index)
        return max_variance_index[0]
    
    def get_best_opponent(self, id, *, choose_random=True):
        """
        Chooses the item that is the best opponent for the given item.
        Chooses the item with the least comparisons with the given item.
        In case of ties, choose the opponent whose expected score is closest to 0.5.
        In case of ties, choose randomly. If choose_random is False, choose the first item in the tie.
        This case is only likely to happen when there are few comparisons,
        so other tiebreakers will likely not make a difference.
        """

        fewest_matches = math.inf
        best_opponents = []
        for i, opponent in enumerate(self.items):
            if i == id:
                continue
            pair = (id, i) if id < i else (i, id)
            if pair not in self.comparisons:
                if fewest_matches > 0:
                    fewest_matches = 0
                    best_opponents = [i]
                else:
                    best_opponents.append(i)
            elif len(self.comparisons[pair]) < fewest_matches:
                fewest_matches = len(self.comparisons[pair])
                best_opponents = [i]
            elif len(self.comparisons[pair]) == fewest_matches:
                best_opponents.append(i)

        if len(best_opponents) == 1:
            return best_opponents[0]
        
        # Choose opponent with expected score closest to 0.5
        item = self.items[id]
        closest_distance = 0.5
        new_best_opponents = []

        for opponent in best_opponents:
            distance = abs(item.get_expected_score(self.items[opponent]) - 0.5)
            if distance < closest_distance:
                closest_distance = distance
                new_best_opponents = [opponent]
            elif distance == closest_distance:
                new_best_opponents.append(opponent)

        if choose_random:
            return random.choice(new_best_opponents)
        return new_best_opponents[0]

    def get_next_comparison(self):
        """
        Determines and returns the next two items to compare, based on current rankings and comparisons.
        """

        # Choose player with highest rating deviation
        best_id = self.get_best_item()

        # Choose best opponent for that player
        best_opponent_id = self.get_best_opponent(best_id)

        return (self.items[best_id].name, self.items[best_opponent_id].name)

    def add_comparison(self, name1, name2, result):
        """
        Updates the internal ranking system based on the outcome of a comparison.
        'result' is a float from 0 to 1 representing the preference for item2.
        """

        if name1 == name2:
            raise ValueError("Cannot compare an item to itself.")
        if result < 0 or result > 1:
            raise ValueError("Comparison result must be between 0 and 1.")
        
        id1, id2 = -1, -1
        for i, item in enumerate(self.items):
            if item.name == name1:
                id1 = i
            elif item.name == name2:
                id2 = i

        if id1 == -1:
            raise ValueError(f"Item '{name1}' not found.")
        if id2 == -1:
            raise ValueError(f"Item '{name2}' not found.")
        
        if id1 > id2:
            id1, id2 = id2, id1
            result = 1 - result

        pair = (id1, id2)
        if pair not in self.comparisons:
            self.comparisons[pair] = []
        self.comparisons[pair].append(result)

        item1 = self.items[id1]
        item2 = self.items[id2]

        item1_copy = Item(item1.name, item1.rating, item1.variance)
        item1.update(1 - result, item2)
        item2.update(result, item1_copy)

    def get_ranking(self):
        """
        Returns the current ranking of all items.
        """
        return sorted(self.items.values(), key=lambda x: x.rating, reverse=True)

    def get_performance(self, ratings, score, *, epsilon=1e-6):
        """
        Computes the performance of a player based on the ratings of opponents and the score against them.
        """

        low = -10000
        high = 10000

        while high - low > epsilon:
            mid = (high + low) / 2
            expected_score = sum(1 / (1 + 10 ** ((rating - mid) / 400)) for rating in ratings)
            if expected_score < score:
                high = mid
            else:
                low = mid

        return mid

    def compile_results(self, *, epsilon=1e-6):
        """
        Applies a more sophisticated algorithm to refine rankings based on comparisons.
        This is a placeholder for actual implementation.
        """

        ratings = [item.rating for item in self.items]

        while True:

            new_ratings = []

            for i, item in enumerate(self.items):
                opponent_ratings = []
                score = 0
                for comparison in self.comparisons:
                    if comparison[0] == i and len(self.comparisons[comparison]) > 0:
                        opponent_ratings.extend([self.items[comparison[1]].rating] * len(self.comparisons[comparison]))
                        score += sum(self.comparisons[comparison])
                    elif comparison[1] == i and len(self.comparisons[comparison]) > 0:
                        opponent_ratings.extend([self.items[comparison[0]].rating] * len(self.comparisons[comparison]))
                        score += len(self.comparisons[comparison]) - sum(self.comparisons[comparison])

                if not opponent_ratings:
                    new_ratings.append(item.rating)
                    continue

                # Correct by 10% of a draw
                if score == 0:
                    score += 0.05
                elif score == len(opponent_ratings):
                    score -= 0.05

                new_rating = self.get_performance(opponent_ratings, score, epsilon=epsilon)
                new_ratings.append(new_rating)

            if all(abs(new - old) < epsilon for new, old in zip(new_ratings, ratings)):
                break
            ratings = new_ratings

        for i, item in enumerate(self.items):
            item.rating = ratings[i]

