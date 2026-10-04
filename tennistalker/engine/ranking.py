"""Motore di classifica basato sul metodo FITP per le classifiche federali (2026/2027).

Punti = somma dei valori delle migliori vittorie + bonus, dove:
- il valore di una vittoria dipende da quante classifiche separano l'avversario dalla propria:
  +2 o più 120, +1 90, pari 60, −1 30, −2 20, −3 15, oltre 0;
- si contano le migliori N vittorie (N di base dipende dalla categoria, es. 7 per un 4.1) più le
  vittorie supplementari ricavate da V − E − 2I − 3G (V vittorie, E sconfitte con pari classifica,
  I con una classifica inferiore, G con due o più inferiori);
- bonus per assenza di sconfitte con pari o inferiori (almeno 5 incontri).
Se i punti raggiungono la soglia di promozione si sale di una classifica e si ricalcola sulla
nuova classifica, finché la soglia successiva non è più raggiunta: i punti mostrati sono quelli
calcolati sulla classifica finale. Si scende di una classifica con punti pari o inferiori alla
soglia di retrocessione.

Valori certi (dal metodo FITP): tabella punti per vittoria, vittorie di base per 4.6 (6), 4.2 e 4.1
(7), 3.1 (9) e 2.1 (16); tabelle delle vittorie supplementari di 4ª e 3ª categoria; soglie maschili
dalla 4.NC alla 4.3, del 4.1 (505/255) e del 3.5 (580); bonus di 4ª (50) e 2ª (100) categoria.
Gli altri valori sono stime interpolate, segnalate con ESTIMATED.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import categories as cat

WIN_VALUES = {2: 120, 1: 90, 0: 60, -1: 30, -2: 20, -3: 15}  # diff = classifica avversario − propria

# vittorie di base per classifica (4.NC … 2.1)
BASE_WINS = [6, 6, 6, 6, 7, 7, 7, 8, 8, 8, 9, 9, 10, 11, 12, 13, 14, 15, 15, 16]
# soglie maschili (promozione, retrocessione); None = nessuna retrocessione
THRESHOLDS = [
    (80, None), (110, 60), (210, 90), (300, 120), (380, 190), (440, 220), (505, 255),   # 4.NC … 4.1
    (580, 290), (620, 310), (660, 330), (700, 350), (740, 370),                          # 3.5 … 3.1
    (790, 395), (840, 420), (890, 445), (940, 470), (990, 495), (1040, 520), (1100, 550),  # 2.8 … 2.2
    (None, 580),                                                                           # 2.1
]
# indici di classifica i cui valori sono stimati (non presi dal metodo ufficiale)
ESTIMATED_BASE_WINS = {0, 2, 3, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18}
ESTIMATED_THRESHOLDS = set(range(7, 20)) | {5}  # per il 3.5 è stimata solo la retrocessione
# vittorie supplementari: (soglie minime del risultato V−E−2I−3G per +1, +2, +3, +4) per gruppo
SUPPLEMENTARY = {4: (4, 11, 16, 21), 3: (5, 13, 19, 25), 2: (6, 15, 22, 29)}  # 2ª categoria stimata
BONUS_CLEAN = {4: 50, 3: 75, 2: 100}  # 3ª categoria stimata
MIN_CLEAN_MATCHES = 5


def win_value(own, opp):
    diff = opp - own
    if diff >= 2:
        return WIN_VALUES[2]
    return WIN_VALUES.get(diff, 0)


def supplementary_wins(own, wins, e, i, g):
    """Vittorie supplementari dalla formula V − E − 2I − 3G."""
    score = wins - e - 2 * i - 3 * g
    return sum(1 for t in SUPPLEMENTARY[cat.group(own)] if score >= t), score


def wins_counted(own, wins, e=0, i=0, g=0):
    return BASE_WINS[own] + supplementary_wins(own, wins, e, i, g)[0]


def promotion_threshold(idx):
    return THRESHOLDS[idx][0]


def retention_threshold(idx):
    return THRESHOLDS[idx][1]


@dataclass
class CountedWin:
    date: date
    opponent: int
    opponent_cat: int
    value: int
    match_id: int = None
    projected: bool = False


@dataclass
class RankingResult:
    player_id: int
    base_category: int
    new_category: int
    coefficient: int
    wins: int
    losses: int
    k: int
    counted: list
    discarded: list
    bonus: int
    bonus_detail: list
    promotion_at: int
    retention_at: int
    window: tuple = None
    notes: list = field(default_factory=list)
    formula: tuple = None   # (V, E, I, G, risultato, vittorie supplementari)
    steps: list = field(default_factory=list)  # [(classifica, punti)] per ogni ricalcolo

    @property
    def delta(self):
        return self.new_category - self.base_category

    @property
    def base_label(self):
        return cat.label(self.base_category)

    @property
    def new_label(self):
        return cat.label(self.new_category)

    @property
    def to_promotion(self):
        return max(0, self.promotion_at - self.coefficient) if self.promotion_at else 0

    @property
    def progress(self):
        """Percentuale verso la soglia di promozione (0-100)."""
        return min(100, int(100 * self.coefficient / self.promotion_at)) if self.promotion_at else 100


def _points_at(own, results, extra_wins, extra_losses):
    """Punti calcolati come se il giocatore fosse di classifica `own`.

    results: [(vinta, classifica_avversario, data, id_avversario, id_partita)]
    """
    wins, e, i, g = [], 0, 0, 0
    for won, opp_cat, d, opp, mid in results:
        if won:
            wins.append(CountedWin(d, opp, opp_cat, win_value(own, opp_cat), mid))
        else:
            diff = opp_cat - own
            if diff == 0:
                e += 1
            elif diff == -1:
                i += 1
            elif diff <= -2:
                g += 1
    wins.extend(extra_wins)
    # le sconfitte proiettate sono attribuite a pari classifica (ipotesi prudente)
    e += extra_losses
    n_sup, score = supplementary_wins(own, len(wins), e, i, g)
    k = BASE_WINS[own] + n_sup
    ordered = sorted(wins, key=lambda w: (-w.value, w.date))
    counted, discarded = ordered[:k], ordered[k:]
    bonus_detail = []
    played = len(results) + len(extra_wins) + extra_losses
    if e == 0 and i == 0 and g == 0 and played >= MIN_CLEAN_MATCHES:
        bonus_detail.append(("Nessuna sconfitta con pari o inferiori", BONUS_CLEAN[cat.group(own)]))
    bonus = sum(v for _, v in bonus_detail)
    points = sum(w.value for w in counted) + bonus
    return points, k, counted, discarded, bonus, bonus_detail, (len(wins), e, i, g, score, n_sup)


def compute(player, matches, world, opponent_category=None, extra_wins=(), extra_losses=0, window=None,
            allow_demotion=True):
    """Calcola la classifica di player sulle partite fornite.

    opponent_category: funzione pid -> indice categoria da usare per l'avversario
                       (default: categoria registrata nella partita).
    extra_wins: vittorie proiettate (CountedWin, valore già fissato) da aggiungere a quelle reali.
    """
    own = player.category
    results = []
    for m in matches:
        opp = m.opponent(player.id)
        won = m.winner == player.id
        if opponent_category:
            opp_cat = opponent_category(opp)
        else:
            opp_cat = m.loser_cat if won else m.winner_cat
        results.append((won, opp_cat, m.date, opp, m.id))
    losses = sum(1 for r in results if not r[0]) + extra_losses

    current = own
    calc = _points_at(current, results, extra_wins, extra_losses)
    steps = [(current, calc[0])]
    notes = []
    while promotion_threshold(current) is not None and calc[0] >= promotion_threshold(current):
        current += 1
        calc = _points_at(current, results, extra_wins, extra_losses)
        steps.append((current, calc[0]))
    if current == own:
        keep = retention_threshold(own)
        if keep is not None and calc[0] <= keep:
            if allow_demotion:
                current = own - 1
                notes.append(f"Punti {calc[0]} ≤ {keep}: retrocessione di una classifica")
            else:
                notes.append(f"Punti {calc[0]} ≤ {keep}: a rischio retrocessione a fine anno "
                             "(nei passaggi infrannuali si viene solo promossi)")
    elif len(steps) > 2:
        notes.append(f"Promozione di {current - own} classifiche")
    if current > own:
        notes.append("Promosso: punti ricalcolati sulla nuova classifica " + cat.label(current)
                     + f" (sulla {cat.label(own)} erano {steps[0][1]})")
    points, k, counted, discarded, bonus, bonus_detail, formula = calc
    show = max(current, own)  # soglie della classifica su cui sono calcolati i punti
    return RankingResult(
        player_id=player.id, base_category=own, new_category=cat.clamp(current), coefficient=points,
        wins=formula[0], losses=losses, k=k, counted=counted, discarded=discarded,
        bonus=bonus, bonus_detail=bonus_detail, promotion_at=promotion_threshold(show),
        retention_at=retention_threshold(show) if current <= own else None,  # dopo una promozione non si scende
        window=window, notes=notes, formula=formula, steps=steps,
    )


class RankingService:
    """Calcoli di classifica con cache sull'intero mondo."""

    def __init__(self, world):
        self.world = world
        self.today = world.today
        self.year_start = date(self.today.year, 1, 1)
        self.year_end = date(self.today.year, 12, 31)
        self._realtime = {}
        self._harmonized = {}

    # --- Classifica simulata in tempo reale (gratuita) ---
    def realtime(self, pid):
        if pid not in self._realtime:
            p = self.world.players[pid]
            ms = self.world.player_matches(pid, self.year_start, self.today)
            self._realtime[pid] = compute(p, ms, self.world, window=(self.year_start, self.today))
        return self._realtime[pid]

    def _harmonizer(self, p):
        """Funzione per armonizzare gli avversari; None per il profilo reale, i cui avversari
        ricostruiti non sono le persone reali e non vanno ricalcolati."""
        return None if getattr(p, "real", False) else self.realtime_category

    def realtime_category(self, pid):
        return self.realtime(pid).new_category

    # --- Classifica Armonizzata (premium) ---
    def harmonized(self, pid):
        """Avversari valutati con la loro categoria simulata + proiezione a fine anno."""
        if pid in self._harmonized:
            return self._harmonized[pid]
        p = self.world.players[pid]
        ms = self.world.player_matches(pid, self.year_start, self.today)
        today_res = compute(p, ms, self.world, opponent_category=self._harmonizer(p),
                            window=(self.year_start, self.today))
        elapsed = max(1, (self.today - self.year_start).days)
        remaining = (self.year_end - self.today).days
        ratio = remaining / elapsed
        exp_wins = round(today_res.wins * ratio)
        exp_losses = round(today_res.losses * ratio)
        avg = (sum(w.value for w in today_res.counted + today_res.discarded) / today_res.wins
               if today_res.wins else 0)
        extra = [CountedWin(self.year_end, None, None, int(avg), projected=True) for _ in range(exp_wins)]
        projected = compute(p, ms, self.world, opponent_category=self._harmonizer(p),
                            extra_wins=extra, extra_losses=exp_losses,
                            window=(self.year_start, self.year_end))
        projected.notes.append(
            f"Proiezione lineare: +{exp_wins} vittorie e +{exp_losses} sconfitte stimate "
            f"nei {remaining} giorni rimanenti (valore medio {int(avg)} punti)")
        self._harmonized[pid] = (today_res, projected)
        return self._harmonized[pid]

    # --- Classifica Supersimulata (premium) ---
    def passages(self):
        """Passaggi di classifica: il primo giorno di ogni trimestre."""
        y = self.today.year
        dates = [date(y, m, 1) for m in (1, 4, 7, 10)] + [date(y + 1, 1, 1)]
        last = max(d for d in dates if d <= self.today)
        nxt = min(d for d in dates if d > self.today)
        return last, nxt

    def at(self, pid, when, harmonize=True):
        """Classifica su finestra mobile di 12 mesi che termina in `when`.

        Come nei passaggi infrannuali FITP, la retrocessione si applica solo a fine anno."""
        p = self.world.players[pid]
        start = when - timedelta(days=365)
        ms = self.world.player_matches(pid, start, when)
        return compute(p, ms, self.world,
                       opponent_category=self._harmonizer(p) if harmonize else None,
                       window=(start, when), allow_demotion=(when.month, when.day) in ((12, 31), (1, 1)))

    def supersimulated(self, pid):
        last, nxt = self.passages()
        now = self.at(pid, self.today)
        at_last = self.at(pid, last - timedelta(days=1))
        timeline = []
        p = self.world.players[pid]
        # per il profilo reale i dati coprono solo l'anno in corso
        if getattr(p, "real", False):
            first = min((m.date for m in self.world.player_matches(pid)), default=self.today)
            d = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        else:
            d = date(self.today.year - 1, self.today.month, 1)
        while d <= self.today:
            res = self.at(pid, d)
            timeline.append((d, res.new_category, res.coefficient))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        timeline.append((self.today, now.new_category, now.coefficient))
        return {"now": now, "at_last": at_last, "last": last, "next": nxt, "timeline": timeline}

    # --- Posizioni ---
    def leaderboard(self, gender=None, region=None, club=None):
        ps = [p for p in self.world.players.values()
              if (gender is None or p.gender == gender) and (region is None or p.region == region)
              and (club is None or p.club == club)]
        return sorted(ps, key=lambda p: (-self.realtime(p.id).new_category,
                                         -self.realtime(p.id).coefficient, p.last))

    def positions(self, pid):
        p = self.world.players[pid]
        out = []
        for label, kw in (
            ("Assoluta", {}),
            ("Nazionale " + ("maschile" if p.gender == "M" else "femminile"), {"gender": p.gender}),
            (f"Regionale · {p.region}", {"gender": p.gender, "region": p.region}),
            (f"Circolo · {p.club}", {"gender": p.gender, "club": p.club}),
        ):
            board = self.leaderboard(**kw)
            pos = next(i for i, x in enumerate(board, 1) if x.id == pid)
            out.append({"label": label, "position": pos, "total": len(board),
                        "top": max(0.1, round(100 * pos / len(board), 1)),
                        "neighbours": board[max(0, pos - 3):pos + 2]})
        return out
