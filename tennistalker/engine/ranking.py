"""Motore di classifica ispirato al regolamento FITP (versione semplificata).

Coefficiente = somma dei migliori K valori-vittoria + bonus.
- Il valore di una vittoria dipende dalla differenza tra la categoria dell'avversario e la propria.
- K cresce con il saldo vittorie/sconfitte.
- Bonus per tornei vinti, finali raggiunte e assenza di sconfitte contro categorie inferiori.
Il coefficiente viene confrontato con le soglie di promozione/permanenza della propria categoria.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import categories as cat

WIN_VALUES = {2: 120, 1: 90, 0: 60, -1: 40, -2: 30, -3: 20}  # diff = cat_avversario - cat_propria
BONUS_TITLE = 25
BONUS_FINAL = 10
BONUS_CLEAN = 20  # nessuna sconfitta contro categorie inferiori (min. 5 vittorie)
MIN_MATCHES_FOR_DEMOTION = 4


def win_value(own, opp):
    diff = opp - own
    if diff >= 2:
        return WIN_VALUES[2]
    return WIN_VALUES.get(diff, 10)


def wins_counted(wins, losses):
    return max(4, min(14, 6 + (wins - losses) // 2))


def promotion_threshold(idx):
    return 300 + 20 * idx


def retention_threshold(idx):
    return int(promotion_threshold(idx) * 0.4)


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
        return max(0, self.promotion_at - self.coefficient)

    @property
    def progress(self):
        """Percentuale verso la soglia di promozione (0-100)."""
        return min(100, int(100 * self.coefficient / self.promotion_at)) if self.promotion_at else 0


def compute(player, matches, world, opponent_category=None, extra_wins=(), extra_losses=0, window=None):
    """Calcola la classifica di player sulle partite fornite.

    opponent_category: funzione pid -> indice categoria da usare per l'avversario
                       (default: categoria ufficiale registrata nella partita).
    extra_wins: vittorie proiettate (CountedWin) da aggiungere a quelle reali.
    """
    own = player.category
    wins, losses = [], 0
    losses_vs_lower = 0
    for m in matches:
        opp = m.opponent(player.id)
        if opponent_category:
            opp_cat = opponent_category(opp)
        else:
            opp_cat = m.loser_cat if m.winner == player.id else m.winner_cat
        if m.winner == player.id:
            wins.append(CountedWin(m.date, opp, opp_cat, win_value(own, opp_cat), m.id))
        else:
            losses += 1
            if opp_cat < own:
                losses_vs_lower += 1
    wins.extend(extra_wins)
    losses += extra_losses

    k = wins_counted(len(wins), losses)
    ordered = sorted(wins, key=lambda w: (-w.value, w.date))
    counted, discarded = ordered[:k], ordered[k:]

    bonus_detail = []
    tournament_ids = {m.tournament_id for m in matches}
    for tid in tournament_ids:
        t = world.tournaments[tid]
        if t.champion == player.id:
            bonus_detail.append((f"Torneo vinto: {t.name}", BONUS_TITLE))
        elif t.finalist == player.id:
            bonus_detail.append((f"Finale: {t.name}", BONUS_FINAL))
    if losses_vs_lower == 0 and len(wins) >= 5:
        bonus_detail.append(("Nessuna sconfitta con categorie inferiori", BONUS_CLEAN))
    bonus = sum(v for _, v in bonus_detail)

    coefficient = sum(w.value for w in counted) + bonus
    promo, keep = promotion_threshold(own), retention_threshold(own)
    new = own
    notes = []
    if coefficient >= promo * 1.8:
        new = own + 2
        notes.append("Doppia promozione: coefficiente oltre 1,8× la soglia")
    elif coefficient >= promo:
        new = own + 1
    elif coefficient < keep and len(wins) + losses >= MIN_MATCHES_FOR_DEMOTION:
        new = own - 1
    elif coefficient < keep:
        notes.append("Meno di 4 partite: nessuna retrocessione per inattività")
    new = cat.clamp(new)
    return RankingResult(
        player_id=player.id, base_category=own, new_category=new, coefficient=coefficient,
        wins=len(wins), losses=losses, k=k, counted=counted, discarded=discarded,
        bonus=bonus, bonus_detail=bonus_detail, promotion_at=promo, retention_at=keep,
        window=window, notes=notes,
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

    def realtime_category(self, pid):
        return self.realtime(pid).new_category

    # --- Classifica Armonizzata (premium) ---
    def harmonized(self, pid):
        """Avversari valutati con la loro categoria simulata + proiezione a fine anno."""
        if pid in self._harmonized:
            return self._harmonized[pid]
        p = self.world.players[pid]
        ms = self.world.player_matches(pid, self.year_start, self.today)
        today_res = compute(p, ms, self.world, opponent_category=self.realtime_category,
                            window=(self.year_start, self.today))
        elapsed = max(1, (self.today - self.year_start).days)
        remaining = (self.year_end - self.today).days
        ratio = remaining / elapsed
        exp_wins = round(today_res.wins * ratio)
        exp_losses = round(today_res.losses * ratio)
        avg = (sum(w.value for w in today_res.counted + today_res.discarded) / today_res.wins
               if today_res.wins else 0)
        extra = [CountedWin(self.year_end, None, None, int(avg), projected=True) for _ in range(exp_wins)]
        projected = compute(p, ms, self.world, opponent_category=self.realtime_category,
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
        """Classifica su finestra mobile di 12 mesi che termina in `when`."""
        p = self.world.players[pid]
        start = when - timedelta(days=365)
        ms = self.world.player_matches(pid, start, when)
        return compute(p, ms, self.world,
                       opponent_category=self.realtime_category if harmonize else None,
                       window=(start, when))

    def supersimulated(self, pid):
        last, nxt = self.passages()
        now = self.at(pid, self.today)
        at_last = self.at(pid, last - timedelta(days=1))
        timeline = []
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
