import random
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from engine import categories as cat  # noqa: E402
from engine.ranking import compute, promotion_threshold, win_value, wins_counted  # noqa: E402
from engine.simulation import monte_carlo, play_match  # noqa: E402

TODAY = date(2026, 10, 4)


@pytest.fixture(scope="module")
def app():
    a = create_app(today=TODAY)
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def world(app):
    return app.config["WORLD"]


def active_player(world):
    return max(world.players.values(), key=lambda p: len(world.matches_by_player[p.id]))


# ---------------------------------------------------------------- motore
def test_match_scores_are_valid():
    rng = random.Random(1)
    for _ in range(300):
        won, sets = play_match(1000, 1010, rng, match_tiebreak=rng.random() < 0.5)
        a = sum(1 for x, y, _ in sets if x > y)
        b = len(sets) - a
        assert max(a, b) == 2 and min(a, b) <= 1
        assert won == (a == 2)
        for x, y, tb in sets:
            if (x, y) in ((1, 0), (0, 1)):
                continue
            assert max(x, y) in (6, 7)
            assert tb is None or {x, y} == {6, 7}


def test_stronger_player_wins_more():
    assert monte_carlo(1045, 1000, n=800)["win_prob"] > 0.55
    assert 0.4 < monte_carlo(1000, 1000, n=800)["win_prob"] < 0.6


def test_win_values_and_thresholds():
    assert win_value(5, 9) == 120
    assert win_value(5, 6) == 90
    assert win_value(5, 5) == 60
    assert win_value(5, 0) == 10
    assert wins_counted(20, 0) == 14
    assert wins_counted(0, 10) == 4
    assert promotion_threshold(10) > promotion_threshold(0)


def test_world_is_deterministic(world):
    from engine.data import generate_world
    other = generate_world(TODAY)
    assert [m.sets for m in other.matches[:50]] == [m.sets for m in world.matches[:50]]
    assert all(m.date < TODAY for m in world.matches)


def test_tournament_eligibility(world):
    for m in world.matches:
        t = world.tournaments[m.tournament_id]
        assert m.winner_cat <= t.max_category and m.loser_cat <= t.max_category
        assert world.players[m.winner].gender == t.gender == world.players[m.loser].gender


def test_ranking_counts_best_wins(app, world):
    ranking = app.config["RANKING"]
    p = active_player(world)
    res = ranking.realtime(p.id)
    assert len(res.counted) <= res.k
    assert res.coefficient == sum(w.value for w in res.counted) + res.bonus
    if res.counted and res.discarded:
        assert min(w.value for w in res.counted) >= max(w.value for w in res.discarded)
    assert abs(res.delta) <= 2 and 0 <= res.new_category <= cat.MAX_IDX


def test_promotion_logic(world):
    p = active_player(world)
    ms = world.player_matches(p.id)
    wins = [m for m in ms if m.winner == p.id]
    res = compute(p, wins, world, opponent_category=lambda _: cat.MAX_IDX)
    if res.coefficient >= res.promotion_at:
        assert res.new_category > p.category or p.category == cat.MAX_IDX


def test_positions_are_consistent(app, world):
    ranking = app.config["RANKING"]
    p = active_player(world)
    pos = ranking.positions(p.id)
    assert pos[0]["total"] == len(world.players)
    assert pos[0]["position"] >= pos[1]["position"] >= pos[2]["position"] >= pos[3]["position"] >= 1


def test_radar_scores_in_range(app, world):
    an = app.config["ANALYTICS"]
    p = active_player(world)
    items = an.radar(p.id)
    assert items, "dovrebbe esserci almeno un torneo compatibile"
    for it in items:
        t = it["tournament"]
        assert 0 <= it["score"] <= 100
        assert t.start > TODAY and t.gender == p.gender and p.category <= t.max_category
    assert [i["score"] for i in items] == sorted((i["score"] for i in items), reverse=True)


# ---------------------------------------------------------------- web
FREE = ["/", "/membership", "/giocatori", "/giocatori?region=Lazio&gender=F&page=2", "/competizioni",
        "/competizioni?when=past&surface=Cemento", "/ricerca?q=ross", "/profilo?q=rossi", "/classifica"]
PREMIUM = ["/classifica/armonizzata", "/classifica/supersimulata", "/radar", "/radar?surface=Cemento",
           "/simula", "/simula?q=a", "/analisi", "/posizione", "/sconto"]


def login(client, pid, premium=False):
    with client.session_transaction() as s:
        s["player_id"] = pid
        if premium:
            s["premium"] = True


def test_free_pages(client, world):
    login(client, active_player(world).id)
    for url in FREE:
        assert client.get(url).status_code == 200, url


def test_premium_pages_locked_without_membership(client, world):
    login(client, active_player(world).id)
    for url in PREMIUM:
        r = client.get(url)
        assert r.status_code == 402, url
        assert "Sblocca la membership" in r.get_data(as_text=True)


def test_premium_pages_with_membership(client, world):
    p = active_player(world)
    login(client, p.id, premium=True)
    for url in PREMIUM:
        assert client.get(url).status_code == 200, url
    opp = next(m.opponent(p.id) for m in world.player_matches(p.id))
    for fmt in ("mtb", "full"):
        r = client.get(f"/simula?opp={opp}&surface=Cemento&fmt={fmt}")
        assert r.status_code == 200 and "Piano di gioco" in r.get_data(as_text=True)


def test_every_player_and_tournament_page_renders(client, world):
    login(client, active_player(world).id, premium=True)
    for pid in list(world.players)[:: 37]:
        assert client.get(f"/giocatore/{pid}").status_code == 200
        assert client.get(f"/analisi?id={pid}").status_code == 200
        assert client.get(f"/classifica/supersimulata?id={pid}").status_code == 200
    for tid in list(world.tournaments)[:: 23]:
        assert client.get(f"/competizioni/{tid}").status_code == 200
    assert client.get("/giocatore/999999").status_code == 404


def test_checkout_and_cancel(client, world):
    login(client, active_player(world).id)
    assert client.get("/radar").status_code == 402
    client.post("/membership/checkout")
    assert client.get("/radar").status_code == 200
    client.post("/membership/disdici")
    assert client.get("/radar").status_code == 402


def test_advanced_search_restricted_on_free(client):
    r = client.get("/ricerca?q=a&region=Lazio").get_data(as_text=True)
    assert "filtri avanzati sono stati ignorati" in r
    assert r.count('href="/giocatore/') <= 5


def test_advanced_search_filters_on_premium(client, world):
    login(client, active_player(world).id, premium=True)
    r = client.get("/ricerca?region=Sardegna&gender=F&sort=elo").get_data(as_text=True)
    sard = [p for p in world.players.values() if p.region == "Sardegna" and p.gender == "F"]
    assert f"{len(sard)} risultati" in r


def test_profile_selection_redirects(client, world):
    pid = active_player(world).id
    r = client.post("/profilo", data={"player_id": pid, "next": "/analisi"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/analisi")
    r = client.post("/profilo", data={"player_id": pid, "next": "https://evil.example"})
    assert r.headers["Location"] == "/"
    r = client.post("/profilo", data={"player_id": pid, "next": "//evil.example"})
    assert r.headers["Location"] == "/"
