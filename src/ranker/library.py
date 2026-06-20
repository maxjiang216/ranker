"""On-disk library of comparison lists, sessions, and exported rankings.

A *list* is a named set of *items* to rank; each item has a name and optional image and
description. The library stores everything under a base folder (default ``./ranker-data``,
overridable with ``$RANKER_DATA``) that is meant to be git-ignored — it is user data:

    <base>/lists/<name>.json       items + metadata (the input set)
    <base>/sessions/<name>.json    in-progress session state (BT v2 format)
    <base>/rankings/<name>.{md,json}   exported final ranking + tiers
    <base>/images/                 optional local item images, served by the web app
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .session import Ranker

DEFAULT_DIR = "ranker-data"
_SAFE = re.compile(r"[^A-Za-z0-9._ -]")


def _slug(name: str) -> str:
    s = _SAFE.sub("_", name).strip()
    if not s:
        raise ValueError("Empty list name.")
    return s


@dataclass
class Item:
    name: str
    image: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(
            name=d["name"], image=d.get("image"), description=d.get("description")
        )


@dataclass
class ListSpec:
    name: str
    items: List[Item] = field(default_factory=list)
    scale: int = 7

    def item_names(self) -> List[str]:
        return [it.name for it in self.items]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scale": self.scale,
            "items": [asdict(it) for it in self.items],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ListSpec":
        return cls(
            name=d["name"],
            scale=d.get("scale", 7),
            items=[Item.from_dict(x) for x in d.get("items", [])],
        )


class Library:
    def __init__(self, base_dir: Optional[str] = None):
        base = base_dir or os.environ.get("RANKER_DATA") or DEFAULT_DIR
        self.base = Path(base)
        self.lists_dir = self.base / "lists"
        self.sessions_dir = self.base / "sessions"
        self.rankings_dir = self.base / "rankings"
        self.images_dir = self.base / "images"
        for d in (self.lists_dir, self.sessions_dir, self.rankings_dir, self.images_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- lists ----------------------------------------------------------------

    def list_names(self) -> List[str]:
        return sorted(p.stem for p in self.lists_dir.glob("*.json"))

    def save_list(self, spec: ListSpec) -> None:
        path = self.lists_dir / f"{_slug(spec.name)}.json"
        path.write_text(json.dumps(spec.to_dict(), indent=2))

    def load_list(self, name: str) -> ListSpec:
        path = self.lists_dir / f"{_slug(name)}.json"
        return ListSpec.from_dict(json.loads(path.read_text()))

    def list_exists(self, name: str) -> bool:
        return (self.lists_dir / f"{_slug(name)}.json").exists()

    # -- sessions -------------------------------------------------------------

    def _session_path(self, name: str) -> Path:
        return self.sessions_dir / f"{_slug(name)}.json"

    def has_session(self, name: str) -> bool:
        return self._session_path(name).exists()

    def new_session(self, name: str, **kwargs) -> Ranker:
        spec = self.load_list(name)
        return Ranker.from_list(spec.item_names(), scale=spec.scale, **kwargs)

    def load_session(self, name: str) -> Ranker:
        return Ranker.load_state(str(self._session_path(name)))

    def get_session(self, name: str, **kwargs) -> Ranker:
        """Load the saved session if present, else start a new one from the list."""
        if self.has_session(name):
            return self.load_session(name)
        return self.new_session(name, **kwargs)

    def save_session(self, name: str, ranker: Ranker) -> None:
        ranker.save_state(str(self._session_path(name)))

    # -- exported rankings ----------------------------------------------------

    def export_ranking(
        self, name: str, ranker: Ranker, *, tier_method: str = "graph", **tier_kwargs
    ) -> Dict[str, str]:
        ranking = ranker.ranking()
        tiers = ranker.tiers(method=tier_method, **tier_kwargs)
        cycles = ranker.report_cycles()

        json_path = self.rankings_dir / f"{_slug(name)}.json"
        json_path.write_text(
            json.dumps(
                {
                    "list": name,
                    "ranking": [
                        {"name": n, "score": s, "sd": sd} for n, s, sd in ranking
                    ],
                    "tiers": tiers,
                    "inconsistency_ratio": cycles["inconsistency_ratio"],
                },
                indent=2,
            )
        )

        lines = [f"# {name} — ranking\n"]
        for i, tier in enumerate(tiers, 1):
            lines.append(f"## Tier {i}")
            for item in tier:
                lines.append(f"- {item}")
            lines.append("")
        lines.append(
            f"_Intransitency: {cycles['inconsistency_ratio']:.1%} of preference "
            f"energy is cyclic._\n"
        )
        md_path = self.rankings_dir / f"{_slug(name)}.md"
        md_path.write_text("\n".join(lines))

        return {"json": str(json_path), "md": str(md_path)}
