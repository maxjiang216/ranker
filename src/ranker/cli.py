"""Command-line interface for the ranker.

Subcommands::

    ranker lists                       list saved lists
    ranker new NAME --items a,b,c      create a list (or --file items.txt)
    ranker rank NAME                   run an interactive comparison session
    ranker show NAME                   print the current ranking + tiers
    ranker web                         launch the localhost web app

The interactive session accepts **decimal** answers on the 1..scale preference scale
(1 = strongly left, scale = strongly right, middle = tie), plus ``u`` undo, ``f`` finish,
``q`` quit. State is saved to the library after every answer.
"""

from __future__ import annotations

import argparse
import math
from typing import Callable, List, Optional

from .library import Item, Library, ListSpec
from .session import Ranker


def _default_tiers(n: int) -> int:
    return max(1, int(math.isqrt(n)))


def print_ranking(ranker: Ranker, *, k: Optional[int] = None, write: Callable = print) -> None:
    ranking = ranker.ranking()
    n = len(ranking)
    if n == 0:
        write("(no items)")
        return
    k = _default_tiers(n) if k is None else max(1, min(k, n))
    scores = {name: s for name, s, _ in ranking}
    tiers = ranker.tiers(method="kmeans", k=k)
    for i, tier in enumerate(tiers, 1):
        write(f"Tier {i}")
        for name in tier:
            write(f"  {name}  ({scores[name]:+.2f})")
    rep = ranker.report_cycles()
    ratio = rep["inconsistency_ratio"]
    write(f"\nIntransitivity: {ratio:.0%} of preference strength is cyclic.")
    if rep["cycles"]:
        write("  loop: " + " > ".join(rep["cycles"][0]["items"]))


def run_session(
    ranker: Ranker,
    *,
    save: Callable[[Ranker], None],
    read: Callable[[str], str] = input,
    write: Callable = print,
) -> None:
    """Drive the interactive comparison loop. ``read`` is the prompt function (injectable
    for testing); ``save`` persists the session after each answer."""
    scale = ranker.model.scale
    mid = (scale + 1) / 2
    write(
        f"Answer 1..{scale}  (1 = left, {scale:g} = right, {mid:g} = tie; decimals ok). "
        "Commands: u=undo, f=finish, q=quit."
    )
    while True:
        pair = ranker.next_pair()
        if pair is None:
            write("\nAll pairs compared.")
            break
        left, right = pair
        prog = ranker.progress()
        bar = f"[{prog['questions_asked']}/~{prog['target']} suggested, {prog['confidence']:.0%} confident]"
        try:
            raw = read(f"\n{bar}\n  1·{left}   vs   {right}·{scale}\n> ").strip()
        except EOFError:
            raw = "q"

        low = raw.lower()
        if low in ("q", "quit"):
            write("Saved. Bye.")
            return
        if low in ("f", "finish", "done"):
            break
        if low in ("u", "undo"):
            undone = ranker.undo()
            write(f"  undid {undone}" if undone else "  nothing to undo")
            save(ranker)
            continue
        try:
            answer = float(raw)
        except ValueError:
            write(f"  ? enter a number 1..{scale}, or u/f/q")
            continue
        if not (1.0 <= answer <= scale):
            write(f"  ? out of range (1..{scale})")
            continue
        ranker.record(left, right, answer)
        save(ranker)

    write("")
    print_ranking(ranker, write=write)


# -- subcommands --------------------------------------------------------------


def cmd_lists(lib: Library, args) -> int:
    names = lib.list_names()
    if not names:
        print("No lists yet. Create one with: ranker new NAME --items a,b,c")
        return 0
    for name in names:
        spec = lib.load_list(name)
        flag = " (in progress)" if lib.has_session(name) else ""
        print(f"{name}  [{len(spec.items)} items, scale {spec.scale}]{flag}")
    return 0


def cmd_new(lib: Library, args) -> int:
    if args.file:
        with open(args.file) as f:
            names = [line.strip() for line in f if line.strip()]
    else:
        names = [s.strip() for s in (args.items or "").split(",") if s.strip()]
    if len(names) < 2:
        print("Need at least 2 items (--items a,b,c or --file path).")
        return 1
    if len(set(names)) != len(names):
        print("Item names must be unique.")
        return 1
    spec = ListSpec(name=args.name, scale=args.scale, items=[Item(n) for n in names])
    lib.save_list(spec)
    print(f"Created '{args.name}' with {len(names)} items (scale {args.scale}).")
    print(f"Start ranking with: ranker rank {args.name!r}")
    return 0


def cmd_rank(lib: Library, args) -> int:
    if not lib.list_exists(args.name):
        print(f"No such list: {args.name!r}. See 'ranker lists'.")
        return 1
    ranker = lib.get_session(args.name)
    run_session(ranker, save=lambda r: lib.save_session(args.name, r))
    lib.save_session(args.name, ranker)
    paths = lib.export_ranking(args.name, ranker, tier_method="kmeans", k=_default_tiers(len(ranker.model.items)))
    print(f"\nSaved ranking to {paths['md']}")
    return 0


def cmd_show(lib: Library, args) -> int:
    if not lib.list_exists(args.name):
        print(f"No such list: {args.name!r}. See 'ranker lists'.")
        return 1
    ranker = lib.get_session(args.name)
    print_ranking(ranker, k=args.tiers)
    return 0


def cmd_web(lib: Library, args) -> int:
    import uvicorn

    from .web.app import create_app

    uvicorn.run(create_app(args.data), host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ranker", description="Rank items via pairwise comparisons.")
    p.add_argument("--data", default=None, help="Library folder (default ./ranker-data or $RANKER_DATA)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("lists", help="list saved lists").set_defaults(func=cmd_lists)

    pn = sub.add_parser("new", help="create a list")
    pn.add_argument("name")
    pn.add_argument("--items", help="comma-separated item names")
    pn.add_argument("--file", help="file with one item per line")
    pn.add_argument("--scale", type=int, default=7)
    pn.set_defaults(func=cmd_new)

    pr = sub.add_parser("rank", help="run an interactive comparison session")
    pr.add_argument("name")
    pr.set_defaults(func=cmd_rank)

    ps = sub.add_parser("show", help="print the current ranking + tiers")
    ps.add_argument("name")
    ps.add_argument("--tiers", type=int, default=None, help="number of tiers (default floor(sqrt(n)))")
    ps.set_defaults(func=cmd_show)

    pw = sub.add_parser("web", help="launch the localhost web app")
    pw.add_argument("--host", default="127.0.0.1")
    pw.add_argument("--port", type=int, default=8000)
    pw.set_defaults(func=cmd_web)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    lib = Library(args.data)
    return args.func(lib, args)


if __name__ == "__main__":
    raise SystemExit(main())
