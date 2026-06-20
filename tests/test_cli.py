from PIL import Image

from ranker.cli import main, run_session
from ranker.session import Ranker


def test_new_and_lists(tmp_path, capsys):
    data = str(tmp_path / "d")
    assert main(["--data", data, "new", "Books", "--items", "A,B,C", "--scale", "5"]) == 0
    assert main(["--data", data, "lists"]) == 0
    out = capsys.readouterr().out
    assert "Books" in out and "3 items" in out


def test_new_rejects_too_few(tmp_path, capsys):
    assert main(["--data", str(tmp_path), "new", "X", "--items", "A"]) == 1


def test_new_from_file(tmp_path):
    f = tmp_path / "items.txt"
    f.write_text("A\nB\nC\nD\n")
    assert main(["--data", str(tmp_path / "d"), "new", "L", "--file", str(f)]) == 0


def test_show_unknown_list(tmp_path, capsys):
    assert main(["--data", str(tmp_path), "show", "Nope"]) == 1


def test_run_session_records_and_ranks():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=1)
    answers = iter(["7", "7", "7", "7", "7", "f"])
    out = []
    saved = []
    run_session(
        r,
        save=lambda x: saved.append(len(x.model.comparisons)),
        read=lambda prompt: next(answers),
        write=out.append,
    )
    assert len(r.model.comparisons) == 5
    assert saved == [1, 2, 3, 4, 5]
    assert any("Tier 1" in line for line in out)


def test_run_session_undo_then_quit():
    r = Ranker.from_list(["A", "B", "C", "D"], seed=1)
    answers = iter(["7", "u", "q"])
    out = []
    run_session(r, save=lambda x: None, read=lambda prompt: next(answers), write=out.append)
    assert len(r.model.comparisons) == 0  # recorded one, undid it, quit


def test_import_tiermaker_and_export(tmp_path, capsys):
    files = tmp_path / "tl_files"
    files.mkdir()
    for i in range(1, 5):
        Image.new("RGB", (30, 30)).save(files / f"i{i}.png")
    page = tmp_path / "tl.html"
    page.write_text(
        '<div id="images-to-sort">'
        + "".join(
            f'<div class="character"><img src="tl_files/i{i}.png" alt="C{i}"></div>'
            for i in range(1, 5)
        )
        + "</div>"
    )
    data = str(tmp_path / "d")
    assert main(["--data", data, "import", "TL", "--tiermaker", str(page)]) == 0
    assert "Imported 4 items" in capsys.readouterr().out

    # record a few answers so export has a ranking
    from ranker.library import Library

    lib = Library(data)
    ranker = lib.get_session("TL")
    ranker.record("C1", "C2", 6)
    ranker.record("C3", "C4", 6)
    lib.save_session("TL", ranker)
    assert main(["--data", data, "export", "TL", "--tiers", "2"]) == 0
    assert "png:" in capsys.readouterr().out


def test_run_session_rejects_out_of_range():
    r = Ranker.from_list(["A", "B", "C"], seed=1)
    answers = iter(["9", "abc", "4", "q"])  # bad, bad, ok, quit
    out = []
    run_session(r, save=lambda x: None, read=lambda prompt: next(answers), write=out.append)
    assert len(r.model.comparisons) == 1
    assert any("out of range" in line for line in out)
