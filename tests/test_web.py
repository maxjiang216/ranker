import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from ranker.web import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "data")))


def _make_list(client):
    resp = client.post(
        "/api/lists",
        json={
            "name": "Anime",
            "scale": 7,
            "items": [
                {"name": "A", "description": "first"},
                {"name": "B", "image": "b.png"},
                {"name": "C"},
                {"name": "D"},
            ],
        },
    )
    assert resp.status_code == 200


def test_create_and_list(client):
    _make_list(client)
    lists = client.get("/api/lists").json()
    assert lists == [{"name": "Anime", "n_items": 4}]


def test_create_rejects_dupes(client):
    resp = client.post(
        "/api/lists",
        json={"name": "X", "items": [{"name": "A"}, {"name": "A"}]},
    )
    assert resp.status_code == 400


def test_session_flow(client):
    _make_list(client)
    st = client.get("/api/session/Anime").json()
    assert st["pair"] is not None
    assert st["scale"] == 7
    left, right = st["pair"]["left"]["name"], st["pair"]["right"]["name"]

    st2 = client.post(
        "/api/session/Anime/answer",
        json={"left": left, "right": right, "answer": 7},
    ).json()
    assert st2["asked"] == 1

    # Pair suggestion is stable across repeated GETs (no side effects).
    a = client.get("/api/session/Anime").json()["pair"]
    b = client.get("/api/session/Anime").json()["pair"]
    assert a == b

    st3 = client.post("/api/session/Anime/undo").json()
    assert st3["asked"] == 0


def test_pair_carries_metadata(client):
    _make_list(client)
    # Drive a few answers to find the A/B pairing eventually; just check shape here.
    st = client.get("/api/session/Anime").json()
    for side in ("left", "right"):
        item = st["pair"][side]
        assert set(item.keys()) == {"name", "image", "description"}


def test_result_and_finish_export(client, tmp_path):
    _make_list(client)
    # Answer until the session wants to stop or we hit a cap.
    for _ in range(40):
        st = client.get("/api/session/Anime").json()
        if st["pair"] is None or st["should_stop"]:
            break
        client.post(
            "/api/session/Anime/answer",
            json={
                "left": st["pair"]["left"]["name"],
                "right": st["pair"]["right"]["name"],
                "answer": 7,
            },
        )
    result = client.get("/api/session/Anime/result").json()
    assert {r["item"]["name"] for r in result["ranking"]} == {"A", "B", "C", "D"}
    assert "inconsistency_ratio" in result["cycles"]

    fin = client.post("/api/session/Anime/finish").json()
    assert fin["exported"]["md"].endswith("Anime.md")
    assert (tmp_path / "data" / "rankings" / "Anime.md").exists()


def test_tier_methods_and_shape(client):
    _make_list(client)
    for _ in range(30):
        st = client.get("/api/session/Anime").json()
        if st["pair"] is None or st["should_stop"]:
            break
        client.post(
            "/api/session/Anime/answer",
            json={
                "left": st["pair"]["left"]["name"],
                "right": st["pair"]["right"]["name"],
                "answer": 7,
            },
        )
    km = client.get("/api/session/Anime/result?method=kmeans&k=3").json()
    assert km["method"] == "kmeans"
    assert len(km["tiers"]) == 3
    # Each tier entry carries display metadata + a score (ranking within tier).
    entry = km["tiers"][0][0]
    assert set(entry.keys()) == {"item", "score", "sd"}
    assert "name" in entry["item"]

    graph = client.get("/api/session/Anime/result?method=graph&low=0.3&high=0.7").json()
    assert graph["method"] == "graph"


def test_index_served(client):
    assert "<title>Ranker</title>" in client.get("/").text
