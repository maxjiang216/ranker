import os
import tempfile
import json
import pytest
from ranker import Ranker

# Use a simple deterministic set of names for reproducibility
PLAYER_NAMES = ["A", "B", "C", "D"]


def make_ranker():
    return Ranker.from_list(PLAYER_NAMES)


def test_init_from_list():
    r = Ranker.from_list(["A", "B"])
    assert sorted([p.name for p in r.players.values()]) == ["A", "B"]


def test_init_from_file(tmp_path):
    fn = tmp_path / "names.txt"
    fn.write_text("A\nB\nC\n")
    r = Ranker.from_file(str(fn))
    assert sorted(r.players.keys()) == ["A", "B", "C"]


def test_add_result_and_ranking():
    r = make_ranker()
    r.add_result("A", "B", 0.0)
    r.add_result("A", "C", 0.0)
    r.add_result("B", "C", 1.0)
    ranking = r.get_ranking()
    # "A" should be ranked highest
    assert ranking[0].name == "A"
    assert all(isinstance(p.rating, float) for p in ranking)


def test_input_validation():
    r = make_ranker()
    with pytest.raises(ValueError):
        r.add_result("A", "A", 1.0)
    with pytest.raises(ValueError):
        r.add_result("A", "B", 1.5)
    with pytest.raises(ValueError):
        r.add_result("A", "X", 1.0)  # X not a player


def test_save_and_load_state(tmp_path):
    r = make_ranker()
    r.add_result("A", "B", 1.0)
    tmpfile = tmp_path / "state.json"
    r.save_state(str(tmpfile))

    # Re-load
    r2 = Ranker.load_state(str(tmpfile))
    assert r2.players["A"].name == "A"
    # Should preserve ratings and comparisons
    assert ("A", "B") in r2.comparisons or ("B", "A") in r2.comparisons


def test_compile_results_spread():
    r = make_ranker()
    r.add_result("A", "B", 1.0)
    r.add_result("C", "D", 1.0)
    r.compile_results()
    rankings = r.get_ranking()
    # Ratings should not all be equal
    unique_ratings = set(round(p.rating, 6) for p in rankings)
    assert len(unique_ratings) > 1
    # All players are still present
    assert set(p.name for p in rankings) == set(PLAYER_NAMES)


def test_get_tiers_partitioning():
    r = make_ranker()
    for i in range(len(PLAYER_NAMES)):
        r.players[PLAYER_NAMES[i]].rating = 100 * i  # deterministic, sorted ratings
    tiers = r.get_tiers(2)
    # All players assigned to a tier
    all_names = [name for names in tiers.values() for name in names]
    assert set(all_names) == set(PLAYER_NAMES)
    # There should be exactly 2 tiers
    assert len(tiers) == 2
    # No tier is empty
    assert all(len(names) > 0 for names in tiers.values())


def test_realistic_interactions_and_tiers():
    r = make_ranker()
    # Simulate a round-robin with some noise
    results = [
        ("A", "B", 1.0),  # A > B
        ("A", "C", 0.75),  # A > C (strong)
        ("A", "D", 0.25),  # D > A (upset)
        ("B", "C", 0.7),  # B > C
        ("B", "D", 0.3),  # D > B
        ("C", "D", 0.8),  # C > D
        ("B", "A", 0.5),  # tie
    ]
    for a, b, score in results:
        r.add_result(a, b, score)
    r.compile_results()
    tiers = r.get_tiers(2)
    # All players are still present and in a tier
    all_names = [name for names in tiers.values() for name in names]
    assert set(all_names) == set(PLAYER_NAMES)
    # There should be exactly 2 tiers
    assert len(tiers) == 2


def test_dump_tiers(tmp_path):
    r = make_ranker()
    r.add_result("A", "B", 1.0)
    filename = tmp_path / "tiers.txt"
    r.dump_tiers(str(filename), n_tiers=2)
    content = filename.read_text()
    assert "Tier 1" in content and "Tier 2" in content
    assert "A" in content and "B" in content


def test_reproducible_kmeans_labels():
    # KMeans can assign cluster labels arbitrarily, but our code sorts by mean rating,
    # so tier 0 should always be the best.
    r = Ranker.from_list(["Best", "Worst"])
    r.players["Best"].rating = 100
    r.players["Worst"].rating = -100
    tiers = r.get_tiers(2)
    # Best should be in tier 0 (sorted by descending mean rating)
    assert "Best" in tiers[0]
    assert "Worst" in tiers[1]


def test_tiers_not_empty():
    r = Ranker.from_list([f"P{i}" for i in range(7)])
    for i in range(6):
        r.add_result(f"P{i}", f"P{i+1}", 1.0)
    tiers = r.get_tiers(3)
    # No tier should be empty
    for names in tiers.values():
        assert len(names) > 0


# Optional: Add performance test for get_performance
def test_get_performance_accuracy():
    r = make_ranker()
    ratings = [1400, 1600]
    # Player scores 1 vs 1400, 0 vs 1600 → average 0.5
    perf = r.get_performance(ratings, 1.0)
    assert abs(perf - 1500) < 1e3  # Should be high
    perf = r.get_performance(ratings, 0.0)
    assert perf < 0  # Should be low
