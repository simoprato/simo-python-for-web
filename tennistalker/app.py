"""TennisSim Club — simulatore delle funzionalità Base e Club Membership di un'app di ranking tennistico.

Avvio:  python app.py   (poi apri http://127.0.0.1:5001)
Tutti i dati sono sintetici e generati all'avvio; nessun pagamento reale viene effettuato.
"""

import hashlib
import os
from datetime import date
from pathlib import Path
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from engine import categories as cat
from engine.analysis import Analytics
from engine.charts import radar_chart, step_chart
from engine.data import REGIONS, SURFACES, TOURNAMENT_KINDS, generate_world
from engine.personal import (PERSONAL_ID, ProfileParseError, add_personal_player, delete_profile,
                             load_profile, parse_profile_text, save_profile)
from engine.ranking import RankingService
from engine.simulation import format_score

VERSION = "1.1"
PRICE = "79,99€"
MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

# (endpoint, titolo, descrizione, premium)
FEATURES = [
    ("realtime", "Classifica simulata in tempo reale", "La tua classifica ricalcolata a ogni partita.", False),
    ("players", "Esplora i giocatori italiani", "Sfoglia giocatori per regione, circolo e categoria.", False),
    ("competitions", "Cerca le competizioni", "Trova tornei per zona, superficie e limite di categoria.", False),
    ("harmonized", "Classifica Armonizzata", "Dove sarai a fine anno, con gli avversari alla loro classifica reale.", True),
    ("supersimulated", "Classifica Supersimulata", "Il tuo ranking tra due passaggi di classifica, mese per mese.", True),
    ("radar", "Radar Tornei", "Uno score 0–100 per ogni torneo a cui puoi iscriverti.", True),
    ("simulate", "Simula Partita", "Studia l'avversario e simula il match 2.000 volte.", True),
    ("analysis", "Forze & Debolezze", "L'analisi del tuo gioco a partire dai risultati.", True),
    ("positions", "Posizione assoluta", "Nazionale, regionale e di circolo.", True),
    ("search", "Ricerca avanzata senza restrizioni", "Tutti i filtri, nessun limite di risultati.", True),
    ("discount", "15% sconto Tennis Warehouse Europe", "Codice sconto riservato ai membri (simulato).", True),
]
FEATURE_BY_ENDPOINT = {f[0]: f for f in FEATURES}


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "data" / "il_mio_profilo.json"


def create_app(today=None, seed=2026, profile_path=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("TENNISSIM_SECRET", "tennissim-dev-key")
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
    profile_path = Path(profile_path or os.environ.get("TENNISSIM_PROFILE") or DEFAULT_PROFILE_PATH)
    world = ranking = analytics = None
    personal_error = None

    def build():
        """(Ri)genera il mondo simulato e, se presente, vi inserisce il profilo reale salvato."""
        nonlocal world, ranking, analytics, personal_error
        world = generate_world(today or date.today(), seed=seed)
        personal_error = None
        profile = load_profile(profile_path)
        if profile:
            try:
                add_personal_player(world, profile)
            except (KeyError, ValueError, RuntimeError) as e:
                personal_error = f"Profilo salvato non valido: {e}"
        ranking = RankingService(world)
        analytics = Analytics(world, ranking)
        app.config.update(WORLD=world, RANKING=ranking, ANALYTICS=analytics, PROFILE=profile)

    build()

    # ------------------------------------------------------------------ helpers
    def is_premium():
        return bool(session.get("premium"))

    def me():
        """Profilo scelto nella sessione; in assenza, il profilo con i dati reali (se importato)."""
        pid = session.get("player_id")
        if pid in world.players:
            return world.players[pid]
        return world.players.get(PERSONAL_ID)

    def target_player():
        """Giocatore su cui lavorare: ?id=... oppure il profilo selezionato."""
        pid = request.args.get("id", type=int)
        if not pid:
            return me()
        p = world.players.get(pid)
        if p is None:
            abort(404)
        return p

    def needs_player(view):
        @wraps(view)
        def wrapper(*a, **kw):
            p = target_player()
            if p is None:
                flash("Prima scegli il tuo profilo giocatore (oppure apri un giocatore dalla lista).", "info")
                return redirect(url_for("profile", next=request.path))
            return view(p, *a, **kw)
        return wrapper

    def premium_required(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if not is_premium():
                return render_template("locked.html", feature=FEATURE_BY_ENDPOINT[request.endpoint]), 402
            return view(*a, **kw)
        return wrapper

    @app.context_processor
    def inject():
        return {"premium": is_premium(), "me": me(), "features": FEATURES, "price": PRICE,
                "today": world.today, "cat": cat, "rank": ranking.realtime,
                "personal_error": personal_error, "version": VERSION}

    @app.template_filter("d")
    def fmt_date(d):
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"

    @app.template_filter("pct")
    def fmt_pct(x, digits=0):
        return f"{x * 100:.{digits}f}%".replace(".", ",")

    @app.template_filter("score")
    def fmt_score(sets):
        return format_score(sets)

    @app.template_filter("catlabel")
    def fmt_cat(idx):
        return cat.label(idx)

    # ------------------------------------------------------------------ pagine generali
    @app.route("/")
    def home():
        p = me()
        summary = ranking.realtime(p.id) if p else None
        return render_template("home.html", summary=summary)

    @app.route("/profilo", methods=["GET", "POST"])
    def profile():
        if request.method == "POST":
            pid = request.form.get("player_id", type=int)
            if pid in world.players:
                session["player_id"] = pid
                flash(f"Profilo impostato: {world.players[pid].name}", "ok")
                nxt = request.form.get("next") or url_for("home")
                safe = nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt
                return redirect(nxt if safe else url_for("home"))
            flash("Giocatore non trovato.", "error")
        q = request.args.get("q", "").strip().lower()
        results = []
        if q:
            results = [p for p in world.players.values() if q in p.name.lower()][:20]
        return render_template("profile.html", q=q, results=results, next=request.args.get("next", ""))

    @app.route("/profilo/esci")
    def profile_clear():
        session.pop("player_id", None)
        return redirect(url_for("home"))

    @app.route("/membership")
    def membership():
        return render_template("membership.html")

    @app.route("/membership/checkout", methods=["GET", "POST"])
    def checkout():
        if request.method == "POST":
            session["premium"] = True
            session["premium_since"] = world.today.isoformat()
            flash("Club Membership attivata (simulazione: nessun addebito).", "ok")
            return redirect(url_for("home"))
        return render_template("checkout.html")

    @app.route("/membership/disdici", methods=["POST"])
    def cancel():
        session.pop("premium", None)
        session.pop("premium_since", None)
        flash("Membership disdetta. Sei tornato al piano Base.", "info")
        return redirect(url_for("membership"))

    # ------------------------------------------------------------------ BASE
    @app.route("/classifica")
    @needs_player
    def realtime(p):
        res = ranking.realtime(p.id)
        return render_template("ranking_realtime.html", p=p, res=res,
                               players=world.players, matches=world.player_matches(p.id, ranking.year_start))

    @app.route("/giocatori")
    def players():
        region = request.args.get("region", "")
        gender = request.args.get("gender", "")
        page = max(1, request.args.get("page", 1, type=int))
        ps = ranking.leaderboard(gender=gender or None, region=region or None)
        per_page = 25
        total = len(ps)
        ps = ps[(page - 1) * per_page: page * per_page]
        return render_template("players.html", players=ps, region=region, gender=gender, page=page,
                               pages=(total + per_page - 1) // per_page, total=total,
                               regions=list(REGIONS), offset=(page - 1) * per_page)

    @app.route("/giocatore/<int:pid>")
    def player(pid):
        p = world.players.get(pid) or abort(404)
        res = ranking.realtime(pid)
        recent = list(reversed(world.player_matches(pid)))[:12]
        return render_template("player.html", p=p, res=res, recent=recent, players=world.players,
                               tournaments=world.tournaments)

    @app.route("/competizioni")
    def competitions():
        f = {k: request.args.get(k, "") for k in ("q", "region", "surface", "gender", "kind", "when")}
        f["when"] = f["when"] or "future"
        ts = list(world.tournaments.values())
        if f["when"] == "future":
            ts = [t for t in ts if t.end >= world.today]
            ts.sort(key=lambda t: t.start)
        else:
            ts = [t for t in ts if t.end < world.today]
            ts.sort(key=lambda t: t.start, reverse=True)
        q = f["q"].lower()
        ts = [t for t in ts
              if (not q or q in t.name.lower() or q in t.city.lower() or q in t.club.lower())
              and (not f["region"] or t.region == f["region"])
              and (not f["surface"] or t.surface == f["surface"])
              and (not f["gender"] or t.gender == f["gender"])
              and (not f["kind"] or t.kind == f["kind"])]
        return render_template("competitions.html", tournaments=ts[:60], total=len(ts), f=f, players=world.players,
                               regions=list(REGIONS), surfaces=SURFACES,
                               kinds=[k for k, _ in TOURNAMENT_KINDS])

    @app.route("/competizioni/<int:tid>")
    def competition(tid):
        t = world.tournaments.get(tid) or abort(404)
        matches = [m for m in world.matches if m.tournament_id == tid]
        rounds = {}
        for m in matches:
            rounds.setdefault(m.round, []).append(m)
        radar = None
        p = me()
        if p and is_premium():
            radar = next((r for r in analytics.radar(p.id) if r["tournament"].id == tid), None)
        entrants = sorted((world.players[x] for x in t.entrants), key=lambda x: -x.category)
        return render_template("competition.html", t=t, rounds=rounds, entrants=entrants,
                               players=world.players, radar=radar)

    # ------------------------------------------------------------------ dati reali
    @app.route("/i-miei-dati", methods=["GET", "POST"])
    def my_data():
        if request.method == "POST":
            if request.form.get("action") == "delete":
                delete_profile(profile_path)
                if session.get("player_id") == PERSONAL_ID:
                    session.pop("player_id")
                build()
                flash("Dati reali eliminati da questo computer.", "info")
                return redirect(url_for("my_data"))
            text = request.form.get("text", "")
            try:
                profile = parse_profile_text(text)
            except ProfileParseError as e:
                flash(str(e), "error")
                return render_template("my_data.html", text=text, profile=None, check=None)
            save_profile(profile_path, profile)
            build()
            if personal_error:
                flash(personal_error, "error")
            else:
                session["player_id"] = PERSONAL_ID
                flash(f"Dati importati: {profile['wins']} vittorie e {profile['losses']} sconfitte ricostruite.", "ok")
            return redirect(url_for("my_data"))
        profile = app.config.get("PROFILE")
        check = None
        if profile and PERSONAL_ID in world.players:
            check = _reconstruction_check(world, profile)
        return render_template("my_data.html", text="", profile=profile, check=check,
                               p=world.players.get(PERSONAL_ID))

    # ------------------------------------------------------------------ PREMIUM
    @app.route("/classifica/armonizzata")
    @premium_required
    @needs_player
    def harmonized(p):
        today_res, projected = ranking.harmonized(p.id)
        official = ranking.realtime(p.id)
        changed = [w for w in today_res.counted + today_res.discarded
                   if w.opponent and world.players[w.opponent].category != w.opponent_cat]
        return render_template("ranking_harmonized.html", p=p, today_res=today_res, projected=projected,
                               official=official, changed=changed, players=world.players)

    @app.route("/classifica/supersimulata")
    @premium_required
    @needs_player
    def supersimulated(p):
        data = ranking.supersimulated(p.id)
        chart = step_chart(data["timeline"], cat.label)
        return render_template("ranking_super.html", p=p, data=data, chart=chart, players=world.players)

    @app.route("/radar")
    @premium_required
    @needs_player
    def radar(p):
        surface = request.args.get("surface", "")
        items = analytics.radar(p.id)
        if surface:
            items = [i for i in items if i["tournament"].surface == surface]
        return render_template("radar.html", p=p, items=items[:40], surfaces=SURFACES, surface=surface)

    @app.route("/simula")
    @premium_required
    @needs_player
    def simulate(p):
        opp_id = request.args.get("opp", type=int)
        q = request.args.get("q", "").strip().lower()
        surface = request.args.get("surface", "Terra battuta")
        if surface not in SURFACES:
            surface = "Terra battuta"
        fmt = request.args.get("fmt", "mtb")
        candidates = []
        if q:
            candidates = [o for o in world.players.values()
                          if q in o.name.lower() and o.id != p.id and o.gender == p.gender][:15]
        else:
            # suggerimenti: avversari affrontati di recente e prossimi possibili avversari
            seen = []
            for m in reversed(world.player_matches(p.id)):
                o = m.opponent(p.id)
                if o not in seen:
                    seen.append(o)
            candidates = [world.players[o] for o in seen[:8]]
        result = opp = None
        if opp_id and opp_id in world.players and opp_id != p.id:
            opp = world.players[opp_id]
            result = analytics.simulate(p.id, opp_id, surface, match_tiebreak=fmt == "mtb")
        return render_template("simulate.html", p=p, opp=opp, result=result, candidates=candidates,
                               q=q, surface=surface, surfaces=SURFACES, fmt=fmt, players=world.players)

    @app.route("/analisi")
    @premium_required
    @needs_player
    def analysis(p):
        prof = analytics.profile(p.id)
        return render_template("analysis.html", p=p, prof=prof, s=prof["stats"], chart=radar_chart(prof["axes"]))

    @app.route("/posizione")
    @premium_required
    @needs_player
    def positions(p):
        return render_template("positions.html", p=p, positions=ranking.positions(p.id), ranking=ranking)

    @app.route("/ricerca")
    def search():
        a = request.args
        q = a.get("q", "").strip().lower()
        premium = is_premium()
        locked_used = False
        ps = list(world.players.values())
        if q:
            ps = [x for x in ps if q in x.name.lower()]
        if premium:
            if a.get("region"):
                ps = [x for x in ps if x.region == a["region"]]
            if a.get("club"):
                cq = a["club"].lower()
                ps = [x for x in ps if cq in x.club.lower()]
            if a.get("gender"):
                ps = [x for x in ps if x.gender == a["gender"]]
            cmin, cmax = a.get("cmin", type=int), a.get("cmax", type=int)
            if cmin is not None:
                ps = [x for x in ps if x.category >= cmin]
            if cmax is not None:
                ps = [x for x in ps if x.category <= cmax]
            amin, amax = a.get("amin", type=int), a.get("amax", type=int)
            if amin is not None:
                ps = [x for x in ps if world.today.year - x.birth_year >= amin]
            if amax is not None:
                ps = [x for x in ps if world.today.year - x.birth_year <= amax]
            trend = a.get("trend")
            if trend == "up":
                ps = [x for x in ps if ranking.realtime(x.id).delta > 0]
            elif trend == "down":
                ps = [x for x in ps if ranking.realtime(x.id).delta < 0]
            sort = a.get("sort", "category")
            keys = {
                "category": lambda x: (-ranking.realtime(x.id).new_category, -ranking.realtime(x.id).coefficient),
                "coefficient": lambda x: -ranking.realtime(x.id).coefficient,
                "winrate": lambda x: -(analytics.stats(x.id)["wins"] / max(1, analytics.stats(x.id)["played"])),
                "elo": lambda x: -analytics.elo[x.id],
                "name": lambda x: (x.last, x.first),
            }
            ps.sort(key=keys.get(sort, keys["category"]))
            limit = 200
        else:
            locked_used = any(a.get(k) for k in ("region", "club", "gender", "cmin", "cmax", "amin", "amax", "trend"))
            ps.sort(key=lambda x: (x.last, x.first))
            limit = 5
        total = len(ps) if (q or premium) else 0
        results = ps[:limit] if (q or premium and request.args) else []
        return render_template("search.html", results=results, total=total, limit=limit, q=a.get("q", ""),
                               a=a, regions=list(REGIONS), locked_used=locked_used, analytics=analytics)

    @app.route("/sconto")
    @premium_required
    def discount():
        seed = f"{session.get('player_id', 0)}-{session.get('premium_since', '')}"
        code = "TWE15-" + hashlib.sha1(seed.encode()).hexdigest()[:8].upper()
        return render_template("discount.html", code=code)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("message.html", title="Pagina non trovata",
                               text="Il giocatore o il torneo richiesto non esiste."), 404

    return app


def _reconstruction_check(world, profile):
    """Confronta i totali incollati con quelli delle partite ricostruite."""
    from engine.personal import REL_LABELS
    me = world.players[PERSONAL_ID]
    rows = []
    ms = world.player_matches(PERSONAL_ID)
    for label, diff in REL_LABELS:
        got = [0, 0]
        for m in ms:
            won = m.winner == PERSONAL_ID
            opp_cat = m.loser_cat if won else m.winner_cat
            d = max(-2, min(2, opp_cat - me.category))
            if d == diff:
                got[0 if won else 1] += 1
        rows.append((label, profile["vs"].get(str(diff), [0, 0]), got))
    for n in (2, 3):
        got = [0, 0]
        for m in ms:
            if len(m.sets) == n:
                got[0 if m.winner == PERSONAL_ID else 1] += 1
        rows.append((f"Match in {n} set", (profile.get("sets") or {}).get(str(n)) or [0, 0], got))
    return rows


if __name__ == "__main__":
    create_app().run(debug=True, port=5001)
