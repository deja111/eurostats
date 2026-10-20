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
import sqlite3
import time

import pandas as pd
from euroleague_api.boxscore_data import BoxScoreData

SEASON = 2026                       # 2026 = sezona 2026/27
COMPETITIONS = {"E": "Evroliga", "U": "Evrokup"}
DB_FILE = "euroleague.db"

STAT_COLS = [
    "Minutes", "Points", "FieldGoalsMade2", "FieldGoalsAttempted2",
    "FieldGoalsMade3", "FieldGoalsAttempted3", "FreeThrowsMade",
    "FreeThrowsAttempted", "OffensiveRebounds", "DefensiveRebounds",
    "TotalRebounds", "Assistances", "Steals", "Turnovers",
    "BlocksFavour", "FoulsCommited", "Valuation", "Home",
]


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_games (
            comp TEXT, season INTEGER, gamecode INTEGER, player_id TEXT,
            player TEXT, team TEXT, stats_json TEXT,
            PRIMARY KEY (comp, season, gamecode, player_id)
        )""")
    return conn


def played_gamecodes(comp):
    meta = BoxScoreData(comp).get_gamecodes_season(SEASON)
    played = meta["played"].astype(str).str.lower().isin(["true", "1"])
    return sorted(meta.loc[played, "gameCode"].astype(int).tolist())


def update(comps):
    conn = get_conn()
    for comp in comps:
        print(f"\n--- {COMPETITIONS[comp]} {SEASON}/{str(SEASON + 1)[-2:]} ---")
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
            continue

        box = BoxScoreData(comp)
        for gc in new_games:
            try:
                df = box.get_players_boxscore_stats(SEASON, gc)
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