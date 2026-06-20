# Ranker

Rank many items from sparse, noisy **pairwise comparisons** — books to read, anime to
watch, favorite characters — without doing all O(n²) matchups.

Comparing two things ("which do you prefer, A or B?") is easy and low-bias; ranking a
whole list directly is hard. Ranker asks a small number of well-chosen pairwise questions
and infers the full ranking, with uncertainty, from your answers.

## How it works

- **Bayesian Bradley-Terry model.** Each item has a latent score; a single posterior over
  all scores is refit after every answer. It assumes preferences are *mostly* transitive
  but tolerates the occasional mistake and mild intransitivity.
- **Graded answers.** You answer on a 1..*scale* scale (default 1–7, middle = tie), not
  just A/B. The strength of preference roughly *doubles* the information per question.
- **Active selection.** It asks the pair expected to be most informative next, and never
  repeats an item from the previous question.
- **Suggested budget.** Accuracy is good by ~3N comparisons (≈0.9 rank correlation in
  simulation); the progress bar shows this as a recommendation — stop whenever you like.
- **Tiers + diagnostics.** Output groups items into tiers and reports any cyclic
  ("A > B > C > A") inconsistencies in your answers.

Design rationale: [`docs/design.md`](docs/design.md). Background research: [`research/`](research/).

## Install

The project is managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra web      # installs the library + CLI + web app
```

## Command line

```bash
uv run ranker new Anime --items "Spirited Away,Akira,Cowboy Bebop,Naruto" --scale 7
uv run ranker rank Anime      # interactive: answer 1..7 (decimals ok), u=undo f=finish q=quit
uv run ranker show Anime      # print the current ranking + tiers
uv run ranker export Anime    # write md + json (+ a tier-list PNG if items have images)
uv run ranker lists
```

(Also available as `python -m ranker ...`.)

## Import from tiermaker.com

tiermaker.com sits behind Cloudflare, so a URL can't be scraped directly. Instead, open
the template in your browser, **Save As → "Webpage, Complete"**, then import the saved
`.html` (the browser writes the item images into the sibling `_files/` folder):

```bash
uv run ranker import Heroes --tiermaker ~/Downloads/heroes.html --scale 7
uv run ranker rank Heroes
uv run ranker export Heroes   # → ranker-data/rankings/Heroes.png, a tiermaker-style image
```

Item labels come from each image's `alt`/`title` (else the filename). Ranking then exports
a tier-list PNG (colored S/A/B/… rows with thumbnails) rendered locally with Pillow.

## Web app

```bash
uv run ranker-web             # http://127.0.0.1:8000
```

Create lists (each item may have an image and description), compare with buttons or
number keys, watch the progress bar, and finish to a tiered ranking. The web UI is
integer-only; decimals are a CLI feature.

Lists, in-progress sessions, and exported rankings are stored in a git-ignored
`ranker-data/` folder (override with `--data DIR` or `$RANKER_DATA`).

## Library API

```python
from ranker import Ranker

r = Ranker.from_list(["A", "B", "C", "D"], scale=7)
while not r.should_stop():
    pair = r.next_pair()
    if pair is None:
        break
    left, right = pair
    r.record(left, right, answer=...)   # 1..scale, decimals allowed
r.ranking()          # [(name, score, sd), ...] best first
r.tiers(method="kmeans", k=3)
r.report_cycles()    # intransitivity diagnostic
```

The original Glicko-based engine is preserved for posterity and selectable with
`Ranker.from_list(..., engine="glicko")` (see `ranker.legacy`).

## Development

```bash
uv run pytest
```

## License

MIT License
