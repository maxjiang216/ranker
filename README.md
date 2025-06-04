# Ranker

Efficient library for ranking many items from sparse, adaptive pairwise comparisons.

## Motivation

Building a ranked list from a large set of options (e.g., movies, characters, restaurants) can be difficult and tedious.  
Pairwise comparison—asking “Which do you prefer: A or B?”—is often much easier and less prone to bias.  
But doing all possible comparisons scales as O(n²), which is impractical for many items.

**Ranker** addresses this by:
- Using Glicko-style rating updates to infer item strength from limited, noisy data
- Selecting the next pair of items to compare based on which comparison will be most informative (maximizing rating uncertainty reduction)
- Rapidly converging to a useful ranking with far fewer than all possible pairwise comparisons

## Features

- Efficiently build rankings from sparse comparison data
- Suggest the “next best” pair to compare
- Robust to uncertainty and user error
- Supports exporting/importing state and results
- Groups items into “tiers” using clustering

## Installation

```bash
git clone https://github.com/maxjiang216/ranker.git
cd ranker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
````

## License

MIT License
