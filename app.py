"""
Web aplikacija za Evroligu / Evrokup statistiku. / EuroLeague + EuroCup stats app.
Pokretanje / Run:  python -m streamlit run app.py
(app.py i euroleague_stats.py moraju biti u istom folderu)
"""
import contextlib
import io
from itertools import groupby

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import euroleague_stats as es

st.set_page_config(page_title="EuroStats", page_icon="📊", layout="wide")

KEYS = ["Points", "TotalRebounds", "Assistances", "Steals", "BlocksFavour", "Valuation", "Minutes"]
NAMES = {
    "sr": {"Points": "Poeni", "TotalRebounds": "Skokovi", "Assistances": "Asistencije",
           "Steals": "Ukradene", "BlocksFavour": "Blokade", "Valuation": "PIR", "Minutes": "Minuti"},
    "en": {"Points": "Points", "TotalRebounds": "Rebounds", "Assistances": "Assists",
           "Steals": "Steals", "BlocksFavour": "Blocks", "Valuation": "PIR", "Minutes": "Minutes"},
}
COLOR = {"Points": "#22c55e", "TotalRebounds": "#ef4444", "Assistances": "#3b82f6",
         "Steals": "#f59e0b", "BlocksFavour": "#a855f7", "Valuation": "#14b8a6", "Minutes": "#94a3b8"}
DOT = {"Points": "🟢", "TotalRebounds": "🔴", "Assistances": "🔵",
       "Steals": "🟠", "BlocksFavour": "🟣", "Valuation": "🟦", "Minutes": "⚪"}
# dodatne props statistike (izvedene kolone) / extra prop stats (derived columns)
COMBOS = {"PRA": ["Points", "TotalRebounds", "Assistances"], "PR": ["Points", "TotalRebounds"],
          "PA": ["Points", "Assistances"], "RA": ["TotalRebounds", "Assistances"]}
EXTRA_NAMES = {
    "sr": {"3PM": "Trojke (pogođene)", "PRA": "Poeni+Skokovi+Asist.", "PR": "Poeni+Skokovi",
           "PA": "Poeni+Asist.", "RA": "Skokovi+Asist.", "Turnovers": "Izgubljene",
           "3PA": "Trojke (pokušane)", "OffensiveRebounds": "Skokovi u napadu",
           "DefensiveRebounds": "Skokovi u odbrani", "FoulsCommited": "Faulovi",
           "PTS_Q1": "Poeni 1. četvrtina", "PTS_H1": "Poeni 1. poluvreme",
           "REB_H1": "Skokovi 1. poluvreme", "AST_H1": "Asist. 1. poluvreme",
           "PRA_H1": "P+S+A 1. poluvreme", "3PM_H1": "Trojke 1. poluvreme"},
    "en": {"3PM": "3-pointers made", "PRA": "Pts+Reb+Ast", "PR": "Pts+Reb",
           "PA": "Pts+Ast", "RA": "Reb+Ast", "Turnovers": "Turnovers",
           "3PA": "3-pointers attempted", "OffensiveRebounds": "Offensive rebounds",
           "DefensiveRebounds": "Defensive rebounds", "FoulsCommited": "Fouls",
           "PTS_Q1": "Points 1st quarter", "PTS_H1": "Points 1st half",
           "REB_H1": "Rebounds 1st half", "AST_H1": "Assists 1st half",
           "PRA_H1": "P+R+A 1st half", "3PM_H1": "3PM 1st half"},
}
# podrazumevane linije za skener / default scanner lines
DEFAULT_LINE = {"Points": 12.5, "TotalRebounds": 5.5, "Assistances": 3.5, "Steals": 0.5,
                "BlocksFavour": 0.5, "Valuation": 12.5, "3PM": 1.5, "PRA": 20.5, "PR": 16.5,
                "PA": 15.5, "RA": 8.5, "Turnovers": 1.5, "3PA": 3.5, "OffensiveRebounds": 1.5,
                "DefensiveRebounds": 3.5, "FoulsCommited": 2.5, "PTS_Q1": 2.5, "PTS_H1": 5.5,
                "REB_H1": 2.5, "AST_H1": 1.5, "PRA_H1": 10.5, "3PM_H1": 0.5}
LIGE = {"E": ["E"], "U": ["U"]}
COMP_NAME = {"sr": {"E": "Evroliga", "U": "Evrokup"}, "en": {"E": "EuroLeague", "U": "EuroCup"}}

T = {
    "sr": {
        "settings": "⚙️ Podešavanja / Settings", "language": "Jezik / Language",
        "league": "Liga", "season": "Sezona {a}/{b}",
        "refresh": "🔄 Osveži podatke", "spinner": "Povlačim nove utakmice...",
        "done": "Gotovo", "details": "Detalji", "no_output": "Nema ispisa",
        "hero_sub": "{liga} · sezona {a}/{b} · statistika igrača posle svake utakmice",
        "no_data": "Još nema podataka. Klikni **Osveži podatke** u meniju levo.",
        "counts": "{g} odigranih utakmica, {p} igrača",
        "tab_player": "👤 Igrač", "tab_leaders": "🏆 Lideri", "tab_props": "🎯 Props",
        "search": "Traži igrača (kucaj prezime)", "placeholder": "npr. Vezenkov",
        "averages": "Proseci u {n} utakmica", "last_short": "posl.",
        "last_help": "Razlika poslednje utakmice u odnosu na prosek",
        "chart_by_game": "Grafikon po utakmicama",
        "opponent": "Protivnik", "statistic": "Statistika", "value": "Vrednost",
        "min_games": "Min. utakmica", "view": "Prikaz", "avg": "Prosek", "total": "Ukupno",
        "gp": "Utakm.", "player": "Igrač", "team": "Tim",
        "props_note": "Statistički prikaz istorijskih podataka. Nije savet za klađenje.",
        "line": "Margina (Over/Under)", "venue": "Teren",
        "all": "Svi", "all_f": "Sve", "home": "Kuća", "away": "Gost",
        "no_games": "Nema utakmica za izabrane filtere.",
        "last_n": "Poslednjih {n}", "n_games": "{o}/{t} utakmica", "season_lbl": "Sezona",
        "streak": "Trenutni niz", "avg_n": "prosek {x}",
        "game_axis": "Utakmica (od najstarije)", "result": "Rezultat",
        "home_away": "Kuća / Gost", "by_opp": "Po protivniku",
        "no_home": "Obriši euroleague.db i pokreni update da bi se sačuvao podatak o domaćinu.",
    },
    "en": {
        "settings": "⚙️ Podešavanja / Settings", "language": "Jezik / Language",
        "league": "League", "season": "Season {a}/{b}",
        "refresh": "🔄 Refresh data", "spinner": "Fetching new games...",
        "done": "Done", "details": "Details", "no_output": "No output",
        "hero_sub": "{liga} · season {a}/{b} · player stats after every game",
        "no_data": "No data yet. Click **Refresh data** in the sidebar.",
        "counts": "{g} games played, {p} players",
        "tab_player": "👤 Player", "tab_leaders": "🏆 Leaders", "tab_props": "🎯 Props",
        "search": "Search player (type surname)", "placeholder": "e.g. Vezenkov",
        "averages": "Averages over {n} games", "last_short": "last",
        "last_help": "Last game vs. average",
        "chart_by_game": "Chart by game",
        "opponent": "Opponent", "statistic": "Statistic", "value": "Value",
        "min_games": "Min. games", "view": "View", "avg": "Average", "total": "Total",
        "gp": "GP", "player": "Player", "team": "Team",
        "props_note": "Statistical view of historical data. Not betting advice.",
        "line": "Line (Over/Under)", "venue": "Venue",
        "all": "All", "all_f": "All", "home": "Home", "away": "Away",
        "no_games": "No games match the selected filters.",
        "last_n": "Last {n}", "n_games": "{o}/{t} games", "season_lbl": "Season",
        "streak": "Current streak", "avg_n": "avg {x}",
        "game_axis": "Game (oldest first)", "result": "Result",
        "home_away": "Home / Away", "by_opp": "By opponent",
        "no_home": "Delete euroleague.db and run update to store the home/away info.",
    },
}
T2 = {
    "sr": {
        "tab_scan": "🔎 Skener", "tab_teams": "🛡️ Timovi", "tab_cmp": "⚖️ Poređenje", "tab_round": "⭐ Pregled kola", "tab_without": "🔄 Bez saigrača",
        "shooting": "Šut", "minutes_h": "Minuti i faulovi", "tpa": "3PA po utakm.",
        "min_avg": "Minuti (prosek)", "min_l3": "Minuti (posl. 3)", "per36": "Poeni na 36 min",
        "foul4": "Utakmice sa 4+ faula", "min_chart": "Minuti po utakmici", "rolling": "Prosek posl. 3",
        "download": "⬇️ Preuzmi CSV",
        "opp_allows": "Protivnik prima", "opp_rank": "Rang odbrane",
        "opp_rank_help": "1 = protivnik prima najviše (najlakši za Over)",
        "scan_note": "Svi igrači za izabranu statistiku i liniju, sortirani po procentu pogodaka.",
        "side": "Strana", "window": "Sortiraj po", "min_minutes": "Min. prosek minuta",
        "l5p": "Posl. 5 %", "l10p": "Posl. 10 %", "seasp": "Sezona %", "streak_s": "Niz",
        "no_players": "Nema igrača za ove filtere.",
        "scored": "Daje", "allowed": "Prima", "diff": "Razlika", "record": "P-I",
        "home_rec": "Kuća P-I", "away_rec": "Gost P-I",
        "allowed_chart": "Koliko timovi primaju po utakmici: {s}",
        "teams_note": "Prima = koliko protivnici tog tima ostvare po utakmici. "
                      "Visoka vrednost = slabija odbrana za taj prop.",
        "p1": "Igrač 1", "p2": "Igrač 2", "cmp_trend": "{s} po utakmici", "game_n": "Utakmica br.",
        "cmp_pick": "Izaberi dva igrača za poređenje.",
        "tab_sched": "📅 Raspored", "round": "Kolo", "date": "Datum", "time": "Vreme",
        "match": "Meč", "res_time": "Rezultat / vreme", "home_allows": "Domaćin prima",
        "away_allows": "Gost prima", "rest": "Odmor (dani)",
        "sched_note": "Uz svaki meč: koliko domaćin i gost primaju za izabranu statistiku "
                      "(u zagradi rang, #1 = prima najviše).",
        "no_sched": "Raspored još nije učitan. Klikni **Osveži podatke** u meniju levo.",
        "next_game": "📅 Sledeća utakmica: **{opp}** ({ha}) · {d} {t} · {opp} prima **{v}** {s} "
                     "po utakmici (rang **{r}/{n}**)",
        "use_next": "Filtriraj na sledećeg protivnika", "next_none": "Nema zakazanih utakmica.",
    },
    "en": {
        "tab_scan": "🔎 Scanner", "tab_teams": "🛡️ Teams", "tab_cmp": "⚖️ Compare", "tab_round": "⭐ Round preview", "tab_without": "🔄 Without teammate",
        "shooting": "Shooting", "minutes_h": "Minutes & fouls", "tpa": "3PA per game",
        "min_avg": "Minutes (avg)", "min_l3": "Minutes (last 3)", "per36": "Points per 36",
        "foul4": "Games with 4+ fouls", "min_chart": "Minutes by game", "rolling": "Last-3 average",
        "download": "⬇️ Download CSV",
        "opp_allows": "Opponent allows", "opp_rank": "Defense rank",
        "opp_rank_help": "1 = opponent allows the most (easiest for Over)",
        "scan_note": "All players for the chosen stat and line, sorted by hit rate.",
        "side": "Side", "window": "Sort by", "min_minutes": "Min. avg minutes",
        "l5p": "Last 5 %", "l10p": "Last 10 %", "seasp": "Season %", "streak_s": "Streak",
        "no_players": "No players match these filters.",
        "scored": "Scores", "allowed": "Allows", "diff": "Diff", "record": "W-L",
        "home_rec": "Home W-L", "away_rec": "Away W-L",
        "allowed_chart": "What teams allow per game: {s}",
        "teams_note": "Allows = what that team's opponents produce per game. "
                      "High value = weaker defense for that prop.",
        "p1": "Player 1", "p2": "Player 2", "cmp_trend": "{s} by game", "game_n": "Game #",
        "cmp_pick": "Pick two players to compare.",
        "tab_sched": "📅 Schedule", "round": "Round", "date": "Date", "time": "Time",
        "match": "Game", "res_time": "Result / time", "home_allows": "Home allows",
        "away_allows": "Away allows", "rest": "Rest (days)",
        "sched_note": "For each game: what the home and away team allow for the chosen stat "
                      "(rank in brackets, #1 = allows the most).",
        "no_sched": "Schedule not loaded yet. Click **Refresh data** in the sidebar.",
        "next_game": "📅 Next game: **{opp}** ({ha}) · {d} {t} · {opp} allows **{v}** {s} "
                     "per game (rank **{r}/{n}**)",
        "use_next": "Filter on next opponent", "next_none": "No scheduled games.",
    },
}
T3 = {
    "sr": {
        "median": "Medijana", "min": "Najmanje", "max": "Najviše", "spread": "Varijacija (±)",
        "spread_help": "Standardna devijacija: koliko igrač prosečno odstupa od proseka",
        "by_rest": "Po odmoru", "rest_short": "1–2 dana", "rest_long": "3+ dana",
        "efficiency": "Efikasnost", "ts": "TS%", "efg": "eFG%", "ast_to": "Asist./izgubljene",
        "ts_help": "Šut uključujući slobodna bacanja: poeni / (2 × (šutevi + 0.44 × bacanja))",
        "efg_help": "Šut iz igre gde trojka vredi 1.5 puta više",
        "form": "🔥 Ko je u formi", "form_up": "Iznad proseka", "form_down": "Ispod proseka",
        "last3": "Posl. 3", "season_avg": "Sezona",
        "form_note": "Prosek poslednje 3 utakmice u odnosu na celu sezonu (min. 4 utakmice).",
        "absent": "Igrač koji ne igra", "with": "Sa njim", "without": "Bez njega",
        "gp_with": "Utakm. sa", "gp_without": "Utakm. bez",
        "without_note": "Izostanak = igrač nije u zapisniku utakmice svog tima. "
                        "Ako je došao u tim tokom sezone, ranije utakmice se računaju kao izostanak.",
        "no_absence": "{p} je odigrao sve utakmice svog tima – nema poređenja.",
        "round_note": "Igrači iz sledećeg kola sa visokim procentom za izabranu liniju, "
                      "protiv protivnika koji je slab (Over) ili jak (Under) za tu statistiku.",
        "min_hit": "Min. % (posl. 5)", "top_def": "Rang protivnika do",
        "top_def_help": "Over: protivnik je među N koji najviše primaju. Under: među N koji najmanje primaju.",
        "opp_rank_s": "Rang prot.", "no_round": "Nema igrača za ove filtere u sledećem kolu.",
        "by_quarter": "Po četvrtinama (prosek)", "quarter": "Četvrtina", "ot": "Produžeci",
        "shot_map": "Mapa šuteva", "made": "Pogođen", "missed": "Promašen", "zone": "Zona",
        "z_paint": "Reket", "z_mid": "Srednja distanca", "z_corner": "Trojka iz ugla",
        "z_above": "Trojka (luk)", "att": "Pokušaji", "made_n": "Pogođeno", "share": "Udeo",
        "no_extra": "Podaci po četvrtinama i šutevi još nisu preuzeti. Klikni **Osveži podatke** "
                    "(prvi put traje duže).",
        "standings": "🏅 Tabela lige", "pos": "#", "won": "P", "lost": "I", "last5": "Posl. 5",
        "pdiff": "Koš razlika", "no_standings": "Tabela trenutno nije dostupna.",
    },
    "en": {
        "median": "Median", "min": "Min", "max": "Max", "spread": "Spread (±)",
        "spread_help": "Standard deviation: how far the player typically is from his average",
        "by_rest": "By rest", "rest_short": "1–2 days", "rest_long": "3+ days",
        "efficiency": "Efficiency", "ts": "TS%", "efg": "eFG%", "ast_to": "Ast/TO",
        "ts_help": "Shooting incl. free throws: points / (2 × (FGA + 0.44 × FTA))",
        "efg_help": "Field-goal % where a three counts 1.5 times",
        "form": "🔥 Who's in form", "form_up": "Above average", "form_down": "Below average",
        "last3": "Last 3", "season_avg": "Season",
        "form_note": "Last-3-games average vs. the full season (min. 4 games).",
        "absent": "Player who sits out", "with": "With him", "without": "Without him",
        "gp_with": "GP with", "gp_without": "GP without",
        "without_note": "Absence = the player is not in his team's box score. "
                        "If he joined mid-season, earlier games count as absences.",
        "no_absence": "{p} played every game for his team – nothing to compare.",
        "round_note": "Players in the next round with a high hit rate for the chosen line, "
                      "facing an opponent that is weak (Over) or strong (Under) for that stat.",
        "min_hit": "Min. % (last 5)", "top_def": "Opponent rank up to",
        "top_def_help": "Over: opponent is among the N that allow the most. Under: among the N that allow the least.",
        "opp_rank_s": "Opp. rank", "no_round": "No players match these filters in the next round.",
        "by_quarter": "By quarter (average)", "quarter": "Quarter", "ot": "Overtime",
        "shot_map": "Shot chart", "made": "Made", "missed": "Missed", "zone": "Zone",
        "z_paint": "Paint", "z_mid": "Mid-range", "z_corner": "Corner three",
        "z_above": "Three (arc)", "att": "Attempts", "made_n": "Made", "share": "Share",
        "no_extra": "Quarter and shot data not downloaded yet. Click **Refresh data** "
                    "(first time takes longer).",
        "standings": "🏅 Standings", "pos": "#", "won": "W", "lost": "L", "last5": "Last 5",
        "pdiff": "Point diff", "no_standings": "Standings are not available right now.",
    },
}
for _l in T:
    T[_l].update(T2[_l])
    T[_l].update(T3[_l])

LOGO = (
    '<svg width="{s}" height="{s}" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="44" height="44" rx="12" fill="#0f172a"/>'
    '<rect x="9" y="22" width="6" height="13" rx="2" fill="#22c55e"/>'
    '<rect x="19" y="14" width="6" height="21" rx="2" fill="#ef4444"/>'
    '<rect x="29" y="8" width="6" height="27" rx="2" fill="#3b82f6"/>'
    '<polyline points="8,20 18,13 28,16 37,6" fill="none" stroke="#f59e0b" '
    'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
.stApp {font-family: 'Inter', sans-serif;}
.block-container {padding-top: 4.5rem; max-width: 1200px;}
footer {visibility: hidden;}

.hero {display: flex; align-items: center; gap: 18px; padding: 22px 26px; margin-bottom: 1.2rem;
       border-radius: 20px; color: #fff;
       background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%);
       box-shadow: 0 8px 24px rgba(15, 23, 42, 0.25);}
.hero-title {font-size: 2.1rem; font-weight: 800; letter-spacing: -0.5px; line-height: 1.1; color: #fff;}
.hero-title span {color: #f59e0b;}
.hero-sub {color: #cbd5e1; font-size: 0.95rem; margin-top: 4px;}
.side-logo {display: flex; align-items: center; gap: 10px; font-size: 1.35rem; font-weight: 800;
            margin-bottom: 0.6rem;}
.side-logo span b {color: #f59e0b;}

[data-testid="stMetric"] {background: rgba(128,128,128,0.08); border: 1px solid rgba(128,128,128,0.22);
    border-radius: 16px; padding: 14px 16px; transition: transform .15s ease, box-shadow .15s ease;}
[data-testid="stMetric"]:hover {transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12);}
[data-testid="stMetricValue"] {font-weight: 800;}

button[data-baseweb="tab"] {font-size: 1.05rem; font-weight: 600; border-radius: 10px 10px 0 0;}
div[data-baseweb="tab-highlight"] {background-color: #f59e0b;}
.stButton > button {border-radius: 12px; font-weight: 600; border: 1px solid rgba(245,158,11,0.7);}
.stButton > button:hover {border-color: #f59e0b; color: #f59e0b;}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {border-radius: 12px;}
[data-testid="stDataFrame"] {border-radius: 14px; overflow: hidden;
    border: 1px solid rgba(128,128,128,0.22);}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,0.22);}
/* grafikoni ne hvataju vertikalni skrol na telefonu / charts don't capture vertical scroll */
.vega-embed, .vega-embed canvas, .vega-embed svg {touch-action: pan-y !important;}

@media (max-width: 640px) {
  .block-container {padding: 4.5rem 0.8rem 3rem;}   /* ispod Streamlit trake (Share/Fork) */
  .hero {padding: 14px 16px; gap: 12px; border-radius: 16px;}
  .hero svg {width: 40px; height: 40px;}
  .hero-title {font-size: 1.5rem;}
  .hero-sub {font-size: 0.8rem;}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {flex-wrap: wrap; gap: 0.6rem;}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="column"] {
      flex: 1 1 calc(50% - 0.6rem) !important; min-width: calc(50% - 0.6rem) !important;}
  [data-testid="stMetric"] {padding: 10px 12px;}
  [data-testid="stMetricValue"] {font-size: 1.5rem;}
  button[data-baseweb="tab"] {font-size: 0.9rem; padding: 0.4rem 0.6rem;}
  /* traka desno od tabele za skrolovanje stranice palcem / strip beside tables for page scroll */
  [data-testid="stDataFrame"] {width: calc(100% - 32px) !important; max-width: calc(100% - 32px) !important;}
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load(comps: tuple) -> pd.DataFrame:
    df = es.load_df(list(comps))
    if df.empty:
        return df
    for name, parts in COMBOS.items():
        if all(p in df.columns for p in parts):
            df[name] = df[parts].sum(axis=1)
    if "FieldGoalsMade3" in df.columns:
        df["3PM"] = df["FieldGoalsMade3"]
    if "FieldGoalsAttempted3" in df.columns:
        df["3PA"] = df["FieldGoalsAttempted3"]
    pairs = df[["comp", "gamecode", "team"]].drop_duplicates()
    opp = pairs.merge(pairs, on=["comp", "gamecode"], suffixes=("", "_o"))
    opp = opp[opp["team"] != opp["team_o"]].rename(columns={"team_o": "opp"})
    return df.merge(opp, on=["comp", "gamecode", "team"], how="left")


# ---------- sidebar ----------
st.sidebar.markdown(
    f'<div class="side-logo">{LOGO.format(s=34)}<span>Euro<b>Stats</b></span></div>',
    unsafe_allow_html=True)
with st.sidebar.expander("⚙️ Podešavanja / Settings"):
    lang_name = st.radio("Jezik / Language", ["Srpski", "English"], horizontal=True)
lang = "sr" if lang_name == "Srpski" else "en"


def tr(key, **kw):
    return T[lang][key].format(**kw)


liga_code = st.sidebar.radio(tr("league"), list(LIGE), format_func=lambda c: COMP_NAME[lang][c])
comps = LIGE[liga_code]
liga = COMP_NAME[lang][liga_code]
season_a, season_b = es.SEASON, str(es.SEASON + 1)[-2:]
st.sidebar.caption(tr("season", a=season_a, b=season_b))

if st.sidebar.button(tr("refresh"), width="stretch"):
    buf = io.StringIO()
    with st.spinner(tr("spinner")), contextlib.redirect_stdout(buf):
        es.update(comps)
    st.cache_data.clear()
    st.sidebar.success(tr("done"))
    with st.sidebar.expander(tr("details")):
        st.code(buf.getvalue() or tr("no_output"))

df = load(tuple(comps))
hero_sub = tr("hero_sub", liga=liga, a=season_a, b=season_b)
st.markdown(
    f'<div class="hero">{LOGO.format(s=56)}<div><div class="hero-title">Euro<span>Stats</span></div>'
    f'<div class="hero-sub">{hero_sub}</div></div></div>',
    unsafe_allow_html=True)

if df.empty:
    st.info(tr("no_data"))
    st.stop()

@st.cache_data(ttl=3600)
def load_sched(comps: tuple) -> pd.DataFrame:
    """Raspored iz baze; ako ga nema (npr. nova baza), pokusa jednom da ga povuce."""
    try:
        s = es.load_schedule(list(comps))
        if s.empty:
            for c in comps:
                with contextlib.redirect_stdout(io.StringIO()):
                    es.update_schedule(c)
            s = es.load_schedule(list(comps))
        return s
    except Exception:
        return pd.DataFrame()


sched = load_sched(tuple(comps))
if not sched.empty:
    df = df.merge(sched[["comp", "gamecode", "date"]], on=["comp", "gamecode"], how="left")
else:
    df["date"] = pd.NaT


@st.cache_data(ttl=300)
def load_periods(comps: tuple) -> pd.DataFrame:
    try:
        return es.load_periods(list(comps))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_shots(comps: tuple) -> pd.DataFrame:
    try:
        s = es.load_shots(list(comps))
        s["player_id"] = s["player_id"].str.strip()
        return s
    except Exception:
        return pd.DataFrame()


periods = load_periods(tuple(comps))
if not periods.empty:
    periods["player_id"] = periods["player_id"].str.strip()
    grp = ["comp", "gamecode", "player_id"]
    q1 = periods[periods["period"] == 1].groupby(grp)[["PTS"]].sum().rename(columns={"PTS": "PTS_Q1"})
    h1 = periods[periods["period"] <= 2].groupby(grp)[["PTS", "REB", "AST", "FG3M"]].sum()
    h1 = h1.rename(columns={"PTS": "PTS_H1", "REB": "REB_H1", "AST": "AST_H1", "FG3M": "3PM_H1"})
    h1["PRA_H1"] = h1["PTS_H1"] + h1["REB_H1"] + h1["AST_H1"]
    per_g = q1.join(h1, how="outer").reset_index()
    pbp_games = set(zip(periods["comp"], periods["gamecode"]))
    df["_pid"] = df["player_id"].str.strip()
    df = df.merge(per_g.rename(columns={"player_id": "_pid"}), on=["comp", "gamecode", "_pid"], how="left")
    has_pbp = [(c, gc) in pbp_games for c, gc in zip(df["comp"], df["gamecode"])]
    per_cols = ["PTS_Q1", "PTS_H1", "REB_H1", "AST_H1", "PRA_H1", "3PM_H1"]
    df.loc[has_pbp, per_cols] = df.loc[has_pbp, per_cols].fillna(0)   # bez akcija u pbp = 0
shots = load_shots(tuple(comps))
SORT = ["date", "gamecode"]
played_codes = set(zip(df["comp"], df["gamecode"]))


def date_lbl(d, opp):
    return f"{d:%d.%m.} {opp}" if pd.notna(d) else opp


stats = {k: NAMES[lang][k] for k in KEYS if k in df.columns}   # kljuc -> prikazani naziv
inv = {v: k for k, v in stats.items()}                          # prikazani naziv -> kljuc
stat_keys = [k for k in stats if k != "Minutes"]
opp_c, stat_c, val_c, res_c = tr("opponent"), tr("statistic"), tr("value"), tr("result")
st.caption(tr("counts", g=df["gamecode"].nunique(), p=df["player_id"].nunique()))

# ---------- zajednicko / shared ----------
players = (df.groupby(["comp", "player_id", "player", "team"]).size()
             .reset_index(name="n").sort_values("player"))
players["label"] = (players["player"] + "  (" + players["team"] + ", "
                    + players["comp"].map(COMP_NAME[lang]) + ")")

prop_stats = {k: stats[k] for k in stat_keys}
prop_stats.update({k: v for k, v in EXTRA_NAMES[lang].items() if k in df.columns})
prop_inv = {v: k for k, v in prop_stats.items()}


def player_games(label):
    r = players[players["label"] == label].iloc[0]
    g = (df[(df["comp"] == r["comp"]) & (df["player_id"] == r["player_id"])]
         .sort_values(SORT).reset_index(drop=True))
    g["rest"] = g["date"].diff().dt.days.astype("Int64")
    return r, g


def next_game(comp, team):
    """Prva neodigrana utakmica tima / team's next unplayed game."""
    if sched.empty:
        return None
    s = sched[(sched["comp"] == comp) & ((sched["homecode"] == team) | (sched["awaycode"] == team))]
    s = s[[(comp, gc) not in played_codes for gc in s["gamecode"]]]
    s = s[s["played"] == 0].sort_values(["date", "startime"])
    if s.empty:
        return None
    n = s.iloc[0]
    home = n["homecode"] == team
    return {"opp": n["awaycode"] if home else n["homecode"], "home": home,
            "date": n["date"], "time": n["startime"]}


def hit_rate(vals, line, side="Over"):
    vals = vals.dropna()
    n = len(vals)
    o = int((vals > line).sum() if side == "Over" else (vals < line).sum())
    return o, n


def pct(made, att):
    return f"{100 * made / att:.0f}%" if att else "—"


def csv_button(frame, name, key):
    st.download_button(tr("download"), frame.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{name}.csv", mime="text/csv", key=key)


@st.cache_data(ttl=300)
def team_games(frame: pd.DataFrame) -> pd.DataFrame:
    """Jedan red po timu po utakmici: sta je dao (k) i sta je primio (k_a)."""
    cols = [k for k in prop_stats if k in frame.columns]
    grp = frame.groupby(["comp", "gamecode", "team"])
    tg = grp[cols].sum(min_count=1)          # NaN ostaje NaN (npr. nema play-by-play)
    if "Home" in frame.columns:
        tg["Home"] = grp["Home"].max()
    tg = tg.reset_index()
    tg = tg.merge(tg[["comp", "gamecode", "team"] + cols], on=["comp", "gamecode"], suffixes=("", "_a"))
    tg = tg[tg["team"] != tg["team_a"]].rename(columns={"team_a": "opp"})
    tg["win"] = tg["Points"] > tg["Points_a"]
    return tg


tgames = team_games(df)


def court_lines():
    """Linije polovine terena (FIBA, cm), kos u (0, 0)."""
    segs, base, top = [], -157.5, 1000
    def add(name, xs, ys):
        segs.extend({"seg": name, "i": i, "x": x, "y": y} for i, (x, y) in enumerate(zip(xs, ys)))
    add("outer", [-750, -750, 750, 750, -750], [top, base, base, top, top])
    add("paint", [-245, -245, 245, 245], [base, 422.5, 422.5, base])
    t = np.linspace(0, np.pi, 40)
    add("ft", 180 * np.cos(t), 422.5 + 180 * np.sin(t))
    a0 = np.arcsin(141.5 / 675)
    t = np.linspace(a0, np.pi - a0, 80)
    add("three", np.r_[660, 675 * np.cos(t), -660], np.r_[base, 675 * np.sin(t), base])
    t = np.linspace(0, 2 * np.pi, 30)
    add("rim", 22.5 * np.cos(t), 22.5 * np.sin(t))
    add("board", [-90, 90], [-37.5, -37.5])
    t = np.linspace(0, np.pi, 30)
    add("ra", 125 * np.cos(t), 125 * np.sin(t))
    return pd.DataFrame(segs)


def shot_zone(r):
    if str(r["action"]).startswith("3"):
        return tr("z_corner") if r["y"] < 141.5 else tr("z_above")
    return tr("z_paint") if abs(r["x"]) <= 245 and r["y"] <= 422.5 else tr("z_mid")


def wl(x):
    return f"{int(x.sum())}-{int((~x).sum())}"


TAB_KEYS = ["player", "leaders", "props", "round", "scan", "sched", "teams", "without", "cmp"]
TAB = dict(zip(TAB_KEYS, st.tabs([tr(f"tab_{k}") for k in TAB_KEYS])))

# ---------- igrac / player ----------
with TAB["player"]:
    choice = st.selectbox(tr("search"), players["label"], index=None,
                          placeholder=tr("placeholder"))
    if choice:
        row, g = player_games(choice)
        st.subheader(f"{row['player']} – {row['team']}")
        st.caption(tr("averages", n=len(g)))

        cols = st.columns(len(stat_keys))
        for c, k in zip(cols, stat_keys):
            last = g[k].iloc[-1]
            c.metric(f"{DOT[k]} {stats[k]}", f"{g[k].mean():.1f}",
                     f"{last - g[k].mean():+.1f} ({tr('last_short')})", help=tr("last_help"))

        # sut / shooting
        st.markdown(f"**{tr('shooting')}**")
        s = g.sum(numeric_only=True)
        c = st.columns(4)
        c[0].metric("2P%", pct(s.get("FieldGoalsMade2", 0), s.get("FieldGoalsAttempted2", 0)),
                    f"{s.get('FieldGoalsMade2', 0):.0f}/{s.get('FieldGoalsAttempted2', 0):.0f}",
                    delta_color="off")
        c[1].metric("3P%", pct(s.get("FieldGoalsMade3", 0), s.get("FieldGoalsAttempted3", 0)),
                    f"{s.get('FieldGoalsMade3', 0):.0f}/{s.get('FieldGoalsAttempted3', 0):.0f}",
                    delta_color="off")
        c[2].metric("FT%", pct(s.get("FreeThrowsMade", 0), s.get("FreeThrowsAttempted", 0)),
                    f"{s.get('FreeThrowsMade', 0):.0f}/{s.get('FreeThrowsAttempted', 0):.0f}",
                    delta_color="off")
        c[3].metric(tr("tpa"), f"{g['3PA'].mean():.1f}" if "3PA" in g else "—")

        # efikasnost / efficiency
        st.markdown(f"**{tr('efficiency')}**")
        fga = s.get("FieldGoalsAttempted2", 0) + s.get("FieldGoalsAttempted3", 0)
        fta = s.get("FreeThrowsAttempted", 0)
        c = st.columns(3)
        c[0].metric(tr("ts"), pct(s["Points"], 2 * (fga + 0.44 * fta)), help=tr("ts_help"))
        c[1].metric(tr("efg"), pct(s.get("FieldGoalsMade2", 0) + 1.5 * s.get("FieldGoalsMade3", 0), fga),
                    help=tr("efg_help"))
        tov = s.get("Turnovers", 0)
        c[2].metric(tr("ast_to"), f"{s['Assistances'] / tov:.1f}" if tov else "—",
                    f"{s['Assistances']:.0f}/{tov:.0f}", delta_color="off")

        # minuti i faulovi / minutes & fouls
        st.markdown(f"**{tr('minutes_h')}**")
        c = st.columns(4)
        c[0].metric(tr("min_avg"), f"{g['Minutes'].mean():.1f}")
        l3 = g["Minutes"].tail(3).mean()
        c[1].metric(tr("min_l3"), f"{l3:.1f}", f"{l3 - g['Minutes'].mean():+.1f}")
        c[2].metric(tr("per36"), f"{36 * s['Points'] / s['Minutes']:.1f}" if s["Minutes"] else "—")
        if "FoulsCommited" in g:
            n4 = int((g["FoulsCommited"] >= 4).sum())
            c[3].metric(tr("foul4"), f"{100 * n4 / len(g):.0f}%",
                        tr("n_games", o=n4, t=len(g)), delta_color="off")

        g[opp_c] = [date_lbl(d, o) for d, o in zip(g["date"], g["opp"].fillna("?"))]
        names = g[opp_c] + g[opp_c].groupby(g[opp_c]).cumcount().map(
            lambda n: "" if n == 0 else f" ({n + 1})")
        g[opp_c] = names
        md = g.assign(**{tr("rolling"): g["Minutes"].rolling(3, min_periods=1).mean()})
        base = alt.Chart(md).encode(x=alt.X(f"{opp_c}:N", sort=list(g[opp_c]), title=None,
                                            axis=alt.Axis(labelAngle=-45)))
        st.altair_chart(
            base.mark_bar(color=COLOR["Minutes"], opacity=0.6).encode(
                y=alt.Y("Minutes:Q", title=tr("min_chart")),
                tooltip=[opp_c, alt.Tooltip("Minutes:Q", format=".1f")])
            + base.mark_line(color="#f59e0b", point=True).encode(
                y=f"{tr('rolling')}:Q",
                tooltip=[opp_c, alt.Tooltip(f"{tr('rolling')}:Q", format=".1f")]),
            width="stretch")

        pick = st.multiselect(tr("chart_by_game"), [stats[k] for k in stat_keys],
                              default=[stats[k] for k in ("Points", "TotalRebounds", "Assistances") if k in stats])
        if pick:
            long = (g[[opp_c] + [inv[p] for p in pick]].rename(columns=stats)
                    .melt(id_vars=opp_c, var_name=stat_c, value_name=val_c))
            chart = alt.Chart(long).mark_bar().encode(
                x=alt.X(f"{opp_c}:N", sort=list(g[opp_c]), title=None,
                        axis=alt.Axis(labelAngle=-45)),
                xOffset=f"{stat_c}:N",
                y=alt.Y(f"{val_c}:Q", title=None),
                color=alt.Color(f"{stat_c}:N", title=None,
                                scale=alt.Scale(domain=pick, range=[COLOR[inv[p]] for p in pick])),
                tooltip=[opp_c, stat_c, val_c])
            st.altair_chart(chart, width="stretch")

        log = g[[opp_c] + list(stats) + ["rest"]].rename(columns={**stats, "rest": tr("rest")}).round(1)
        st.dataframe(log, hide_index=True, width="stretch", height=min(300, 38 + 35 * len(g)))
        csv_button(log, row["player"], "dl_player")

        # po cetvrtinama / by quarter
        pid = str(row["player_id"]).strip()
        pp = periods[(periods["comp"] == row["comp"]) & (periods["player_id"] == pid)] \
            if not periods.empty else pd.DataFrame()
        st.markdown(f"**{tr('by_quarter')}**")
        if periods.empty:
            st.caption(tr("no_extra"))
        else:
            n_pbp = len({gc for c, gc in pbp_games if c == row["comp"]} & set(g["gamecode"]))
            if n_pbp and not pp.empty:
                q = pp.assign(_q=np.where(pp["period"] <= 4, "Q" + pp["period"].astype(str), tr("ot")))
                qt = (q.groupby("_q")[["PTS", "REB", "AST", "FG3M"]].sum() / n_pbp).round(1)
                order = ["Q1", "Q2", "Q3", "Q4"] + ([tr("ot")] if tr("ot") in qt.index else [])
                qt = qt.reindex(order, fill_value=0)
                qt = qt.rename(columns={"PTS": stats["Points"], "REB": stats["TotalRebounds"],
                                        "AST": stats["Assistances"], "FG3M": EXTRA_NAMES[lang]["3PM"]})
                qt.index.name = tr("quarter")
                st.dataframe(qt, width="stretch")

        # mapa suteva / shot chart
        st.markdown(f"**{tr('shot_map')}**")
        ps = shots[(shots["comp"] == row["comp"]) & (shots["player_id"] == pid)] \
            if not shots.empty else pd.DataFrame()
        if shots.empty:
            st.caption(tr("no_extra"))
        elif not ps.empty:
            ps = ps.assign(**{res_c: np.where(ps["action"].str.endswith("M"), tr("made"), tr("missed"))})
            ps[tr("zone")] = ps.apply(shot_zone, axis=1)
            court = alt.Chart(court_lines()).mark_line(color="#64748b", strokeWidth=1.5).encode(
                x=alt.X("x:Q", scale=alt.Scale(domain=[-760, 760], nice=False), axis=None),
                y=alt.Y("y:Q", scale=alt.Scale(domain=[-170, 1000], nice=False), axis=None),
                detail="seg:N", order="i:Q")
            dots = alt.Chart(ps).mark_point(filled=True, size=70, opacity=0.85).encode(
                x="x:Q", y="y:Q",
                color=alt.Color(f"{res_c}:N", title=None, legend=alt.Legend(orient="top"),
                                scale=alt.Scale(domain=[tr("made"), tr("missed")], range=["#22c55e", "#ef4444"])),
                shape=alt.Shape(f"{res_c}:N", legend=None,
                                scale=alt.Scale(domain=[tr("made"), tr("missed")], range=["circle", "cross"])),
                tooltip=[tr("zone"), res_c, alt.Tooltip("minute:Q", title="Min")])
            st.altair_chart((court + dots).properties(width=340, height=262), width="content")
            zt = ps.groupby(tr("zone")).agg(**{tr("att"): (res_c, "size"),
                                              tr("made_n"): (res_c, lambda x: int((x == tr("made")).sum()))})
            zt["%"] = (100 * zt[tr("made_n")] / zt[tr("att")]).round().astype(int).astype(str) + "%"
            zt[tr("share")] = (100 * zt[tr("att")] / zt[tr("att")].sum()).round().astype(int).astype(str) + "%"
            st.dataframe(zt, width="stretch")

# ---------- lideri / leaders ----------
with TAB["leaders"]:
    c1, c2, c3 = st.columns(3)
    stat_name = c1.selectbox(stat_c, list(stats.values()))
    min_games = c2.slider(tr("min_games"), 1, max(1, int(df.groupby("player_id").size().max())), 3)
    mode = c3.radio(tr("view"), [tr("avg"), tr("total")], horizontal=True)
    key = inv[stat_name]
    agg = "mean" if mode == tr("avg") else "sum"
    for comp in comps:
        d = df[df["comp"] == comp]
        if d.empty:
            continue
        t = (d.groupby(["player_id", "player", "team"])[key]
               .agg([agg, "count"]).reset_index()
               .rename(columns={agg: stat_name, "count": tr("gp")}))
        t = t[t[tr("gp")] >= min_games].sort_values(stat_name, ascending=False).head(15)
        st.subheader(COMP_NAME[lang][comp])
        left, right = st.columns([3, 2])
        lt = t[["player", stat_name, "team", tr("gp")]].rename(
            columns={"player": tr("player"), "team": tr("team")}).round(1)
        left.dataframe(lt, hide_index=True, width="stretch")
        with left:
            csv_button(lt, f"lideri_{key}", f"dl_lead_{comp}")
        # Altair umesto st.bar_chart (koji ima zum/pomeranje i hvata prst na telefonu)
        right.altair_chart(alt.Chart(t).mark_bar(color=COLOR.get(key, "#f59e0b")).encode(
            x=alt.X("player:N", sort=list(t["player"]), title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y(f"{stat_name}:Q", title=None),
            tooltip=["player", "team", alt.Tooltip(f"{stat_name}:Q", format=".1f")]),
            width="stretch")

    # forma: posl. 3 vs sezona / form: last 3 vs season
    st.subheader(tr("form"))
    st.caption(tr("form_note"))
    fr = []
    for (comp, pid), pg in df.sort_values(SORT).groupby(["comp", "player_id"]):
        if len(pg) < max(4, min_games):
            continue
        l3, sa = pg[key].tail(3).mean(), pg[key].mean()
        fr.append({tr("player"): pg["player"].iloc[-1], tr("team"): pg["team"].iloc[-1],
                   tr("last3"): round(l3, 1), tr("season_avg"): round(sa, 1),
                   tr("diff"): round(l3 - sa, 1)})
    if fr:
        fr = pd.DataFrame(fr).sort_values(tr("diff"), ascending=False)
        f1, f2 = st.columns(2)
        f1.markdown(f"**📈 {tr('form_up')}**")
        f1.dataframe(fr.head(10), hide_index=True, width="stretch")
        f2.markdown(f"**📉 {tr('form_down')}**")
        f2.dataframe(fr.tail(10).iloc[::-1], hide_index=True, width="stretch")


# ---------- props ----------
def render_props():
    st.caption(tr("props_note"))
    c1, c2 = st.columns([3, 2])
    pc = c1.selectbox(tr("player"), players["label"], index=None,
                      placeholder=tr("placeholder"), key="p3")
    prop_name = c2.selectbox(stat_c, list(prop_stats.values()), key="s3")
    if not pc:
        return
    row, g = player_games(pc)
    key = prop_inv[prop_name]
    opp_key = f"opp_{row['comp']}_{row['player_id']}"
    opp_opts = ["__all__"] + sorted(g["opp"].dropna().unique())

    # sledeci protivnik / next opponent
    ta = tgames[tgames["comp"] == row["comp"]].groupby("team")[f"{key}_a"].mean().dropna()
    rank = ta.rank(ascending=False, method="min").astype(int)
    nxt = next_game(row["comp"], g["team"].iloc[-1])
    if nxt:
        o = nxt["opp"]
        st.info(tr("next_game", opp=o, ha=tr("home") if nxt["home"] else tr("away"),
                   d=f"{nxt['date']:%d.%m.}" if pd.notna(nxt["date"]) else "", t=nxt["time"] or "",
                   v=f"{ta.get(o, float('nan')):.1f}", s=prop_name,
                   r=rank.get(o, "–"), n=len(ta)))
        # dugme je pre selectbox-a, pa smemo direktno da postavimo njegovu vrednost
        if o in opp_opts and st.button(tr("use_next"), key=f"use_next_{opp_key}"):
            st.session_state[opp_key] = o
    elif not sched.empty:
        st.caption(tr("next_none"))

    default = float(round(g[key].mean() * 2) / 2)
    c3, c4, c5 = st.columns(3)
    line = c3.number_input(tr("line"), value=default, step=0.5,
                           key=f"line_{row['player_id']}_{key}")
    has_home = "Home" in g.columns and g["Home"].notna().any()
    venue = c4.radio(tr("venue"), ["all", "home", "away"], horizontal=True,
                     disabled=not has_home,
                     format_func=lambda x: tr("all_f") if x == "all" else tr(x))
    opp_sel = c5.selectbox(opp_c, opp_opts, key=opp_key,
                           format_func=lambda x: tr("all") if x == "__all__" else x)

    f = g.copy()
    if has_home and venue != "all":
        f = f[f["Home"] == (1 if venue == "home" else 0)]
    if opp_sel != "__all__":
        f = f[f["opp"] == opp_sel]
    f = f.dropna(subset=[key]).reset_index(drop=True)
    g = g.dropna(subset=[key]).reset_index(drop=True)
    if f.empty:
        st.warning(tr("no_games"))
        return

    st.subheader(f"{row['player']} – {prop_name} {line:g}")
    cols = st.columns(5)
    for c, n in zip(cols[:3], (5, 10, 20)):
        o, tot = hit_rate(f[key].tail(n), line)
        c.metric(tr("last_n", n=n), f"{100 * o / tot:.0f}% Over",
                 tr("n_games", o=o, t=tot), delta_color="off")
    o, tot = hit_rate(f[key], line)
    cols[3].metric(tr("season_lbl"), f"{100 * o / tot:.0f}% Over",
                   tr("n_games", o=o, t=tot), delta_color="off")
    # niz / streak
    over_flags = (f[key] > line).tolist()
    streak = len(list(next(groupby(over_flags[::-1]))[1]))
    cols[4].metric(tr("streak"), f"{streak} x {'Over' if over_flags[-1] else 'Under'}",
                   tr("avg_n", x=f"{f[key].mean():.1f}"), delta_color="off")
    # stabilnost / consistency
    cols = st.columns(4)
    cols[0].metric(tr("median"), f"{f[key].median():g}")
    cols[1].metric(tr("min"), f"{f[key].min():g}")
    cols[2].metric(tr("max"), f"{f[key].max():g}")
    cols[3].metric(tr("spread"), f"{f[key].std(ddof=0):.1f}", help=tr("spread_help"))

    d = f.assign(Game=np.arange(1, len(f) + 1))
    d[res_c] = np.where(f[key] > line, "Over", "Under")
    d[opp_c] = [date_lbl(dt, o) for dt, o in zip(d["date"], d["opp"].fillna("?"))]
    d[opp_c] = d[opp_c] + d.groupby(opp_c).cumcount().map(lambda n: "" if n == 0 else f" ({n + 1})")
    d[tr("rest")] = d["rest"]
    bars = alt.Chart(d).mark_bar().encode(
        x=alt.X(f"{opp_c}:N", sort=list(d[opp_c]), title=tr("game_axis"),
                axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(f"{key}:Q", title=prop_name),
        color=alt.Color(f"{res_c}:N", legend=None,
                        scale=alt.Scale(domain=["Over", "Under"], range=["#22c55e", "#ef4444"])),
        tooltip=[opp_c, alt.Tooltip(f"{key}:Q", title=prop_name), res_c, tr("rest")])
    rule = alt.Chart(pd.DataFrame({"l": [line]})).mark_rule(
        strokeDash=[6, 4], color="#f59e0b", size=2).encode(y="l:Q")
    st.altair_chart(bars + rule, width="stretch")

    # splitovi (na svim utakmicama igraca, bez filtera) / splits
    def summarize(x):
        o, tot = hit_rate(x[key], line)
        return pd.Series({tr("gp"): tot, tr("avg"): round(x[key].mean(), 1),
                          "Over %": round(100 * o / tot)})
    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown(f"**{tr('home_away')}**")
        if has_home:
            sp = g.assign(_v=np.where(g["Home"] == 1, tr("home"), tr("away"))).groupby("_v").apply(
                summarize, include_groups=False)
            sp.index.name = tr("venue")
            st.dataframe(sp, width="stretch")
        else:
            st.caption(tr("no_home"))
        # po odmoru (prva utakmica nema podatak) / by rest days
        gr = g.dropna(subset=["rest"])
        if not gr.empty:
            st.markdown(f"**{tr('by_rest')}**")
            rs = gr.assign(_r=np.where(gr["rest"] <= 2, tr("rest_short"), tr("rest_long"))).groupby(
                "_r").apply(summarize, include_groups=False)
            rs.index.name = tr("rest")
            st.dataframe(rs, width="stretch")
    with sc2:
        st.markdown(f"**{tr('by_opp')}**")
        vs = g.dropna(subset=["opp"]).groupby("opp").apply(summarize, include_groups=False)
        # koliko taj protivnik prima te statistike (timski) i rang / what the opponent allows
        ta = tgames[tgames["comp"] == row["comp"]].groupby("team")[f"{key}_a"].mean().dropna()
        rank = ta.rank(ascending=False, method="min").astype(int)
        vs[tr("opp_allows")] = vs.index.map(ta).round(1)
        vs[tr("opp_rank")] = vs.index.map(rank).astype("Int64")
        vs.index.name = opp_c
        st.dataframe(vs.sort_values("Over %", ascending=False), width="stretch",
                     height=min(300, 38 + 35 * len(vs)),
                     column_config={tr("opp_rank"): st.column_config.NumberColumn(
                         help=tr("opp_rank_help"))})


with TAB["props"]:
    render_props()

# ---------- skener / scanner ----------
with TAB["scan"]:
    st.caption(tr("scan_note") + " " + tr("props_note"))
    c1, c2, c3 = st.columns(3)
    sname = c1.selectbox(stat_c, list(prop_stats.values()), key="scan_stat")
    skey = prop_inv[sname]
    sline = c2.number_input(tr("line"), value=DEFAULT_LINE.get(skey, 5.5), step=0.5,
                            key=f"scan_line_{skey}")
    side = c3.radio(tr("side"), ["Over", "Under"], horizontal=True, key="scan_side")
    c4, c5, c6 = st.columns(3)
    sort_opts = {tr("l5p"): 5, tr("l10p"): 10, tr("seasp"): None}
    sort_by = c4.radio(tr("window"), list(sort_opts), horizontal=True, key="scan_sort")
    smin_g = c5.slider(tr("min_games"), 1, max(1, int(df.groupby("player_id").size().max())), 3,
                       key="scan_min_g")
    smin_m = c6.slider(tr("min_minutes"), 0, 35, 10, key="scan_min_m")

    rows = []
    for (comp, pid), pg in df.sort_values(SORT).groupby(["comp", "player_id"]):
        if len(pg) < smin_g or pg["Minutes"].mean() < smin_m:
            continue
        v = pg[skey].dropna()
        if v.empty:
            continue
        rec = {tr("player"): pg["player"].iloc[-1], tr("team"): pg["team"].iloc[-1],
               tr("gp"): len(v), tr("avg"): round(v.mean(), 1)}
        for lbl, n in sort_opts.items():
            o, tot = hit_rate(v.tail(n) if n else v, sline, side)
            rec[lbl] = round(100 * o / tot)
        flags = (v > sline if side == "Over" else v < sline).tolist()[::-1]
        rec[tr("streak_s")] = len(list(next(groupby(flags))[1])) if flags[0] else 0
        rows.append(rec)
    if not rows:
        st.info(tr("no_players"))
    else:
        scan = pd.DataFrame(rows).sort_values([sort_by, tr("avg")],
                                              ascending=[False, side == "Under"])
        # procenti odmah posle imena da se vide na telefonu / % columns first for phones
        order = ([tr("player"), sort_by] + [x for x in sort_opts if x != sort_by]
                 + [tr("avg"), tr("streak_s"), tr("team"), tr("gp")])
        scan = scan[order]
        st.dataframe(scan, hide_index=True, width="stretch", height=420,
                     column_config={lbl: st.column_config.NumberColumn(lbl, format="%d%%")
                                    for lbl in sort_opts})
        csv_button(scan, f"skener_{skey}_{sline:g}_{side}", "dl_scan")

# ---------- timovi / teams ----------
@st.cache_data(ttl=3600)
def load_standings(comp: str, rnd: int) -> pd.DataFrame:
    try:
        return es.load_standings(comp, rnd)
    except Exception:
        return pd.DataFrame()


def form_icons(v):
    if isinstance(v, str):
        v = [c for c in v if c in "WL"]
    return "".join("🟢" if c == "W" else "🔴" for c in (v or []))


with TAB["teams"]:
    st.subheader(tr("standings"))
    for comp in comps:
        if sched.empty:
            break
        done_r = sched[(sched["comp"] == comp) & (sched["played"] == 1)]["gameday"]
        last_r = int(done_r.max()) if not done_r.empty else 1
        stn = load_standings(comp, last_r)
        if stn.empty:
            st.caption(tr("no_standings"))
            continue
        tbl = pd.DataFrame({
            tr("pos"): stn["position"], tr("team"): stn["club.code"],
            tr("gp"): stn["gamesPlayed"], tr("won"): stn["gamesWon"], tr("lost"): stn["gamesLost"],
            tr("pdiff"): stn["pointsDifference"], tr("home_rec"): stn["homeRecord"],
            tr("away_rec"): stn["awayRecord"], tr("last5"): stn["last5Form"].map(form_icons),
        })
        st.caption(f"{COMP_NAME[lang][comp]} · {tr('round')} {last_r}")
        st.dataframe(tbl, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(tbl)))
    st.divider()
    st.caption(tr("teams_note"))
    tname = st.selectbox(stat_c, list(prop_stats.values()), key="team_stat")
    tkey = prop_inv[tname]
    for comp in comps:
        tg = tgames[tgames["comp"] == comp]
        if tg.empty:
            continue
        grp = tg.groupby("team")
        tt = pd.DataFrame({
            tr("team"): grp.size().index,
            tr("allowed"): grp[f"{tkey}_a"].mean().round(1).values,
            tr("scored"): grp[tkey].mean().round(1).values,
            tr("gp"): grp.size().values,
            tr("record"): grp["win"].apply(wl).values,
        })
        tt[tr("diff")] = (tt[tr("scored")] - tt[tr("allowed")]).round(1)
        if "Home" in tg.columns:
            tt[tr("home_rec")] = tg[tg["Home"] == 1].groupby("team")["win"].apply(wl).reindex(
                tt[tr("team")]).fillna("0-0").values
            tt[tr("away_rec")] = tg[tg["Home"] == 0].groupby("team")["win"].apply(wl).reindex(
                tt[tr("team")]).fillna("0-0").values
        tt = tt.sort_values(tr("allowed"), ascending=False)
        st.subheader(COMP_NAME[lang][comp])
        st.dataframe(tt, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(tt)))
        csv_button(tt, f"timovi_{tkey}", f"dl_team_{comp}")
        st.markdown(f"**{tr('allowed_chart', s=tname)}**")
        st.altair_chart(alt.Chart(tt).mark_bar(color=COLOR.get(tkey, "#f59e0b")).encode(
            x=alt.X(f"{tr('team')}:N", sort=list(tt[tr("team")]), title=None,
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y(f"{tr('allowed')}:Q", title=None),
            tooltip=[tr("team"), tr("allowed"), tr("scored"), tr("record")]), width="stretch")

# ---------- poredjenje / compare ----------
with TAB["cmp"]:
    c1, c2 = st.columns(2)
    a = c1.selectbox(tr("p1"), players["label"], index=None, placeholder=tr("placeholder"), key="cmp1")
    b = c2.selectbox(tr("p2"), players["label"], index=None, placeholder=tr("placeholder"), key="cmp2")
    if not (a and b):
        st.info(tr("cmp_pick"))
    else:
        (ra, ga), (rb, gb) = player_games(a), player_games(b)
        na, nb = ra["player"], rb["player"]
        if na == nb:
            nb = f"{nb} ({rb['team']})"
        keys = [k for k in list(stats) if k in df.columns] + [k for k in ("3PM", "PRA") if k in df.columns]
        lbl = {**stats, **EXTRA_NAMES[lang]}

        def summary(g):
            out = {lbl[k]: round(g[k].mean(), 1) for k in keys}
            s = g.sum(numeric_only=True)
            out["3P%"] = pct(s.get("FieldGoalsMade3", 0), s.get("FieldGoalsAttempted3", 0))
            out["FT%"] = pct(s.get("FreeThrowsMade", 0), s.get("FreeThrowsAttempted", 0))
            return out
        ct = pd.DataFrame({
            na: summary(ga), nb: summary(gb),
            f"{na} – {tr('last_n', n=5)}": summary(ga.tail(5)),
            f"{nb} – {tr('last_n', n=5)}": summary(gb.tail(5)),
        }).astype(str)
        ct.loc[tr("gp")] = [str(len(ga)), str(len(gb)), str(min(5, len(ga))), str(min(5, len(gb)))]
        ct.index.name = stat_c
        st.dataframe(ct, width="stretch")

        cname = st.selectbox(stat_c, list(prop_stats.values()), key="cmp_stat")
        ckey = prop_inv[cname]
        both = pd.concat([
            pd.DataFrame({tr("game_n"): np.arange(1, len(ga) + 1), val_c: ga[ckey], tr("player"): na,
                          opp_c: ga["opp"].fillna("?")}),
            pd.DataFrame({tr("game_n"): np.arange(1, len(gb) + 1), val_c: gb[ckey], tr("player"): nb,
                          opp_c: gb["opp"].fillna("?")}),
        ])
        st.markdown(f"**{tr('cmp_trend', s=cname)}**")
        st.altair_chart(alt.Chart(both).mark_line(point=True).encode(
            x=alt.X(f"{tr('game_n')}:O", title=None),
            y=alt.Y(f"{val_c}:Q", title=None),
            color=alt.Color(f"{tr('player')}:N", title=None,
                            scale=alt.Scale(range=["#3b82f6", "#f59e0b"]),
                            legend=alt.Legend(orient="top")),
            tooltip=[tr("player"), opp_c, val_c]), width="stretch")

# ---------- raspored / schedule ----------
with TAB["sched"]:
    if sched.empty:
        st.info(tr("no_sched"))
    else:
        st.caption(tr("sched_note"))
        c1, c2 = st.columns(2)
        rs_name = c1.selectbox(stat_c, list(prop_stats.values()), key="sched_stat")
        rs_key = prop_inv[rs_name]
        for comp in comps:
            s = sched[sched["comp"] == comp].copy()
            if s.empty:
                continue
            s["is_played"] = [(comp, gc) in played_codes or p == 1
                              for gc, p in zip(s["gamecode"], s["played"])]
            rounds = sorted(s["gameday"].unique())
            upcoming = s.loc[~s["is_played"], "gameday"]
            default_r = int(upcoming.min()) if not upcoming.empty else int(max(rounds))
            rnd = c2.selectbox(tr("round"), rounds, index=rounds.index(default_r),
                               key=f"sched_round_{comp}")
            s = s[s["gameday"] == rnd].sort_values(["date", "startime"])

            ta = tgames[tgames["comp"] == comp].groupby("team")[f"{rs_key}_a"].mean().dropna()
            rank = ta.rank(ascending=False, method="min")
            pts = tgames[tgames["comp"] == comp].set_index(["gamecode", "team"])["Points"]

            def allow(team):
                return f"{ta[team]:.1f} (#{int(rank[team])})" if team in ta.index else "–"

            def res_or_time(r):
                try:
                    return f"{int(pts[(r.gamecode, r.homecode)])}–{int(pts[(r.gamecode, r.awaycode)])}"
                except KeyError:
                    return r.startime or ""

            tbl = pd.DataFrame({
                tr("date"): s["date"].dt.strftime("%d.%m.").fillna(""),
                tr("match"): s["homecode"] + " – " + s["awaycode"],
                tr("res_time"): [res_or_time(r) for r in s.itertuples()],
                tr("home_allows"): s["homecode"].map(allow),
                tr("away_allows"): s["awaycode"].map(allow),
            })
            st.subheader(f"{COMP_NAME[lang][comp]} · {tr('round')} {rnd}")
            st.dataframe(tbl, hide_index=True, width="stretch",
                         height=min(420, 38 + 35 * len(tbl)))
            csv_button(tbl, f"raspored_{comp}_kolo{rnd}", f"dl_sched_{comp}")

# ---------- bez saigraca / without teammate ----------
with TAB["without"]:
    st.caption(tr("without_note"))
    c1, c2, c3 = st.columns(3)
    w_team = c1.selectbox(tr("team"), sorted(df["team"].unique()), key="wo_team")
    td = df[df["team"] == w_team]
    n_team = td["gamecode"].nunique()
    roster = td.groupby(["player_id", "player"]).size().reset_index(name="n")
    roster["missed"] = roster["n"] < n_team
    # prvo oni koji su propustili utakmice, pa po broju odigranih / absentees first
    roster = roster.sort_values(["missed", "n"], ascending=False).set_index("player_id")
    absent = c2.selectbox(tr("absent"), list(roster.index), key=f"wo_abs_{w_team}",
                          format_func=lambda p: f"{roster.loc[p, 'player']} ({roster.loc[p, 'n']}/{n_team})")
    wo_opts = {**prop_stats, "Minutes": stats.get("Minutes", "Minutes")}
    wo_name = c3.selectbox(stat_c, list(wo_opts.values()), key="wo_stat")
    wo_key = {v: k for k, v in wo_opts.items()}[wo_name]

    all_g = set(td["gamecode"])
    with_g = set(td.loc[td["player_id"] == absent, "gamecode"])
    without_g = all_g - with_g
    aname = roster.loc[absent, "player"]
    if not without_g:
        st.info(tr("no_absence", p=aname))
    else:
        # tim u celini / team as a whole
        tt = tgames[(tgames["team"] == w_team)]
        tw, two = tt[tt["gamecode"].isin(with_g)], tt[tt["gamecode"].isin(without_g)]
        c = st.columns(3)
        c[0].metric(f"{w_team} – {tr('with')}", wl(tw["win"]) if len(tw) else "—",
                    f"{tw['Points'].mean():.1f} {stats['Points']}" if len(tw) else None, delta_color="off")
        c[1].metric(f"{w_team} – {tr('without')}", wl(two["win"]),
                    f"{two['Points'].mean():.1f} {stats['Points']}", delta_color="off")
        c[2].metric(tr("gp_without"), len(without_g))

        rows = []
        for (pid, pname), pg in td[td["player_id"] != absent].groupby(["player_id", "player"]):
            a = pg.loc[pg["gamecode"].isin(with_g), wo_key].dropna()
            b = pg.loc[pg["gamecode"].isin(without_g), wo_key].dropna()
            if a.empty or b.empty:
                continue
            rows.append({tr("player"): pname, tr("with"): round(a.mean(), 1),
                         tr("without"): round(b.mean(), 1), tr("diff"): round(b.mean() - a.mean(), 1),
                         tr("gp_with"): len(a), tr("gp_without"): len(b)})
        if rows:
            wt = pd.DataFrame(rows).sort_values(tr("diff"), ascending=False)
            st.markdown(f"**{wo_name}: {tr('without').lower()} {aname}**")
            st.dataframe(wt, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(wt)),
                         column_config={tr("diff"): st.column_config.NumberColumn(format="%+.1f")})
            csv_button(wt, f"bez_{aname}_{wo_key}", "dl_without")

# ---------- pregled kola / round preview ----------
with TAB["round"]:
    if sched.empty:
        st.info(tr("no_sched"))
    else:
        st.caption(tr("round_note") + " " + tr("props_note"))
        c1, c2, c3 = st.columns(3)
        r_name = c1.selectbox(stat_c, list(prop_stats.values()), key="rp_stat")
        r_key = prop_inv[r_name]
        r_line = c2.number_input(tr("line"), value=DEFAULT_LINE.get(r_key, 5.5), step=0.5,
                                 key=f"rp_line_{r_key}")
        r_side = c3.radio(tr("side"), ["Over", "Under"], horizontal=True, key="rp_side")
        c4, c5, c6 = st.columns(3)
        r_hit = c4.slider(tr("min_hit"), 0, 100, 60, step=10, key="rp_hit")
        r_top = c5.slider(tr("top_def"), 1, 20, 8, key="rp_top", help=tr("top_def_help"))
        r_min = c6.slider(tr("min_minutes"), 0, 35, 15, key="rp_min")

        hist = df.sort_values(SORT)
        last_team = hist.groupby(["comp", "player_id"]).tail(1).set_index(["comp", "player_id"])["team"]
        out = []
        for comp in comps:
            s = sched[sched["comp"] == comp]
            s = s[[(comp, gc) not in played_codes and p == 0 for gc, p in zip(s["gamecode"], s["played"])]]
            if s.empty:
                continue
            rnd = s["gameday"].min()
            s = s[s["gameday"] == rnd].sort_values(["date", "startime"])
            ta = tgames[tgames["comp"] == comp].groupby("team")[f"{r_key}_a"].mean().dropna()
            rank = ta.rank(ascending=(r_side == "Under"), method="min")
            hc = hist[hist["comp"] == comp]
            for m in s.itertuples():
                match = f"{m.date:%d.%m.} {m.homecode}–{m.awaycode}" if pd.notna(m.date) else \
                    f"{m.homecode}–{m.awaycode}"
                for team, opp in ((m.homecode, m.awaycode), (m.awaycode, m.homecode)):
                    if opp not in rank.index or rank[opp] > r_top:
                        continue
                    pids = last_team[last_team == team].index.get_level_values(1)
                    for pid, pg in hc[hc["player_id"].isin(pids)].groupby("player_id"):
                        v = pg[r_key].dropna()
                        if len(v) < 3 or pg["Minutes"].mean() < r_min:
                            continue
                        o5, t5 = hit_rate(v.tail(5), r_line, r_side)
                        if 100 * o5 / t5 < r_hit:
                            continue
                        oa, tall = hit_rate(v, r_line, r_side)
                        out.append({tr("match"): match, tr("player"): pg["player"].iloc[-1],
                                    tr("team"): team, tr("l5p"): round(100 * o5 / t5),
                                    tr("seasp"): round(100 * oa / tall), tr("avg"): round(v.mean(), 1),
                                    tr("opponent"): f"{opp} (#{int(rank[opp])})"})
            st.subheader(f"{COMP_NAME[lang][comp]} · {tr('round')} {rnd} · {r_name} {r_side} {r_line:g}")
        if not out:
            st.info(tr("no_round"))
        else:
            rp = pd.DataFrame(out).sort_values([tr("l5p"), tr("seasp")], ascending=False)
            rp = rp[[tr("player"), tr("l5p"), tr("seasp"), tr("opponent"), tr("match"),
                     tr("avg"), tr("team")]]
            st.dataframe(rp, hide_index=True, width="stretch", height=min(480, 38 + 35 * len(rp)),
                         column_config={k: st.column_config.NumberColumn(format="%d%%")
                                        for k in (tr("l5p"), tr("seasp"))})
            csv_button(rp, f"pregled_kola_{r_key}_{r_line:g}_{r_side}", "dl_round")
