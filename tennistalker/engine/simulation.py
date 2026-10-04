"""Simulazione punto per punto di una partita di tennis (2 set su 3)."""

import random
from collections import Counter

BASE_SERVE = 0.60       # probabilità di vincere un punto al servizio a parità di livello
POINT_PER_RATING = 0.0004  # spostamento della probabilità per punto di rating di differenza


def serve_prob(rating_a, rating_b):
    """Probabilità che A vinca un punto al servizio contro B."""
    p = BASE_SERVE + POINT_PER_RATING * (rating_a - rating_b)
    return min(0.9, max(0.3, p))


def _game(p_server, rng):
    a = b = 0
    while True:
        if rng.random() < p_server:
            a += 1
        else:
            b += 1
        if a >= 4 and a - b >= 2:
            return True
        if b >= 4 and b - a >= 2:
            return False


def _tiebreak(pa, pb, rng, target, a_serves_first):
    """pa/pb: prob. di A e B di vincere il punto al proprio servizio."""
    a = b = 0
    n = 0
    while True:
        # al primo punto serve uno, poi si alterna ogni due punti
        server_is_a = a_serves_first if (n == 0 or ((n - 1) // 2) % 2 == 1) else not a_serves_first
        if server_is_a:
            won = rng.random() < pa
        else:
            won = rng.random() >= pb
        if won:
            a += 1
        else:
            b += 1
        n += 1
        if a >= target and a - b >= 2:
            return True, a, b
        if b >= target and b - a >= 2:
            return False, a, b


def _set(pa, pb, rng, a_serves_first, tb_pa, tb_pb):
    """Gioca un set; tb_pa/tb_pb sono le probabilità al servizio usate nel tie-break."""
    ga = gb = 0
    a_serving = a_serves_first
    while True:
        if ga == 6 and gb == 6:
            won, ta, tb = _tiebreak(tb_pa, tb_pb, rng, 7, a_serving)
            return ((7, 6, min(ta, tb)) if won else (6, 7, min(ta, tb))), not a_serving
        won = _game(pa, rng) if a_serving else not _game(pb, rng)
        ga += won
        gb += not won
        a_serving = not a_serving
        if (ga >= 6 or gb >= 6) and abs(ga - gb) >= 2:
            return (ga, gb, None), a_serving


def play_match(rating_a, rating_b, rng, match_tiebreak=False, clutch_a=0.0, clutch_b=0.0,
               stamina_a=0.0, stamina_b=0.0):
    """Simula una partita. Ritorna (vince_a, set) con set = [(game_a, game_b, punti_tb_perdente|None)].

    Con match_tiebreak=True il terzo set è un tie-break a 10 punti, registrato come (1, 0, punti_perdente).
    clutch alza le probabilità nei tie-break e nel set decisivo, stamina solo nel set decisivo.
    """
    pa = serve_prob(rating_a, rating_b)
    pb = serve_prob(rating_b, rating_a)
    tb_pa, tb_pb = pa + 0.03 * clutch_a, pb + 0.03 * clutch_b
    sets = []
    wa = wb = 0
    a_serves = rng.random() < 0.5
    while wa < 2 and wb < 2:
        if wa == 1 and wb == 1:
            da = 0.02 * (clutch_a + stamina_a)
            db = 0.02 * (clutch_b + stamina_b)
            if match_tiebreak:
                won, ta, tb = _tiebreak(tb_pa + da, tb_pb + db, rng, 10, a_serves)
                sets.append((1, 0, min(ta, tb)) if won else (0, 1, min(ta, tb)))
            else:
                s, a_serves = _set(pa + da, pb + db, rng, a_serves, tb_pa + da, tb_pb + db)
                sets.append(s)
        else:
            s, a_serves = _set(pa, pb, rng, a_serves, tb_pa, tb_pb)
            sets.append(s)
        if sets[-1][0] > sets[-1][1]:
            wa += 1
        else:
            wb += 1
    return wa == 2, sets


def is_match_tiebreak(s):
    return (s[0], s[1]) in ((1, 0), (0, 1))


def flip(sets):
    return [(b, a, t) for a, b, t in sets]


def format_score(sets):
    out = []
    for a, b, tb in sets:
        if is_match_tiebreak((a, b)):
            w, l = max(10, (tb or 0) + 2), tb or 0
            out.append(f"[{w}-{l}]" if a else f"[{l}-{w}]")
        elif tb is not None:
            out.append(f"{a}-{b}({tb})")
        else:
            out.append(f"{a}-{b}")
    return " ".join(out)


def monte_carlo(rating_a, rating_b, n=2000, seed=7, match_tiebreak=False, **kw):
    """Simula n partite e restituisce statistiche aggregate dal punto di vista di A."""
    rng = random.Random(seed)
    wins = straight_wins = straight_losses = deciders = tiebreaks = 0
    scores = Counter()
    for _ in range(n):
        won, sets = play_match(rating_a, rating_b, rng, match_tiebreak=match_tiebreak, **kw)
        wins += won
        if len(sets) == 2:
            straight_wins += won
            straight_losses += not won
        else:
            deciders += 1
        tiebreaks += any(s[2] is not None and not is_match_tiebreak(s) for s in sets)
        scores[format_score(sets)] += 1
    return {
        "win_prob": wins / n,
        "straight_win": straight_wins / n,
        "straight_loss": straight_losses / n,
        "decider": deciders / n,
        "tiebreak": tiebreaks / n,
        "top_scores": [(s, c / n) for s, c in scores.most_common(6)],
    }
