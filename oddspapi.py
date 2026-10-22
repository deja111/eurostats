"""
Linije igraca sa kladionica (OddsPapi) -> linije_oddspapi.json

Pokretanje:  python oddspapi.py            (kljuc iz promenljive ODDSPAPI_KEY ili ga pita)
             python oddspapi.py --file oddspapi_odds.json   (proba na sacuvanom odgovoru, bez trosenja zahteva)

Za svaku utakmicu Evrolige u narednih ~36 h: jedan zahtev /odds (besplatno 250 zahteva mesecno).
Iz odgovora se uzimaju samo Over/Under linije igraca; za svakog igraca i statistiku bira se
"glavna" linija (ona koju nudi najvise kladionica) i medijana kvota za Over i Under.
"""
import argparse
import json
import os
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.oddspapi.io/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(HERE, "linije_oddspapi.json")
META_FILE = os.path.join(HERE, "oddspapi_markets_kosarka.json")
TOURNAMENTS = {"E": 138}          # Evroliga (Evrokup: dodati kad saznamo tournamentId)
HOURS_AHEAD = 36
MIN_BOOKS = 2                     # linija mora da postoji kod bar 2 kladionice

# OddsPapi tip -> kljuc statistike u aplikaciji
STAT = {"points": "Points", "rebounds": "TotalRebounds", "assists": "Assistances", "3pointers": "3PM",
        "ptsassreb": "PRA", "ptsreb": "PR", "ptsass": "PA", "assreb": "RA",
        "steals": "Steals", "blocks": "BlocksFavour", "turnovers": "Turnovers"}


def load_meta():
    with open(META_FILE, encoding="utf-8") as f:
        return json.load(f)


def extract(odds, meta):
    """Odgovor /odds -> {(igrac, stat, linija): {kladionica: {'Over': kvota, 'Under': kvota}}}."""
    found = {}
    for slug, book in (odds.get("bookmakerOdds") or {}).items():
        if not book.get("bookmakerIsActive", True) or book.get("suspended"):
            continue
        for mid, market in (book.get("markets") or {}).items():
            m = meta.get(str(mid))
            if not m or m[0] not in STAT:
                continue
            kind, line, outcomes = m
            for oid, out in (market.get("outcomes") or {}).items():
                side = outcomes.get(str(oid))
                if side not in ("Over", "Under"):
                    continue
                for pk, pr in (out.get("players") or {}).items():
                    if pk == "0" or not pr.get("active") or not pr.get("price") or not pr.get("playerName"):
                        continue
                    key = (pr["playerName"].strip(), STAT[kind], float(line))
                    found.setdefault(key, {}).setdefault(slug, {})[side] = float(pr["price"])
    return found


def consensus(found):
    """Po igracu i statistici: glavna linija (najvise kladionica) + medijana i najbolja kvota."""
    by_ps = {}
    for (player, stat, line), books in found.items():
        # samo kladionice koje nude obe strane i realne kvote (glavna linija, ne "alternativne")
        both = {b: v for b, v in books.items()
                if "Over" in v and "Under" in v and 1.25 <= v["Over"] <= 3 and 1.25 <= v["Under"] <= 3}
        by_ps.setdefault((player, stat), []).append((line, both))
    out = []
    for (player, stat), lines in by_ps.items():
        good = [x for x in lines if len(x[1]) >= MIN_BOOKS]
        if not good:
            continue
        # najvise kladionica; kod nerešenog ona gde su Over i Under najbliže
        good.sort(key=lambda x: (-len(x[1]), abs(statistics.median(v["Over"] for v in x[1].values())
                                                 - statistics.median(v["Under"] for v in x[1].values()))))
        line, books = good[0]
        ov = [v["Over"] for v in books.values() if "Over" in v]
        un = [v["Under"] for v in books.values() if "Under" in v]
        out.append({"player": player, "stat": stat, "line": line, "books": len(books),
                    "over": round(statistics.median(ov), 2) if ov else None,
                    "under": round(statistics.median(un), 2) if un else None,
                    "best_over": max(ov) if ov else None, "best_under": max(un) if un else None,
                    "alt_lines": sorted({ln for ln, b in lines if b})})
    out.sort(key=lambda r: (r["player"], r["stat"]))
    return out


def fetch(key, comp="E", hours=HOURS_AHEAD):
    meta = load_meta()
    calls = 0

    def call(path, **params):
        nonlocal calls
        calls += 1
        r = requests.get(f"{BASE}{path}", params={"apiKey": key, **params}, timeout=120)
        r.raise_for_status()
        time.sleep(1.5)
        return r.json()

    now = datetime.now(timezone.utc)
    fixtures = call("/fixtures", sportId=11, tournamentId=TOURNAMENTS[comp],
                    **{"from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "to": (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    fixtures = fixtures if isinstance(fixtures, list) else fixtures.get("data", [])
    games, lines = [], []
    for fx in fixtures:
        if fx.get("statusId", 0) != 0:          # samo utakmice koje jos nisu pocele
            continue
        try:
            odds = call("/odds", fixtureId=fx["fixtureId"])
        except Exception as e:
            print(f"{fx.get('participant1Name')} - {fx.get('participant2Name')}: preskacem ({e})")
            continue
        rows = consensus(extract(odds, meta))
        for r in rows:
            r["fixtureId"] = fx["fixtureId"]
        lines += rows
        games.append({"fixtureId": fx["fixtureId"], "start": fx.get("startTime"),
                      "home": fx.get("participant1Name"), "away": fx.get("participant2Name"),
                      "home_abbr": fx.get("participant1Abbr"), "away_abbr": fx.get("participant2Abbr"),
                      "lines": len(rows)})
        print(f"{fx.get('participant1Name')} - {fx.get('participant2Name')}: {len(rows)} linija")
    print(f"Zahteva potroseno: {calls}")
    return {"comp": comp, "fetched": now.isoformat(timespec="minutes"), "games": games, "lines": lines}


def save(data, path=OUT_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    print(f"Sacuvano: {len(data['lines'])} linija u {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="sacuvan odgovor /odds (proba bez trosenja zahteva)")
    a = ap.parse_args()
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            odds = json.load(f)
        rows = consensus(extract(odds, load_meta()))
        save({"comp": "E", "fetched": datetime.now(timezone.utc).isoformat(timespec="minutes"),
              "games": [{"fixtureId": odds.get("fixtureId"), "lines": len(rows)}], "lines": rows})
        return
    key = os.environ.get("ODDSPAPI_KEY") or __import__("getpass").getpass("OddsPapi kljuc: ").strip()
    if not key:
        print("Nema ODDSPAPI_KEY - preskacem.")
        return
    try:
        save(fetch(key))
    except Exception as e:                    # API nedostupan: stari fajl ostaje
        print(f"OddsPapi: ne mogu da preuzmem linije ({e}). Stari podaci ostaju.")


if __name__ == "__main__":
    main()
