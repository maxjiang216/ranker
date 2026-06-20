from ranker.library import Item, Library, ListSpec
from ranker.session import Ranker


def _lib(tmp_path):
    return Library(str(tmp_path / "data"))


def test_save_and_load_list(tmp_path):
    lib = _lib(tmp_path)
    spec = ListSpec(
        name="Anime",
        scale=5,
        items=[
            Item("Spirited Away", description="Miyazaki"),
            Item("Akira", image="akira.jpg"),
        ],
    )
    lib.save_list(spec)
    assert lib.list_names() == ["Anime"]
    loaded = lib.load_list("Anime")
    assert loaded.scale == 5
    assert loaded.item_names() == ["Spirited Away", "Akira"]
    assert loaded.items[1].image == "akira.jpg"


def test_session_roundtrip(tmp_path):
    lib = _lib(tmp_path)
    lib.save_list(ListSpec(name="L", items=[Item("A"), Item("B"), Item("C")]))
    r = lib.get_session("L")
    assert isinstance(r, Ranker)
    r.record("A", "B", 7)
    lib.save_session("L", r)

    assert lib.has_session("L")
    r2 = lib.load_session("L")
    assert len(r2.model.comparisons) == 1


def test_export_ranking_writes_files(tmp_path):
    lib = _lib(tmp_path)
    lib.save_list(ListSpec(name="L", items=[Item("A"), Item("B"), Item("C")]))
    r = lib.get_session("L")
    for _ in range(5):
        r.record("B", "A", 7)
        r.record("C", "B", 7)
    paths = lib.export_ranking("L", r)
    assert (tmp_path / "data" / "rankings" / "L.md").exists()
    assert (tmp_path / "data" / "rankings" / "L.json").exists()
    assert "Tier 1" in open(paths["md"]).read()
