# Ranker Redesign — Design Spec

Status: proposed (2026-06-20). Adds a Bayesian Bradley-Terry engine as the new
**default**, while keeping the original Glicko + performance-solver + k-means
implementation as a selectable **legacy engine** (preserved for posterity, not deleted).
Background research in `research/` (four deep-research docs that independently converged
on this stack).

## 1. Problem

Rank a fixed set of `N` items (typically 20–80) by one user's preference, asked as
pairwise "A or B?" questions in a single session. Optimize for **fewest questions**
while being robust to occasional user mistakes and mild intransitivity, and produce a
**graceful** result at any stopping point (more answers → finer ranking, never a hard
fail).

### Why not the current model
- Items have **fixed latent scores** — they don't drift over time, so Glicko/TrueSkill
  (built for time-varying skill) are the wrong tool.
- Single session = **persistent noise**: re-asking the same pair returns the same
  answer (user is consistent, including consistent mistakes). Re-sampling can't average
  out error, and exact recovery is information-theoretically impossible. A *parametric*
  model (Bradley-Terry) sidesteps this by inferring un-asked pairs from latent scores,
  so we never need the full O(N²) tournament.
- Current code maintains **two contradictory rating systems** (online Glicko via
  `get_ranking`, batch performance-solver via `dump_tiers`) with no single source of
  truth. The new default engine has exactly one: the BT posterior.

### Keeping Glicko
The existing implementation stays in the tree as a legacy engine — it is the author's
original work and is kept **in full** for posterity and comparison: the online Glicko
updates, the batch performance-rating solver (`compile_results` / `get_performance`),
*and* the k-means tiers. All of it moves under `ranker.legacy` unchanged (behavior
preserved, tests preserved) and is selectable via an `engine=` argument. It is not the
default and gains no new features.

## 2. Model

Bradley-Terry with a Gaussian prior, a graded (not binary) answer, and an explicit
error rate.

Each item `i` has a latent score `β_i ∈ ℝ`. For a comparison of items `i` (left) and `j`
(right), `σ(x) = 1/(1 + e^{−x})` and the model's win probability for `j` is

```
P(prefer j | β) = η + (1 − 2η) · σ(β_j − β_i)
```

### Graded answers (not just A-or-B)
The user does not answer a hard binary. They answer on a **linear preference scale**
(Likert-style; human discrimination tops out around 7 points, so 7 is the cap, 5 a
sensible alternative). The scale is configurable, default **1–7**, with **4 = tie**:

```
1 = strongly prefer i (left)      4 = no preference / tie      7 = strongly prefer j (right)
```

Map the raw answer `a` on a `1..S` scale to a soft preference for `j`:

```
y = (a − 1) / (S − 1) ∈ [0, 1]      # 1→0 (all i),  4→0.5 (tie),  7→1 (all j)  for S=7
```

The likelihood uses the **continuous-target (soft) BT cross-entropy** — identical to
binary BT when `y ∈ {0,1}`, and well-defined for fractional `y`:

```
log P(answer | β) = y · log P(prefer j) + (1 − y) · log(1 − P(prefer j))
```

Decimals are allowed (CLI), so a user who feels "between 5 and 6" can enter `5.5`. The
graded signal carries preference *magnitude*: a confident `1` or `7` produces a stronger
gradient than a wishy-washy `3`/`5`, which both sharpens the posterior faster and gives
the cold start better information per question (see §3). This generalizes the original
code's `result ∈ [0,1]` "preference for name2" semantics — that convention is preserved,
just exposed to the user as a friendly integer/decimal scale instead of a raw float.

### Error rate and robustness
- **`η ∈ [0, 0.5)`** — flip / mistake rate. Floors the probability away from 0 and 1, so
  one answer that contradicts many others is treated as likely noise rather than forcing
  a score to ±∞ (Crowd-BT style). Default lowered to **`η = 0.05`**: the graded scale
  already softens individual answers, and the UX provides **undo-last** plus
  **edit-any-comparison** (cheap because the raw answer log is the source of truth — pop
  or rewrite an entry and refit), so we rely less on the likelihood to absorb mistakes.
  Configurable; fixed hyperparameter in v1 (not learned).
- **Prior** `β_i ~ N(0, σ_p²)`, default `σ_p = 1.5`. Fixes the additive gauge (BT is only
  identified up to a shift) and prevents complete-separation blow-up (an item that won
  every comparison). Replaces the ad-hoc mean-centering in the old `compile_results`.

### Inference — Laplace approximation
Maintain a Gaussian posterior `β ~ N(μ, Σ)`:

1. **MAP**: maximize `log P(β) + Σ log P(y_c | β)` over all observed comparisons `c`.
   Concave (BT log-likelihood + Gaussian prior), so a few Newton steps converge.
   `μ = argmax`.
2. **Covariance**: `Σ = (−H)^{−1}`, `H` = Hessian of the log-posterior at `μ`.

`N ≤ 80` → `H` is at most 80×80; full refit after every answer is milliseconds. Refit
each step (no incremental hack needed in v1; revisit only if profiling demands it).

Known limitation (flagged by the research): Laplace under-estimates variance with very
little data. Acceptable for v1. Upgrade path: EP (`choix`) or MCMC behind the same
interface.

### Derived quantities (all from `μ, Σ`)
- **Ranking**: sort by `μ_i` descending.
- **Pair probability** `P(i > j)`: integrate the BT link over the Gaussian on
  `δ = β_i − β_j ~ N(μ_i − μ_j, Σ_ii + Σ_jj − 2Σ_ij)`. Use the probit approximation to
  the logistic-normal integral: `P(i>j) ≈ η + (1−2η)·σ(μ_δ / sqrt(1 + π·s_δ²/8))`.
- **Per-item uncertainty**: `sqrt(Σ_ii)`, or posterior rank distribution via sampling.

## 3. Active pair selection — hybrid

Two phases, switching on comparison count.

### Phase A — cold start (first ~N comparisons): random matchings
Seed the posterior with a couple of random *matchings*: shuffle the items and pair them
up `(0,1),(2,3),…`, repeated for `cold_rounds` (default 2) so every item is seen ~twice,
spread across the set. (This replaced the originally-planned noisy-quicksort: strict
connectivity isn't actually needed because the Gaussian prior anchors every score, so a
matching seed plus Phase B works and is simpler.) Already-asked pairs are never re-asked
(persistent noise → re-ask is wasted).

### Strict no-repeat rule (both phases)
`next_pair` never suggests a pair that shares an item with the **immediately preceding**
comparison — asking about the same item twice in a row feels repetitive. Enforced by
reading the last logged comparison and excluding its two items from the candidate set, in
both Phase A and Phase B. Falls back to allowing a repeat only when avoidance is
impossible (too few items left, e.g. N < 4 late in a session).

### Phase B — refinement: expected information gain (EIG)
For each *un-asked* pair `(i, j)`, compute the expected reduction in posterior entropy
from learning its outcome:

```
EIG(i,j) = H(β) − E_y[ H(β | y) ]
```

With a Gaussian posterior this is cheap:
- Predict `p = P(y=1)` (pair-probability formula above).
- Each hypothetical outcome adds a rank-1 term to `H`; update `Σ` via Sherman-Morrison
  and read the change in `log det Σ` (entropy of a Gaussian ∝ ½ log det Σ).
- `EIG = ½ E_y[ log det Σ − log det Σ_after_y ]`, averaged over `y ∈ {0,1}` weighted by
  `p, 1−p`.

Cost: O(N²) pairs × O(N²) rank-1 update ≈ O(N⁴) ≈ 4×10⁷ at N=80 — fine in NumPy per
question. Pick `argmax EIG`. The same `max EIG` value feeds stopping and progress, so
one computation serves three purposes.

## 4. Stopping

A **suggested budget of 3N** comparisons is shown on the progress bar as a
recommendation — the empirical sweet spot from `benchmarks/accuracy_vs_budget.py`
(graded answers reach ~0.9 Kendall-τ at 3N, diminishing returns after). It does **not**
force a stop: `target_budget` / `progress` expose `target` and `remaining_to_target` for
display only. The user keeps comparing as long as they like and stops whenever (Bayesian
stopping is ignorable — the posterior stays valid).

`should_stop` is a separate, conservative "genuinely settled" signal (used to end when
there's nothing useful left to ask):

```
q ≥ 5N                                  # hard safety cap, OR
q ≥ N AND max_pair EIG < τ              # already very settled:
        AND ≥90% adjacent pairs decided #   P(i>j) > 0.9 OR < 0.1 either way
```

`target_per_item` (default 3.0) is configurable. Benchmark reference (graded user,
spread 1.5): τ ≈ 0.85 / 0.89 / 0.91 at 2N / 2.5N / 3N. Binary (no graded magnitude) is
~half as accurate per question — the 1..S scale roughly doubles information per answer.

## 5. Progress indicator

Report, per step:
- **Confidence %** — normalized total posterior entropy reduction since start.
- **Estimated questions remaining** — fit `EIG_t ≈ I₀·e^{−λt}` online, solve for `t`
  where `EIG = τ`. Order-of-magnitude only; label it approximate.
- **Unsettled pairs** — count of adjacent pairs with `0.25 < P(i>j) < 0.75`.

## 6. Tiers

Tiered output is a first-class feature (kept from the original). Two methods, both
available, chosen via argument so they can be compared by feel:

**(a) Posterior pair-probability graph (new default).** Undirected graph on items with an
edge `(i,j)` whenever the order is uncertain:

```
edge(i, j)  iff  t_lo < P(i > j) < t_hi      # default 0.2 / 0.8
```

Connected components, ordered by mean `μ`, are the tiers. Tier count emerges from the
posterior — no `k` to choose. Optional conservative↔aggressive slider maps to the
threshold band (0.4/0.6 … 0.1/0.9). Uncertainty-aware: won't split statistically tied
items.

**(b) K-means on scores (kept as an option).** 1-D k-means over `μ` with a user-set `k`,
re-indexed so tier 0 is best — the original behavior, available for the new BT engine too
(reuses `scikit-learn`). Ignores uncertainty, but gives a fixed tier count when the user
wants exactly `k` tiers. Useful for side-by-side comparison against (a).

`tiers(method="graph"|"kmeans", ...)`. Default `"graph"`.

**Stretch (later, not now):** export a tier list to / integrate with
[tiermaker.com](https://tiermaker.com/) — produce its expected format directly. Out of
scope for v1; noted so the tier data model stays export-friendly.

## 7. Intransitivity — HodgeRank diagnostic

`η` already absorbs small cycles in the likelihood. On top, run HodgeRank for reporting:
- Build skew-symmetric edge flow `X_ij` from comparison stats.
- Solve `Δ₀ s = div X` (graph-Laplacian least squares) for the gradient/consistent part.
- `‖residual‖² / ‖X‖²` = inconsistency ratio (reliability certificate); split residual
  into curl (local 3-cycles) vs harmonic (global) for diagnosis.

Policy: **report, don't auto-fix.** Surface cycles gently ("these items form a preference
loop"). Offer a single re-ask only for a large high-confidence cycle. Never repeatedly
challenge the user, never silently down-weight.

## 8. Module layout

```
src/ranker/
  model.py       # BTModel: data (items, comparisons, η, prior), MAP fit, Σ, P(i>j), ranking
  inference.py   # Laplace: Newton MAP solve + Hessian  (separable for future EP/MCMC swap)
  select.py      # cold-start sort + EIG; next_pair(), eig_all()
  stopping.py    # should_stop(), progress()
  tiers.py       # pair-probability graph + k-means options
  hodge.py       # HodgeRank decomposition + inconsistency report
  session.py     # Ranker: orchestrates a session, holds state, public API, engine dispatch
  io.py          # save/load session state + list/item library (§11)
  legacy/
    __init__.py
    player.py    # original Player (Glicko) — moved unchanged
    glicko.py    # original Ranker (Glicko updates, compile_results, get_performance, k-means tiers) — moved unchanged
  web/           # localhost web app (§11) — optional extra, depends on FastAPI/uvicorn
    app.py
    static/
```

In the new BT engine the `Player` class is retired: an item is just a name (str) and all
numeric state lives in model arrays indexed by a stable item order. The original
`Player`/Glicko `Ranker` move verbatim into `ranker.legacy` so the old behavior and its
tests keep working.

## 9. Public API (sketch)

```python
r = Ranker.from_list(names, scale=7, eta=0.05, prior_sd=1.5)  # engine="bt" default; "glicko" for legacy
pair = r.next_pair()                 # (name_i, name_j) or None if stop suggested
r.record(name_i, name_j, answer)     # answer = point on the 1..scale linear scale (decimals ok via API/CLI)
r.undo()                             # pop the last comparison and refit
r.edit(index, answer)                # rewrite any past comparison's answer and refit
r.progress()                         # {confidence, est_remaining, unsettled_pairs}
r.should_stop()                      # bool
r.ranking()                          # [(name, score, sd), ...] descending
r.tiers(method="graph", low=0.2, high=0.8)   # or method="kmeans", k=5
r.report_cycles()                    # {inconsistency_ratio, cycles: [...]}
r.save_state(path); Ranker.load_state(path)
```

`record` takes the raw scale point (e.g. `1..7`); the model maps it to `y ∈ [0,1]`
internally (§2). A binary "just pick A/B" is the special case `answer ∈ {1, scale}`.

## 10. State format (v2)

JSON for the BT engine: `{ "version": 2, "engine": "bt", "scale": 7, "items": [...],
"eta": ..., "prior_sd": ..., "comparisons": [[item_i, item_j, answer], ...] }`. In the
persisted log, `item_i`/`item_j` are the **item names** (stable identifiers), not
positional indices — so editing/reordering the `items` list never corrupts the history.
`answer` is the raw scale point. (Internally the model maps names→indices once per fit;
the on-disk format stays name-based.) Comparisons are the **raw answer log** (source of
truth); scores are always recomputed from them, never persisted as truth. This makes
undo/edit trivial (mutate the log, refit). No migration of BT state from v1.

The legacy Glicko engine keeps its original v1 state format (and its own
`save_state`/`load_state`) unchanged. `load_state` dispatches on the `"engine"` tag; a
file **with no tag** is treated as a legacy v1 file (`engine="glicko"`), since only the
old code ever wrote untagged state.

## 11. Lists, items, and UX

### Item & list model
A **list** is a named set of **items** to rank. Each item:

```
{ "name": str, "image": optional path/URL, "description": optional str }
```

Lists (the things to compare) and finished ranked outputs are saved as files in a
local **library folder** that is **git-ignored** (user data, not source):

```
ranker-data/                # gitignored
  lists/<list-name>.json        # items + metadata (the input set)
  sessions/<list-name>.json     # in-progress / finished session state (v2 format, §10)
  rankings/<list-name>.md|json  # exported final rankings + tiers
```

(Exact folder name TBD; add it to `.gitignore`.)

### Interfaces
- **CLI** — full functionality, including **decimal** answers on the 1..S scale. Prompts
  pair, reads a number, supports undo. The reference/most-complete interface.
- **Web app (localhost)** — `ranker.web`, a small FastAPI + static-page server launched
  locally. Selection screen shows the two items with image + description and offers:
  - **click** the choice buttons,
  - **type** a custom score into a textbox that auto-submits ("clicked in") on entry,
  - **hotkeys 1–S** for the scale points.

  Because hotkeys collide with decimal entry, the **web UI is integer-only for now**
  (1..S buttons/hotkeys; no decimals). Decimals remain a CLI feature. Revisit later.

Both interfaces are thin clients over the same `Ranker` API + library files; the web app
is an optional extra dependency, not required for the core library.

## 12. Dependencies

- Add `scipy` (optimize, linalg) — core.
- Keep `numpy` — core.
- Keep `scikit-learn` — k-means tiers (legacy engine *and* new optional k-means tiers).
- Web app (optional extra `ranker[web]`): `fastapi`, `uvicorn`.
- Optional later: `choix` (EP inference).

## 13. Testing

- BT recovery: simulate items with known `β`, generate noisy answers at known `η`,
  assert recovered ranking matches by Kendall-τ within tolerance.
- Graded answers: `answer=4` on a 1–7 scale → `y=0.5` (no rating change at equal scores);
  stronger answers move scores more than weak ones; binary `{1,7}` matches hard BT.
- Prior guard: item that wins every comparison → finite score (no `inf`).
- Undo/edit: `record` then `undo` restores the prior posterior; `edit` of a logged answer
  changes the fit deterministically.
- EIG: chosen pair has higher information than a random pair on average; EIG ≥ 0.
- Tiers: both methods — graph merges near-ties / separates clear gaps; k-means returns `k`.
- HodgeRank: injected 3-cycle → nonzero curl residual; consistent data → ~0 residual.
- Stopping: converges before `5N` on easy synthetic; respects min `N` floor.
- Determinism: fixed seed → reproducible session.
- Legacy: original Glicko tests pass unchanged against `engine="glicko"`.

## 14. Open questions / v2+
- Learn `η` instead of fixing it (per-session reliability).
- EP or MCMC for honest tail uncertainty.
- Incremental posterior update if per-step refit ever becomes a bottleneck (won't at N≤80).
- Item features → GP preference model (Chu & Ghahramani) if cross-item correlation ever wanted.
- tiermaker.com export/integration (§6 stretch).
- Web UI decimals (currently CLI-only due to hotkey collision).
```
