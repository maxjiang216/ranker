"""How accurate is the ranking after k*N comparisons?

Simulates a noisy user with known true scores, runs the real Ranker pipeline
(cold-start chain + EIG active selection), and reports ranking accuracy as a function
of the comparison budget (in multiples of N). Compares active selection against a
random-pair baseline to show the value of EIG.

Run: uv run python benchmarks/accuracy_vs_budget.py
"""

from __future__ import annotations

import math
import random
from statistics import mean

import numpy as np
from scipy.stats import kendalltau

from ranker.model import BTModel
from ranker.select import Selector

BUDGETS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


def _answer(beta, a, b, scale, eta, rng, mode):
    diff = beta[b] - beta[a]
    if mode == "binary":
        # prefer the truly-better item with BT probability
        p = eta + (1 - 2 * eta) / (1 + math.exp(-diff))
        return scale if rng.random() < p else 1
    # graded: report perceived preference strength on the scale (carries magnitude)
    p = 1 / (1 + math.exp(-diff))
    p = min(max(p + rng.gauss(0, eta), 0.0), 1.0)  # perception noise
    return 1 + (scale - 1) * p


def _accuracy(model, beta):
    mu = model.posterior().mu
    tau = kendalltau(mu, beta).statistic
    k = min(3, len(beta))
    top_true = set(np.argsort([-b for b in beta])[:k])
    top_pred = set(np.argsort(-mu)[:k])
    return tau, len(top_true & top_pred) / k


def run_trial(n, *, strategy, mode, scale, eta, spread, seed):
    rng = random.Random(seed)
    beta = [rng.gauss(0, spread) for _ in range(n)]
    names = [str(i) for i in range(n)]
    model = BTModel(names, scale=scale, eta=0.1)
    selector = Selector(model, seed=seed)

    max_q = int(max(BUDGETS) * n)
    snapshots = {round(k * n): None for k in BUDGETS}
    for q in range(1, max_q + 1):
        if strategy == "active":
            pair = selector.next_pair(model)
            if pair is None:
                break
            a, b = int(pair[0]), int(pair[1])
        else:  # random unasked pair
            asked = model.asked_pairs()
            choices = [
                (i, j)
                for i in range(n)
                for j in range(i + 1, n)
                if frozenset((i, j)) not in asked
            ]
            if not choices:
                break
            a, b = rng.choice(choices)
        model.add(names[a], names[b], _answer(beta, a, b, scale, eta, rng, mode))
        if q in snapshots:
            snapshots[q] = _accuracy(model, beta)
    return snapshots


def main():
    trials = 80
    eta = 0.1
    spread = 1.5
    scale = 7
    print(f"trials={trials}  eta={eta}  spread={spread}  scale={scale}")
    print("tau = Kendall rank corr vs truth (1=perfect); top3 = fraction of true top-3 found\n")
    for mode in ("graded", "binary"):
        print(f"##### {mode.upper()} user #####\n")
        for n in (10, 20, 40):
            print(f"== N = {n} ==")
            header = "budget    " + "".join(f"{int(k*n):>5}" for k in BUDGETS)
            print(header + "   comparisons")
            for strategy in ("active", "random"):
                taus = {round(k * n): [] for k in BUDGETS}
                tops = {round(k * n): [] for k in BUDGETS}
                for t in range(trials):
                    snaps = run_trial(
                        n,
                        strategy=strategy,
                        mode=mode,
                        scale=scale,
                        eta=eta,
                        spread=spread,
                        seed=t,
                    )
                    for q, val in snaps.items():
                        if val is not None:
                            taus[q].append(val[0])
                            tops[q].append(val[1])
                cell = lambda d, k: (
                    f"{mean(d[round(k*n)]):>5.2f}" if d[round(k * n)] else "    -"
                )
                tau_row = "".join(cell(taus, k) for k in BUDGETS)
                top_row = "".join(cell(tops, k) for k in BUDGETS)
                print(f"  {strategy:<6} tau {tau_row}")
                print(f"  {strategy:<6} top3{top_row}")
            print()


if __name__ == "__main__":
    main()
