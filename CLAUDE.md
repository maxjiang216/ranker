# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The project is managed with **uv** (run everything via `uv run`; there is no global
`python`). `uv sync` creates `.venv` and installs the project, the `dev` dependency
group, and—with `--extra web`—the web extra.

```bash
# Setup (project + dev group + web extra)
uv sync --extra web

# Run all tests
uv run pytest

# Run a single test file / test / keyword
uv run pytest tests/test_bt.py
uv run pytest tests/test_bt.py::test_bt_recovers_clear_order
uv run pytest -k tiers

# CLI (entry point `ranker`, or `python -m ranker`)
uv run ranker new L --items "A,B,C" --scale 7
uv run ranker rank L          # interactive; decimal answers allowed
uv run ranker show L

# Launch the web app (http://127.0.0.1:8000)
uv run ranker-web --port 8000 --data ranker-data   # or: uv run ranker web
```

Dependencies: runtime `numpy`, `scikit-learn`; `[project.optional-dependencies].web`
= `fastapi`, `uvicorn`; `[dependency-groups].dev` = `pytest`, `httpx`, `fastapi`,
`uvicorn`. There is no configured linter/formatter; code follows Black-style formatting
and PEP 484 type hints by convention.

## Architecture

A library (package `ranker` under `src/`, hatchling build) that ranks many items
(typically dozens) from sparse, noisy pairwise comparisons instead of full O(n²)
round-robins. There are **two engines**; the design rationale is in `docs/design.md`.

### Default engine: Bayesian Bradley-Terry (`engine="bt"`)

`ranker.Ranker` (`src/ranker/session.py`) is the orchestrator. Each item has a latent
score `β`; a single Laplace posterior `β ~ N(μ, Σ)` is the **one source of truth** — fit
from the raw answer log after every change. Modules:

- **`model.py`** (`BTModel`) — items, the answer log, the 1..`scale` graded-answer mapping
  (`answer_to_y`: 1→prefer-left, `scale`→prefer-right, mid→tie), and everything derived
  from the posterior: `ranking`, `prob_matrix` (P(i>j)), `eig_matrix`.
- **`inference.py`** — Newton MAP + Hessian → `Posterior(mu, cov)`. numpy-only (no scipy).
  Likelihood `p = η + (1−2η)·σ(β_b − β_a)` with continuous target `y` (graded answers);
  Gaussian prior `N(0, prior_sd²)` fixes the gauge and prevents win-everything blow-up.
- **`select.py`** (`Selector`) — Phase A cold start = random spanning chain (connects the
  graph in N−1 questions; a v1 stand-in for the planned noisy-quicksort); Phase B =
  pick max **expected information gain**. EIG has a closed form, `½·log(1 + κ·varᵢⱼ)`
  (the outcome expectation collapses because expected Fisher info is outcome-independent).
- **`stopping.py`** — `should_stop` (min N, then `max_eig < τ` AND ≥90% adjacent pairs
  decided either way; hard cap 5N) and `progress` (confidence from variance reduction,
  unsettled pairs, exp-decay estimate of remaining questions).
- **`tiers.py`** — `graph_tiers` (default; connected components over uncertain pairs
  `low < P(i>j) < high`, uncertainty-aware) and `kmeans_tiers` (kept option, needs `k`).
- **`hodge.py`** — HodgeRank intransitivity diagnostic. **Measures cardinal (margin)
  consistency, not just ordinal**: additive margins → ~0 residual; saturated answers on a
  chain produce real curl. Reports `inconsistency_ratio` + triangle cycles. Report-only.
- **`tiermaker.py`** — tiermaker.com bridge. Import: tiermaker is behind Cloudflare so
  URLs can't be scraped server-side; flow is browser **"Save As → Webpage, Complete"** then
  `parse_saved_page(html)` (stdlib `html.parser`; reads item-pool `<img>`s, labels from
  `alt`/`title` else filename) + `resolve_src` (sibling `_files/` images). Export:
  `render_tierlist` (Pillow) draws a tiermaker-style PNG — colored S/A/B/… rows + thumbnails.

Comparison convention everywhere: `(a, b, answer)` = left item `a`, right item `b`,
`answer` on the 1..`scale` scale = preference toward the **right** item (generalizes the
legacy `result ∈ [0,1]` "preference for name2"). The on-disk log stores **item names**
(reorder-safe), mapped to indices per fit. Undo/edit just mutate the log and refit.

### Legacy engine: Glicko (`engine="glicko"`, `ranker.legacy`)

The original author's implementation, kept verbatim for posterity (not the default,
no new features). `ranker.legacy.Ranker` + `Player` (`src/ranker/legacy/{glicko,player}.py`).
Online Glicko `add_result` + a batch performance-rating solver (`compile_results` /
`get_performance`, with `shrink_factor` regularization and mean-centering) that *replaces*
the online ratings, + k-means `get_tiers`. Note it still has the two-source-of-truth quirk
(`get_ranking` = online, `dump_tiers` = batch). Tests: `tests/test_legacy.py`.

`Ranker.from_list(..., engine=...)` and `load_state` dispatch between engines; untagged
state files are treated as legacy.

### State format

BT engine: JSON `{version:2, engine:"bt", scale, eta, prior_sd, items, comparisons:
[[left_name, right_name, answer], ...]}`. Comparisons are the raw log (source of truth);
scores are always recomputed, never persisted. Legacy keeps its original format,
tagged `engine:"glicko"`.

### Web app + library

`ranker.library.Library` manages a git-ignored data folder (default `./ranker-data`,
overridable via `$RANKER_DATA` or `--data`): `lists/` (Item/ListSpec input sets),
`sessions/` (BT state), `rankings/` (exported md+json+png), `images/`.
`import_tiermaker(name, html)` builds a list + copies images; `export_ranking` also
renders a PNG when items have local images (`image_paths` helper). `ranker.web` is a
FastAPI app (`create_app`) plus a static SPA in `web/static/`; launch with
`uv run ranker-web`. The web UI is integer-only (1..scale buttons/hotkeys);
decimals stay a CLI feature. The `Selector` is side-effect-free so the UI can poll
`next_pair` each request.

### CLI

`ranker.cli` provides subcommands (`lists`, `new`, `import`, `rank`, `show`, `export`,
`web`) over the same `Library` + `Ranker`. `import` ingests a saved tiermaker page
(`--tiermaker FILE.html`); `export` writes md+json (+ PNG when items have images). `run_session` is the interactive loop (decimal answers; `u`/`f`/`q`);
its `read`/`write`/`save` callbacks are injectable for testing. Entry points in pyproject:
`ranker` → `ranker.cli:main` (also `python -m ranker`), `ranker-web` → the web launcher.

### Not yet built

tiermaker import/export is implemented in the CLI (`tiermaker.py`); a web-UI surface for
it (upload saved page, show/download the rendered PNG) is not yet wired in.
