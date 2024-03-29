import unittest
from ranker import Ranker
from item import Item

class TestItem(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.item = Item("TestItem", 1500, 200)

    def test_initial_rating(self):
        """Test that the initial rating is set correctly."""
        self.assertEqual(self.item.rating, 1500)

    def test_initial_variance(self):
        """Test that the initial variance is set correctly."""
        self.assertEqual(self.item.variance, 200)

    def test_update_rating_variance(self):
        """Test updating the rating and variance of the item."""
        other_item = Item("OtherItem", 1400, 200)
        self.item.update(1, other_item)  # Assume a win against 'OtherItem'
        # Check if rating and variance updated to expected values; these values need to be calculated based on your update logic
        self.assertNotEqual(self.item.rating, 1500)
        self.assertNotEqual(self.item.variance, 200)


class TestRanker(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.ranker = Ranker()

    def test_import_items(self):
        """Test importing items from a file."""
        # You'll need a sample file with test data
        self.ranker.import_items("test_items.txt")
        self.assertEqual(len(self.ranker.items), 7)

    def test_get_next_comparison(self):
        """Test the selection of the next comparison."""
        # Setup items and possible comparisons
        self.ranker.import_items("test_items.txt")
        next_comparison = self.ranker.get_next_comparison()
        self.assertIsInstance(next_comparison, tuple)
        self.assertEqual(len(next_comparison), 2)

if __name__ == '__main__':
    unittest.main()