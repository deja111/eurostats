"""
Citanje linija kladionice iz nalepljenog teksta ili CSV-a i racun vrednosti kvote.

Jedan red = jedan igrac:  igrac, statistika, linija[, kvota Over[, kvota Under]]
Primeri koji rade:
    Vezenkov, poeni, 17.5, 1.85, 1.90
    Vezenkov; poeni; 17,5; 1,85; 1,90
    Sasha Vezenkov poeni 17.5 1.85 1.90
    Edwards (ZAL)  PRA  24.5
"""
import re
import unicodedata

# statistika -> kljuc u aplikaciji (poredjenje bez razmaka, tacaka, plusa i kvacica)
STAT_ALIASES = {
    "Points": ["poeni", "poena", "poen", "pts", "points", "pt", "p"],
    "TotalRebounds": ["skokovi", "skoka", "skok", "reb", "rebounds", "rebs", "s", "r"],
    "Assistances": ["asistencije", "asistencija", "asist", "ast", "assists", "a"],
    "PRA": ["pra", "psa", "poeniskokoviasistencije", "poeniskokoviasist", "pointsreboundsassists", "ptsrebast"],
    "PR": ["pr", "ps", "poeniskokovi", "pointsrebounds", "ptsreb"],
    "PA": ["pa", "poeniasistencije", "poeniasist", "pointsassists", "ptsast"],
    "RA": ["ra", "sa", "skokoviasistencije", "skokoviasist", "reboundsassists", "rebast"],
    "3PM": ["trojke", "trojka", "trojki", "3pm", "3p", "3", "threes", "trojkepogodjene"],
    "Steals": ["ukradene", "ukradena", "ukradenih", "ukr", "stl", "steals"],
    "BlocksFavour": ["blokade", "blokada", "blok", "blk", "blocks"],
    "Valuation": ["pir", "indeks", "index", "valuation"],
    "Turnovers": ["izgubljene", "izgubljena", "to", "turnovers", "tov"],
    "PTS_H1": ["poeni1p", "poeni1pol", "poeni1poluvreme", "h1poeni", "1ppoeni", "poenih1", "points1sthalf"],
    "PTS_Q1": ["poeni1c", "poeni1cetvrtina", "q1poeni", "poeniq1", "points1stquarter"],
    "REB_H1": ["skokovi1p", "skokovi1poluvreme", "h1skokovi"],
    "AST_H1": ["asistencije1p", "asist1p", "h1asist"],
    "PRA_H1": ["pra1p", "psa1p", "h1pra"],
    "3PM_H1": ["trojke1p", "h1trojke"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return s.replace("đ", "dj")


def stat_key(text, extra=None):
    """'Poeni+Skokovi+Asist.' -> 'PRA'. extra = {normalizovan naziv: kljuc} iz aplikacije."""
    t = re.sub(r"[\s.+\-_/()]", "", norm(text).replace("dj", "d"))
    t2 = re.sub(r"[\s.+\-_/()]", "", norm(text))
    for key, al in STAT_ALIASES.items():
        if t in al or t2 in al:
            return key
    if extra:
        return extra.get(t2) or extra.get(t)
    return None


def _num(tok):
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


def parse_line(raw, extra=None):
    """Jedan red -> dict(name, team, stat, line, over, under) ili dict sa 'error'."""
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    team = None
    m = re.search(r"\(([A-Za-z]{2,4})\)", line)
    if m:
        team = m.group(1).upper()
        line = line[:m.start()] + line[m.end():]
    line = re.sub(r"(?<=\d),(?=\d)", ".", line)          # 17,5 -> 17.5
    toks = [t.strip() for t in re.split(r"[;,|\t]", line) if t.strip()]
    if len(toks) <= 1:
        toks = line.split()
    nums = [(_num(t), t) for t in toks]
    numbers = [n for n, _ in nums if n is not None]
    words = " ".join(t for n, t in nums if n is None).split()
    # statistika = najduzi kraj reci koji je poznat ("poeni 1p", "p+s+a", "poeni")
    stat, name_words = None, words
    for k in (3, 2, 1):
        if len(words) > k - 1 and len(words) >= k:
            cand = stat_key(" ".join(words[-k:]), extra)
            if cand and len(words) > k:
                stat, name_words = cand, words[:-k]
                break
    out = {"raw": raw.strip(), "name": " ".join(name_words), "team": team, "stat": stat,
           "line": numbers[0] if numbers else None,
           "over": numbers[1] if len(numbers) > 1 else None,
           "under": numbers[2] if len(numbers) > 2 else None}
    if not out["name"]:
        out["error"] = "player"
    elif not stat:
        out["error"] = "stat"
    elif out["line"] is None:
        out["error"] = "line"
    for k in ("over", "under"):        # kvota mora biti realna
        if out[k] is not None and not (1.01 <= out[k] <= 50):
            out[k] = None
    return out


def parse_text(text, extra=None):
    return [r for r in (parse_line(l, extra) for l in str(text).splitlines()) if r]


def match_player(name, roster, team=None):
    """roster: lista (pid, 'PREZIME, IME', tim, minuti). Vraca pid ili None."""
    want = [w for w in re.split(r"[\s,.\-]+", norm(name)) if w]
    if not want:
        return None
    best = []
    for pid, full, tm, mins in roster:
        last, _, first = full.partition(",")
        lw = [w for w in re.split(r"[\s\-]+", norm(last)) if w]
        fw = [w for w in re.split(r"[\s\-]+", norm(first)) if w]
        allw = lw + fw
        if not all(any(a == w or (len(w) >= 3 and a.startswith(w)) for a in allw) for w in want):
            continue
        has_last = any(w in lw for w in want) or norm(last).replace(" ", "") in "".join(want)
        best.append((has_last, team is not None and tm == team, mins, pid))
    if not best:
        # greska u kucanju: najslicnije prezime (npr. "Willliams-Goss" -> WILLIAMS-GOSS)
        from difflib import SequenceMatcher
        typed = "".join(want)
        scored = []
        for pid, full, tm, mins in roster:
            last, _, first = full.partition(",")
            l_ = re.sub(r"[^a-z]", "", norm(last))
            r = max(SequenceMatcher(None, typed, l_).ratio(),
                    SequenceMatcher(None, typed, l_ + re.sub(r"[^a-z]", "", norm(first))).ratio(),
                    SequenceMatcher(None, typed, re.sub(r"[^a-z]", "", norm(first)) + l_).ratio())
            scored.append((r, team is not None and tm == team, mins, pid))
        scored.sort(reverse=True)
        return scored[0][3] if scored and scored[0][0] >= 0.85 else None
    best.sort(reverse=True)
    return best[0][3]


# ---------- vrednost kvote / odds value ----------
def book_prob(over, under):
    """Sansa za Over iz kvota, bez marze kladionice (ako ima obe kvote)."""
    if over and under:
        po, pu = 1 / over, 1 / under
        return po / (po + pu)
    if over:
        return 1 / over
    if under:
        return 1 - 1 / under
    return None


def our_prob(hits, n, prior=2):
    """Procenat pogodaka ublazen ka 50%: (pogoci + 2) / (utakmice + 4)."""
    return (hits + prior) / (n + 2 * prior) if n else None


def ev(p, odd):
    """Ocekivani povrat po ulozenoj jedinici (0.10 = +10%)."""
    return p * odd - 1 if (p is not None and odd) else None
