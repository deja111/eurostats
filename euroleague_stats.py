"""
Euroleague + EuroCup statistika igraca - azurira se posle svake odigrane utakmice.

Instalacija:  pip install euroleague-api pandas

Primeri:
  python euroleague_stats.py update                        # obe lige
  python euroleague_stats.py update --comp E               # samo Evroliga
  python euroleague_stats.py player "Vezenkov"             # trazi u obe lige
  python euroleague_stats.py leaders --stat Points --comp U
  python euroleague_stats.py watch --every 30              # auto-azuriranje na 30 min
"""
import argparse
import json
import os
import sqlite3
import time

import pandas as pd
from euroleague_api.boxscore_data import BoxScoreData

SEASON = 2026                       # 2026 = sezona 2026/27
COMPETITIONS = {"E": "Evroliga", "U": "Evrokup"}
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "euroleague.db")

STAT_COLS = [
    "Minutes", "Points", "FieldGoalsMade2", "FieldGoalsAttempted2",
    "FieldGoalsMade3", "FieldGoalsAttempted3", "FreeThrowsMade",
    "FreeThrowsAttempted", "OffensiveRebounds", "DefensiveRebounds",
    "TotalRebounds", "Assistances", "Steals", "Turnovers",
    "BlocksFavour", "FoulsCommited", "Valuation", "Home",
]


# ---------- ljubazni zahtevi / polite requests ----------
# Euroleague server vraca "429 Too Many Requests" ako se salje previse zahteva zaredom.
MIN_GAP = 1.5          # sekundi izmedju dva zahteva
MAX_EXTRAS = 60        # najvise cetvrtina/suteva po ligi u jednom pokretanju (ostatak sledeci put)
_last_call = [0.0]


def polite(fn, *args, **kwargs):
    """Pozovi Euroleague API sa pauzom izmedju zahteva i ponovnim pokusajem posle 429."""
    for attempt in range(5):
        wait = MIN_GAP - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                pause = 10 * (attempt + 1) ** 2          # 10, 40, 90, 160 s
                print(f"  server trazi pauzu (429), cekam {pause} s...")
                time.sleep(pause)
                continue
            raise


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_games (
            comp TEXT, season INTEGER, gamecode INTEGER, player_id TEXT,
            player TEXT, team TEXT, stats_json TEXT,
            PRIMARY KEY (comp, season, gamecode, player_id)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            comp TEXT, season INTEGER, gamecode INTEGER, gameday INTEGER, date TEXT,
            startime TEXT, homecode TEXT, awaycode TEXT, hometeam TEXT, awayteam TEXT,
            played INTEGER,
            PRIMARY KEY (comp, season, gamecode)
        )""")
    return conn


def update_schedule(comp, conn=None):
    """Raspored cele sezone (odigrane i predstojece utakmice) / full season schedule."""
    from euroleague_api.schedule import Schedule
    conn = conn or get_conn()
    s = polite(Schedule(comp).get_schedule, SEASON)
    date = pd.to_datetime(s["date"], format="%b %d, %Y", errors="coerce").dt.strftime("%Y-%m-%d")
    played = s["played"].astype(str).str.lower().isin(["true", "1"]).astype(int)
    rows = list(zip([comp] * len(s), [SEASON] * len(s), s["game"].astype(int),
                    s["gameday"].astype(int), date, s["startime"], s["homecode"], s["awaycode"],
                    s["hometeam"], s["awayteam"], played))
    conn.executemany("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"Raspored: {len(rows)} utakmica ({int(played.sum())} odigrano)")


POSITIONS = {"Guards": "G", "Forwards": "F", "Centers": "C"}


def update_positions(comp, conn=None):
    """Zvanicne pozicije (G/F/C) iz Euroleague liste lidera filtrirane po poziciji.

    Lista lidera trazi minimalan broj utakmica, pa za igrace koji fale
    probamo jos i po klubu.
    """
    from euroleague_api.player_stats import PlayerStats
    conn = conn or get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS positions (
        comp TEXT, season INTEGER, player_id TEXT, pos TEXT,
        PRIMARY KEY (comp, season, player_id))""")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    row = conn.execute("SELECT value FROM meta WHERE key=?", (f"positions_{comp}_{SEASON}",)).fetchone()
    if row and time.time() - float(row[0]) < 20 * 3600:
        print("Pozicije: osvezene u poslednjih 20 h, preskacem.")
        return
    api = PlayerStats(comp)
    found = {}

    def fetch(**kw):
        for name, code in POSITIONS.items():
            d = polite(api.get_player_stats_leaders_single_season,
                SEASON, stat_category="GamesPlayed", top_n=500,
                statistic_mode="Accumulated", position=name, **kw)
            if d is not None and not d.empty and "playerCode" in d:
                for pc in d["playerCode"]:
                    found.setdefault("P" + str(pc).strip().zfill(6), code)
    fetch()
    have = {r[0].strip() for r in conn.execute(
        "SELECT DISTINCT player_id FROM player_games WHERE comp=? AND season=?", (comp, SEASON))}
    missing = have - set(found)
    if missing:
        clubs = [r[0] for r in conn.execute(
            "SELECT DISTINCT team FROM player_games WHERE comp=? AND season=?", (comp, SEASON))]
        for club in clubs:
            try:
                fetch(club_code=club)
            except Exception:
                pass
    conn.executemany("INSERT OR REPLACE INTO positions VALUES (?,?,?,?)",
                     [(comp, SEASON, pid, pos) for pid, pos in found.items()])
    if found:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"positions_{comp}_{SEASON}", str(time.time())))
    conn.commit()
    print(f"Pozicije: {len(found)} igraca ({len(have - set(found))} bez zvanicne pozicije)")


def load_positions(comps):
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS positions (
        comp TEXT, season INTEGER, player_id TEXT, pos TEXT,
        PRIMARY KEY (comp, season, player_id))""")
    q = f"SELECT * FROM positions WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    return pd.read_sql(q, conn, params=(SEASON, *comps))


def load_schedule(comps):
    conn = get_conn()
    q = f"SELECT * FROM schedule WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    s = pd.read_sql(q, conn, params=(SEASON, *comps))
    s["date"] = pd.to_datetime(s["date"], errors="coerce")
    return s


def played_gamecodes(comp):
    meta = polite(BoxScoreData(comp).get_gamecodes_season, SEASON)
    played = meta["played"].astype(str).str.lower().isin(["true", "1"])
    return sorted(meta.loc[played, "gameCode"].astype(int).tolist())


def update(comps):
    conn = get_conn()
    for comp in comps:
        print(f"\n--- {COMPETITIONS[comp]} {SEASON}/{str(SEASON + 1)[-2:]} ---")
        try:
            update_schedule(comp, conn)
        except Exception as e:
            print(f"Ne mogu da dobijem raspored utakmica ({e})")
        try:
            games = played_gamecodes(comp)
        except Exception as e:
            print(f"Ne mogu da dobijem raspored ({e})")
            continue
        done = {r[0] for r in conn.execute(
            "SELECT DISTINCT gamecode FROM player_games WHERE comp=? AND season=?",
            (comp, SEASON))}
        new_games = [g for g in games if g not in done]
        if not new_games:
            print("Nema novih utakmica.")

        box = BoxScoreData(comp)
        for gc in new_games:
            try:
                df = polite(box.get_players_boxscore_stats, SEASON, gc)
            except Exception as e:
                print(f"Utakmica {gc}: preskacem ({e})")
                continue
            df = df[~df["Player"].isin(["Team", "Total"])]
            cols = [c for c in STAT_COLS if c in df.columns]
            rows = [(comp, SEASON, gc, str(r.get("Player_ID", r["Player"])),
                     r["Player"], r["Team"], pd.Series({c: r[c] for c in cols}).to_json())
                    for _, r in df.iterrows()]
            conn.executemany(
                "INSERT OR REPLACE INTO player_games VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
            print(f"Utakmica {gc}: sacuvano {len(rows)} igraca")
        update_extras(comp, conn)
        try:
            update_positions(comp, conn)
        except Exception as e:
            print(f"Ne mogu da dobijem pozicije ({e})")


# ---------- cetvrtine (play-by-play) i sutevi / quarters and shots ----------
PBP_STATS = {  # PLAYTYPE -> (kolona, vrednost)
    "2FGM": ("PTS", 2), "3FGM": ("PTS", 3), "FTM": ("PTS", 1),
    "D": ("REB", 1), "O": ("REB", 1), "AS": ("AST", 1), "ST": ("STL", 1),
    "FV": ("BLK", 1), "TO": ("TOV", 1),
}
PERIOD_COLS = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M"]


def _extra_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS player_periods (
        comp TEXT, season INTEGER, gamecode INTEGER, player_id TEXT, period INTEGER,
        PTS INTEGER, REB INTEGER, AST INTEGER, STL INTEGER, BLK INTEGER, TOV INTEGER, FG3M INTEGER,
        PRIMARY KEY (comp, season, gamecode, player_id, period))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shots (
        comp TEXT, season INTEGER, gamecode INTEGER, num INTEGER, player_id TEXT, team TEXT,
        action TEXT, points INTEGER, x REAL, y REAL, minute INTEGER,
        PRIMARY KEY (comp, season, gamecode, num))""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS onoff (
        comp TEXT, season INTEGER, gamecode INTEGER, player_id TEXT, team TEXT,
        sec REAL, pm INTEGER, c_sec REAL, c_pm INTEGER, {", ".join(c + " INTEGER" for c in CLUTCH_COLS)},
        PRIMARY KEY (comp, season, gamecode, player_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS lineups (
        comp TEXT, season INTEGER, gamecode INTEGER, team TEXT, lineup TEXT,
        sec REAL, pf INTEGER, pa INTEGER,
        PRIMARY KEY (comp, season, gamecode, team, lineup))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS extra_done (
        comp TEXT, season INTEGER, gamecode INTEGER, kind TEXT,
        PRIMARY KEY (comp, season, gamecode, kind))""")


def periods_from_pbp(pbp):
    """Play-by-play -> statistika igraca po cetvrtinama (5+ = produzeci)."""
    p = pbp.dropna(subset=["PLAYER_ID"]).copy()
    p["PLAYER_ID"] = p["PLAYER_ID"].astype(str).str.strip()
    p["PLAYTYPE"] = p["PLAYTYPE"].astype(str).str.strip()
    p = p[p["PLAYTYPE"].isin(PBP_STATS)]
    p["col"] = p["PLAYTYPE"].map(lambda t: PBP_STATS[t][0])
    p["val"] = p["PLAYTYPE"].map(lambda t: PBP_STATS[t][1])
    out = p.pivot_table(index=["PLAYER_ID", "PERIOD"], columns="col", values="val",
                        aggfunc="sum", fill_value=0)
    out["FG3M"] = (p[p["PLAYTYPE"] == "3FGM"].groupby(["PLAYER_ID", "PERIOD"]).size()
                   .reindex(out.index, fill_value=0))
    for c in PERIOD_COLS:
        if c not in out.columns:
            out[c] = 0
    return out[PERIOD_COLS].reset_index()


SCORE = {"2FGM": 2, "3FGM": 3, "FTM": 1}
CLUTCH_COLS = ["c_pts", "c_reb", "c_ast", "c_tov", "c_fgm", "c_fga", "c_ftm", "c_fta"]


def _marker_sec(m):
    try:
        mm, ss = str(m).split(":")
        return int(mm) * 60 + int(ss)
    except ValueError:
        return None


def onoff_from_pbp(pbp):
    """Iz play-by-play: ko je na terenu, minuti, +/-, petorke i clutch statistika.

    Clutch = 4. cetvrtina (posl. 5 min) i produzeci, razlika <= 5 poena pre akcije.
    Vraca (igraci_df, petorke_df).
    """
    p = pbp.sort_values("TRUE_NUMBEROFPLAY").copy()
    p["PLAYTYPE"] = p["PLAYTYPE"].astype(str).str.strip()
    p["PLAYER_ID"] = p["PLAYER_ID"].where(p["PLAYER_ID"].isna(), p["PLAYER_ID"].astype(str).str.strip())
    p["CODETEAM"] = p["CODETEAM"].where(p["CODETEAM"].isna(), p["CODETEAM"].astype(str).str.strip())
    teams = [t for t in p["CODETEAM"].dropna().unique()][:2]
    if len(teams) < 2:
        return pd.DataFrame(), pd.DataFrame()
    team_of = p.dropna(subset=["PLAYER_ID", "CODETEAM"]).groupby("PLAYER_ID")["CODETEAM"].first().to_dict()

    pl = {}   # player -> statistika
    lu = {}   # (team, lineup) -> [sec, pf, pa]

    def P(pid):
        return pl.setdefault(pid, {"sec": 0.0, "pm": 0, "c_sec": 0.0, "c_pm": 0, **{c: 0 for c in CLUTCH_COLS}})

    on = {t: set() for t in teams}
    score = {t: 0 for t in teams}
    last_t = 0.0
    for per, ev in p.groupby("PERIOD", sort=True):
        per = int(per)
        start = 600 * (min(per, 4) - 1) + 300 * max(0, per - 4)
        length = 600 if per <= 4 else 300
        # ko pocinje cetvrtinu: prenos sa kraja prethodne + prvi dogadjaj igraca u ovoj cetvrtini
        first = {}
        for r in ev.itertuples():
            if isinstance(r.PLAYER_ID, str) and r.PLAYER_ID in team_of and r.PLAYER_ID not in first:
                first[r.PLAYER_ID] = r.PLAYTYPE
        for pid, kind in first.items():
            t = team_of[pid]
            if kind == "IN":
                on[t].discard(pid)
            else:
                on[t].add(pid)
        last_t = float(start)
        for r in ev.itertuples():
            ms = _marker_sec(r.MARKERTIME)
            now = start + (length - ms) if ms is not None else (start if r.PLAYTYPE == "BP" else last_t)
            now = max(now, last_t)
            dt = now - last_t
            rem = (start + length) - last_t
            clutch_now = per >= 4 and rem <= 300 and abs(score[teams[0]] - score[teams[1]]) <= 5
            if dt > 0:
                for t in teams:
                    key = (t, "|".join(sorted(on[t])))
                    lu.setdefault(key, [0.0, 0, 0])[0] += dt
                    for pid in on[t]:
                        P(pid)["sec"] += dt
                        if clutch_now:
                            P(pid)["c_sec"] += dt
            last_t = now
            ty, pid, t = r.PLAYTYPE, r.PLAYER_ID, r.CODETEAM
            if ty == "IN" and pid in team_of:
                on[team_of[pid]].add(pid)
                continue
            if ty == "OUT" and pid in team_of:
                on[team_of[pid]].discard(pid)
                continue
            clutch_ev = per >= 4 and (ms is not None and ms <= 300) and \
                abs(score[teams[0]] - score[teams[1]]) <= 5
            if clutch_ev and isinstance(pid, str) and pid in team_of:
                d = P(pid)
                d["c_pts"] += SCORE.get(ty, 0)
                d["c_reb"] += ty in ("D", "O")
                d["c_ast"] += ty == "AS"
                d["c_tov"] += ty == "TO"
                d["c_fgm"] += ty in ("2FGM", "3FGM")
                d["c_fga"] += ty in ("2FGM", "3FGM", "2FGA", "3FGA")
                d["c_ftm"] += ty == "FTM"
                d["c_fta"] += ty in ("FTM", "FTA")
            if ty in SCORE and t in score:
                pts = SCORE[ty]
                score[t] += pts
                o = teams[1] if t == teams[0] else teams[0]
                lu.setdefault((t, "|".join(sorted(on[t]))), [0.0, 0, 0])[1] += pts
                lu.setdefault((o, "|".join(sorted(on[o]))), [0.0, 0, 0])[2] += pts
                for x in on[t]:
                    P(x)["pm"] += pts
                    if clutch_ev:
                        P(x)["c_pm"] += pts
                for x in on[o]:
                    P(x)["pm"] -= pts
                    if clutch_ev:
                        P(x)["c_pm"] -= pts
        # kraj cetvrtine / end of period
        end = start + length
        if end > last_t:
            for t in teams:
                key = (t, "|".join(sorted(on[t])))
                lu.setdefault(key, [0.0, 0, 0])[0] += end - last_t
                for pid in on[t]:
                    P(pid)["sec"] += end - last_t
            last_t = end
    players = pd.DataFrame([{"player_id": k, "team": team_of.get(k), **v} for k, v in pl.items()])
    lineups = pd.DataFrame([{"team": t, "lineup": l, "sec": v[0], "pf": v[1], "pa": v[2]}
                            for (t, l), v in lu.items() if l.count("|") == 4])
    return players, lineups


def update_extras(comp, conn):
    """Dopuni cetvrtine i suteve za sve vec sacuvane utakmice kojima fale."""
    from euroleague_api.play_by_play_data import PlayByPlay
    from euroleague_api.shot_data import ShotData
    _extra_tables(conn)
    games = [r[0] for r in conn.execute(
        "SELECT DISTINCT gamecode FROM player_games WHERE comp=? AND season=? ORDER BY gamecode",
        (comp, SEASON))]
    done = set(conn.execute("SELECT gamecode, kind FROM extra_done WHERE comp=? AND season=?",
                            (comp, SEASON)))
    todo = [(g, k) for g in games for k in ("pbp2", "shots") if (g, k) not in done]
    if not todo:
        return
    left = max(0, len(todo) - MAX_EXTRAS)
    todo = todo[:MAX_EXTRAS]
    print(f"Cetvrtine i sutevi: {len(todo)} preuzimanja" + (f" (jos {left} sledeci put)" if left else "") + "...")
    pbp_api, shot_api = PlayByPlay(comp), ShotData(comp)
    for gc, kind in todo:
        try:
            if kind == "pbp2":
                raw = polite(pbp_api.get_game_play_by_play_data, SEASON, gc)
                per = periods_from_pbp(raw)
                players, lineups = onoff_from_pbp(raw)
                cols = ["sec", "pm", "c_sec", "c_pm"] + CLUTCH_COLS
                conn.executemany(
                    f"INSERT OR REPLACE INTO onoff VALUES ({','.join('?' * (5 + len(cols)))})",
                    [(comp, SEASON, gc, r["player_id"], r["team"], *[float(r[c]) for c in cols])
                     for _, r in players.iterrows()])
                conn.executemany(
                    "INSERT OR REPLACE INTO lineups VALUES (?,?,?,?,?,?,?,?)",
                    [(comp, SEASON, gc, r.team, r.lineup, float(r.sec), int(r.pf), int(r.pa))
                     for r in lineups.itertuples()])
                conn.executemany(
                    "INSERT OR REPLACE INTO player_periods VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(comp, SEASON, gc, r.PLAYER_ID, int(r.PERIOD), *[int(getattr(r, c)) for c in PERIOD_COLS])
                     for r in per.itertuples()])
            else:
                sh = polite(shot_api.get_game_shot_data, SEASON, gc)
                if not sh.empty:
                    sh = sh[sh["ID_ACTION"].isin(["2FGM", "2FGA", "3FGM", "3FGA"])]
                    conn.executemany(
                        "INSERT OR REPLACE INTO shots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [(comp, SEASON, gc, int(r.NUM_ANOT), str(r.ID_PLAYER).strip(), str(r.TEAM).strip(),
                          r.ID_ACTION, int(r.POINTS), float(r.COORD_X), float(r.COORD_Y), int(r.MINUTE))
                         for r in sh.itertuples()])
            conn.execute("INSERT OR REPLACE INTO extra_done VALUES (?,?,?,?)", (comp, SEASON, gc, kind))
            conn.commit()
        except Exception as e:
            print(f"Utakmica {gc} ({kind}): preskacem ({e})")
    print("Cetvrtine i sutevi: gotovo")


def load_periods(comps):
    conn = get_conn()
    _extra_tables(conn)
    q = f"SELECT * FROM player_periods WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    return pd.read_sql(q, conn, params=(SEASON, *comps))


def load_onoff(comps):
    conn = get_conn()
    _extra_tables(conn)
    q = f"SELECT * FROM onoff WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    return pd.read_sql(q, conn, params=(SEASON, *comps))


def load_lineups(comps):
    conn = get_conn()
    _extra_tables(conn)
    q = f"SELECT * FROM lineups WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    return pd.read_sql(q, conn, params=(SEASON, *comps))


def load_shots(comps):
    conn = get_conn()
    _extra_tables(conn)
    q = f"SELECT * FROM shots WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    return pd.read_sql(q, conn, params=(SEASON, *comps))


def load_standings(comp, round_number):
    from euroleague_api.standings import Standings
    return Standings(comp).get_standings(SEASON, round_number)


def load_df(comps):
    conn = get_conn()
    q = f"SELECT * FROM player_games WHERE season=? AND comp IN ({','.join('?' * len(comps))})"
    raw = pd.read_sql(q, conn, params=(SEASON, *comps))
    if raw.empty:
        return raw
    stats = pd.json_normalize(raw["stats_json"].apply(json.loads))
    df = pd.concat([raw.drop(columns="stats_json"), stats], axis=1)

    def to_min(x):
        try:
            m, s = str(x).split(":")
            return int(m) + int(s) / 60
        except ValueError:
            return 0.0
    if "Minutes" in df.columns:
        df["Minutes"] = df["Minutes"].apply(to_min)
    for c in stats.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def show_player(name, comps):
    df = load_df(comps)
    if df.empty:
        print("Nema podataka. Pokreni 'update'.")
        return
    p = df[df["player"].str.contains(name, case=False, na=False)]
    if p.empty:
        print("Igrac nije pronadjen. Probaj samo prezime.")
        return
    for (comp, pid), g in p.groupby(["comp", "player_id"]):
        print(f"\n=== {g['player'].iloc[0]} ({g['team'].iloc[-1]}) - {COMPETITIONS[comp]} ===")
        view = g.sort_values("gamecode")[
            ["gamecode", "Minutes", "Points", "TotalRebounds",
             "Assistances", "Steals", "BlocksFavour", "Valuation"]]
        view = view.rename(columns={
            "gamecode": "Utakm.", "Points": "PTS", "TotalRebounds": "REB",
            "Assistances": "AST", "Steals": "STL", "BlocksFavour": "BLK",
            "Valuation": "PIR"})
        print(view.round(1).to_string(index=False))
        print(f"\nProsek ({len(g)} utakm.):  "
              f"{g['Points'].mean():.1f} poena, "
              f"{g['TotalRebounds'].mean():.1f} skokova, "
              f"{g['Assistances'].mean():.1f} asistencija, "
              f"{g['Steals'].mean():.1f} ukradenih, "
              f"{g['BlocksFavour'].mean():.1f} blokada")


def show_leaders(stat, comps, top=10):
    df = load_df(comps)
    if df.empty or stat not in df.columns:
        print("Nema podataka ili pogresna statistika.")
        return
    for comp, d in df.groupby("comp"):
        avg = (d.groupby(["player_id", "player", "team"])[stat]
                .agg(["mean", "count"]).reset_index())
        avg = avg[avg["count"] >= 3].sort_values("mean", ascending=False).head(top)
        print(f"\n{COMPETITIONS[comp]} - top {top} po proseku ({stat}), min. 3 utakmice:")
        for i, r in enumerate(avg.itertuples(), 1):
            print(f"{i:>2}. {r.player:<28} {r.team:<5} {r.mean:5.1f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("update", "player", "leaders", "watch"):
        sp = sub.add_parser(name)
        sp.add_argument("--comp", choices=["E", "U", "both"], default="both",
                        help="E=Evroliga, U=Evrokup, both=obe (default)")
        if name == "player":
            sp.add_argument("name")
        if name == "leaders":
            sp.add_argument("--stat", default="Points")
        if name == "watch":
            sp.add_argument("--every", type=int, default=30, help="minuta")
    a = ap.parse_args()
    comps = list(COMPETITIONS) if a.comp == "both" else [a.comp]

    if a.cmd == "update":
        update(comps)
    elif a.cmd == "player":
        show_player(a.name, comps)
    elif a.cmd == "leaders":
        show_leaders(a.stat, comps)
    elif a.cmd == "watch":
        while True:
            update(comps)
            time.sleep(a.every * 60)


if __name__ == "__main__":
    main()