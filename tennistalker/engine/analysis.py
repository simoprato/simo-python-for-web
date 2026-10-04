"""Rating Elo, Forze & Debolezze, Simula Partita e Radar Tornei.

Tutte le stime usano solo dati osservabili (risultati e categorie), mai la skill nascosta.
"""

from datetime import timedelta

from . import categories as cat
from .data import SURFACES
from .ranking import win_value
from .simulation import is_match_tiebreak, monte_carlo, serve_prob

ELO_K = 28
ELO_STEP = 115  # in scala Elo una categoria di differenza vale ~66% di vittoria
SIM_SCALE = 45 / ELO_STEP  # conversione Elo -> scala del simulatore punto per punto


def _expected(ra, rb):
    return 1 / (1 + 10 ** ((rb - ra) / 400))


class Analytics:
    def __init__(self, world, ranking):
        self.world = world
        self.ranking = ranking
        self.elo = {pid: 1500.0 + ELO_STEP * p.category for pid, p in world.players.items()}
        self.surface_elo = {pid: {s: 0.0 for s in SURFACES} for pid in world.players}
        for m in world.matches:  # ordinate cronologicamente
            w, l = m.winner, m.loser
            e = _expected(self.elo[w], self.elo[l])
            self.elo[w] += ELO_K * (1 - e)
            self.elo[l] -= ELO_K * (1 - e)
            # scostamento specifico per superficie (aggiornato con K ridotto)
            if m.surface not in SURFACES:  # superficie sconosciuta: solo Elo generale
                continue
            es = _expected(self.elo[w] + self.surface_elo[w][m.surface],
                           self.elo[l] + self.surface_elo[l][m.surface])
            self.surface_elo[w][m.surface] += 10 * (1 - es)
            self.surface_elo[l][m.surface] -= 10 * (1 - es)
        self._stats = {}

    # ------------------------------------------------------------------ statistiche
    def stats(self, pid):
        if pid in self._stats:
            return self._stats[pid]
        p = self.world.players[pid]
        ms = self.world.player_matches(pid)
        s = {
            "played": len(ms), "wins": 0, "losses": 0,
            "surface": {x: [0, 0] for x in SURFACES},
            "vs": {"higher": [0, 0], "equal": [0, 0], "lower": [0, 0]},
            "tiebreak": [0, 0], "decider": [0, 0], "first_set_lost": [0, 0],
            "sets": [0, 0], "games": [0, 0], "bagels": [0, 0],
            "form": [], "best_wins": [], "worst_losses": [],
        }
        for m in ms:
            won = m.winner == pid
            opp = m.opponent(pid)
            opp_cat = m.loser_cat if won else m.winner_cat
            sets = m.player_view(pid)
            idx = 0 if won else 1
            s["wins" if won else "losses"] += 1
            s["surface"].setdefault(m.surface, [0, 0])[idx] += 1
            rel = "higher" if opp_cat > p.category else "lower" if opp_cat < p.category else "equal"
            s["vs"][rel][idx] += 1
            for a, b, tb in sets:
                s["sets"][0 if a > b else 1] += 1
                if is_match_tiebreak((a, b)):
                    s["tiebreak"][0 if a > b else 1] += 1
                    continue
                s["games"][0] += a
                s["games"][1] += b
                if tb is not None:
                    s["tiebreak"][0 if a > b else 1] += 1
                if b == 0:
                    s["bagels"][0] += 1
                if a == 0:
                    s["bagels"][1] += 1
            if len(sets) == 3:
                s["decider"][idx] += 1
            if sets[0][0] < sets[0][1]:
                s["first_set_lost"][idx] += 1
            entry = {"match": m, "opponent": self.world.players[opp], "opp_cat": opp_cat, "won": won,
                     "value": win_value(p.category, opp_cat)}
            (s["best_wins"] if won else s["worst_losses"]).append(entry)
            s["form"].append("V" if won else "S")
        s["best_wins"].sort(key=lambda e: (-e["opp_cat"], e["match"].date))
        s["worst_losses"].sort(key=lambda e: (e["opp_cat"], e["match"].date))
        s["best_wins"] = s["best_wins"][:5]
        s["worst_losses"] = s["worst_losses"][:5]
        s["form"] = s["form"][-10:]
        self._stats[pid] = s
        return s

    @staticmethod
    def pct(pair, prior=0.5, weight=3):
        """Percentuale di vittoria con smoothing bayesiano per campioni piccoli."""
        w, l = pair
        return (w + prior * weight) / (w + l + weight)

    def profile(self, pid):
        """Assi del radar Forze & Debolezze (0-100) e liste di forze/debolezze testuali."""
        s = self.stats(pid)
        overall = self.pct((s["wins"], s["losses"]))
        clay = self.pct(s["surface"]["Terra battuta"], overall)
        fast = self.pct([sum(s["surface"][x][i] for x in SURFACES if x != "Terra battuta") for i in (0, 1)],
                        overall)
        axes = [
            ("Terra battuta", clay),
            ("Superfici veloci", fast),
            ("Tie-break", self.pct(s["tiebreak"])),
            ("Set decisivo", self.pct(s["decider"])),
            ("Vs più forti", self.pct(s["vs"]["higher"], 0.3)),
            ("Solidità vs più deboli", self.pct(s["vs"]["lower"], 0.7)),
            ("Rimonte", self.pct(s["first_set_lost"], 0.2)),
            ("Forma recente", self.pct((s["form"].count("V"), s["form"].count("S")))),
        ]
        axes = [(n, round(v * 100)) for n, v in axes]

        strengths, weaknesses = [], []

        def judge(name, pair, good, bad, min_n=4, note=""):
            n = sum(pair)
            if n < min_n:
                return
            r = pair[0] / n
            txt = f"{name}: {pair[0]}V–{pair[1]}S ({round(r * 100)}%){note}"
            if r >= good:
                strengths.append(txt)
            elif r <= bad:
                weaknesses.append(txt)

        for surf, pair in s["surface"].items():
            if surf in SURFACES:
                judge(f"Su {surf.lower()}", pair, 0.65, 0.35)
        judge("Tie-break", s["tiebreak"], 0.62, 0.38, 3)
        judge("Set decisivi", s["decider"], 0.62, 0.38, 3)
        judge("Contro categorie superiori", s["vs"]["higher"], 0.45, 0.25, 3)
        judge("Contro categorie inferiori", s["vs"]["lower"], 0.8, 0.6, 3)
        judge("Dopo aver perso il primo set", s["first_set_lost"], 0.35, 0.1, 3)
        if s["bagels"][0] >= 3:
            strengths.append(f"Killer instinct: {s['bagels'][0]} set chiusi 6-0")
        if s["bagels"][1] >= 2:
            weaknesses.append(f"Blackout: {s['bagels'][1]} set persi 6-0")
        g = s["games"]
        if sum(g):
            gp = g[0] / sum(g)
            if gp >= 0.56:
                strengths.append(f"Domina i game: {round(gp * 100)}% dei game vinti")
            elif gp <= 0.44:
                weaknesses.append(f"Pochi game vinti: {round(gp * 100)}%")
        return {"axes": axes, "strengths": strengths, "weaknesses": weaknesses, "stats": s}

    # ------------------------------------------------------------------ Simula Partita
    def rating(self, pid, surface=None):
        r = self.elo[pid]
        if surface:
            r += self.surface_elo[pid].get(surface, 0.0)
        return r

    def simulate(self, pid, opp_id, surface, match_tiebreak=True, n=2000):
        ra, rb = self.rating(pid, surface), self.rating(opp_id, surface)
        # clutch stimato dai tie-break osservati (non dal valore nascosto)
        ca = (self.pct(self.stats(pid)["tiebreak"]) - 0.5) * 2
        cb = (self.pct(self.stats(opp_id)["tiebreak"]) - 0.5) * 2
        res = monte_carlo(ra * SIM_SCALE, rb * SIM_SCALE, n=n, seed=pid * 7919 + opp_id, match_tiebreak=match_tiebreak,
                          clutch_a=ca, clutch_b=cb)
        h2h = [m for m in self.world.player_matches(pid) if m.opponent(pid) == opp_id]
        mine = {m.opponent(pid): m for m in self.world.player_matches(pid)}
        theirs = {m.opponent(opp_id): m for m in self.world.player_matches(opp_id)}
        common = []
        for o in sorted(set(mine) & set(theirs) - {pid, opp_id}):
            common.append({"opponent": self.world.players[o],
                           "me": mine[o].winner == pid, "them": theirs[o].winner == opp_id})
        opp_profile = self.profile(opp_id)
        res.update({
            "rating_me": round(ra), "rating_opp": round(rb),
            "serve_me": serve_prob(ra * SIM_SCALE, rb * SIM_SCALE),
            "serve_opp": serve_prob(rb * SIM_SCALE, ra * SIM_SCALE),
            "h2h": h2h, "common": common, "opp_profile": opp_profile,
            "tactics": self._tactics(pid, opp_id, opp_profile, res),
            "stake": self._stake(pid, opp_id),
        })
        return res

    def _stake(self, pid, opp_id):
        """Cosa vale la vittoria in classifica."""
        p = self.world.players[pid]
        rt = self.ranking.realtime(pid)
        value = win_value(rt.new_category, self.world.players[opp_id].category)
        counted_vals = sorted((w.value for w in rt.counted), reverse=True)
        if len(counted_vals) < rt.k:
            gain = value
        else:
            gain = max(0, value - (counted_vals[-1] if counted_vals else 0))
        return {"value": value, "gain": gain, "coefficient": rt.coefficient,
                "promotion_at": rt.promotion_at}

    def _tactics(self, pid, opp_id, opp_profile, sim):
        tips = []
        s = opp_profile["stats"]
        axes = dict(opp_profile["axes"])
        if axes["Set decisivo"] <= 40:
            tips.append("Allunga la partita: l'avversario cala nei set decisivi.")
        if axes["Tie-break"] <= 40:
            tips.append("Nei tie-break è fragile: resta agganciato al set fino al 6-6.")
        if axes["Tie-break"] >= 62:
            tips.append("Evita i tie-break: ha molto sangue freddo nei punti decisivi. Cerca il break presto.")
        if axes["Rimonte"] >= 45:
            tips.append("Non mollare dopo il primo set vinto: rimonta spesso.")
        if axes["Rimonte"] <= 15:
            tips.append("Vinci il primo set: quando va sotto raramente reagisce.")
        surf = max(s["surface"].items(), key=lambda kv: sum(kv[1]))[0] if s["played"] else None
        if surf:
            tips.append(f"Gioca più spesso su {surf.lower()}: preparati a quel tipo di scambi.")
        if sim["win_prob"] < 0.35:
            tips.append("Partita in salita: alza la percentuale di prime e riduci gli errori gratuiti.")
        elif sim["win_prob"] > 0.65:
            tips.append("Sei favorito: gestisci la pressione e gioca il tuo tennis.")
        return tips

    # ------------------------------------------------------------------ Radar Tornei
    def radar(self, pid, limit=None):
        p = self.world.players[pid]
        cur = self.ranking.realtime(pid)
        min_counted = min((w.value for w in cur.counted), default=0) if len(cur.counted) >= cur.k else 0
        today = self.world.today
        surf_pct = {x: self.pct(self.stats(pid)["surface"][x]) for x in SURFACES}
        out = []
        for t in self.world.tournaments.values():
            if t.start <= today or t.gender != p.gender:
                continue
            if p.category > t.max_category:
                continue
            field_ids = [x for x in t.entrants if x != pid]
            if not field_ids:
                continue
            rating = self.rating(pid, t.surface)
            exp_values, win_probs = [], []
            for o in field_ids:
                po = _expected(rating, self.rating(o, t.surface))
                v = win_value(cur.new_category, self.world.players[o].category)
                exp_values.append(po * max(0, v - min_counted))
                win_probs.append(po)
            opportunity = min(1, (sum(exp_values) / len(exp_values)) / 60)
            avg_p = sum(win_probs) / len(win_probs)
            competitiveness = avg_p ** 2  # prob. approssimata di superare due turni
            surface_fit = surf_pct[t.surface]
            if t.city == p.city:
                logistics = 1.0
            elif t.region == p.region:
                logistics = 0.75
            else:
                logistics = 0.25
            days = (t.start - today).days
            timing = 0.4 if days < 4 else 1.0 if days <= 30 else 0.75 if days <= 60 else 0.5
            parts = [
                ("Punti in palio", opportunity, 35),
                ("Probabilità di avanzare", competitiveness, 25),
                ("Superficie", surface_fit, 15),
                ("Distanza", logistics, 15),
                ("Tempistica", timing, 10),
            ]
            score = round(sum(v * w for _, v, w in parts))
            out.append({
                "tournament": t, "score": score, "parts": [(n, round(v * 100), w) for n, v, w in parts],
                "field": len(field_ids), "avg_win": avg_p,
                "field_cats": sorted((self.world.players[o].category for o in field_ids), reverse=True)[:5],
            })
        out.sort(key=lambda x: -x["score"])
        return out[:limit] if limit else out

    def recent_window(self, days=60):
        return self.world.today - timedelta(days=days)


def category_label(idx):
    return cat.label(idx)
