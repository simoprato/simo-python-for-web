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
def app(tmp_path_factory):
    a = create_app(today=TODAY, profile_path=tmp_path_factory.mktemp("noprofile") / "none.json")
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
    i41, i35 = cat.index("4.1"), cat.index("3.5")
    assert win_value(i41, i41 + 3) == 120
    assert win_value(i41, i41 + 1) == 90
    assert win_value(i41, i41) == 60
    assert [win_value(i41, i41 - d) for d in (1, 2, 3, 4)] == [30, 20, 15, 0]
    assert wins_counted(i41, 12, e=3, i=1, g=0) == 8   # 7 di base + 1 (12−3−2 = 7)
    assert wins_counted(i41, 25) == 11                  # 7 + 4
    assert wins_counted(i35, 12, e=2, i=3, g=1) == 8    # risultato 1: nessuna supplementare
    assert promotion_threshold(i41) == 505 and promotion_threshold(i35) == 580
    assert promotion_threshold(cat.index("4.NC")) == 80


def test_fitp_promotion_recalculates_on_new_category(world):
    """Caso reale: 4.1 con 12V–11S → 510 punti da 4.1, promosso e ricalcolato a 3.5 (290)."""
    from types import SimpleNamespace
    from engine.data import Match
    i41 = cat.index("4.1")
    me = SimpleNamespace(id=-1, category=i41)
    spec = [(1, 2, 0), (0, 2, 5), (1, 1, 2), (0, 1, 2), (1, 0, 5), (0, 0, 3), (1, -1, 3), (0, -1, 1), (1, -2, 2)]
    ms = []
    for won, diff, n in spec:
        for _ in range(n):
            w, l = (-1, -2) if won else (-2, -1)
            wc, lc = (i41, i41 + diff) if won else (i41 + diff, i41)
            ms.append(Match(len(ms), TODAY, None, "", w, l, [(6, 4, None), (6, 4, None)], "Cemento", wc, lc))
    res = compute(me, ms, world)
    assert res.steps == [(i41, 510), (i41 + 1, 290)]
    assert res.new_label == "3.5" and res.coefficient == 290 and res.promotion_at == 580


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
    assert res.new_category >= p.category  # solo vittorie: mai retrocessione


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


def test_home_always_links_my_data(client, world):
    login(client, active_player(world).id)  # anche con un giocatore simulato scelto
    html = client.get("/").get_data(as_text=True)
    assert 'href="/i-miei-dati"' in html and "Importa i miei dati" in html and "v1.2" in html


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


# ---------------------------------------------------------------- dati reali
SAMPLE_PROFILE = """[Home](https://example.it/)[Classifiche](https://example.it/classifiche)
Nuovo postAggiungi amichevole
Mario Bianchi
O40
[4.2](https://example.it/classifiche?rank=4.2)
Regionale
[Guarda i migliori giocatori della regione Toscana](https://example.it/classifiche?gender=male&region=TOS)
[Guarda i migliori giocatori della provincia di FI](https://example.it/classifiche?gender=male&province=FI)
Posizione relativa al club "CIRCOLO TENNIS DI ESEMPIO ASD"
Vinte/Perse in base alla classifica dell'avversario
Vittorie
Sconfitte
2 o più classifiche superiori
1 Vinte4 Perse
1 classifica superiore
2 Vinte3 Perse
Stessa classifica
4 Vinte2 Perse
1 classifica inferiore
3 Vinte1 Perse
2 o più classifiche inferiori
2 Vinte0 Perse
Vinte/Perse per numero di set
Match conclusi in 2 set
8 Vinte6 Perse
Match conclusi in 3 set
4 Vinte4 Perse
Vinte/Perse per superficie
Vittorie
Sconfitte
Terra rossa
9 Vinte7 Perse
Sconosciuta
3 Vinte3 Perse
Vinte/Perse per tipo di competizione
Tornei
10 Vinte8 Perse
Gare a squadre
2 Vinte2 Perse
Vinte/Perse per tipo di campo
Indoor
2 Vinte2 Perse
Stato di forma
Ultimi 10 match
VVSVSSVVVS
Tornei giocati nel periodo considerato
8
Massima classifica raggiunta
[4.2](https://example.it/classifiche?rank=4.2)
nel 2025
"""


def test_parse_profile_text():
    from engine.personal import parse_profile_text
    p = parse_profile_text(SAMPLE_PROFILE)
    assert (p["name"], p["age_group"], p["category"]) == ("Mario Bianchi", "O40", "4.2")
    assert (p["region"], p["province"], p["club"]) == ("Toscana", "FI", "CIRCOLO TENNIS DI ESEMPIO ASD")
    assert p["vs"] == {"2": [1, 4], "1": [2, 3], "0": [4, 2], "-1": [3, 1], "-2": [2, 0]}
    assert p["sets"] == {"2": [8, 6], "3": [4, 4]}
    assert p["surfaces"] == {"Terra rossa": [9, 7], "Sconosciuta": [3, 3]}
    assert p["competition"] == {"Tornei": [10, 8], "Gare a squadre": [2, 2]}
    assert (p["form"], p["tournaments"], p["max_category"]) == ("VVSVSSVVVS", 8, ["4.2", 2025])
    assert (p["wins"], p["losses"]) == (12, 10)


def test_parse_rejects_unrelated_text():
    from engine.personal import ProfileParseError, parse_profile_text
    with pytest.raises(ProfileParseError):
        parse_profile_text("ciao, questo non è un profilo")


def test_import_flow_reconstructs_exact_totals(tmp_path):
    from engine.personal import PERSONAL_ID, REL_LABELS
    a = create_app(today=TODAY, profile_path=tmp_path / "p.json")
    c = a.test_client()
    r = c.post("/i-miei-dati", data={"action": "import", "text": SAMPLE_PROFILE})
    assert r.status_code == 302 and (tmp_path / "p.json").exists()
    world = a.config["WORLD"]
    me = world.players[PERSONAL_ID]
    assert me.real and me.category_label == "4.2" and me.region == "Toscana"
    ms = world.player_matches(PERSONAL_ID)
    assert len(ms) == 22
    wins = [m for m in ms if m.winner == PERSONAL_ID]
    assert len(wins) == 12
    # totali per classifica dell'avversario, numero di set e superficie
    for _, diff in REL_LABELS:
        got = [0, 0]
        for m in ms:
            won = m.winner == PERSONAL_ID
            d = max(-2, min(2, (m.loser_cat if won else m.winner_cat) - me.category))
            if d == diff:
                got[0 if won else 1] += 1
        assert got == world_profile(a)["vs"][str(diff)]
    assert sum(1 for m in wins if len(m.sets) == 3) == 4
    assert sum(1 for m in ms if m.surface == "Terra battuta") == 16
    for m in ms:  # i set sono dal punto di vista del vincitore
        assert sum(1 for a, b, _ in m.sets if a > b) == 2, m.sets
    form = "".join("V" if m.winner == PERSONAL_ID else "S" for m in ms[-10:])
    assert form == "VVSVSSVVVS"
    # ogni torneo (non a squadre) termina con una sconfitta o è l'ultimo
    for t in {m.tournament_id for m in ms}:
        tm = [m for m in ms if m.tournament_id == t]
        assert all(m.winner == PERSONAL_ID for m in tm[:-1])
    # il profilo reale diventa quello predefinito e tutte le pagine funzionano
    with c.session_transaction() as s:
        s["premium"] = True
    for url in ["/", "/i-miei-dati", "/classifica", "/classifica/armonizzata", "/classifica/supersimulata",
                "/radar", "/analisi", "/posizione", "/simula", f"/giocatore/{PERSONAL_ID}", "/competizioni?when=past"]:
        assert c.get(url).status_code == 200, url
    home = c.get("/").get_data(as_text=True)
    assert "Mario Bianchi" in home and "Stai usando i tuoi dati reali" in home
    # eliminazione
    c.post("/i-miei-dati", data={"action": "delete"})
    assert not (tmp_path / "p.json").exists()
    assert PERSONAL_ID not in a.config["WORLD"].players


def world_profile(a):
    return a.config["PROFILE"]


def test_import_error_shows_message(tmp_path):
    a = create_app(today=TODAY, profile_path=tmp_path / "p.json")
    r = a.test_client().post("/i-miei-dati", data={"action": "import", "text": "testo a caso"})
    assert r.status_code == 200 and "Non trovo" in r.get_data(as_text=True)
    assert not (tmp_path / "p.json").exists()


SAMPLE_SUMMARY = """Mario Bianchi
O40
[4.2](https://example.it/classifiche?rank=4.2)
Statistiche base
Vittorie
55%
Punti FITP
250
Classifica
Classifica Simulata
i
4.1
1da inizio anno
Ti mancano 255 punti su 505 necessari per essere promossi
Classifica Supersimulata
i
Ora
4.1
"""


def test_summary_page_adds_reference_and_comparison(tmp_path):
    a = create_app(today=TODAY, profile_path=tmp_path / "p.json")
    c = a.test_client()
    # senza statistiche importate prima, la pagina riepilogo da sola non basta
    r = c.post("/i-miei-dati", data={"action": "import", "text": SAMPLE_SUMMARY})
    assert "pagina riepilogo" in r.get_data(as_text=True)
    c.post("/i-miei-dati", data={"action": "import", "text": SAMPLE_PROFILE})
    r = c.post("/i-miei-dati", data={"action": "import", "text": SAMPLE_SUMMARY})
    assert r.status_code == 302
    ref = a.config["PROFILE"]["reference"]
    assert ref == {"points": 250, "simulated": "4.1", "supersimulated": "4.1", "missing": 255, "promotion_at": 505}
    html = c.get("/i-miei-dati").get_data(as_text=True)
    assert "Confronto con i valori" in html
    # reimportare le statistiche conserva il confronto
    c.post("/i-miei-dati", data={"action": "import", "text": SAMPLE_PROFILE})
    assert a.config["PROFILE"]["reference"]["points"] == 250


def test_real_profile_is_not_harmonized_with_fake_opponents(tmp_path):
    from engine.personal import PERSONAL_ID
    a = create_app(today=TODAY, profile_path=tmp_path / "p.json")
    a.test_client().post("/i-miei-dati", data={"action": "import", "text": SAMPLE_PROFILE})
    r = a.config["RANKING"]
    today_res, _ = r.harmonized(PERSONAL_ID)
    assert today_res.coefficient == r.realtime(PERSONAL_ID).coefficient
