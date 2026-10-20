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
           "PA": "Poeni+Asist.", "RA": "Skokovi+Asist.", "Turnovers": "Izgubljene"},
    "en": {"3PM": "3-pointers made", "PRA": "Pts+Reb+Ast", "PR": "Pts+Reb",
           "PA": "Pts+Ast", "RA": "Reb+Ast", "Turnovers": "Turnovers"},
}
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

stats = {k: NAMES[lang][k] for k in KEYS if k in df.columns}   # kljuc -> prikazani naziv
inv = {v: k for k, v in stats.items()}                          # prikazani naziv -> kljuc
stat_keys = [k for k in stats if k != "Minutes"]
opp_c, stat_c, val_c, res_c = tr("opponent"), tr("statistic"), tr("value"), tr("result")
st.caption(tr("counts", g=df["gamecode"].nunique(), p=df["player_id"].nunique()))

tab1, tab2, tab3 = st.tabs([tr("tab_player"), tr("tab_leaders"), tr("tab_props")])

# ---------- igrac / player ----------
with tab1:
    players = (df.groupby(["comp", "player_id", "player", "team"]).size()
                 .reset_index(name="n").sort_values("player"))
    players["label"] = (players["player"] + "  (" + players["team"] + ", "
                        + players["comp"].map(COMP_NAME[lang]) + ")")
    choice = st.selectbox(tr("search"), players["label"], index=None,
                          placeholder=tr("placeholder"))
    if choice:
        row = players[players["label"] == choice].iloc[0]
        g = df[(df["comp"] == row["comp"]) & (df["player_id"] == row["player_id"])]
        g = g.sort_values("gamecode")
        st.subheader(f"{row['player']} – {row['team']}")
        st.caption(tr("averages", n=len(g)))

        cols = st.columns(len(stat_keys))
        for c, k in zip(cols, stat_keys):
            last = g[k].iloc[-1]
            c.metric(f"{DOT[k]} {stats[k]}", f"{g[k].mean():.1f}",
                     f"{last - g[k].mean():+.1f} ({tr('last_short')})", help=tr("last_help"))

        pick = st.multiselect(tr("chart_by_game"), [stats[k] for k in stat_keys],
                              default=[stats[k] for k in ("Points", "TotalRebounds", "Assistances") if k in stats])
        g = g.reset_index(drop=True)
        names = g["opp"].fillna("?")
        names = names + names.groupby(names).cumcount().map(lambda n: "" if n == 0 else f" ({n + 1})")
        g[opp_c] = names
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

        st.dataframe(g[[opp_c] + list(stats)].rename(columns=stats).round(1),
                     hide_index=True, width="stretch", height=min(300, 38 + 35 * len(g)))

# ---------- lideri / leaders ----------
with tab2:
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
        left.dataframe(t[["player", stat_name, "team", tr("gp")]].rename(
            columns={"player": tr("player"), "team": tr("team")}).round(1),
            hide_index=True, width="stretch")
        # Altair umesto st.bar_chart (koji ima zum/pomeranje i hvata prst na telefonu)
        right.altair_chart(alt.Chart(t).mark_bar(color=COLOR.get(key, "#f59e0b")).encode(
            x=alt.X("player:N", sort=list(t["player"]), title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y(f"{stat_name}:Q", title=None),
            tooltip=["player", "team", alt.Tooltip(f"{stat_name}:Q", format=".1f")]),
            width="stretch")

        # ---------- props ----------
def hit_rate(vals, line):
    n = len(vals)
    o = int((vals > line).sum())
    return o, n


with tab3:
    st.caption(tr("props_note"))
    c1, c2 = st.columns([3, 2])
    pc = c1.selectbox(tr("player"), players["label"], index=None,
                      placeholder=tr("placeholder"), key="p3")
    prop_stats = {k: stats[k] for k in stat_keys}
    prop_stats.update({k: v for k, v in EXTRA_NAMES[lang].items() if k in df.columns})
    prop_inv = {v: k for k, v in prop_stats.items()}
    prop_name = c2.selectbox(stat_c, list(prop_stats.values()), key="s3")
    if pc:
        row = players[players["label"] == pc].iloc[0]
        key = prop_inv[prop_name]
        g = (df[(df["comp"] == row["comp"]) & (df["player_id"] == row["player_id"])]
             .sort_values("gamecode").reset_index(drop=True))
        default = float(round(g[key].mean() * 2) / 2)
        c3, c4, c5 = st.columns(3)
        line = c3.number_input(tr("line"), value=default, step=0.5,
                               key=f"line_{row['player_id']}_{key}")
        has_home = "Home" in g.columns and g["Home"].notna().any()
        venue = c4.radio(tr("venue"), ["all", "home", "away"], horizontal=True,
                         disabled=not has_home,
                         format_func=lambda x: tr("all_f") if x == "all" else tr(x))
        opp_sel = c5.selectbox(opp_c, ["__all__"] + sorted(g["opp"].dropna().unique()),
                               format_func=lambda x: tr("all") if x == "__all__" else x)

        f = g.copy()
        if has_home and venue != "all":
            f = f[f["Home"] == (1 if venue == "home" else 0)]
        if opp_sel != "__all__":
            f = f[f["opp"] == opp_sel]
        f = f.reset_index(drop=True)
        if f.empty:
            st.warning(tr("no_games"))
            st.stop()

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

        d = f.assign(Game=np.arange(1, len(f) + 1))
        d[res_c] = np.where(f[key] > line, "Over", "Under")
        d[opp_c] = d["opp"].fillna("?")
        bars = alt.Chart(d).mark_bar().encode(
            x=alt.X("Game:O", title=tr("game_axis")),
            y=alt.Y(f"{key}:Q", title=prop_name),
            color=alt.Color(f"{res_c}:N", legend=None,
                            scale=alt.Scale(domain=["Over", "Under"], range=["#22c55e", "#ef4444"])),
            tooltip=[opp_c, alt.Tooltip(f"{key}:Q", title=prop_name), res_c])
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
        with sc2:
            st.markdown(f"**{tr('by_opp')}**")
            vs = g.dropna(subset=["opp"]).groupby("opp").apply(summarize, include_groups=False)
            vs.index.name = opp_c
            st.dataframe(vs.sort_values("Over %", ascending=False), width="stretch",
                         height=min(300, 38 + 35 * len(vs)))

            