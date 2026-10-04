"""Generazione di un mondo tennistico sintetico e deterministico.

Tutti i giocatori, circoli e tornei sono inventati. Ogni giocatore ha un livello "reale"
nascosto (skill) che guida i risultati delle partite: chi ha una skill superiore alla propria
categoria tende a vincere e quindi a essere promosso dal motore di classifica.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import categories as cat
from .simulation import play_match

REGIONS = {
    "Lombardia": ["Milano", "Bergamo", "Brescia", "Monza"],
    "Piemonte": ["Torino", "Novara", "Cuneo"],
    "Veneto": ["Verona", "Padova", "Venezia", "Treviso"],
    "Emilia-Romagna": ["Bologna", "Modena", "Parma", "Rimini"],
    "Toscana": ["Firenze", "Pisa", "Siena", "Lucca"],
    "Lazio": ["Roma", "Latina", "Viterbo"],
    "Campania": ["Napoli", "Salerno", "Caserta"],
    "Puglia": ["Bari", "Lecce", "Taranto"],
    "Sicilia": ["Palermo", "Catania", "Messina"],
    "Liguria": ["Genova", "Sanremo", "La Spezia"],
    "Marche": ["Ancona", "Pesaro"],
    "Sardegna": ["Cagliari", "Sassari"],
}
REGION_WEIGHTS = {"Lombardia": 16, "Lazio": 12, "Veneto": 9, "Emilia-Romagna": 9, "Piemonte": 8,
                  "Toscana": 8, "Campania": 8, "Puglia": 6, "Sicilia": 7, "Liguria": 5,
                  "Marche": 4, "Sardegna": 4}

CLUB_WORDS = ["Aurora", "Le Querce", "Il Pino", "Villa Verde", "Monte Rosa", "I Tigli", "La Pineta",
              "San Marco", "Le Palme", "Belvedere", "Riviera", "Olimpia", "Primavera", "Le Rose",
              "Il Castello", "Le Magnolie", "Parco Nord", "Lungolago", "Il Faro", "Green Park"]
CLUB_PATTERNS = ["Circolo Tennis {w}", "Tennis Club {w}", "ASD Tennis {w}", "Sporting {w}", "Racchetta {w}"]

MALE = ["Luca", "Marco", "Andrea", "Matteo", "Lorenzo", "Alessandro", "Davide", "Simone", "Federico",
        "Riccardo", "Giacomo", "Francesco", "Tommaso", "Gabriele", "Nicola", "Stefano", "Paolo",
        "Edoardo", "Filippo", "Pietro", "Giovanni", "Michele", "Leonardo", "Daniele", "Alberto",
        "Enrico", "Fabio", "Emanuele", "Jacopo", "Claudio", "Mattia", "Samuele", "Diego", "Elia"]
FEMALE = ["Giulia", "Francesca", "Chiara", "Sara", "Martina", "Alessia", "Elena", "Valentina",
          "Federica", "Silvia", "Laura", "Giorgia", "Beatrice", "Sofia", "Aurora", "Camilla",
          "Ilaria", "Marta", "Elisa", "Anna", "Caterina", "Greta", "Noemi", "Irene"]
SURNAMES = ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino",
            "Greco", "Bruno", "Gallo", "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo",
            "Lombardi", "Moretti", "Barbieri", "Fontana", "Santoro", "Mariani", "Rinaldi", "Caruso",
            "Ferrara", "Galli", "Martini", "Leone", "Longo", "Gentile", "Martinelli", "Vitale",
            "Lombardo", "Serra", "Coppola", "De Santis", "D'Angelo", "Marchetti", "Parisi", "Villa",
            "Conte", "Ferraro", "Ferri", "Fabbri", "Bianco", "Marini", "Grasso", "Valentini", "Messina",
            "Sala", "De Angelis", "Gatti", "Pellegrini", "Palumbo", "Sanna", "Farina", "Rizzi",
            "Monti", "Cattaneo", "Morelli", "Amato", "Silvestri", "Mazza", "Testa", "Grassi",
            "Pellegrino", "Carbone", "Giuliani", "Benedetti", "Barone", "Rossetti", "Caputo", "Montanari"]

# distribuzione delle categorie ufficiali (dalla 4.NC alla 2.1)
CATEGORY_WEIGHTS = [14, 9, 9, 9, 8, 7, 7, 6, 5, 5, 4, 3, 2.5, 2, 1.5, 1.2, 1, 0.8, 0.6, 0.4]

SURFACES = ["Terra battuta", "Cemento", "Erba sintetica", "Sintetico indoor"]
SURFACE_WEIGHTS = [55, 20, 13, 12]

# tipologie di torneo: (nome, indice massimo di categoria ammessa)
TOURNAMENT_KINDS = [
    ("Open", cat.MAX_IDX),
    ("Limitato 2.5", cat.index("2.5")),
    ("Limitato 3.1", cat.index("3.1")),
    ("Limitato 3.3", cat.index("3.3")),
    ("Limitato 4.1", cat.index("4.1")),
    ("Limitato 4.3", cat.index("4.3")),
]
KIND_WEIGHTS = [10, 10, 20, 15, 25, 20]

RATING_BASE = 1000
RATING_STEP = 45  # punti di rating per ogni categoria


def category_rating(idx):
    return RATING_BASE + RATING_STEP * idx


@dataclass
class Player:
    id: int
    first: str
    last: str
    gender: str
    birth_year: int
    region: str
    city: str
    club: str
    category: int          # categoria ufficiale (indice) a inizio anno
    skill: float           # livello reale nascosto
    surface_bonus: dict    # bonus di rating per superficie
    clutch: float          # rendimento nei momenti decisivi (-1..1)
    stamina: float         # tenuta fisica nel set decisivo (-1..1)
    activity: int          # tornei per anno desiderati

    @property
    def name(self):
        return f"{self.first} {self.last}"

    @property
    def category_label(self):
        return cat.label(self.category)


@dataclass
class Tournament:
    id: int
    name: str
    kind: str
    max_category: int
    gender: str
    club: str
    city: str
    region: str
    surface: str
    start: date
    end: date
    draw_size: int
    match_tiebreak: bool
    entrants: list = field(default_factory=list)
    champion: int = None
    finalist: int = None

    @property
    def indoor(self):
        return "indoor" in self.surface

    @property
    def deadline(self):
        return self.start - timedelta(days=3)

    @property
    def gender_label(self):
        return "Maschile" if self.gender == "M" else "Femminile"


@dataclass
class Match:
    id: int
    date: date
    tournament_id: int
    round: str
    winner: int
    loser: int
    sets: list          # dal punto di vista del vincitore: [(game_v, game_p, tb_perdente|None)]
    surface: str
    winner_cat: int     # categoria ufficiale al momento della partita
    loser_cat: int

    def player_view(self, pid):
        """Set dal punto di vista di pid."""
        if pid == self.winner:
            return self.sets
        return [(b, a, t) for a, b, t in self.sets]

    def opponent(self, pid):
        return self.loser if pid == self.winner else self.winner


ROUND_NAMES = {2: "Finale", 4: "Semifinale", 8: "Quarti", 16: "Ottavi", 32: "Sedicesimi"}


class World:
    def __init__(self, players, tournaments, matches, today):
        self.today = today
        self.players = {p.id: p for p in players}
        self.tournaments = {t.id: t for t in tournaments}
        self.matches = sorted(matches, key=lambda m: (m.date, m.id))
        self.clubs = sorted({(p.club, p.city, p.region) for p in players})
        self.matches_by_player = {p.id: [] for p in players}
        for m in self.matches:
            self.matches_by_player[m.winner].append(m)
            self.matches_by_player[m.loser].append(m)

    def player_matches(self, pid, start=None, end=None):
        out = self.matches_by_player.get(pid, [])
        return [m for m in out if (start is None or m.date >= start) and (end is None or m.date <= end)]


def _surface_rating(p, surface):
    return p.skill + p.surface_bonus.get(surface, 0)


def generate_world(today=None, seed=2026, n_players=900):
    today = today or date.today()
    rng = random.Random(seed)

    # --- circoli ---
    clubs_by_city = {}
    used = set()
    for region, cities in REGIONS.items():
        for city in cities:
            clubs = []
            for _ in range(rng.randint(2, 4)):
                while True:
                    name = rng.choice(CLUB_PATTERNS).format(w=rng.choice(CLUB_WORDS)) + f" {city}"
                    if name not in used:
                        used.add(name)
                        break
                clubs.append(name)
            clubs_by_city[city] = clubs

    # --- giocatori ---
    players = []
    region_names = list(REGION_WEIGHTS)
    names_used = set()
    for pid in range(1, n_players + 1):
        gender = "M" if rng.random() < 0.7 else "F"
        while True:
            first = rng.choice(MALE if gender == "M" else FEMALE)
            last = rng.choice(SURNAMES)
            if (first, last) not in names_used:
                names_used.add((first, last))
                break
        region = rng.choices(region_names, weights=[REGION_WEIGHTS[r] for r in region_names])[0]
        city = rng.choice(REGIONS[region])
        category = rng.choices(range(len(CATEGORY_WEIGHTS)), weights=CATEGORY_WEIGHTS)[0]
        # la skill reale si discosta dalla categoria: alcuni sono in crescita, altri in calo
        skill = category_rating(category) + rng.gauss(0, 30) + rng.gauss(8, 30)
        bonus = {s: rng.gauss(0, 22) for s in SURFACES}
        players.append(Player(
            id=pid, first=first, last=last, gender=gender,
            birth_year=today.year - int(min(70, max(13, rng.gauss(32, 12)))),
            region=region, city=city, club=rng.choice(clubs_by_city[city]),
            category=category, skill=skill, surface_bonus=bonus,
            clutch=max(-1, min(1, rng.gauss(0, 0.5))),
            stamina=max(-1, min(1, rng.gauss(0, 0.5))),
            activity=rng.randint(3, 14),
        ))

    # --- tornei e partite ---
    tournaments, matches = [], []
    first_monday = today - timedelta(days=400 + today.weekday())
    last_day = today + timedelta(days=90)
    played = {p.id: 0 for p in players}
    busy = {}  # (pid, settimana) -> True
    tid = mid = 0
    week = first_monday
    while week <= last_day:
        for gender, count in (("M", 4), ("F", 2)):
            for _ in range(count):
                tid += 1
                region = rng.choices(region_names, weights=[REGION_WEIGHTS[r] for r in region_names])[0]
                city = rng.choice(REGIONS[region])
                club = rng.choice(clubs_by_city[city])
                kind, max_cat = rng.choices(TOURNAMENT_KINDS, weights=KIND_WEIGHTS)[0]
                start = week + timedelta(days=rng.randint(0, 3))
                surface = rng.choices(SURFACES, weights=SURFACE_WEIGHTS)[0]
                # in inverno si gioca più indoor
                if start.month in (11, 12, 1, 2) and rng.random() < 0.5:
                    surface = "Sintetico indoor"
                draw_size = rng.choice([16, 16, 32]) if kind != "Open" else rng.choice([16, 32])
                t = Tournament(
                    id=tid, name=f"{kind} {club.split(' ' + city)[0]}", kind=kind, max_category=max_cat,
                    gender=gender, club=club, city=city, region=region, surface=surface,
                    start=start, end=start + timedelta(days=rng.randint(6, 9)), draw_size=draw_size,
                    match_tiebreak=kind != "Open",
                )
                eligible = [p for p in players if p.gender == gender and p.category <= max_cat
                            and not busy.get((p.id, week))]

                def weight(p):
                    w = max(0.05, p.activity * (today - first_monday).days / 365 - played[p.id])
                    w *= 1.0 if p.region == region else 0.08
                    w *= 1.0 if max_cat - p.category <= 6 else 0.25
                    return w

                # campionamento pesato senza reinserimento (Efraimidis-Spirakis)
                keyed = sorted(eligible, key=lambda p: rng.random() ** (1 / weight(p)), reverse=True)
                chosen = keyed[:draw_size]

                if t.end < today:
                    size = 1 << (len(chosen).bit_length() - 1) if chosen else 0
                    if size < 4:
                        tid -= 1
                        continue
                    chosen = chosen[:size]
                    t.draw_size = size
                    t.entrants = [p.id for p in chosen]
                    for p in chosen:
                        played[p.id] += 1
                        busy[(p.id, week)] = True
                    mid = _play_draw(t, chosen, rng, matches, mid)
                else:
                    # torneo futuro o in corso: solo una parte degli iscritti è già nota
                    days = (t.start - today).days
                    fill = 1.0 if days <= 7 else max(0.2, 1 - days / 100)
                    t.entrants = [p.id for p in chosen[:max(2, int(len(chosen) * fill))]]
                tournaments.append(t)
        week += timedelta(days=7)

    return World(players, tournaments, matches, today)


def _seeded_order(entrants):
    """Ordina il tabellone mettendo le teste di serie (per categoria) agli estremi."""
    by_cat = sorted(entrants, key=lambda p: -p.category)
    n = len(by_cat)
    draw = [None] * n
    seeds_pos = [0, n - 1, n // 2, n // 2 - 1][: max(2, n // 4)]
    for pos, p in zip(seeds_pos, by_cat):
        draw[pos] = p
    rest = by_cat[len(seeds_pos):]
    free = [i for i, x in enumerate(draw) if x is None]
    for i, p in zip(free, rest):
        draw[i] = p
    return draw


def _play_draw(t, entrants, rng, matches, mid):
    rest = list(entrants)
    rng.shuffle(rest)
    current = _seeded_order(rest)
    day = t.start
    days_span = max(1, (t.end - t.start).days)
    rounds = (len(current)).bit_length() - 1
    for r in range(rounds):
        size = len(current)
        rnd_name = ROUND_NAMES.get(size, f"Turno da {size}")
        nxt = []
        for i in range(0, size, 2):
            a, b = current[i], current[i + 1]
            won, sets = play_match(
                _surface_rating(a, t.surface), _surface_rating(b, t.surface), rng,
                match_tiebreak=t.match_tiebreak, clutch_a=a.clutch, clutch_b=b.clutch,
                stamina_a=a.stamina, stamina_b=b.stamina,
            )
            w, l = (a, b) if won else (b, a)
            if not won:
                sets = [(y, x, z) for x, y, z in sets]
            mid += 1
            matches.append(Match(
                id=mid, date=day, tournament_id=t.id, round=rnd_name, winner=w.id, loser=l.id,
                sets=sets, surface=t.surface, winner_cat=w.category, loser_cat=l.category,
            ))
            nxt.append(w)
        if size == 2:
            t.champion, t.finalist = nxt[0].id, (b.id if nxt[0] is a else a.id)
        current = nxt
        day = min(t.end, t.start + timedelta(days=int(days_span * (r + 1) / rounds)))
    return mid
