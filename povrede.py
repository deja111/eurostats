"""
Povrede igraca iz zvanicnog Euroleague izvestaja (Injury report) -> povrede.json

Pokretanje:  python povrede.py           (cita sajt i upisuje povrede.json pored ovog fajla)
             python povrede.py --file primer_povrede.html   (proba na sacuvanoj stranici)

Izvestaj je clanak na euroleaguebasketball.net koji se dopunjuje kako klubovi salju podatke.
Za svaku utakmicu kola ima naslov "### Domacin vs. Gost", ispod oba tima ("##### Tim"),
recenicu sta je klub potvrdio i napomene po igracima.
"""
import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

import requests

import euroleague_stats as es

BASE = "https://www.euroleaguebasketball.net"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "povrede.json")

# status iz potvrdjene recenice kluba (redosled je bitan)
STATUS_PATTERNS = [
    ("out", r"\b(?:is|are)\s+(?:all\s+|both\s+)?ruled\s+out"),
    ("out", r"\b(?:remains?|remain)\s+(?:sidelined|out)"),
    ("out", r"\b(?:is|are)\s+(?:all\s+)?out\b"),
    ("out", r"\bis\s+(?:[\w']+\s+)?only\s+absentee"),
    ("out", r"\bis\s+the\s+only\s+player\s+that\s+did\s+not\s+travel"),
    ("out", r"\b(?:will|won't)\s+(?:miss|not\s+play)"),
    ("doubtful", r"\b(?:is|are)\s+(?:both\s+)?doubtful"),
    ("questionable", r"\b(?:is|are)\s+(?:both\s+)?questionable"),
    ("gtd", r"\b(?:is|are)\s+(?:a\s+)?game-time\s+decisions?"),
    ("available", r"\b(?:is\s+|are\s+)?(?:listed\s+as\s+)?available(?:\s+once\s+again)?"),
]
# napomene za klubove koji jos nisu poslali izvestaj: jaki znaci da igrac ne igra
LIKELY_OUT = re.compile(
    r"out\s+(?:until|for)|sidelined\s+(?:for|until)|has\s+been\s+out\s+since|remains\s+sidelined|"
    r"season-ending|undergo(?:ne|ing)?\s+surgery|not\s+yet\s+been\s+registered|will\s+be\s+out|"
    r"yet\s+to\s+play\s+(?:so\s+far\s+)?this\s+season|has\s+not\s+played\s+so\s+far", re.I)
BACK = re.compile(r"returned\s+to\s+action|listed\s+as\s+available|is\s+available", re.I)
NAME = re.compile(r"[A-Z][A-Za-z'\.\-]+(?:\s+(?:de|De|del|Del|da|Da|van|Van|von|Le|La|Dos|di|Di)?\s*"
                  r"[A-Z][A-Za-z'\.\-]+)+")


NOT_NAMES = {"league", "cup", "round", "rounds", "euroleague", "final", "four", "season", "club", "coach",
             "german", "greek", "spanish", "french", "turkish", "italian", "new", "both", "and", "the"}


def is_name(n):
    w = norm(n)
    return len(w) >= 2 and not (set(w) & NOT_NAMES)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s.replace("-", " ")).split()


def strip_md(s):
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).strip()


# ---------- preuzimanje / fetching ----------
def find_report_url(session=requests):
    r = session.get(f"{BASE}/euroleague/news/", headers=HEADERS, timeout=30)
    r.raise_for_status()
    for blok in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', r.text, re.S):
        try:
            data = json.loads(blok)
        except ValueError:
            continue
        for d in (data if isinstance(data, list) else [data]):
            for it in (d.get("itemListElement", []) if isinstance(d, dict) else []):
                if isinstance(it, dict) and "injury-report" in str(it.get("url", "")).lower():
                    return it["url"]
    return None


def extract(html):
    """Iz stranice clanka izvuci markdown tekst, naslov, datum i utakmice (gamecode, naziv)."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    full = "".join(json.loads('"' + c + '"') for c in chunks)
    m = re.search(r'"slug":"[^"]*injury-report[^"]*".*?"content":\[\{[^\]]*?"text":"\$(\w+)"', full, re.S)
    if not m:
        raise ValueError("Ne nalazim tekst izvestaja u stranici")
    ref = m.group(1)
    t = re.search(rf'(?:^|\n|\]){ref}:T([0-9a-f]+),', full)
    if not t:
        raise ValueError("Ne nalazim telo izvestaja")
    start = t.end()
    body = full[start:start + int(t.group(1), 16) + 200]
    body = re.split(r"\n?\b[0-9a-f]{1,3}:T[0-9a-f]+,", body)[0]
    meta = full[m.start():m.end()]
    title = re.search(r'"title":"(Injury report[^"]*)"', full)
    pub = re.search(r'"publishDate":"([^"]+)"', meta) or re.search(r'"publishDate":"([^"]+)"', full)
    games = re.findall(r'"text":"([^"]+?) v ([^"]+?) \([^)]*\)","sourceSystem":"FS_BASKETBALL_MATCH",'
                       r'"sourceSystemId":"(\d+)"', full)
    return {"markdown": body, "title": title.group(1) if title else "",
            "published": pub.group(1) if pub else None,
            "games": list({int(g): {"home": h, "away": a, "gamecode": int(g)} for h, a, g in games}.values())}


# ---------- citanje teksta / parsing ----------
def parse_confirmed(sentence):
    """'A and B are ruled out while C is questionable' -> [(ime, status)]"""
    s = re.split(r"\s+for\s+[\w\s'’.]+?(?:'s|’s|its)\s+game|,\s+the\s+club", sentence)[0]
    hits = []
    for status, pat in STATUS_PATTERNS:
        for m in re.finditer(pat, s):
            if not any(a <= m.start() < b for a, b, _ in hits):
                hits.append((m.start(), m.end(), status))
    hits.sort()
    out, prev = [], 0
    for a, b, status in hits:
        seg = s[prev:a].split(" while ")[-1]
        for name in NAME.findall(seg):
            if is_name(name):
                out.append((name.strip(), status))
        prev = b
    return out


def parse_markdown(md):
    """Vrati listu timova: {'label', 'game', 'side', 'summary', 'reported', 'full', 'players': [...]}"""
    teams, game, side = [], None, 0
    cur = None
    for line in md.splitlines():
        line = line.rstrip()
        g = re.match(r"^###\s+(.+?)\s+vs\.\s+(.+?)\s*\((.*?)\)\s*$", line)
        if g:
            game, side = (g.group(1).strip(), g.group(2).strip()), 0
            continue
        t = re.match(r"^#####\s+(.+)$", line)
        if t and game:
            cur = {"label": t.group(1).strip(), "game": game, "side": side, "summary": "",
                   "bullets": []}
            side += 1
            teams.append(cur)
            continue
        if not cur or not line.strip() or line.startswith("#"):
            continue
        if line.lstrip().startswith("- "):
            cur["bullets"].append(strip_md(line.lstrip()[2:]))
        elif not cur["summary"]:
            cur["summary"] = strip_md(line)
    for tm in teams:
        summ = tm["summary"]
        tm["reported"] = "not yet sent an injury report" not in summ
        tm["full"] = bool(re.search(r"full roster|full strength|no injuries", summ, re.I))
        players = {}
        if tm["reported"] and not tm["full"]:
            for name, st in parse_confirmed(summ):
                players[name] = {"name": name, "status": st, "confirmed": True, "note": ""}
        for b in tm["bullets"]:
            names = [n for n in NAME.findall(b) if is_name(n)]
            if not names:
                continue
            name = names[0]
            key = next((k for k in players if norm(k)[-1] == norm(name)[-1]), None)
            if key:
                players[key]["note"] = b
            elif not tm["reported"] and LIKELY_OUT.search(b) and not BACK.search(b):
                for nm in names:   # "Nunn and Sloukas are yet to play" -> oba
                    players.setdefault(nm, {"name": nm, "status": "likely_out", "confirmed": False, "note": b})
            elif not tm["reported"]:
                players.setdefault(name, {"name": name, "status": "info", "confirmed": False, "note": b})
        tm["players"] = list(players.values())
    return teams


# ---------- povezivanje sa bazom / linking ----------
def link(teams, games, comp="E"):
    """Dodeli timovima zvanicnu sifru (preko gamecode iz rasporeda), a igracima player_id."""
    sched = es.load_schedule([comp])
    code_of = {}
    for g in games:
        row = sched[sched["gamecode"] == g["gamecode"]]
        if not row.empty:
            code_of[(g["home"].lower(), g["away"].lower())] = (row["homecode"].iloc[0], row["awaycode"].iloc[0],
                                                               g["gamecode"])
    df = es.load_df([comp])
    roster = {}
    if not df.empty:
        last = df.sort_values("gamecode").groupby("player_id").tail(1)
        for r in last.itertuples():
            last_name, _, first = r.player.partition(",")
            roster.setdefault(r.team, []).append((r.player_id.strip(), r.player, norm(first), norm(last_name)))
    for tm in teams:
        key = (tm["game"][0].lower(), tm["game"][1].lower())
        h, a, gc = code_of.get(key, (None, None, None))
        tm["team"] = (h, a)[tm["side"]] if h else None
        tm["gamecode"] = gc
        for p in tm["players"]:
            parts = norm(p["name"])
            cands = roster.get(tm["team"], [])
            # 1) ime + prezime, 2) samo prezime (ako je jedinstveno u timu)
            m = [c for c in cands if c[3] and c[3][-1] == parts[-1] and (not c[2] or c[2][0] == parts[0])]
            if len(m) != 1:
                m = [c for c in cands if c[3] and " ".join(c[3]).endswith(" ".join(parts[1:]))]
            p["player_id"], p["db_name"] = (m[0][0], m[0][1]) if len(m) == 1 else (None, None)
    return teams


def build(html, url=None, comp="E"):
    info = extract(html)
    teams = link(parse_markdown(info["markdown"]), info["games"], comp)
    return {
        "source": url, "title": info["title"], "published": info["published"], "comp": comp,
        "games": info["games"],
        "teams": [{k: tm[k] for k in ("label", "team", "gamecode", "reported", "full", "summary")}
                  for tm in teams],
        "players": [{**p, "team": tm["team"], "gamecode": tm["gamecode"]}
                    for tm in teams for p in tm["players"]],
    }


def save(data, path=OUT_FILE):
    """Upisi samo ako se sadrzaj promenio (da se sajt ne restartuje bez potrebe)."""
    old = None
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
        except ValueError:
            old = None
    if old and {k: v for k, v in old.items() if k != "fetched"} == data:
        print("Povrede: nema promena.")
        return False
    data = {**data, "fetched": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Povrede: upisano {len(data['players'])} igraca u {path}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="sacuvana stranica izvestaja (za probu)")
    a = ap.parse_args()
    try:
        if a.file:
            html, url = open(a.file, encoding="utf-8").read(), None
        else:
            url = find_report_url()
            if not url:
                print("Nema izvestaja o povredama na stranici sa vestima.")
                return
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            html = r.text
        save(build(html, url))
    except Exception as e:      # sajt nedostupan ili promenjen izgled: zadrzi stari povrede.json
        print(f"Povrede: ne mogu da procitam izvestaj ({e}). Stari podaci ostaju.")


if __name__ == "__main__":
    main()
