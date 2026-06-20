"""FastAPI app: pick/create a list, run the comparison loop, export the ranking.

Thin client over :class:`ranker.session.Ranker` + :class:`ranker.library.Library`. The
web UI is integer-only (1..scale buttons / hotkeys); decimals stay a CLI feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..library import Item, Library, ListSpec
from ..session import Ranker

STATIC = Path(__file__).parent / "static"


class ItemIn(BaseModel):
    name: str
    image: Optional[str] = None
    description: Optional[str] = None


class ListIn(BaseModel):
    name: str
    scale: int = 7
    items: List[ItemIn]


class AnswerIn(BaseModel):
    left: str
    right: str
    answer: int


def create_app(data_dir: Optional[str] = None) -> FastAPI:
    library = Library(data_dir)
    app = FastAPI(title="Ranker")
    sessions: Dict[str, Ranker] = {}
    specs: Dict[str, ListSpec] = {}

    def _spec(name: str) -> ListSpec:
        if name not in specs:
            if not library.list_exists(name):
                raise HTTPException(404, f"No such list: {name}")
            specs[name] = library.load_list(name)
        return specs[name]

    def _ranker(name: str) -> Ranker:
        if name not in sessions:
            _spec(name)  # 404 if missing
            sessions[name] = library.get_session(name)
        return sessions[name]

    def _item(spec: ListSpec, item_name: str) -> dict:
        for it in spec.items:
            if it.name == item_name:
                return {"name": it.name, "image": it.image, "description": it.description}
        return {"name": item_name, "image": None, "description": None}

    def _state(name: str) -> dict:
        spec = _spec(name)
        ranker = _ranker(name)
        pair = ranker.next_pair()
        stop = ranker.should_stop()
        out = {
            "list": name,
            "scale": spec.scale,
            "asked": len(ranker.model.comparisons),
            "progress": ranker.progress(),
            "should_stop": stop,
            "pair": None,
        }
        if pair is not None:
            out["pair"] = {
                "left": _item(spec, pair[0]),
                "right": _item(spec, pair[1]),
            }
        return out

    def _tiers(ranker: Ranker, method: str, k: int, low: float, high: float):
        if method == "kmeans":
            return ranker.tiers(method="kmeans", k=k)
        return ranker.tiers(method="graph", low=low, high=high)

    def _result(
        name: str,
        *,
        method: str = "graph",
        k: int = 5,
        low: float = 0.2,
        high: float = 0.8,
    ) -> dict:
        spec = _spec(name)
        ranker = _ranker(name)
        scores = {n: (s, sd) for n, s, sd in ranker.ranking()}
        # Tiers, each a list of items (best-first) carrying display metadata + score.
        tiers = []
        for tier in _tiers(ranker, method, k, low, high):
            tiers.append(
                [
                    {
                        "item": _item(spec, n),
                        "score": scores[n][0],
                        "sd": scores[n][1],
                    }
                    for n in tier
                ]
            )
        ranking = [
            {"item": _item(spec, n), "score": s, "sd": sd}
            for n, (s, sd) in scores.items()
        ]
        return {
            "list": name,
            "method": method,
            "ranking": ranking,
            "tiers": tiers,
            "cycles": ranker.report_cycles(),
        }

    # -- lists ----------------------------------------------------------------

    @app.get("/api/lists")
    def get_lists():
        return [
            {"name": n, "n_items": len(library.load_list(n).items)}
            for n in library.list_names()
        ]

    @app.post("/api/lists")
    def create_list(body: ListIn):
        spec = ListSpec(
            name=body.name,
            scale=body.scale,
            items=[Item(i.name, i.image, i.description) for i in body.items],
        )
        if len({i.name for i in spec.items}) != len(spec.items):
            raise HTTPException(400, "Item names must be unique.")
        if len(spec.items) < 2:
            raise HTTPException(400, "A list needs at least 2 items.")
        library.save_list(spec)
        specs.pop(body.name, None)
        return {"ok": True, "name": body.name}

    @app.get("/api/lists/{name}")
    def get_list(name: str):
        return _spec(name).to_dict()

    # -- session --------------------------------------------------------------

    @app.get("/api/session/{name}")
    def get_session(name: str):
        return _state(name)

    @app.post("/api/session/{name}/answer")
    def answer(name: str, body: AnswerIn):
        ranker = _ranker(name)
        ranker.record(body.left, body.right, body.answer)
        library.save_session(name, ranker)
        return _state(name)

    @app.post("/api/session/{name}/undo")
    def undo(name: str):
        ranker = _ranker(name)
        ranker.undo()
        library.save_session(name, ranker)
        return _state(name)

    @app.get("/api/session/{name}/result")
    def result(
        name: str,
        method: str = "graph",
        k: int = 5,
        low: float = 0.2,
        high: float = 0.8,
    ):
        return _result(name, method=method, k=k, low=low, high=high)

    @app.post("/api/session/{name}/finish")
    def finish(
        name: str,
        method: str = "graph",
        k: int = 5,
        low: float = 0.2,
        high: float = 0.8,
    ):
        ranker = _ranker(name)
        library.save_session(name, ranker)
        if method == "kmeans":
            paths = library.export_ranking(name, ranker, tier_method="kmeans", k=k)
        else:
            paths = library.export_ranking(
                name, ranker, tier_method="graph", low=low, high=high
            )
        return {
            "result": _result(name, method=method, k=k, low=low, high=high),
            "exported": paths,
        }

    # -- static ---------------------------------------------------------------

    app.mount("/images", StaticFiles(directory=str(library.images_dir)), name="images")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC / "index.html"))

    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")

    return app
