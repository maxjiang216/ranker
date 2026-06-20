from pathlib import Path

from PIL import Image

from ranker.library import Library
from ranker.tiermaker import parse_saved_page, render_tierlist, resolve_src, tier_labels


def _png(path: Path, color=(200, 30, 30)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40), color).save(path)


def _saved_page(tmp_path: Path, n: int = 4) -> Path:
    """Write a fake 'Webpage, Complete' tiermaker page with a sibling _files folder."""
    files = tmp_path / "page_files"
    names = [f"Item {i}" for i in range(1, n + 1)]
    imgs = []
    for i, name in enumerate(names, 1):
        rel = f"page_files/img{i}.png"
        _png(tmp_path / rel)
        imgs.append((name, rel))
    body = "\n".join(
        f'<div class="character"><img src="{rel}" alt="{name}"></div>'
        for name, rel in imgs
    )
    html = (
        "<html><body>"
        '<img src="page_files/logo.png" alt="site logo">'  # chrome, outside pool
        f'<div id="images-to-sort">{body}</div>'
        "</body></html>"
    )
    _png(files / "logo.png", color=(10, 10, 10))
    page = tmp_path / "page.html"
    page.write_text(html)
    return page


def test_parse_extracts_pool_items_in_order(tmp_path):
    page = _saved_page(tmp_path, n=4)
    items = parse_saved_page(str(page))
    assert [it.name for it in items] == ["Item 1", "Item 2", "Item 3", "Item 4"]
    # The out-of-pool logo is excluded because a pool container exists.
    assert all("logo" not in it.src for it in items)


def test_parse_falls_back_to_filename(tmp_path):
    _png(tmp_path / "p_files/cool_thing.png")
    _png(tmp_path / "p_files/another-one.png")
    page = tmp_path / "p.html"
    page.write_text(
        '<div id="untiered">'
        '<img src="p_files/cool_thing.png">'
        '<img src="p_files/another-one.png">'
        "</div>"
    )
    items = parse_saved_page(str(page))
    assert [it.name for it in items] == ["cool thing", "another one"]


def test_parse_dedupes_repeated_src_and_names(tmp_path):
    _png(tmp_path / "q_files/a.png")
    page = tmp_path / "q.html"
    page.write_text(
        '<div class="character"><img src="q_files/a.png" alt="Dup"></div>'
        '<div class="character"><img src="q_files/a.png" alt="Dup"></div>'
    )
    items = parse_saved_page(str(page))
    assert len(items) == 1  # same src collapsed


def test_resolve_src_local_vs_remote(tmp_path):
    page = _saved_page(tmp_path, n=2)
    assert resolve_src("page_files/img1.png", str(page)) is not None
    assert resolve_src("https://cdn.example.com/x.png", str(page)) is None
    assert resolve_src("page_files/missing.png", str(page)) is None


def test_import_tiermaker_copies_images(tmp_path):
    page = _saved_page(tmp_path, n=4)
    lib = Library(str(tmp_path / "data"))
    spec = lib.import_tiermaker("Stuff", str(page), scale=5)
    assert spec.scale == 5
    assert spec.item_names() == ["Item 1", "Item 2", "Item 3", "Item 4"]
    paths = lib.image_paths("Stuff")
    assert len(paths) == 4
    assert all(p.is_file() for p in paths.values())


def test_import_too_few_items_raises(tmp_path):
    page = tmp_path / "x.html"
    page.write_text('<div id="untiered"><img src="x_files/only.png" alt="One"></div>')
    _png(tmp_path / "x_files/only.png")
    lib = Library(str(tmp_path / "data"))
    try:
        lib.import_tiermaker("X", str(page))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_export_ranking_writes_png(tmp_path):
    page = _saved_page(tmp_path, n=5)
    lib = Library(str(tmp_path / "data"))
    lib.import_tiermaker("Pics", str(page))
    ranker = lib.new_session("Pics", seed=1)
    for left, right in [("Item 1", "Item 2"), ("Item 3", "Item 4"), ("Item 5", "Item 1")]:
        ranker.record(left, right, 6)
    paths = lib.export_ranking("Pics", ranker, tier_method="kmeans", k=2)
    assert "png" in paths
    assert Path(paths["png"]).is_file()
    with Image.open(paths["png"]) as im:
        assert im.width > 0 and im.height > 0


def test_render_tierlist_handles_missing_images(tmp_path):
    out = tmp_path / "t.png"
    render_tierlist([["A", "B"], ["C"]], {}, str(out))  # no image_paths -> text boxes
    assert out.is_file()


def test_tier_labels():
    assert tier_labels(3) == ["S", "A", "B"]
    assert tier_labels(11)[-1] == "T11"
