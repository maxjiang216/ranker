import math
import random

import numpy as np
import pytest

from ranker import Ranker
from ranker.model import BTModel


def _simulate(ranker, true_scores, n_comparisons, seed=0, eta=0.0):
    """Feed binary answers generated from a BT model with the given true scores."""
    rng = random.Random(seed)
    names = list(true_scores.keys())
    for _ in range(n_comparisons):
        a, b = rng.sample(names, 2)
        p = eta + (1 - 2 * eta) / (1 + math.exp(-(true_scores[b] - true_scores[a])))
        answer = ranker.model.scale if rng.random() < p else 1
        ranker.record(a, b, answer)


# -- recovery -----------------------------------------------------------------


def test_bt_recovers_clear_order():
    true = {n: s for n, s in zip("ABCDEF", [3.0, 2.0, 1.0, -1.0, -2.0, -3.0])}
    r = Ranker.from_list(list(true), seed=1)
    _simulate(r, true, 400, seed=1)
    recovered = [name for name, _, _ in r.ranking()]
    assert recovered == sorted(true, key=lambda n: -true[n])


def test_bt_robust_to_a_few_mistakes():
    true = {n: s for n, s in zip("ABCDE", [2.0, 1.0, 0.0, -1.0, -2.0])}
    r = Ranker.from_list(list(true), seed=2)
    _simulate(r, true, 300, seed=2, eta=0.0)
    # Inject contradictory answers; the ranking should survive.
    for _ in range(3):
        r.record("E", "A", r.model.scale)  # claim worst beats best
    recovered = [name for name, _, _ in r.ranking()]
    assert recovered[0] == "A" and recovered[-1] == "E"


# -- graded answers -----------------------------------------------------------


def test_tie_answer_leaves_scores_equal():
    r = Ranker.from_list(["A", "B"])
    mid = (r.model.scale + 1) / 2  # 4 on a 1..7 scale
    for _ in range(5):
        r.record("A", "B", mid)
    mu = {n: s for n, s, _ in r.ranking()}
    assert abs(mu["A"] - mu["B"]) < 1e-6


def test_stronger_answer_moves_scores_more():
    weak = Ranker.from_list(["A", "B"])
    strong = Ranker.from_list(["A", "B"])
    weak.record("A", "B", 5)  # mild preference for B
    strong.record("A", "B", 7)  # strong preference for B
    gap = lambda rk: rk.prob("B", "A")
    assert gap(strong) > gap(weak) > 0.5


# -- prior guard --------------------------------------------------------------


def test_winner_of_everything_has_finite_score():
    # answer=scale means the right item is fully preferred; make A always the winner.
    r = Ranker.from_list(["A", "B", "C", "D"])
    for opp in ["B", "C", "D"]:
        for _ in range(5):
            r.record(opp, "A", r.model.scale)  # right=A always preferred
    mu = {n: s for n, s, _ in r.ranking()}
    assert all(math.isfinite(v) for v in mu.values())
    assert r.ranking()[0][0] == "A"


# -- undo / edit --------------------------------------------------------------


def test_undo_restores_posterior():
    r = Ranker.from_list(["A", "B", "C"], seed=3)
    r.record("A", "B", 7)
    before = r.model.posterior().mu.copy()
    r.record("B", "C", 7)
    r.undo()
    after = r.model.posterior().mu
    assert np.allclose(before, after)


def test_edit_changes_fit():
    r = Ranker.from_list(["A", "B"])
    r.record("A", "B", 7)  # B preferred
    b_first = r.prob("B", "A")
    r.edit(0, 1)  # now A preferred
    a_first = r.prob("A", "B")
    assert b_first > 0.5 and a_first > 0.5


# -- EIG ----------------------------------------------------------------------


def test_eig_nonnegative_and_zero_for_asked():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=4)
    r.record("A", "B", 7)
    eig = r.model.eig_matrix()
    assert (eig >= -1e-12).all()
    assert eig[r.model.index["A"], r.model.index["B"]] == 0.0
    assert eig[r.model.index["B"], r.model.index["A"]] == 0.0


def test_next_pair_picks_max_eig():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=5)
    # Exhaust the cold-start chain first.
    while True:
        pre = len(r.model.comparisons)
        pair = r.next_pair()
        if pair is None:
            break
        r.record(pair[0], pair[1], 7)
        if len(r.model.comparisons) - pre == 1 and len(r.model.comparisons) >= 4:
            break
    eig = r.model.eig_matrix()
    pair = r.next_pair()
    if pair is not None:
        a, b = r.model.index[pair[0]], r.model.index[pair[1]]
        assert eig[a, b] == pytest.approx(eig.max())


# -- tiers --------------------------------------------------------------------


def test_graph_tiers_separates_and_merges():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=6)
    # A,B clearly above C,D; within pairs near-tied.
    for _ in range(20):
        r.record("C", "A", 7)
        r.record("D", "A", 7)
        r.record("C", "B", 7)
        r.record("D", "B", 7)
        r.record("A", "B", 4)
        r.record("C", "D", 4)
    tiers = r.tiers(method="graph")
    assert len(tiers) == 2
    assert set(tiers[0]) == {"A", "B"}
    assert set(tiers[1]) == {"C", "D"}


def test_kmeans_tiers_returns_k():
    r = Ranker.from_list([f"P{i}" for i in range(6)], seed=7)
    for i in range(5):
        for _ in range(3):
            r.record(f"P{i+1}", f"P{i}", 7)
    tiers = r.tiers(method="kmeans", k=3)
    assert len(tiers) == 3
    all_items = [x for t in tiers for x in t]
    assert sorted(all_items) == sorted(r.model.items)


# -- hodge --------------------------------------------------------------------


def test_hodge_detects_cycle():
    r = Ranker.from_list(["A", "B", "C"])
    for _ in range(5):
        r.record("A", "B", 7)  # B > A
        r.record("B", "C", 7)  # C > B
        r.record("C", "A", 7)  # A > C  -> cycle
    rep = r.report_cycles()
    assert rep["inconsistency_ratio"] > 0.5
    assert len(rep["cycles"]) >= 1


def test_hodge_consistent_data_low_residual():
    # HodgeRank checks *cardinal* consistency, so the margins must be additive:
    # A beats B by one step, B beats C by one step, A beats C by two steps.
    r = Ranker.from_list(["A", "B", "C"])
    for _ in range(5):
        r.record("A", "B", 2.5)  # mild: A > B  (g = -0.5)
        r.record("B", "C", 2.5)  # mild: B > C  (g = -0.5)
        r.record("A", "C", 1.0)  # strong: A > C (g = -1.0 = sum of the two)
    rep = r.report_cycles()
    assert rep["inconsistency_ratio"] < 1e-6


# -- stopping -----------------------------------------------------------------


def test_should_not_stop_before_floor():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=8)
    r.record("A", "B", 7)
    assert r.should_stop() is False


def test_target_budget_is_recommendation_only():
    n = 10
    r = Ranker.from_list([str(i) for i in range(n)], seed=12)
    prog = r.progress()
    assert prog["target"] == 3 * n
    assert prog["remaining_to_target"] == 3 * n
    r.record("0", "1", 7)
    assert r.progress()["remaining_to_target"] == 3 * n - 1
    # Reaching the budget does NOT force a stop.
    for _ in range(3 * n):
        pair = r.next_pair()
        if pair is None:
            break
        r.record(pair[0], pair[1], 4)  # ties keep it unsettled
    assert r.progress()["remaining_to_target"] == 0
    assert r.should_stop() is False


def test_good_ranking_at_budget():
    # Well-separated scores, graded answers: 3N comparisons should recover the order.
    true = {n: s for n, s in zip("ABCDE", [4.0, 2.0, 0.0, -2.0, -4.0])}
    r = Ranker.from_list(list(true), seed=9)
    n = len(true)
    for _ in range(3 * n):
        pair = r.next_pair()
        if pair is None:  # all pairs exhausted (small N)
            break
        a, b = pair
        p = 1 / (1 + math.exp(-(true[b] - true[a])))
        r.record(a, b, 1 + (r.model.scale - 1) * p)  # graded, noiseless
    assert [name for name, _, _ in r.ranking()] == sorted(true, key=lambda n: -true[n])


# -- determinism & persistence ------------------------------------------------


def test_no_consecutive_item_repeats():
    r = Ranker.from_list([str(i) for i in range(8)], seed=3)
    prev = None
    for _ in range(25):
        pair = r.next_pair()
        if pair is None:
            break
        if prev is not None:
            assert not (set(pair) & set(prev)), f"{prev} then {pair} share an item"
        prev = pair
        r.record(pair[0], pair[1], 5)


def test_seed_determinism():
    r1 = Ranker.from_list(["A", "B", "C", "D"], seed=42)
    r2 = Ranker.from_list(["A", "B", "C", "D"], seed=42)
    assert r1.next_pair() == r2.next_pair()


def test_save_load_roundtrip(tmp_path):
    r = Ranker.from_list(["A", "B", "C"], scale=5, eta=0.1, seed=11)
    r.record("A", "B", 5)
    r.record("B", "C", 4.5)
    path = tmp_path / "state.json"
    r.save_state(str(path))
    r2 = Ranker.load_state(str(path))
    assert r2.model.scale == 5 and r2.model.eta == 0.1
    assert np.allclose(r.model.posterior().mu, r2.model.posterior().mu)


def test_load_untagged_state_uses_legacy(tmp_path):
    from ranker.legacy import Ranker as GlickoRanker

    g = GlickoRanker.from_list(["A", "B"])
    g.add_result("A", "B", 0.0)
    path = tmp_path / "legacy.json"
    g.save_state(str(path))
    loaded = Ranker.load_state(str(path))
    assert isinstance(loaded, GlickoRanker)


def test_glicko_engine_selector():
    from ranker.legacy import Ranker as GlickoRanker

    g = Ranker.from_list(["A", "B"], engine="glicko")
    assert isinstance(g, GlickoRanker)
