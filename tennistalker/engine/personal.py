"""Profilo reale dell'utente.

Legge il testo copiato dalla pagina profilo di un'app di ranking (statistiche aggregate) e
ricostruisce un elenco di partite coerente con quei totali, che viene poi inserito nel mondo
simulato. Il testo contiene solo aggregati: date, avversari e punteggi sono ricostruiti.
"""

import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

from . import categories as cat
from .data import Match, Player, Tournament, category_rating
from .simulation import play_match

PERSONAL_ID = 10000

REL_LABELS = [  # (etichetta nel testo, differenza di categoria usata per la ricostruzione)
    ("2 o più classifiche superiori", 2),
    ("1 classifica superiore", 1),
    ("Stessa classifica", 0),
    ("1 classifica inferiore", -1),
    ("2 o più classifiche inferiori", -2),
]
SURFACE_MAP = {"terra rossa": "Terra battuta", "terra battuta": "Terra battuta", "cemento": "Cemento",
               "erba sintetica": "Erba sintetica", "sintetico": "Sintetico indoor",
               "sintetico indoor": "Sintetico indoor", "erba": "Erba sintetica"}
UNKNOWN_SURFACE = "Sconosciuta"


class ProfileParseError(ValueError):
    pass


def _wl(text, label):
    m = re.search(re.escape(label) + r"\s*(\d+)\s*Vinte\s*(\d+)\s*Perse", text)
    return [int(m.group(1)), int(m.group(2))] if m else None


def _section(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start)) if end else -1
    return text[i + len(start): j if j > 0 else None]


def _rows(section):
    """Righe 'Etichetta\\nX VinteY Perse' di una sezione."""
    out = {}
    for m in re.finditer(r"([^\n\d][^\n]*?)\s*\n\s*(\d+)\s*Vinte\s*(\d+)\s*Perse", section):
        out[m.group(1).strip()] = [int(m.group(2)), int(m.group(3))]
    return out


def parse_profile_text(text):
    """Estrae dal testo incollato i dati del profilo. Solleva ProfileParseError se mancano i dati base."""
    text = text.replace("\r\n", "\n")
    head = re.search(r"\n\s*([A-ZÀ-Ý][^\n\[\]]{1,60}?)\s*\n\s*(O\d{2}|U\d{2}|Open|Over\s?\d{2})\s*\n\s*\[?(4\.NC|[1-4]\.\d)\]?",
                     "\n" + text)
    if not head:
        raise ProfileParseError("Non trovo nome, fascia d'età e classifica (es. 'Mario Rossi / O30 / 4.1').")
    name, age_group, category = head.group(1).strip(), head.group(2), head.group(3)
    if category not in cat.CATEGORIES:
        raise ProfileParseError(f"Classifica {category} non supportata (gestite dalla 4.NC alla 2.1).")

    vs = {}
    for label, diff in REL_LABELS:
        wl = _wl(text, label)
        if wl:
            vs[str(diff)] = wl
    if not vs:
        raise ProfileParseError("Non trovo le statistiche 'Vinte/Perse in base alla classifica dell'avversario'.")

    def opt(pattern, group=1, conv=str):
        m = re.search(pattern, text)
        return conv(m.group(group).strip()) if m else None

    surfaces = _rows(_section(text, "Vinte/Perse per superficie", "Vinte/Perse per tipo di competizione"))
    competition = _rows(_section(text, "Vinte/Perse per tipo di competizione", "Vinte/Perse per tipo di campo"))
    courts = _rows(_section(text, "Vinte/Perse per tipo di campo", "Stato di forma"))
    max_cat = re.search(r"Massima classifica raggiunta\s*\[?(4\.NC|[1-4]\.\d)\]?(?:\([^)]*\))?\s*nel\s*(\d{4})", text)

    profile = {
        "name": name,
        "age_group": age_group,
        "category": category,
        "gender": "F" if opt(r"gender=(female)") else "M",
        "region": opt(r"regione ([A-ZÀ-Ý][\w'À-ÿ-]+(?: [A-ZÀ-Ý][\w'À-ÿ-]+)*)"),
        "province": opt(r"provincia di ([A-Z]{2})\b"),
        "club": opt(r'Posizione relativa al club\s*"([^"]+)"'),
        "vs": vs,
        "sets": {"2": _wl(text, "Match conclusi in 2 set"), "3": _wl(text, "Match conclusi in 3 set")},
        "surfaces": surfaces,
        "competition": competition,
        "courts": courts,
        "form": opt(r"Ultimi 10 match\s*\n?\s*([VS]{1,10})\b"),
        "tournaments": opt(r"Tornei giocati nel periodo considerato\s*(\d+)", conv=int),
        "max_category": [max_cat.group(1), int(max_cat.group(2))] if max_cat else None,
    }
    profile["wins"] = sum(v[0] for v in vs.values())
    profile["losses"] = sum(v[1] for v in vs.values())
    return profile


# ---------------------------------------------------------------------- persistenza
def load_profile(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_profile(path, profile):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_profile(path):
    p = Path(path)
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------------- ricostruzione
def _expand(counts, n, default, rng):
    """Lista di n valori che rispetta i conteggi (troncata o completata con default) mescolata."""
    out = [k for k, c in counts for _ in range(c)][:n]
    out += [default] * (n - len(out))
    rng.shuffle(out)
    return out


def _title(s):
    return " ".join(w.capitalize() if len(w) > 2 else w.lower() for w in s.split())


def add_personal_player(world, profile, seed=93):
    """Inserisce nel mondo il giocatore reale e le partite ricostruite. Ritorna il Player."""
    rng = random.Random(seed)
    today = world.today
    own = cat.index(profile["category"])
    region = profile.get("region") or "Lombardia"
    first, _, last = profile["name"].partition(" ")
    club = _title(profile["club"]) if profile.get("club") else "Circolo non indicato"
    city = {"GE": "Genova", "MI": "Milano", "RM": "Roma", "TO": "Torino"}.get(profile.get("province"), region)
    me = Player(
        id=PERSONAL_ID, first=first, last=last or "", gender=profile.get("gender", "M"),
        birth_year=today.year - 30, region=region, city=city, club=club, category=own,
        skill=category_rating(own), surface_bonus={}, clutch=0.0, stamina=0.0, activity=10,
        age_group=profile.get("age_group"), real=True,
    )
    W, L = profile["wins"], profile["losses"]

    def attrs(key_counts, idx, default):
        return _expand([(k, v[idx]) for k, v in key_counts], [W, L][idx], default, rng)

    vs = [(int(k), v) for k, v in profile["vs"].items()]
    sets = [(int(k), v) for k, v in (profile.get("sets") or {}).items() if v]
    surf = [(SURFACE_MAP.get(k.lower(), UNKNOWN_SURFACE), v) for k, v in (profile.get("surfaces") or {}).items()]
    comp = [("team" if "squadr" in k.lower() else "tour", v) for k, v in (profile.get("competition") or {}).items()]
    per_result = {}
    for idx, res in ((0, "V"), (1, "S")):
        per_result[res] = list(zip(attrs(vs, idx, 0), attrs(sets, idx, 2), attrs(surf, idx, UNKNOWN_SURFACE),
                                   attrs(comp, idx, "tour")))

    # ordine cronologico: le ultime 10 seguono lo "stato di forma" (sinistra = più vecchia)
    form = (profile.get("form") or "")[-(W + L):]
    nV, nS = W - form.count("V"), L - form.count("S")
    if nV < 0 or nS < 0:
        form, nV, nS = "", W, L
    head = ["V"] * nV + ["S"] * nS
    rng.shuffle(head)
    sequence = head + list(form)
    # le partite a squadre non devono interrompere la logica "un torneo finisce con una sconfitta"
    pools = {r: sorted(per_result[r], key=lambda a: a[3] == "tour") for r in "VS"}
    team_first = {r: [a for a in pools[r] if a[3] == "team"] for r in "VS"}
    tour = {r: [a for a in pools[r] if a[3] == "tour"] for r in "VS"}
    for r in "VS":
        rng.shuffle(tour[r])
    team_positions = set()
    for r in "VS":
        idxs = [i for i, x in enumerate(sequence) if x == r]
        if r == "S" and len(idxs) > len(team_first[r]):
            idxs = idxs[:-1]  # l'ultima sconfitta resta in torneo
        team_positions |= set(rng.sample(idxs, min(len(team_first[r]), len(idxs))))

    # date distribuite nell'anno in corso
    start = date(today.year, 1, 20)
    end = today - timedelta(days=7)
    n = len(sequence)
    dates = [start + timedelta(days=int((end - start).days * i / max(1, n - 1))) for i in range(n)]

    used_opp = set()
    candidates = {}
    for p in world.players.values():
        if p.gender == me.gender:
            candidates.setdefault(p.category, []).append(p)

    def pick_opponent(target):
        target = cat.clamp(target)
        for d in (0, 1, -1, 2, -2):
            pool = [p for p in candidates.get(cat.clamp(target + d), []) if p.id not in used_opp]
            local = [p for p in pool if p.region == region] or pool
            if local:
                o = rng.choice(local)
                used_opp.add(o.id)
                return o
        raise RuntimeError("nessun avversario disponibile")

    def score(won, n_sets, diff):
        """Punteggio dal punto di vista del vincitore, con il numero di set richiesto."""
        r_me, r_opp = 1000.0, 1000.0 + 45 * diff
        for _ in range(400):
            w, s = play_match(r_me, r_opp, rng, match_tiebreak=True)
            if w == won and len(s) == n_sets:
                return s if won else [(b, a, t) for a, b, t in s]
        return [(6, 4, None), (4, 6, None), (1, 0, 6)] if n_sets == 3 else [(6, 4, None), (6, 3, None)]

    next_tid = max(world.tournaments) + 1
    next_mid = max((m.id for m in world.matches), default=0) + 1
    current = None
    rounds_in_current = 0
    new_matches, new_tournaments = [], []
    for i, (res, d) in enumerate(zip(sequence, dates)):
        is_team = i in team_positions
        pool = team_first[res] if is_team else tour[res]
        if not pool:  # sicurezza: prende dall'altro gruppo
            pool = tour[res] or team_first[res]
        diff, n_sets, surface, _ = pool.pop()
        opp = pick_opponent(own + diff)
        if is_team:
            t = Tournament(
                id=next_tid, name=f"Gara a squadre · {d.strftime('%m/%Y')}", kind="Gara a squadre",
                max_category=cat.MAX_IDX, gender=me.gender, club=club, city=city, region=region,
                surface=surface, start=d, end=d, draw_size=2, match_tiebreak=True,
                entrants=[me.id, opp.id])
            next_tid += 1
            new_tournaments.append(t)
            rnd = "Incontro a squadre"
        else:
            if current is None:
                current = Tournament(
                    id=next_tid, name=f"Torneo {len([x for x in new_tournaments if x.kind == 'Torneo']) + 1} "
                                      f"(ricostruito)", kind="Torneo", max_category=cat.MAX_IDX,
                    gender=me.gender, club=club, city=city, region=region, surface=surface,
                    start=d, end=d, draw_size=2, match_tiebreak=True, entrants=[me.id])
                next_tid += 1
                new_tournaments.append(current)
                rounds_in_current = 0
            rounds_in_current += 1
            current.entrants.append(opp.id)
            current.end = d
            t = current
            rnd = f"{rounds_in_current}° turno"
        winner, loser = (me, opp) if res == "V" else (opp, me)
        new_matches.append(Match(
            id=next_mid, date=d, tournament_id=t.id, round=rnd, winner=winner.id, loser=loser.id,
            sets=score(res == "V", n_sets, diff),
            surface=surface, winner_cat=winner.category if winner is opp else own,
            loser_cat=loser.category if loser is opp else own))
        next_mid += 1
        if not is_team and res == "S":
            current = None

    world.add(me, new_tournaments, new_matches)
    return me
