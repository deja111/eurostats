"""
Web aplikacija za Evroligu / Evrokup statistiku. / EuroLeague + EuroCup stats app.
Pokretanje / Run:  python -m streamlit run app.py
(app.py i euroleague_stats.py moraju biti u istom folderu)
"""
import contextlib
import io
import json
import re
import os
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
        "tab_scan": "🔎 Skener", "tab_teams": "🛡️ Timovi", "tab_cmp": "⚖️ Poređenje", "tab_round": "⭐ Pregled kola", "tab_picks": "🔥 Predlozi", "tab_without": "🔄 Bez saigrača",
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
        "tab_scan": "🔎 Scanner", "tab_teams": "🛡️ Teams", "tab_cmp": "⚖️ Compare", "tab_round": "⭐ Round preview", "tab_picks": "🔥 Picks", "tab_without": "🔄 Without teammate",
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
        "pm_h": "Plus/minus i clutch", "pm_avg": "+/- po utakmici", "pm_40": "+/- na 40 min",
        "pm_help": "Razlika u poenima dok je igrač na terenu",
        "clutch_help": "Clutch = posl. 5 min 4. četvrtine i produžeci, razlika do 5 poena",
        "c_pts": "Clutch poeni", "c_fg": "Clutch šut", "c_min": "Clutch minuti",
        "clutch_lead": "⏱️ Clutch lideri (ukupno)", "c_games": "Utakm. u clutch",
        "lineups": "👥 Najčešće petorke", "lineup": "Petorka", "min_short": "Min",
        "pf": "Dali", "pa": "Primili", "net40": "+/- na 40", "min_lineup": "Min. minuta zajedno",
        "totals": "🏀 Totali utakmica", "total_line": "Linija (ukupno poena)", "half_opt": "Deo utakmice",
        "full": "Cela utakmica", "h1": "1. poluvreme", "proj": "Projekcija",
        "home_proj": "Domaćin proj.", "away_proj": "Gost proj.", "home_over": "Dom. % preko",
        "away_over": "Gost % preko",
        "totals_note": "Projekcija = prosek (koliko tim daje + koliko protivnik prima) za oba tima. "
                       "% preko = koliko utakmica tog tima je imalo više poena od linije.",
        "pos_G": "Bekovi", "pos_F": "Krila", "pos_C": "Centri",
        "pos1_G": "Bek", "pos1_F": "Krilo", "pos1_C": "Centar", "pos_short": "Poz.",
        "pos_est": "procena", "pos_manual": "ručno",
        "dvp": "🎯 Odbrana po poziciji (DvP)",
        "rank_col": "Rang ({p})",
        "sig": "Predlog", "sig_score": "Jačina", "reasons": "Zašto", "line_s": "Linija",
        "sig_fire": "🔥 Over (jak)", "sig_over": "🟢 Over", "sig_none": "⚪ Bez signala",
        "sig_under": "🔴 Under", "sig_ice": "🧊 Under (jak)", "sig_few": "⚪ Malo utakmica",
        "r_hit": "{o}/{t} preko", "r_med": "medijana {m:g} vs {l:g}", "r_opp": "{o} #{r} {p}",
        "r_min": "minuti {d:+.1f}", "r_ven": "{v}: prosek {a:.1f}",
        "sig_note": "Predlog je statistički signal iz dosadašnjih utakmica (hit-rate, medijana, "
                    "protivnik po poziciji, minuti, kuća/gost), ne garancija. 🔥 / 🧊 = skoro svi "
                    "pokazatelji se slažu. Uzorak je mali na početku sezone.",
        "line_mode": "Linija", "line_fixed": "Ista za sve", "line_avg": "Prosek igrača (≈ kladionica)",
        "show": "Prikaži", "show_all": "Sve", "show_strong": "Samo 🔥 / 🧊",
        "picks_count": "🔥 {f} jakih Over · 🟢 {o} Over · 🔴 {u} Under · 🧊 {i} jakih Under",
        "no_picks": "Nema igrača za sledeće kolo sa ovim filterima.",
        "tot_sig": "Predlog (total)",
        "inj_out": "🚑 Ne igra", "inj_doubtful": "🟠 Verovatno ne igra", "inj_questionable": "🟡 Upitan",
        "inj_gtd": "🟡 Odluka pred meč", "inj_likely_out": "⚠️ Van terena (nepotvrđeno)",
        "inj_available": "✅ Vraća se", "inj_info": "ℹ️ Napomena", "inj_col": "🚑 Status",
        "inj_h": "🚑 Povrede za sledeće kolo", "inj_src": "Izvor: [{t}]({u}) · objavljeno {p} · provereno {f}",
        "inj_manual": "ručno (povrede.csv)", "inj_none": "Izveštaj o povredama još nije preuzet.",
        "inj_not_sent": "Nije poslao izveštaj", "inj_full": "Svi igrači na raspolaganju",
        "inj_hide": "Sakrij igrače koji ne igraju",
        "check_h": "🔍 Proveri igrača", "check_list": "📋 Lista za sledeće kolo",
        "check_note": "Izaberi igrača, statistiku i marginu, pa vidi predlog za njegovu sledeću utakmicu.",
        "factor": "Faktor", "weight": "Težina", "vote": "Glas", "detail": "Detalj",
        "f_hit": "Hit-rate (posl. 10)", "f_med": "Medijana", "f_opp": "Protivnik (DvP)",
        "f_ven": "Kuća / gost", "f_min": "Minuti (posl. 3)", "neutral": "neutralno",
        "next_vs": "Sledeća utakmica: **{o}** ({ha}, {d})", "no_next": "Nema zakazane utakmice – "
        "protivnik i teren nisu uračunati.", "line_each": "Linija = prosek svakog igrača, na .5 "
        "(npr. prosek 14.3 → 14.5).",
        "dvp_legend": "**Kako čitati tabelu:**\n\n"
                      "- **Bekovi / Krila / Centri:** koliko poena (ili izabrane statistike) tim prosečno "
                      "primi po utakmici od **svih** protivničkih igrača na toj poziciji zajedno.\n"
                      "- **Rang:** mesto tima za tu poziciju, od 1 do {n}. "
                      "**Rang 1 = prima najviše** (najslabija odbrana protiv te pozicije, dobar meč za Over). "
                      "**Rang {n} = prima najmanje** (najjača odbrana, teži meč, bolje za Under).\n"
                      "- Timovi koji primaju isto dele isti rang.\n\n"
                      "*Primer:* ako tim ima **Rang (bek) 1**, protivnički bekovi protiv njega u proseku "
                      "postižu više nego protiv bilo kog drugog tima.",
        "dvp_note": "Koliko tim po utakmici primi od svih protivničkih igrača na toj poziciji "
                    "(zbir). #1 = prima najviše. Pozicije su zvanične Euroleague (bek/krilo/centar); "
                    "igračima bez zvanične pozicije je procenjena iz statistike, a pozicije.csv ima prednost.",
        "dvp_next": "🎯 {opp} protiv pozicije **{pos}**: prima **{v}** {s} po utakmici (rang **{r}/{n}**)",
        "rank_by": "Rang odbrane", "rank_pos": "Po poziciji (DvP)", "rank_team": "Cela odbrana",
        "no_pos": "Pozicije igrača još nisu preuzete. Klikni **Osveži podatke**.",
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
        "pm_h": "Plus/minus & clutch", "pm_avg": "+/- per game", "pm_40": "+/- per 40 min",
        "pm_help": "Point differential while the player is on the floor",
        "clutch_help": "Clutch = last 5 min of the 4th quarter and overtime, margin within 5",
        "c_pts": "Clutch points", "c_fg": "Clutch FG", "c_min": "Clutch minutes",
        "clutch_lead": "⏱️ Clutch leaders (total)", "c_games": "Clutch games",
        "lineups": "👥 Most used lineups", "lineup": "Lineup", "min_short": "Min",
        "pf": "Scored", "pa": "Allowed", "net40": "+/- per 40", "min_lineup": "Min. minutes together",
        "totals": "🏀 Game totals", "total_line": "Line (total points)", "half_opt": "Part of game",
        "full": "Full game", "h1": "1st half", "proj": "Projection",
        "home_proj": "Home proj.", "away_proj": "Away proj.", "home_over": "Home % over",
        "away_over": "Away % over",
        "totals_note": "Projection = average of (what a team scores + what the opponent allows) for both teams. "
                       "% over = share of that team's games that went over the line.",
        "pos_G": "Guards", "pos_F": "Forwards", "pos_C": "Centers",
        "pos1_G": "Guard", "pos1_F": "Forward", "pos1_C": "Center", "pos_short": "Pos.",
        "pos_est": "estimate", "pos_manual": "manual",
        "dvp": "🎯 Defense vs position (DvP)",
        "rank_col": "Rank ({p})",
        "sig": "Pick", "sig_score": "Strength", "reasons": "Why", "line_s": "Line",
        "sig_fire": "🔥 Over (strong)", "sig_over": "🟢 Over", "sig_none": "⚪ No signal",
        "sig_under": "🔴 Under", "sig_ice": "🧊 Under (strong)", "sig_few": "⚪ Few games",
        "r_hit": "{o}/{t} over", "r_med": "median {m:g} vs {l:g}", "r_opp": "{o} #{r} {p}",
        "r_min": "minutes {d:+.1f}", "r_ven": "{v}: avg {a:.1f}",
        "sig_note": "A pick is a statistical signal from games so far (hit rate, median, "
                    "opponent vs position, minutes, home/away), not a guarantee. 🔥 / 🧊 = nearly all "
                    "indicators agree. Sample is small early in the season.",
        "line_mode": "Line", "line_fixed": "Same for all", "line_avg": "Player average (≈ bookmaker)",
        "show": "Show", "show_all": "All", "show_strong": "Only 🔥 / 🧊",
        "picks_count": "🔥 {f} strong Over · 🟢 {o} Over · 🔴 {u} Under · 🧊 {i} strong Under",
        "no_picks": "No players in the next round match these filters.",
        "tot_sig": "Pick (total)",
        "inj_out": "🚑 Out", "inj_doubtful": "🟠 Doubtful", "inj_questionable": "🟡 Questionable",
        "inj_gtd": "🟡 Game-time decision", "inj_likely_out": "⚠️ Sidelined (unconfirmed)",
        "inj_available": "✅ Returning", "inj_info": "ℹ️ Note", "inj_col": "🚑 Status",
        "inj_h": "🚑 Injuries for the next round", "inj_src": "Source: [{t}]({u}) · published {p} · checked {f}",
        "inj_manual": "manual (povrede.csv)", "inj_none": "Injury report not downloaded yet.",
        "inj_not_sent": "Report not sent", "inj_full": "Full roster available",
        "inj_hide": "Hide players who are out",
        "check_h": "🔍 Check a player", "check_list": "📋 List for the next round",
        "check_note": "Pick a player, stat and line to see the pick for his next game.",
        "factor": "Factor", "weight": "Weight", "vote": "Vote", "detail": "Detail",
        "f_hit": "Hit rate (last 10)", "f_med": "Median", "f_opp": "Opponent (DvP)",
        "f_ven": "Home / away", "f_min": "Minutes (last 3)", "neutral": "neutral",
        "next_vs": "Next game: **{o}** ({ha}, {d})", "no_next": "No scheduled game – "
        "opponent and venue are not counted.", "line_each": "Line = each player's average, at .5 "
        "(e.g. average 14.3 → 14.5).",
        "dvp_legend": "**How to read the table:**\n\n"
                      "- **Guards / Forwards / Centers:** how much (points or the chosen stat) a team allows "
                      "per game to **all** opposing players at that position combined.\n"
                      "- **Rank:** the team's place for that position, 1 to {n}. "
                      "**Rank 1 = allows the most** (weakest defense vs that position, good spot for an Over). "
                      "**Rank {n} = allows the least** (toughest defense, better for an Under).\n"
                      "- Teams that allow the same share the same rank.\n\n"
                      "*Example:* a team with **Rank (guard) 1** gives up more to opposing guards than any other team.",
        "dvp_note": "What a team allows per game to all opposing players at that position (sum). "
                    "#1 = allows the most. Positions are official EuroLeague (guard/forward/center); "
                    "players without one get an estimate from their stats, and pozicije.csv overrides both.",
        "dvp_next": "🎯 {opp} vs **{pos}**: allows **{v}** {s} per game (rank **{r}/{n}**)",
        "rank_by": "Defense rank", "rank_pos": "By position (DvP)", "rank_team": "Whole defense",
        "no_pos": "Player positions not downloaded yet. Click **Refresh data**.",
    },
}
T4 = {
    "sr": {
        "nav_home": "🏠\nPočetna", "nav_props": "🎯\nProps", "nav_players": "👤\nIgrači", "nav_league": "🏀\nLiga",
        "sub_picks": "🔥 Predlozi", "sub_lines": "📋 Linije",
        "src_book": "📡 Kladionice", "src_manual": "✍️ Ručni unos", "source": "Izvor linija",
        "all_stats": "Sve", "line_book": "Linije kladionica (📡)",
        "line_book_help": "Samo igrači za koje kladionice već nude liniju.",
        "book_none": "Još nema linija kladionica za predstojeće utakmice. Linije se preuzimaju jednom dnevno "
                     "(obično ujutru na dan utakmice) – do tada koristi ✍️ Ručni unos.",
        "book_only_el": "Linije kladionica trenutno postoje samo za Evroligu.",
        "book_note": "Prave linije igrača sa kladionica (prosek ~50 kladionica, OddsPapi), preuzete {t}. "
                     "Za svaku liniju aplikacija računa da li igrač dolazi Over ili Under.",
        "book_src": "{n} kladionica", "book_alt": "druge linije:",
        "lines_note": "Nalepi linije sa kladionice – jedan red po igraču: **igrač, statistika, linija, kvota Over, "
                      "kvota Under** (kvote nisu obavezne). Radi sa bilo kojom kladionicom; decimalni zarez je u redu.",
        "lines_input": "Linije", "lines_file": "…ili ubaci CSV fajl", "lines_btn": "Proveri linije",
        "lines_clear": "Obriši", "lines_example": "Ubaci primer",
        "lines_unmatched": "Nisam prepoznao ({n}): {x}", "lines_count": "Prepoznato {n} linija",
        "lines_none": "Nalepi linije iznad (ili klikni **Ubaci primer**) – provera ide odmah.",
        "lines_sort": "Sortiraj", "sort_value": "💰 Vrednost", "sort_signal": "Jačina predloga",
        "odds": "Kvota", "book_p": "Kladionica", "our_p": "Naša procena", "value": "Vrednost",
        "value_tag": "💰 Vredno", "no_value": "nije isplativo", "best_side": "Bolja strana",
        "value_help": "Kladionica = šansa iz kvota bez marže. Naša procena = procenat pogodaka u posl. 10 utakmica, "
                      "ublažen ka 50% (mali uzorak). Vrednost = koliko se u proseku vraća na uloženih 100: "
                      "+10% znači da kvota plaća više nego što bi trebalo po statistici. Gruba procena, ne garancija.",
        "stat_unknown": "nepoznata statistika", "player_unknown": "nepoznat igrač", "sub_props": "🎯 Igrač", "sub_scan": "🔎 Skener", "sub_round": "⭐ Kolo",
        "sub_player": "👤 Igrač", "sub_cmp": "⚖️ Poređenje", "sub_without": "🔄 Bez saigrača",
        "sub_leaders": "🏆 Lideri", "sub_sched": "📅 Raspored", "sub_teams": "🛡️ Timovi", "sub_injuries": "🚑 Povrede",
        "home_next": "Sledeće kolo · Kolo {r}", "home_games": "{n} utakmica", "home_games_h": "Utakmice",
        "home_picks_h": "Najjači predlozi", "home_inj_h": "🚑 Ne igraju", "home_form_h": "🔥 U formi",
        "home_form_sub": "posl. 3 vs sezona · poeni", "go_sched": "Raspored →", "go_picks": "Svi predlozi →",
        "go_inj": "Sve povrede →", "go_form": "Lideri →",
        "chip_fire": "🔥 {n} jaka Over", "chip_ice": "🧊 {n} jaka Under", "chip_out": "🚑 {n} ne igra",
        "chip_games": "🏀 {g} odigrano · {p} igrača",
        "total_s": "Total", "as_table": "Prikaži kao tabelu", "more": "Ostalo ▾", "show_more": "Prikaži još",
        "filters": "⚙️ Još filtera", "no_next_round": "Nema zakazanih utakmica.", "home_no_picks":
        "Još nema dovoljno utakmica za predloge.", "days": "Pon,Uto,Sre,Čet,Pet,Sub,Ned",
        "check_one": "🔍 Proveri jednog igrača", "inj_none_round": "Nema prijavljenih povreda za sledeće kolo.",
        "home_picks_note": "Poeni, skokovi i asistencije · linija ≈ prosek igrača",
    },
    "en": {
        "nav_home": "🏠\nHome", "nav_props": "🎯\nProps", "nav_players": "👤\nPlayers", "nav_league": "🏀\nLeague",
        "sub_picks": "🔥 Picks", "sub_lines": "📋 Lines",
        "src_book": "📡 Bookmakers", "src_manual": "✍️ Manual input", "source": "Lines source",
        "all_stats": "All", "line_book": "Bookmaker lines (📡)",
        "line_book_help": "Only players bookmakers already offer a line for.",
        "book_none": "No bookmaker lines for upcoming games yet. Lines are fetched once a day "
                     "(usually on game-day morning) – use ✍️ Manual input until then.",
        "book_only_el": "Bookmaker lines are currently available for EuroLeague only.",
        "book_note": "Real player lines from bookmakers (consensus of ~50 books, OddsPapi), fetched {t}. "
                     "For every line the app tells whether the player goes Over or Under.",
        "book_src": "{n} bookmakers", "book_alt": "other lines:",
        "lines_note": "Paste bookmaker lines – one row per player: **player, stat, line, Over odds, Under odds** "
                      "(odds optional). Works with any bookmaker; decimal comma is fine.",
        "lines_input": "Lines", "lines_file": "…or upload a CSV file", "lines_btn": "Check lines",
        "lines_clear": "Clear", "lines_example": "Insert example",
        "lines_unmatched": "Not recognized ({n}): {x}", "lines_count": "Recognized {n} lines",
        "lines_none": "Paste lines above (or click **Insert example**) – they are checked right away.",
        "lines_sort": "Sort", "sort_value": "💰 Value", "sort_signal": "Pick strength",
        "odds": "Odds", "book_p": "Bookmaker", "our_p": "Our estimate", "value": "Value",
        "value_tag": "💰 Value", "no_value": "no value", "best_side": "Better side",
        "value_help": "Bookmaker = probability from the odds without margin. Our estimate = hit rate over the last "
                      "10 games, pulled toward 50% (small sample). Value = average return per 100 staked: +10% means "
                      "the odds pay more than the stats say they should. Rough estimate, not a guarantee.",
        "stat_unknown": "unknown stat", "player_unknown": "unknown player", "sub_props": "🎯 Player", "sub_scan": "🔎 Scanner", "sub_round": "⭐ Round",
        "sub_player": "👤 Player", "sub_cmp": "⚖️ Compare", "sub_without": "🔄 Without teammate",
        "sub_leaders": "🏆 Leaders", "sub_sched": "📅 Schedule", "sub_teams": "🛡️ Teams", "sub_injuries": "🚑 Injuries",
        "home_next": "Next round · Round {r}", "home_games": "{n} games", "home_games_h": "Games",
        "home_picks_h": "Strongest picks", "home_inj_h": "🚑 Out", "home_form_h": "🔥 In form",
        "home_form_sub": "last 3 vs season · points", "go_sched": "Schedule →", "go_picks": "All picks →",
        "go_inj": "All injuries →", "go_form": "Leaders →",
        "chip_fire": "🔥 {n} strong Over", "chip_ice": "🧊 {n} strong Under", "chip_out": "🚑 {n} out",
        "chip_games": "🏀 {g} played · {p} players",
        "total_s": "Total", "as_table": "Show as table", "more": "More ▾", "show_more": "Show more",
        "filters": "⚙️ More filters", "no_next_round": "No scheduled games.", "home_no_picks":
        "Not enough games for picks yet.", "days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "check_one": "🔍 Check one player", "inj_none_round": "No injuries reported for the next round.",
        "home_picks_note": "Points, rebounds and assists · line ≈ player average",
    },
}
for _l in T:
    T[_l].update(T2[_l])
    T[_l].update(T3[_l])
    T[_l].update(T4[_l])

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

/* ---------- novi izgled / new look ---------- */
.app-logo {display:flex; align-items:center; gap:9px; font-size:1.45rem; font-weight:800; line-height:1;}
.app-logo b {color:#f59e0b;}
.st-key-hdr [data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; gap:.5rem !important;}
.st-key-hdr [data-testid="stColumn"] {min-width:0 !important;}
.st-key-hdr [data-testid="stColumn"]:last-child {display:flex; justify-content:flex-end;}
[data-testid="stSegmentedControl"] button, [data-testid="stPills"] button {font-weight:600;}

/* meni: na racunaru red dugmica ispod zaglavlja */
.st-key-bottomnav {border-bottom:1px solid rgba(128,128,128,.22); padding-bottom:.35rem; margin-bottom:.4rem;}
.st-key-bottomnav [data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; gap:.35rem !important;}
.st-key-bottomnav [data-testid="stColumn"] {min-width:0 !important; flex:1 1 0 !important; width:auto !important;}
.st-key-bottomnav button {border:none !important; background:transparent !important; box-shadow:none !important;
    font-weight:600; opacity:.75; min-height:44px;}
.st-key-bottomnav button:hover {opacity:1; color:#f59e0b !important;}
.st-key-bottomnav button[kind="primary"], .st-key-bottomnav [data-testid="stBaseButton-primary"] {
    color:#f59e0b !important; opacity:1; font-weight:800; border-bottom:3px solid #f59e0b !important;
    border-radius:0 !important;}
.st-key-bottomnav button p {font-size:1rem;}

/* kartice / cards (rade i u svetloj i u tamnoj temi) */
.es-card {background:rgba(128,128,128,.07); border:1px solid rgba(128,128,128,.22); border-radius:16px;
    padding:12px 14px; margin-bottom:10px;}
.es-hero {background:linear-gradient(135deg, rgba(245,158,11,.14), rgba(59,130,246,.08));
    border:1px solid rgba(245,158,11,.30); border-radius:18px; padding:14px 16px; margin:.2rem 0 .6rem;}
.es-hero .t {font-size:.8rem; opacity:.7;} .es-hero .b {font-size:1.2rem; font-weight:800; margin-top:2px;}
.es-hero .b span {color:#f59e0b;}
.es-chips {display:flex; flex-wrap:wrap; gap:6px; margin-top:10px;}
.es-chip {font-size:.75rem; padding:4px 10px; border-radius:12px; background:rgba(245,158,11,.13);
    border:1px solid rgba(245,158,11,.30); color:#d97706; font-weight:600;}
.es-games {display:flex; gap:8px; overflow-x:auto; padding:2px 0 8px; -webkit-overflow-scrolling:touch;}
.es-games::-webkit-scrollbar {height:0;}
.es-game {min-width:122px; background:rgba(128,128,128,.07); border:1px solid rgba(128,128,128,.22);
    border-radius:14px; padding:9px 11px; flex:none;}
.es-game .d {font-size:.7rem; opacity:.65;} .es-game .m {font-weight:800; font-size:.95rem; margin:4px 0 2px;}
.es-game .x {font-size:.72rem; opacity:.85;} .es-game .x b {color:#16a34a;}
.es-row {display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px solid rgba(128,128,128,.18);}
.es-row:last-child {border-bottom:0;}
.es-ico {width:34px; height:34px; border-radius:10px; display:grid; place-items:center; font-size:1.05rem; flex:none;}
.i-fire {background:rgba(245,158,11,.16);} .i-over {background:rgba(34,197,94,.14);}
.i-under {background:rgba(239,68,68,.14);} .i-ice {background:rgba(59,130,246,.16);} .i-none {background:rgba(128,128,128,.12);}
.es-main {flex:1; min-width:0;}
.es-name {font-weight:700; font-size:.9rem;} .es-name span {opacity:.6; font-weight:500; font-size:.78rem;}
.es-sub {font-size:.76rem; opacity:.65; margin-top:1px;}
.es-val {text-align:right; flex:none;} .es-val b {font-size:.88rem;} .es-val div {font-size:.72rem; opacity:.65;}
.c-fire {color:#f59e0b;} .c-over {color:#16a34a;} .c-under {color:#dc2626;} .c-ice {color:#3b82f6;}
.c-none {opacity:.7;}
.es-st {font-size:.7rem; padding:3px 8px; border-radius:10px; white-space:nowrap; font-weight:600;}
.s-out {background:rgba(239,68,68,.15); color:#dc2626;} .s-q {background:rgba(234,179,8,.18); color:#ca8a04;}
.s-l {background:rgba(128,128,128,.15);} .s-ok {background:rgba(34,197,94,.15); color:#16a34a;}
.es-form {display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:8px;}
.es-form .es-card {margin:0;} .es-form .n {font-weight:700; font-size:.8rem;}
.es-form .v {font-size:1.35rem; font-weight:800; color:#16a34a;} .es-form .v.dn {color:#dc2626;}
.es-form .x {font-size:.7rem; opacity:.65;}
/* kartica predloga */
.es-pick {background:rgba(128,128,128,.07); border:1px solid rgba(128,128,128,.22); border-radius:16px;
    padding:12px 14px;}
.es-pick.fire {border-color:rgba(245,158,11,.6);} .es-pick.ice {border-color:rgba(59,130,246,.55);}
.es-pick .hd {display:flex; justify-content:space-between; align-items:flex-start; gap:8px;}
.es-pick .nm {font-weight:800; font-size:1rem;} .es-pick .nm span {font-weight:500; opacity:.6; font-size:.78rem;}
.es-pick .sub {font-size:.78rem; opacity:.7; margin-top:2px;}
.es-tag {font-size:.78rem; font-weight:800; padding:5px 9px; border-radius:10px; white-space:nowrap;}
.t-fire {background:rgba(245,158,11,.17); color:#d97706;} .t-over {background:rgba(34,197,94,.15); color:#16a34a;}
.t-under {background:rgba(239,68,68,.15); color:#dc2626;} .t-ice {background:rgba(59,130,246,.17); color:#2563eb;}
.t-none {background:rgba(128,128,128,.14);}
.es-bar {height:6px; background:rgba(128,128,128,.18); border-radius:6px; margin:10px 0 6px; position:relative;
    overflow:hidden;}
.es-bar i {position:absolute; top:0; bottom:0; border-radius:6px;}
.es-bar u {position:absolute; left:50%; top:-2px; bottom:-2px; width:1px; background:rgba(128,128,128,.6);}
.es-stats {display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-top:8px;}
.es-stats div {background:rgba(128,128,128,.10); border-radius:10px; padding:6px 4px; text-align:center;}
.es-stats b {display:block; font-size:.9rem;} .es-stats span {font-size:.66rem; opacity:.65;}
.es-why {font-size:.76rem; margin-top:9px; line-height:1.55; opacity:.9;}
.es-warn {font-size:.76rem; margin-top:8px; padding:6px 9px; border-radius:9px; background:rgba(234,179,8,.15);}
.es-grid {display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:10px;}
.es-h {display:flex; justify-content:space-between; align-items:baseline; margin:1rem 0 .4rem;}
.es-h b {font-size:1.02rem;}

/* izabrano dugme narandzasto (umesto crvenog) / active state in brand orange */
[data-testid="stBaseButton-segmented_controlActive"], [data-testid="stBaseButton-pillsActive"] {
    border-color:#f59e0b !important; background:rgba(245,158,11,.13) !important;}
[data-testid="stBaseButton-segmented_controlActive"] *, [data-testid="stBaseButton-pillsActive"] * {
    color:#f59e0b !important;}
div[class*="st-key-row_"] button, div[class*="st-key-row_"] button:hover {border:none !important;
    background:transparent !important; box-shadow:none !important;}

@media (max-width: 640px) {
  .block-container {padding-bottom: 6.5rem !important;}
  .st-key-hdr [data-testid="stButtonGroup"] button {padding:.2rem .55rem !important; min-height:2rem;}
  .st-key-hdr [data-testid="stButtonGroup"] button p {font-size:.78rem !important;}
  /* podmeni u jednom redu, pomera se prstom ako ne stane */
  div[class*="st-key-sub_"] [data-testid="stButtonGroup"] > div {flex-wrap:nowrap !important; overflow-x:auto;
      scrollbar-width:none;}
  div[class*="st-key-sub_"] [data-testid="stButtonGroup"] > div::-webkit-scrollbar {height:0;}
  div[class*="st-key-sub_"] [data-testid="stButtonGroup"] button {padding:.3rem .55rem !important; flex:none;}
  div[class*="st-key-sub_"] [data-testid="stButtonGroup"] button p {font-size:.8rem !important; white-space:nowrap;}
  .app-logo {font-size:1.2rem;}
  .app-logo svg {width:26px; height:26px;}
  /* meni zalepljen za dno ekrana na telefonu */
  .st-key-bottomnav {position:fixed; left:0; right:0; bottom:0; z-index:999990; margin:0;
      padding:4px 6px calc(6px + env(safe-area-inset-bottom)); border-bottom:none;
      border-top:1px solid rgba(128,128,128,.25); backdrop-filter:blur(10px);}
  .st-key-bottomnav button {min-height:52px; padding:2px 0 !important;}
  .st-key-bottomnav button p {font-size:.72rem; line-height:1.25; white-space:pre-line;}
  .st-key-bottomnav button[kind="primary"], .st-key-bottomnav [data-testid="stBaseButton-primary"] {
      border-bottom:none !important;}
  .es-grid {grid-template-columns:1fr;}
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


with st.container(key="hdr"):
    _h1, _h2 = st.columns([1, 1], vertical_alignment="center")
    _h1.markdown(f'<div class="app-logo">{LOGO.format(s=30)}<span>Euro<b>Stats</b></span></div>',
                 unsafe_allow_html=True)
    liga_code = _h2.segmented_control(tr("league"), list(LIGE), default="E", key="liga",
                                      format_func=lambda c: COMP_NAME[lang][c],
                                      label_visibility="collapsed") or "E"
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


# skracenice timova (zvanicna sifra -> prikaz); skracenice.csv ih moze promeniti
DEFAULT_ABBR = {
    "E": {"PAN": "PAO", "ULK": "FBT", "OLY": "OLY", "PAM": "VBC", "RED": "CZV", "HTA": "HTA", "VIR": "VIR", "DUB": "DUB",
          "MAD": "RMB", "BAR": "BAR", "BES": "BJK", "PAR": "PAR", "IST": "EFS", "ZAL": "ZAL", "MUN": "BAY", "TEL": "MTA",
          "ASV": "ASV", "PRS": "PBB", "MIL": "MIL", "BAS": "KBA"},
    "U": {"ARI": "ARI", "JER": "JLM", "RIG": "RIG", "LEM": "MSB", "BGS": "BUR", "TRT": "DER", "RTK": "ROS", "LJU": "COL",
          "VNC": "URV", "TNF": "LLT", "CLU": "UBT", "FRA": "SKY", "SIA": "SIA", "LLI": "LDN", "MRO": "RMA", "TTK": "TTA",
          "NAP": "NAP", "BUR": "TOF", "NIN": "CHE", "BUD": "BUD", "WRO": "WKS", "TRN": "TRE", "KLA": "NEP", "BOU": "JLB",
          "BAH": "BKS", "LKB": "LIE", "ULM": "ULM", "PAO": "PBC", "MAN": "MAN", "BCR": "ROM", "BOS": "BOS", "BLK": "BLK"},
}


def load_abbr():
    """Skracenice: ugradjene (DEFAULT_ABBR) + skracenice.csv pored app.py, koji ima prednost.

    skracenice.csv kolone: liga,stara,nova[,tim]. Menja se samo prikaz, ne baza.
    """
    out = {(liga, k): v for liga, m in DEFAULT_ABBR.items() for k, v in m.items()}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skracenice.csv")
    try:
        m = pd.read_csv(path, dtype=str).fillna("")
        out.update({(r.liga.strip(), r.stara.strip()): r.nova.strip()
                    for r in m.itertuples() if r.nova.strip()})
    except Exception:
        pass
    return out


ABBR = load_abbr()


def remap(frame, cols, comp_col="comp"):
    """Zameni zvanicne sifre timova skracenicama iz skracenice.csv (u datom DataFrame-u)."""
    if not ABBR or frame is None or frame.empty:
        return frame
    for c in cols:
        if c in frame.columns:
            frame[c] = [ABBR.get((cp, x), x) for cp, x in zip(frame[comp_col], frame[c])]
    return frame


if df.empty:
    st.info(tr("no_data"))
    st.stop()
df = remap(df, ["team", "opp"])

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


sched = remap(load_sched(tuple(comps)), ["homecode", "awaycode"])
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


df["_pid"] = df["player_id"].str.strip()
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
    df = df.merge(per_g.rename(columns={"player_id": "_pid"}), on=["comp", "gamecode", "_pid"], how="left")
    has_pbp = [(c, gc) in pbp_games for c, gc in zip(df["comp"], df["gamecode"])]
    per_cols = ["PTS_Q1", "PTS_H1", "REB_H1", "AST_H1", "PRA_H1", "3PM_H1"]
    df.loc[has_pbp, per_cols] = df.loc[has_pbp, per_cols].fillna(0)   # bez akcija u pbp = 0
shots = load_shots(tuple(comps))


@st.cache_data(ttl=300)
def load_onoff(comps: tuple):
    try:
        o, l = es.load_onoff(list(comps)), es.load_lineups(list(comps))
        o["player_id"] = o["player_id"].str.strip()
        return o, l
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


onoff, lineups = load_onoff(tuple(comps))
onoff, lineups = remap(onoff, ["team"]), remap(lineups, ["team"])

POS_MAP = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}


@st.cache_data(ttl=3600)
def load_pos(comps: tuple) -> pd.DataFrame:
    try:
        p = es.load_positions(list(comps))
        p["player_id"] = p["player_id"].str.strip()
        return p
    except Exception:
        return pd.DataFrame()


def manual_positions():
    """pozicije.csv pored app.py: kolone igrac (ime kao u aplikaciji ili ID), pozicija (PG/SG/SF/PF/C ili G/F/C)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pozicije.csv")
    if not os.path.exists(path):
        return {}
    try:
        m = pd.read_csv(path)
        m.columns = [c.strip().lower() for c in m.columns]
        who, what = m.columns[0], m.columns[1]
        return {str(a).strip().upper(): POS_MAP.get(str(b).strip().upper())
                for a, b in zip(m[who], m[what]) if POS_MAP.get(str(b).strip().upper())}
    except Exception:
        return {}


def estimate_positions(frame, known):
    """Procena G/F/C iz statistike po 36 min (k najblizih poznatih igraca)."""
    d = frame[frame["Minutes"] > 0]
    cols = ["Minutes", "TotalRebounds", "OffensiveRebounds", "Assistances", "BlocksFavour",
            "FieldGoalsAttempted3", "FieldGoalsAttempted2", "FoulsCommited"]
    if d.empty or any(c not in d for c in cols):
        return {}
    g = d.groupby("_pid")[cols].sum()
    m = g["Minutes"].clip(lower=1)
    f = pd.DataFrame({"reb": g["TotalRebounds"] / m, "oreb": g["OffensiveRebounds"] / m,
                      "ast": g["Assistances"] / m, "blk": g["BlocksFavour"] / m,
                      "tpa": g["FieldGoalsAttempted3"] / m,
                      "tsh": g["FieldGoalsAttempted3"] / (g["FieldGoalsAttempted3"]
                                                         + g["FieldGoalsAttempted2"]).clip(lower=1),
                      "pf": g["FoulsCommited"] / m})
    tr_ids = f.index.intersection(list(known))
    if len(tr_ids) < 30:
        return {}
    mu, sd = f.loc[tr_ids].mean(), f.loc[tr_ids].std().replace(0, 1)
    z = (f - mu) / sd
    zt, yt, wt = z.loc[tr_ids].values, np.array([known[i] for i in tr_ids]), np.sqrt(m.loc[tr_ids].values)
    out = {}
    for pid in f.index.difference(tr_ids):
        dist = np.sqrt(((zt - z.loc[pid].values) ** 2).sum(1))
        idx = np.argsort(dist)[:9]
        out[pid] = pd.Series(wt[idx] / (dist[idx] + 0.3)).groupby(yt[idx]).sum().idxmax()
    return out


pos_tbl = load_pos(tuple(comps))
official = dict(zip(pos_tbl["player_id"], pos_tbl["pos"])) if not pos_tbl.empty else {}
manual = manual_positions()
estimated = estimate_positions(df, official) if official else {}
names_up = df.drop_duplicates("_pid").set_index("_pid")["player"].str.upper()


def player_pos(pid):
    m = manual.get(pid.upper()) or manual.get(names_up.get(pid, ""))
    if m:
        return m, "manual"
    if pid in official:
        return official[pid], "api"
    if pid in estimated:
        return estimated[pid], "est"
    return None, None


_pp = {pid: player_pos(pid) for pid in df["_pid"].unique()}
df["pos"] = df["_pid"].map(lambda x: _pp[x][0])
df["pos_src"] = df["_pid"].map(lambda x: _pp[x][1])
HAS_POS = df["pos"].notna().any()


# ---------- povrede / injuries ----------
INJ_STATUS = {"out": "out", "ne igra": "out", "doubtful": "doubtful", "verovatno ne igra": "doubtful",
              "questionable": "questionable", "upitan": "questionable", "gtd": "gtd",
              "likely_out": "likely_out", "available": "available", "igra": "available", "info": "info"}
INJ_HIDE = {"out", "doubtful"}


@st.cache_data(ttl=3600, show_spinner=False)
def live_injury_report():
    """Aplikacija sama cita Euroleague izvestaj, najvise jednom na sat (GitHub serveri su blokirani).
    Brzo odustaje (1 pokusaj, 8 s) da ne uspori sajt; tada ostaje povrede.json iz repoa."""
    try:
        import povrede as pv
        return pv.fetch_report(tries=1, timeout=8) or {}
    except Exception:
        return {}


def load_injuries():
    """Izvestaj: sveze procitan sa sajta ili povrede.json; povrede.csv (rucno) ima prednost."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = {}
    try:
        rep_ = json.load(open(os.path.join(here, "povrede.json"), encoding="utf-8"))
    except Exception:
        rep_ = {}
    live = live_injury_report()
    if live.get("players") is not None and (live.get("published") or "") >= (rep_.get("published") or ""):
        rep_ = live
    for p in rep_.get("players", []):
        gc = p.get("gamecode")
        if not p.get("player_id") or (rep_.get("comp", "E"), gc) in played_codes:
            continue      # nepovezan igrac ili utakmica je vec odigrana
        out[p["player_id"]] = {"status": p["status"], "note": p.get("note", ""),
                               "confirmed": p.get("confirmed", False), "src": "report"}
    try:
        m = pd.read_csv(os.path.join(here, "povrede.csv"), dtype=str).fillna("")
        m.columns = [c.strip().lower() for c in m.columns]
        for r in m.itertuples(index=False):
            who, st_ = str(r[0]).strip().upper(), INJ_STATUS.get(str(r[1]).strip().lower())
            pid = who if who in _pp else next((k for k, v in names_up.items() if v == who), None)
            if pid and st_:
                out[pid] = {"status": st_, "note": str(r[2]) if len(r) > 2 else "", "confirmed": True,
                            "src": "manual"}
    except Exception:
        pass
    return rep_, out




def inj_status(pid):
    return INJ.get(str(pid).strip(), {}).get("status")


def inj_badge(pid):
    st_ = inj_status(pid)
    return tr(f"inj_{st_}") if st_ and st_ != "info" else ""


def inj_box(pid):
    i = INJ.get(str(pid).strip())
    if not i:
        return
    txt = f"**{tr('inj_' + i['status'])}**" + (f" · {i['note']}" if i.get("note") else "")
    if i["src"] == "manual":
        txt += f" ({tr('inj_manual')})"
    (st.error if i["status"] in INJ_HIDE else st.success if i["status"] == "available"
     else st.warning if i["status"] != "info" else st.info)(txt)


def pos_label(pid, short=False):
    pos, src = _pp.get(str(pid).strip(), (None, None))
    if not pos:
        return ""
    lbl = tr(f"pos1_{pos}")
    if src == "est" and not short:
        lbl += f" ({tr('pos_est')})"
    elif src == "manual" and not short:
        lbl += f" ({tr('pos_manual')})"
    return lbl
if not onoff.empty:
    df = df.merge(onoff[["comp", "gamecode", "player_id", "pm"]].rename(
        columns={"player_id": "_pid", "pm": "PlusMinus"}), on=["comp", "gamecode", "_pid"], how="left")
SORT = ["date", "gamecode"]
played_codes = set(zip(df["comp"], df["gamecode"]))
INJ_REPORT, INJ = load_injuries()


def date_lbl(d, opp):
    return f"{d:%d.%m.} {opp}" if pd.notna(d) else opp


stats = {k: NAMES[lang][k] for k in KEYS if k in df.columns}   # kljuc -> prikazani naziv
inv = {v: k for k, v in stats.items()}                          # prikazani naziv -> kljuc
stat_keys = [k for k in stats if k != "Minutes"]
opp_c, stat_c, val_c, res_c = tr("opponent"), tr("statistic"), tr("value"), tr("result")


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


@st.cache_data(ttl=300)
def dvp_table(frame: pd.DataFrame, keys: tuple) -> pd.DataFrame:
    """Prosek po utakmici: koliko tim (opp = odbrana) primi od igraca svake pozicije."""
    keys = [k for k in keys if k in frame.columns]
    d = frame.dropna(subset=["pos", "opp"])
    if d.empty:
        return pd.DataFrame()
    grp = d.groupby(["comp", "gamecode", "opp", "pos"])[keys].sum(min_count=1)
    games = frame.dropna(subset=["opp"])[["comp", "gamecode", "opp"]].drop_duplicates()
    full = pd.MultiIndex.from_tuples(
        [(c, g, o, p) for c, g, o in games.itertuples(index=False) for p in ("G", "F", "C")],
        names=["comp", "gamecode", "opp", "pos"])
    grp = grp.reindex(full)
    for k in keys:   # pozicija bez igraca = 0, ali samo ako utakmica ima podatak za tu statistiku
        has = grp[k].notna().groupby(level=[0, 1, 2]).transform("any")
        grp.loc[has & grp[k].isna(), k] = 0
    out = grp.groupby(level=["comp", "opp", "pos"]).mean()
    out.index = out.index.set_names(["comp", "team", "pos"])
    return out


dvp = dvp_table(df, tuple(prop_stats)) if HAS_POS else pd.DataFrame()


def dvp_rank(comp, key, pos, ascending=False):
    """(prosek, rang) po timu za poziciju; rang 1 = prima najvise (ili najmanje ako ascending)."""
    if dvp.empty or key not in dvp.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    try:
        v = dvp.loc[(comp, slice(None), pos), key].droplevel([0, 2]).dropna()
    except KeyError:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return v, v.rank(ascending=ascending, method="min")


def team_rank(comp, key):
    ta = tgames[tgames["comp"] == comp].groupby("team")[f"{key}_a"].mean().dropna()
    return ta, ta.rank(ascending=False, method="min")


def signal(pg, key, line, comp, nxt=None):
    """Over/Under signal za sledecu utakmicu igraca.

    pg = utakmice igraca (sortirane), nxt = next_game(...) ili None.
    Vraca dict: score (-100..100, + = Over), label, reasons (lista teksta).
    Tezine: hit-rate 30%, medijana 25%, protivnik 20%, teren 15%, minuti 10%.
    """
    v = pg[key].dropna()
    n = len(v)
    if n < 5:
        return {"score": 0, "label": tr("sig_few"), "reasons": [], "hit": None, "factors": [], "wsum": 1}
    parts, reasons, factors = [], [], []
    sd = max(float(v.std(ddof=0)), 1.0)

    last = v.tail(10)
    h = float((last > line).mean())
    parts.append((0.30, (h - 0.5) * 2))
    reasons.append((h - 0.5, tr("r_hit", o=int((last > line).sum()), t=len(last))))
    factors.append((tr("f_hit"), 0.30, (h - 0.5) * 2, reasons[-1][1]))

    med = float(v.median())
    parts.append((0.25, float(np.clip((med - line) / sd, -1, 1))))
    reasons.append((med - line, tr("r_med", m=med, l=line)))
    factors.append((tr("f_med"), 0.25, parts[-1][1], reasons[-1][1]))

    if nxt:
        o = nxt["opp"]
        pos = _pp.get(str(pg["player_id"].iloc[-1]).strip(), (None, None))[0]
        vals, rk = dvp_rank(comp, key, pos) if pos else (pd.Series(dtype=float), pd.Series(dtype=float))
        plabel = tr(f"pos1_{pos}").lower() if pos else ""
        if o not in rk.index:
            vals, rk = team_rank(comp, key)
            plabel = ""
        if o in rk.index and len(rk) > 1:
            N = len(rk)
            x = (N + 1 - 2 * float(rk[o])) / (N - 1)
            parts.append((0.20, x))
            reasons.append((x, tr("r_opp", o=o, r=int(rk[o]), p=plabel).strip()))
            factors.append((tr("f_opp"), 0.20, x, reasons[-1][1] + f" · {vals[o]:.1f}/utakm."))
        if "Home" in pg:
            ven = pg[pg["Home"] == (1 if nxt["home"] else 0)][key].dropna()
            if len(ven) >= 2:
                x = float(np.clip((ven.mean() - line) / sd, -1, 1))
                parts.append((0.15, x))
                reasons.append((x, tr("r_ven", v=tr("home") if nxt["home"] else tr("away"), a=ven.mean())))
                factors.append((tr("f_ven"), 0.15, x, reasons[-1][1]))

    mins = pg["Minutes"].dropna()
    if len(mins) >= 4:
        dm = float(mins.tail(3).mean() - mins.mean())
        x = float(np.clip(dm / max(0.15 * mins.mean(), 2.0), -1, 1))
        parts.append((0.10, x))
        factors.append((tr("f_min"), 0.10, x, tr("r_min", d=dm)))
        if abs(dm) >= 1:
            reasons.append((x, tr("r_min", d=dm)))

    score = 100 * sum(w * x for w, x in parts) / sum(w for w, _ in parts)
    if score >= 55 and h >= 0.7:
        label = tr("sig_fire")
    elif score >= 25:
        label = tr("sig_over")
    elif score <= -55 and h <= 0.3:
        label = tr("sig_ice")
    elif score <= -25:
        label = tr("sig_under")
    else:
        label = tr("sig_none")
    direction = 1 if score >= 0 else -1
    txt = [("✔ " if np.sign(x) == direction else "✘ ") + r for x, r in reasons if x != 0]
    return {"score": int(round(score)), "label": label, "reasons": txt, "hit": h,
            "factors": factors, "wsum": sum(w for w, _ in parts)}


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


def render_injuries():
    """Tabela povreda za sledece kolo (iz izvestaja + povrede.csv)."""
    if not INJ_REPORT:
        st.caption(tr("inj_none"))
    else:
        pub = pd.to_datetime(INJ_REPORT.get("published"), errors="coerce", utc=True)
        fet = pd.to_datetime(INJ_REPORT.get("fetched"), errors="coerce", utc=True)
        fmt = lambda x: x.tz_convert("Europe/Belgrade").strftime("%d.%m. %H:%M") if pd.notna(x) else "—"
        st.caption(tr("inj_src", t=INJ_REPORT.get("title", "Injury report"),
                      u=INJ_REPORT.get("source") or "https://www.euroleaguebasketball.net/euroleague/news/",
                      p=fmt(pub), f=fmt(fet)))
        comp_r = INJ_REPORT.get("comp", "E")
        rows_i = []
        for tm in INJ_REPORT.get("teams", []):
            if (comp_r, tm.get("gamecode")) in played_codes or comp_r not in comps:
                continue
            code = ABBR.get((comp_r, tm.get("team")), tm.get("team") or tm.get("label"))
            pl = [p for p in INJ_REPORT.get("players", []) if p.get("team") == tm.get("team")
                  and p.get("status") != "info"]
            if not pl:
                rows_i.append({tr("team"): code, tr("player"): "",
                               "Status": tr("inj_full") if tm.get("full") else
                               (tr("inj_not_sent") if not tm.get("reported") else ""), tr("detail"): ""})
            for p in pl:
                rows_i.append({tr("team"): code, tr("player"): p.get("db_name") or p["name"],
                               "Status": tr("inj_" + p["status"]) + ("" if p.get("confirmed") or
                                                                      p["status"] == "likely_out" else ""),
                               tr("detail"): p.get("note", "")})
        if rows_i:
            st.dataframe(pd.DataFrame(rows_i), hide_index=True, width="stretch",
                         height=min(420, 38 + 35 * len(rows_i)),
                         column_config={tr("detail"): st.column_config.TextColumn(width="large")})


# ---------- navigacija / navigation ----------
SECTIONS = {"home": ["home"], "props": ["picks", "lines", "props", "scan", "round"],
            "players": ["player", "cmp", "without", "leaders"], "league": ["sched", "teams", "injuries"]}


def goto(sec, sub=None):
    st.session_state["sec"] = sec
    if sub:
        st.session_state[f"sub_{sec}"] = sub


SEC = st.session_state.setdefault("sec", "home")
_theme = getattr(getattr(st.context, "theme", None), "type", None) or "dark"
st.markdown(f"<style>@media (max-width: 640px) {{.st-key-bottomnav {{background:"
            f"{'rgba(255,255,255,.96)' if _theme == 'light' else 'rgba(14,17,23,.96)'};}}}}</style>",
            unsafe_allow_html=True)
with st.container(key="bottomnav"):
    for _c, _k in zip(st.columns(4), SECTIONS):
        _c.button(tr(f"nav_{_k}"), key=f"nav_{_k}", type="primary" if SEC == _k else "secondary",
                  width="stretch", on_click=goto, args=(_k,))

if SEC == "home":
    PAGE = "home"
else:
    _subs, _sk = SECTIONS[SEC], f"sub_{SEC}"
    if st.session_state.get(_sk) not in _subs:
        st.session_state[_sk] = st.session_state.get(_sk + "_last", _subs[0])
    PAGE = st.segmented_control("nav", _subs, key=_sk, format_func=lambda k: tr(f"sub_{k}"),
                                label_visibility="collapsed") or _subs[0]
    st.session_state[_sk + "_last"] = PAGE


# ---------- novi izgled: pomocne funkcije / new look helpers ----------
import html as _html

SIG_COLOR = {"fire": "#f59e0b", "over": "#22c55e", "under": "#ef4444", "ice": "#3b82f6", "none": "#94a3b8"}
st.markdown("""<style>
div[class*="st-key-row_"] [data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; align-items:baseline;}
div[class*="st-key-row_"] [data-testid="stColumn"] {min-width:0 !important;}
div[class*="st-key-row_"] [data-testid="stColumn"]:last-child {display:flex; justify-content:flex-end;}
div[class*="st-key-row_"] button {padding:0 !important; min-height:0 !important; color:#f59e0b !important;}
div[class*="st-key-row_"] button p {font-size:.8rem !important;}
</style>""", unsafe_allow_html=True)


def esc(x):
    return _html.escape(str(x))


def sig_class(label):
    return {tr("sig_fire"): "fire", tr("sig_over"): "over", tr("sig_under"): "under",
            tr("sig_ice"): "ice"}.get(label, "none")


def short_name(full):
    last = str(full).split(",")[0].strip()
    return last.title()


def nice_name(full):
    last, _, first = str(full).partition(",")
    return f"{first.strip().title()} {last.strip().title()}".strip()


def day_time(d, t):
    if pd.isna(d):
        return t or ""
    return f"{tr('days').split(',')[d.weekday()]} {d:%d.%m.} {t or ''}".strip()


def section_head(title, btn=None, target=None, key=None, sub=None):
    with st.container(key=f"row_{key}"):
        c1, c2 = st.columns([3, 2])
        c1.markdown(f"**{title}**" + (f"  \n<span style='font-size:.75rem;opacity:.65'>{esc(sub)}</span>"
                                      if sub else ""), unsafe_allow_html=True)
        if btn:
            c2.button(btn, key=f"go_{key}", type="tertiary", on_click=goto, args=target)


def next_round_games(comp):
    """(kolo, utakmice) prvog neodigranog kola."""
    if sched.empty:
        return None, pd.DataFrame()
    s_ = sched[sched["comp"] == comp]
    s_ = s_[[(comp, gc) not in played_codes and p == 0 for gc, p in zip(s_["gamecode"], s_["played"])]]
    if s_.empty:
        return None, s_
    rnd = int(s_["gameday"].min())
    return rnd, s_[s_["gameday"] == rnd].sort_values(["date", "startime"])


def game_total(comp, h, a, pk="Points", line=None):
    """Projekcija ukupnih poena i predlog za meč (ista logika kao u Rasporedu)."""
    tc = tgames[tgames["comp"] == comp].dropna(subset=[pk, f"{pk}_a"])
    if tc.empty:
        return None, None, None
    tc = tc.assign(_tot=tc[pk] + tc[f"{pk}_a"])
    if line is None:
        line = float(np.floor(tc["_tot"].mean()) + 0.5)
    sc_, al_ = tc.groupby("team")[pk].mean(), tc.groupby("team")[f"{pk}_a"].mean()
    if h not in sc_.index or a not in sc_.index:
        return None, None, line
    over = tc.groupby("team")["_tot"].apply(lambda x: 100 * (x > line).mean())
    proj = (sc_[h] + al_[a]) / 2 + (sc_[a] + al_[h]) / 2
    x1 = float(np.clip((proj - line) / 8, -1, 1))
    x2 = (over[h] + over[a]) / 100 - 1
    sc = 100 * (0.5 * x1 + 0.5 * x2)
    lab = (tr("sig_fire") if sc >= 55 and min(over[h], over[a]) >= 70 else tr("sig_over") if sc >= 25 else
           tr("sig_ice") if sc <= -55 and max(over[h], over[a]) <= 30 else tr("sig_under") if sc <= -25
           else tr("sig_none"))
    return round(proj, 1), lab, line


def make_pick(comp, pid, pg, key, line, nxt):
    """Jedan predlog sa svim podacima za karticu i tabelu."""
    v = pg[key].dropna()
    sg = signal(pg, key, line, comp, nxt)
    last = v.tail(10)
    pos = _pp.get(str(pid).strip(), (None, None))[0]
    dv, dr = dvp_rank(comp, key, pos) if pos else (pd.Series(dtype=float), pd.Series(dtype=float))
    plabel = tr(f"pos1_{pos}").lower() if pos else ""
    if not nxt or nxt["opp"] not in dr.index:
        dv, dr = team_rank(comp, key)
        plabel = ""
    o = nxt["opp"] if nxt else None
    return {
        "label": sg["label"], "cls": sig_class(sg["label"]), "score": sg["score"], "reasons": sg["reasons"],
        "player": pg["player"].iloc[-1], "team": pg["team"].iloc[-1], "pid": pid,
        "pos": pos_label(pid, short=True), "key": key, "stat": prop_stats.get(key, key), "line": line,
        "opp": o, "home": nxt["home"] if nxt else None,
        "when": day_time(nxt["date"], nxt["time"]) if nxt else "",
        "hit": f"{int((last > line).sum())}/{len(last)}", "hit_pct": sg["hit"],
        "median": float(v.median()), "avg": float(v.mean()),
        "dvp": f"#{int(dr[o])}" if o in dr.index else "–", "dvp_lbl": f"DvP {plabel}".strip(),
        "inj": inj_badge(pid), "inj_note": INJ.get(str(pid).strip(), {}).get("note", ""),
    }


def pick_card(p, extra=""):
    cls, sc = p["cls"], p["score"]
    w = min(abs(sc), 100) / 2
    left = 50 if sc >= 0 else 50 - w
    direction = "Over" if sc > 0 else "Under" if sc < 0 else "–"
    tag = p["label"] if cls != "none" else p["label"]
    ha = (tr("home") if p["home"] else tr("away")) if p["home"] is not None else ""
    vs = f" · vs {esc(p['opp'])} · {ha} · {esc(p['when'])}" if p["opp"] else ""
    why = " · ".join(esc(r).replace("✔", "<span class='c-over'>✔</span>").replace("✘", "<span class='c-under'>✘</span>")
                     for r in p["reasons"])
    warn = f"<div class='es-warn'>{esc(p['inj'])}{' · ' + esc(p['inj_note'][:90]) if p['inj_note'] else ''}</div>" \
        if p["inj"] else ""
    return (f"<div class='es-pick {cls}'><div class='hd'><div><div class='nm'>{esc(nice_name(p['player']))} "
            f"<span>{esc(p['team'])}{' · ' + esc(p['pos']) if p['pos'] else ''}</span></div>"
            f"<div class='sub'>{esc(p['stat'])} <b>{p['line']:g}</b>{vs}</div></div>"
            f"<div class='es-tag t-{cls}'>{esc(tag)}</div></div>"
            f"<div class='es-bar'><i style='left:{left}%;width:{w}%;background:{SIG_COLOR[cls]}'></i><u></u></div>"
            f"<div class='es-stats'><div><b>{esc(p['hit'])}</b><span>{esc(tr('r_hit', o='', t='').split()[-1])}</span></div>"
            f"<div><b>{p['median']:g}</b><span>{esc(tr('median').lower())}</span></div>"
            f"<div><b>{p['avg']:.1f}</b><span>{esc(tr('avg').lower())}</span></div>"
            f"<div><b>{esc(p['dvp'])}</b><span>{esc(p['dvp_lbl'])}</span></div></div>"
            f"<div class='es-why'>{why}</div>{warn}{extra}</div>")


def pick_row(p):
    """Kompaktan red za pocetnu stranu."""
    cls = p["cls"]
    icon = p["label"].split()[0] if p["label"] else "⚪"
    direction = "Over" if p["score"] > 0 else "Under"
    ha = (tr("home") if p["home"] else tr("away")).lower() if p["home"] is not None else ""
    return (f"<div class='es-row'><div class='es-ico i-{cls}'>{icon}</div><div class='es-main'>"
            f"<div class='es-name'>{esc(short_name(p['player']))} <span>{esc(p['team'])}"
            f"{' · ' + esc(p['pos']) if p['pos'] else ''}</span></div>"
            f"<div class='es-sub'>{esc(p['stat'])} {p['line']:g} · vs {esc(p['opp'])} ({esc(ha)})</div></div>"
            f"<div class='es-val'><b class='c-{cls}'>{direction}</b><div>{esc(p['hit'])}</div></div></div>")


# ---------- linije kladionica (OddsPapi) / bookmaker lines ----------
import linije as LN


@st.cache_data(ttl=600, show_spinner=False)
def load_book_file():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "linije_oddspapi.json"),
                  encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


BOOK_FILE = load_book_file()


def build_book():
    """{player_id: {stat: red}} samo za utakmice koje jos nisu pocele i za izabranu ligu."""
    if not BOOK_FILE.get("lines") or BOOK_FILE.get("comp", "E") not in comps:
        return {}
    now = pd.Timestamp.now(tz="UTC")
    start = {g["fixtureId"]: pd.to_datetime(g.get("start"), utc=True, errors="coerce")
             for g in BOOK_FILE.get("games", [])}
    comp_ = BOOK_FILE.get("comp", "E")
    hist = df[df["comp"] == comp_].sort_values(SORT).groupby("player_id")
    roster = [(pid, g["player"].iloc[-1], g["team"].iloc[-1], float(g["Minutes"].mean())) for pid, g in hist]
    by_name = {LN.norm(n).strip(): pid for pid, n, _, _ in roster}
    out = {}
    for r in BOOK_FILE["lines"]:
        st_ = start.get(r.get("fixtureId"))
        if st_ is not None and pd.notna(st_) and st_ < now:
            continue                      # utakmica je vec pocela/odigrana
        pid = by_name.get(LN.norm(r["player"]).strip()) or LN.match_player(r["player"], roster)
        if pid and r["stat"] in df.columns:
            out.setdefault(pid, {})[r["stat"]] = r
    return out


BOOK = build_book()


def book_line(pid, key):
    return BOOK.get(pid, {}).get(key)


def eval_line(comp, pid, key, line, over=None, under=None, nxt=None):
    """Predlog + vrednost kvote za tacnu liniju (isti racun za rucni unos i OddsPapi)."""
    pg = df[(df["comp"] == comp) & (df["player_id"] == pid)].sort_values(SORT)
    pg = pg.dropna(subset=[key]).reset_index(drop=True) if key in pg else pg.iloc[0:0]
    if pg.empty:
        return None
    nxt = nxt or next_game(comp, pg["team"].iloc[-1])
    p = make_pick(comp, pid, pg, key, float(line), nxt)
    last10 = pg[key].tail(10)
    p_our = LN.our_prob(int((last10 > line).sum()), len(last10))
    ev_o = LN.ev(p_our, over)
    ev_u = LN.ev(1 - p_our, under) if p_our is not None else None
    side, best = None, None
    for sd, e in (("Over", ev_o), ("Under", ev_u)):
        if e is not None and (best is None or e > best):
            side, best = sd, e
    return {**p, "over": over, "under": under, "p_our": p_our, "p_book": LN.book_prob(over, under),
            "ev_side": side, "ev": best}


st.markdown("""<style>
.es-odds {display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-top:9px;}
.es-odds div {background:rgba(245,158,11,.08); border:1px solid rgba(245,158,11,.22); border-radius:10px;
    padding:6px 6px; text-align:center;}
.es-odds span {display:block; font-size:.64rem; opacity:.7;} .es-odds b {font-size:.82rem;}
.es-odds .val {background:rgba(34,197,94,.12); border-color:rgba(34,197,94,.45);}
.es-src {font-size:.7rem; opacity:.65; margin-top:6px;}
@media (max-width:640px) {.es-odds {grid-template-columns:repeat(2,1fr);}}
</style>""", unsafe_allow_html=True)


def odds_block(p):
    if not (p.get("over") or p.get("under")):
        return ""
    o = f"O {p['over']:.2f}" if p.get("over") else "O –"
    u = f"U {p['under']:.2f}" if p.get("under") else "U –"
    book = f"{100 * p['p_book']:.0f}% Over" if p.get("p_book") is not None else "–"
    our = f"{100 * p['p_our']:.0f}% Over" if p.get("p_our") is not None else "–"
    if p.get("ev") is not None and p["ev"] >= 0.05:
        val = (f"<div class='val'><span>{esc(tr('value'))}</span>"
               f"<b class='c-over'>{esc(p['ev_side'])} {100 * p['ev']:+.0f}% 💰</b></div>")
    elif p.get("ev") is not None:
        val = f"<div><span>{esc(tr('value'))}</span><b>{esc(p['ev_side'])} {100 * p['ev']:+.0f}%</b></div>"
    else:
        val = f"<div><span>{esc(tr('value'))}</span><b>–</b></div>"
    src = (f"<div class='es-src'>📡 {esc(tr('book_src', n=p['books']))}"
           f"{' · ' + esc(tr('book_alt')) + ' ' + ' / '.join(f'{x:g}' for x in p['alt_lines']) if len(p.get('alt_lines') or []) > 1 else ''}"
           f"</div>") if p.get("books") else ""
    return (f"<div class='es-odds'><div><span>{esc(tr('odds'))}</span><b>{o} · {u}</b></div>"
            f"<div><span>{esc(tr('book_p'))}</span><b>{book}</b></div>"
            f"<div><span>{esc(tr('our_p'))}</span><b>{our}</b></div>{val}</div>{src}")


@st.cache_data(ttl=600, show_spinner=False)
def book_results(lang_, sig):
    """Procena za svaku liniju kladionice (OddsPapi) iz linije_oddspapi.json."""
    comp_ = BOOK_FILE.get("comp", "E")
    out = []
    for pid, stats in BOOK.items():
        for key, r in stats.items():
            e = eval_line(comp_, pid, key, r["line"], r.get("over"), r.get("under"))
            if e:
                out.append({**e, "books": r.get("books"), "alt_lines": r.get("alt_lines"), "book": True})
    return out


@st.cache_data(ttl=600, show_spinner=False)
def round_picks(comp, keys, lang_, data_sig):
    """Predlozi za sledece kolo (linija kladionice ako postoji, inace ≈ prosek) za date statistike."""
    out = []
    hist = df[df["comp"] == comp].sort_values(SORT)
    for pid, pg in hist.groupby("player_id"):
        if len(pg) < 5 or pg["Minutes"].mean() < 15 or inj_status(pid) in INJ_HIDE:
            continue
        nxt = next_game(comp, pg["team"].iloc[-1])
        if not nxt:
            continue
        for key in keys:
            v = pg[key].dropna() if key in pg else pd.Series(dtype=float)
            if len(v) < 5:
                continue
            bl = book_line(pid, key)
            if bl:   # prava linija kladionice (OddsPapi)
                r_ = eval_line(comp, pid, key, bl["line"], bl.get("over"), bl.get("under"), nxt)
                if r_:
                    out.append({**r_, "book": True})
            else:
                out.append(make_pick(comp, pid, pg, key, float(np.floor(v.mean()) + 0.5), nxt))
    return out


# ---------- igrac / player ----------
if PAGE == "player":
    choice = st.selectbox(tr("search"), players["label"], index=None,
                          placeholder=tr("placeholder"))
    if choice:
        row, g = player_games(choice)
        pl_pos = pos_label(row["player_id"])
        st.subheader(f"{row['player']} – {row['team']}" + (f" · {pl_pos}" if pl_pos else ""))
        inj_box(row["player_id"])
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

        extra = (["PlusMinus"] if "PlusMinus" in g else []) + ["rest"]
        log = g[[opp_c] + list(stats) + extra].rename(
            columns={**stats, "rest": tr("rest"), "PlusMinus": "+/-"}).round(1)
        st.dataframe(log, hide_index=True, width="stretch", height=min(300, 38 + 35 * len(g)))
        csv_button(log, row["player"], "dl_player")

        # plus/minus i clutch
        pid = str(row["player_id"]).strip()
        po = onoff[(onoff["comp"] == row["comp"]) & (onoff["player_id"] == pid)] if not onoff.empty \
            else pd.DataFrame()
        if not po.empty:
            st.markdown(f"**{tr('pm_h')}**")
            c = st.columns(4)
            c[0].metric(tr("pm_avg"), f"{po['pm'].mean():+.1f}", help=tr("pm_help"))
            c[1].metric(tr("pm_40"), f"{2400 * po['pm'].sum() / po['sec'].sum():+.1f}"
                        if po["sec"].sum() else "—")
            c[2].metric(tr("c_pts"), f"{int(po['c_pts'].sum())}",
                        f"{tr('c_min')}: {po['c_sec'].sum() / 60:.0f}", delta_color="off",
                        help=tr("clutch_help"))
            c[3].metric(tr("c_fg"), f"{int(po['c_fgm'].sum())}/{int(po['c_fga'].sum())}",
                        f"+/- {int(po['c_pm'].sum()):+d}", delta_color="off")

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
if PAGE == "leaders":
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

    if not onoff.empty:
        st.subheader(tr("clutch_lead"))
        st.caption(tr("clutch_help"))
        names = df.drop_duplicates(["comp", "_pid"], keep="last").set_index(["comp", "_pid"])
        cl = onoff[onoff["c_sec"] > 0].groupby(["comp", "player_id"]).agg(
            c_pts=("c_pts", "sum"), c_fgm=("c_fgm", "sum"), c_fga=("c_fga", "sum"),
            c_pm=("c_pm", "sum"), c_sec=("c_sec", "sum"), n=("gamecode", "nunique")).reset_index()
        cl = cl.sort_values(["c_pts", "c_pm"], ascending=False).head(15)
        cl_t = pd.DataFrame({
            tr("player"): [names["player"].get((c, p), p) for c, p in zip(cl["comp"], cl["player_id"])],
            tr("c_pts"): cl["c_pts"].astype(int).values,
            tr("c_fg"): [f"{int(m)}/{int(a)}" for m, a in zip(cl["c_fgm"], cl["c_fga"])],
            "+/-": cl["c_pm"].astype(int).values,
            tr("c_min"): (cl["c_sec"] / 60).round(1).values,
            tr("c_games"): cl["n"].values,
            tr("team"): [names["team"].get((c, p), "") for c, p in zip(cl["comp"], cl["player_id"])],
        })
        st.dataframe(cl_t, hide_index=True, width="stretch")


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
        ppos = _pp.get(str(row["player_id"]).strip(), (None, None))[0]
        if ppos:
            dv, dr = dvp_rank(row["comp"], key, ppos)
            if o in dv.index:
                st.caption(tr("dvp_next", opp=o, pos=tr(f"pos1_{ppos}").lower(), v=f"{dv[o]:.1f}",
                              s=prop_name, r=int(dr[o]), n=len(dv)))
        if o in opp_opts and st.button(tr("use_next"), key=f"use_next_{opp_key}"):
            st.session_state[opp_key] = o
    elif not sched.empty:
        st.caption(tr("next_none"))
    inj_box(row["player_id"])

    default = float(np.floor(g[key].mean()) + 0.5)   # .5 linija kao kod kladionica
    c3, c4, c5 = st.columns(3)
    line = c3.number_input(tr("line"), value=default, step=0.5, format="%.1f",
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
    if nxt:
        sg = signal(g, key, line, row["comp"], nxt)
        box = st.success if sg["score"] >= 25 else st.error if sg["score"] <= -25 else st.info
        box(f"**{tr('sig')}: {sg['label']}** ({tr('sig_score').lower()} {sg['score']:+d})  \n"
            + " · ".join(sg["reasons"]))
        st.caption(tr("sig_note"))
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


if PAGE == "props":
    render_props()

# ---------- skener / scanner ----------
if PAGE == "scan":
    st.caption(tr("scan_note") + " " + tr("props_note"))
    c1, c2, c3 = st.columns(3)
    sname = c1.selectbox(stat_c, list(prop_stats.values()), key="scan_stat")
    skey = prop_inv[sname]
    sline = c2.number_input(tr("line"), value=DEFAULT_LINE.get(skey, 5.5), step=0.5, format="%.1f",
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
        rec[tr("pos_short")] = pos_label(pid, short=True)
        rec[tr("inj_col")] = inj_badge(pid)
        _sg = signal(pg, skey, sline, comp, next_game(comp, pg["team"].iloc[-1]))
        rec[tr("sig")] = _sg["label"]
        rows.append(rec)
    if not rows:
        st.info(tr("no_players"))
    else:
        scan = pd.DataFrame(rows).sort_values([sort_by, tr("avg")],
                                              ascending=[False, side == "Under"])
        # procenti odmah posle imena da se vide na telefonu / % columns first for phones
        order = ([tr("player"), tr("sig"), tr("inj_col"), sort_by] + [x for x in sort_opts if x != sort_by]
                 + [tr("avg"), tr("streak_s"), tr("pos_short"), tr("team"), tr("gp")])
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


if PAGE == "teams":
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
            tr("pos"): stn["position"],
            tr("team"): [ABBR.get((comp, x), x) for x in stn["club.code"]],
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

    st.subheader(tr("dvp"))
    if dvp.empty:
        st.caption(tr("no_pos"))
    else:
        st.caption(tr("dvp_note"))
        n_teams = df.loc[df["comp"].isin(comps), "team"].nunique()
        with st.expander("ℹ️ " + ("Legenda" if lang == "sr" else "Legend"), expanded=True):
            st.markdown(tr("dvp_legend", n=n_teams))
        for comp in comps:
            if tkey not in dvp.columns:
                break
            cols_ = {}
            for ps in ("G", "F", "C"):
                v, r = dvp_rank(comp, tkey, ps)
                cols_[tr(f"pos_{ps}")] = v.round(1)
                cols_[tr("rank_col", p=tr(f"pos1_{ps}").lower())] = r.astype("Int64")
            dt_ = pd.DataFrame(cols_)
            if dt_.empty:
                continue
            dt_.index.name = tr("team")
            dt_ = dt_.reset_index().sort_values(tr("pos_G"), ascending=False)
            st.markdown(f"**{tname} · {COMP_NAME[lang][comp]}**")
            st.dataframe(dt_, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(dt_)))
            csv_button(dt_, f"dvp_{tkey}", f"dl_dvp_{comp}")

    if not lineups.empty:
        st.subheader(tr("lineups"))
        c1, c2 = st.columns(2)
        l_team = c1.selectbox(tr("team"), sorted(lineups["team"].unique()), key="lu_team")
        l_min = c2.slider(tr("min_lineup"), 0, 60, 5, key="lu_min")
        surname = (df.drop_duplicates("_pid", keep="last").set_index("_pid")["player"]
                   .str.split(",").str[0].str.title())
        lt = (lineups[lineups["team"] == l_team].groupby("lineup")[["sec", "pf", "pa"]].sum()
              .reset_index())
        lt = lt[lt["sec"] >= 60 * l_min].sort_values("sec", ascending=False)
        if lt.empty:
            st.info(tr("no_players"))
        else:
            lt_t = pd.DataFrame({
                tr("lineup"): [", ".join(surname.get(x, x) for x in l.split("|")) for l in lt["lineup"]],
                tr("min_short"): (lt["sec"] / 60).round(1).values,
                "+/-": (lt["pf"] - lt["pa"]).values,
                tr("net40"): (2400 * (lt["pf"] - lt["pa"]) / lt["sec"]).round(1).values,
                tr("pf"): lt["pf"].values, tr("pa"): lt["pa"].values,
            })
            st.dataframe(lt_t, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(lt_t)),
                         column_config={tr("lineup"): st.column_config.TextColumn(width="large")})

# ---------- poredjenje / compare ----------
if PAGE == "cmp":
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
if PAGE == "sched":
    if sched.empty:
        st.info(tr("no_sched"))
    else:
        with st.expander(tr("inj_h"), expanded=False):
            render_injuries()
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

            # totali utakmica / game totals
            st.markdown(f"**{tr('totals')}**")
            st.caption(tr("totals_note"))
            parts = {tr("full"): "Points"}
            if "PTS_H1" in tgames.columns and tgames["PTS_H1"].notna().any():
                parts[tr("h1")] = "PTS_H1"
            t1, t2 = st.columns(2)
            part = t1.radio(tr("half_opt"), list(parts), horizontal=True, key=f"tot_part_{comp}")
            pk = parts[part]
            tc = tgames[tgames["comp"] == comp].dropna(subset=[pk, f"{pk}_a"])
            tc = tc.assign(_tot=tc[pk] + tc[f"{pk}_a"])
            # podrazumevana linija = prosek ukupnih poena u ligi (zaokruzeno na .5)
            avg_tot = float(tc["_tot"].mean()) if not tc.empty else (165.0 if pk == "Points" else 82.0)
            tl = t2.number_input(tr("total_line"), value=float(np.floor(avg_tot) + 0.5), step=0.5,
                                 key=f"tot_line_{comp}_{pk}")
            sc_, al_ = tc.groupby("team")[pk].mean(), tc.groupby("team")[f"{pk}_a"].mean()
            over = tc.groupby("team")["_tot"].apply(lambda x: round(100 * (x > tl).mean()))
            rows_t = []
            for m in s.itertuples():
                h, a = m.homecode, m.awaycode
                if h not in sc_.index or a not in sc_.index:
                    continue
                hp, ap = (sc_[h] + al_[a]) / 2, (sc_[a] + al_[h]) / 2
                x1 = float(np.clip((hp + ap - tl) / 8, -1, 1))
                x2 = (over[h] + over[a]) / 100 - 1
                sc = 100 * (0.5 * x1 + 0.5 * x2)
                lab = (tr("sig_fire") if sc >= 55 and min(over[h], over[a]) >= 70 else
                       tr("sig_over") if sc >= 25 else
                       tr("sig_ice") if sc <= -55 and max(over[h], over[a]) <= 30 else
                       tr("sig_under") if sc <= -25 else tr("sig_none"))
                rows_t.append({tr("match"): f"{h} – {a}", tr("tot_sig"): lab, tr("proj"): round(hp + ap, 1),
                               tr("home_over"): over[h], tr("away_over"): over[a],
                               tr("home_proj"): round(hp, 1), tr("away_proj"): round(ap, 1),
                               tr("res_time"): res_or_time(m) if pk == "Points" else ""})
            if rows_t:
                tt_ = pd.DataFrame(rows_t)
                if pk != "Points":
                    tt_ = tt_.drop(columns=[tr("res_time")])
                st.dataframe(tt_, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(tt_)),
                             column_config={k: st.column_config.NumberColumn(format="%d%%")
                                            for k in (tr("home_over"), tr("away_over"))})

# ---------- bez saigraca / without teammate ----------
if PAGE == "without":
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
                          format_func=lambda p: f"{roster.loc[p, 'player']} ({roster.loc[p, 'n']}/{n_team})"
                                                + (f" {inj_badge(p)}" if inj_badge(p) else ""))
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
if PAGE == "round":
    if sched.empty:
        st.info(tr("no_sched"))
    else:
        st.caption(tr("round_note") + " " + tr("props_note"))
        c1, c2, c3 = st.columns(3)
        r_name = c1.selectbox(stat_c, list(prop_stats.values()), key="rp_stat")
        r_key = prop_inv[r_name]
        r_line = c2.number_input(tr("line"), value=DEFAULT_LINE.get(r_key, 5.5), step=0.5, format="%.1f",
                                 key=f"rp_line_{r_key}")
        r_side = c3.radio(tr("side"), ["Over", "Under"], horizontal=True, key="rp_side")
        c4, c5, c6 = st.columns(3)
        r_hit = c4.slider(tr("min_hit"), 0, 100, 60, step=10, key="rp_hit")
        r_top = c5.slider(tr("top_def"), 1, 20, 8, key="rp_top", help=tr("top_def_help"))
        r_min = c6.slider(tr("min_minutes"), 0, 35, 15, key="rp_min")
        rank_opts = ([tr("rank_pos")] if not dvp.empty else []) + [tr("rank_team")]
        r_by = st.radio(tr("rank_by"), rank_opts, horizontal=True, key="rp_rank_by")
        use_dvp = r_by == tr("rank_pos")

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
                    if not use_dvp and (opp not in rank.index or rank[opp] > r_top):
                        continue
                    pids = last_team[last_team == team].index.get_level_values(1)
                    for pid, pg in hc[hc["player_id"].isin(pids)].groupby("player_id"):
                        ppos = _pp.get(str(pid).strip(), (None, None))[0]
                        if use_dvp:
                            if not ppos:
                                continue
                            _, prk = dvp_rank(comp, r_key, ppos, ascending=(r_side == "Under"))
                            if opp not in prk.index or prk[opp] > r_top:
                                continue
                            opp_lbl = f"{opp} (#{int(prk[opp])} {tr(f'pos1_{ppos}').lower()})"
                        else:
                            opp_lbl = f"{opp} (#{int(rank[opp])})"
                        v = pg[r_key].dropna()
                        if len(v) < 3 or pg["Minutes"].mean() < r_min or inj_status(pid) in INJ_HIDE:
                            continue
                        o5, t5 = hit_rate(v.tail(5), r_line, r_side)
                        if 100 * o5 / t5 < r_hit:
                            continue
                        oa, tall = hit_rate(v, r_line, r_side)
                        out.append({tr("match"): match, tr("player"): pg["player"].iloc[-1],
                                    tr("team"): team, tr("l5p"): round(100 * o5 / t5),
                                    tr("seasp"): round(100 * oa / tall), tr("avg"): round(v.mean(), 1),
                                    tr("opponent"): opp_lbl, tr("pos_short"): pos_label(pid, short=True),
                                    tr("sig"): signal(pg, r_key, r_line, comp,
                                                      {"opp": opp, "home": team == m.homecode,
                                                       "date": m.date, "time": m.startime})["label"],
                                    tr("inj_col"): inj_badge(pid)})
            st.subheader(f"{COMP_NAME[lang][comp]} · {tr('round')} {rnd} · {r_name} {r_side} {r_line:g}")
        if not out:
            st.info(tr("no_round"))
        else:
            rp = pd.DataFrame(out).sort_values([tr("l5p"), tr("seasp")], ascending=False)
            rp = rp[[tr("player"), tr("sig"), tr("inj_col"), tr("l5p"), tr("seasp"), tr("opponent"), tr("match"),
                     tr("avg"), tr("pos_short"), tr("team")]]
            st.dataframe(rp, hide_index=True, width="stretch", height=min(480, 38 + 35 * len(rp)),
                         column_config={k: st.column_config.NumberColumn(format="%d%%")
                                        for k in (tr("l5p"), tr("seasp"))})
            csv_button(rp, f"pregled_kola_{r_key}_{r_line:g}_{r_side}", "dl_round")

# ---------- predlozi / picks ----------
if PAGE == "picks":
    st.caption(tr("sig_note"))
    with st.expander(tr("check_one")):
        st.caption(tr("check_note"))
        q1, q2, q3 = st.columns([3, 2, 2])
        q_pl = q1.selectbox(tr("player"), players["label"], index=None, placeholder=tr("placeholder"),
                            key="pk_one_player")
        q_name = q2.selectbox(stat_c, list(prop_stats.values()), key="pk_one_stat")
        q_key = prop_inv[q_name]
        if q_pl:
            q_row, q_g = player_games(q_pl)
            q_v = q_g[q_key].dropna()
            q_def = float(np.floor(q_v.mean()) + 0.5) if not q_v.empty else 0.5
            q_line = q3.number_input(tr("line_s"), value=q_def, step=0.5, min_value=0.0, format="%.1f",
                                     key=f"pk_one_line_{q_row['player_id']}_{q_key}")
            q_g = q_g.dropna(subset=[q_key]).reset_index(drop=True)
            q_nxt = next_game(q_row["comp"], q_g["team"].iloc[-1]) if not q_g.empty else None
            q_sg = signal(q_g, q_key, q_line, q_row["comp"], q_nxt)
            verdict = f"### {q_sg['label']}\n**{q_row['player']}** · {q_name} **{q_line:g}** · " \
                      f"{tr('sig_score').lower()} **{q_sg['score']:+d}**"
            if q_nxt:
                verdict += "  \n" + tr("next_vs", o=q_nxt["opp"], ha=tr("home") if q_nxt["home"] else tr("away"),
                                        d=f"{q_nxt['date']:%d.%m.}" if pd.notna(q_nxt["date"]) else "")
            box = (st.success if q_sg["score"] >= 25 else st.error if q_sg["score"] <= -25 else st.info)
            box(verdict)
            inj_box(q_row["player_id"])
            if not q_nxt:
                st.caption(tr("no_next"))
            if q_sg["factors"]:
                ft = pd.DataFrame([{
                    tr("factor"): n, tr("weight"): f"{round(100 * w / q_sg['wsum'])}%",
                    tr("vote"): ("🟢 Over" if x > 0.05 else "🔴 Under" if x < -0.05 else f"⚪ {tr('neutral')}"),
                    tr("detail"): d} for n, w, x, d in q_sg["factors"]])
                st.dataframe(ft, hide_index=True, width="stretch")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(tr("avg"), f"{q_v.mean():.1f}")
                m2.metric(tr("median"), f"{q_v.median():g}")
                o5, t5 = hit_rate(q_v.tail(5), q_line)
                m3.metric(tr("last_n", n=5), f"{100 * o5 / t5:.0f}% Over" if t5 else "—")
                oa, ta_ = hit_rate(q_v, q_line)
                m4.metric(tr("season_lbl"), f"{100 * oa / ta_:.0f}% Over" if ta_ else "—")
        else:
            q3.number_input(tr("line_s"), value=0.0, disabled=True, key="pk_one_line_empty")


    if sched.empty:
        st.info(tr("no_sched"))
    else:
        _main = [k for k in ("Points", "TotalRebounds", "Assistances", "PRA", "3PM") if k in prop_stats]
        _opts = [prop_stats[k] for k in _main] + [tr("more")]
        k_name = st.pills(stat_c, _opts, default=_opts[0], key="pk_stat_p", label_visibility="collapsed") or _opts[0]
        if k_name == tr("more"):
            k_name = st.selectbox(stat_c, [v for k, v in prop_stats.items() if k not in _main], key="pk_stat_more")
        k_key = prop_inv[k_name]
        show_opts = [tr("show_all"), "Over", "Under", tr("show_strong")]
        k_show = st.segmented_control(tr("show"), show_opts, default=show_opts[0], key="pk_show_s",
                                      label_visibility="collapsed") or show_opts[0]
        with st.expander(tr("filters")):
            c1, c2 = st.columns(2)
            _modes = ([tr("line_book")] if BOOK else []) + [tr("line_avg"), tr("line_fixed")]
            k_mode = c1.radio(tr("line_mode"), _modes, key="pk_mode")
            if k_mode == tr("line_book"):
                k_line = None
                c2.caption(tr("line_book_help"))
            elif k_mode == tr("line_fixed"):
                k_line = c2.number_input(tr("line_s"), value=DEFAULT_LINE.get(k_key, 5.5), step=0.5,
                                         min_value=0.0, format="%.1f", key=f"pk_line_{k_key}")
            else:
                k_line = None
                c2.caption(tr("line_each"))
            c3, c4 = st.columns(2)
            k_min = c3.slider(tr("min_minutes"), 0, 35, 15, key="pk_min")
            k_g = c4.slider(tr("min_games"), 5, 20, 5, key="pk_g")
            k_hide_inj = st.checkbox(tr("inj_hide"), value=True, key="pk_hide_inj")

        picks_all = []
        for (comp, pid), pg in df.sort_values(SORT).groupby(["comp", "player_id"]):
            v = pg[k_key].dropna()
            if len(v) < k_g or pg["Minutes"].mean() < k_min:
                continue
            nxt = next_game(comp, pg["team"].iloc[-1])
            if not nxt or (k_hide_inj and inj_status(pid) in INJ_HIDE):
                continue
            if k_mode == tr("line_book"):
                bl = book_line(pid, k_key)
                if not bl:
                    continue
                e = eval_line(comp, pid, k_key, bl["line"], bl.get("over"), bl.get("under"), nxt)
                if e:
                    picks_all.append({**e, "books": bl.get("books"), "alt_lines": bl.get("alt_lines")})
                continue
            line = float(np.floor(v.mean()) + 0.5) if k_mode != tr("line_fixed") else float(k_line)
            picks_all.append(make_pick(comp, pid, pg, k_key, line, nxt))
        if not picks_all:
            st.info(tr("no_picks"))
        else:
            labels = [p["label"] for p in picks_all]
            st.markdown(tr("picks_count", f=labels.count(tr("sig_fire")), o=labels.count(tr("sig_over")),
                           u=labels.count(tr("sig_under")), i=labels.count(tr("sig_ice"))))
            if k_show == "Over":
                sel = sorted([p for p in picks_all if p["score"] >= 25], key=lambda p: -p["score"])
            elif k_show == "Under":
                sel = sorted([p for p in picks_all if p["score"] <= -25], key=lambda p: p["score"])
            elif k_show == tr("show_strong"):
                sel = sorted([p for p in picks_all if p["cls"] in ("fire", "ice")], key=lambda p: -abs(p["score"]))
            else:
                sel = sorted(picks_all, key=lambda p: -abs(p["score"]))
            pk = pd.DataFrame([{
                tr("sig"): p["label"], tr("player"): p["player"], tr("line_s"): p["line"],
                tr("sig_score"): p["score"],
                tr("l10p"): round(100 * p["hit_pct"]) if p["hit_pct"] is not None else None,
                tr("median"): p["median"], tr("avg"): round(p["avg"], 1),
                tr("opponent"): f"{p['opp']} ({tr('home') if p['home'] else tr('away')}, {p['when']})",
                tr("reasons"): " · ".join(p["reasons"]), tr("pos_short"): p["pos"], tr("team"): p["team"],
                tr("inj_col"): p["inj"]} for p in sel])
            if not sel:
                st.info(tr("no_picks"))
            elif st.toggle(tr("as_table"), key="pk_table"):
                st.dataframe(pk, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(pk)),
                             column_config={
                                 tr("sig_score"): st.column_config.NumberColumn(
                                     format="%+d", help="-100 … +100 (+ = Over)"),
                                 tr("l10p"): st.column_config.NumberColumn(format="%d%%"),
                                 tr("line_s"): st.column_config.NumberColumn(format="%.1f"),
                                 tr("reasons"): st.column_config.TextColumn(width="large")})
            else:
                n_show = st.session_state.get("pk_n", 20)
                st.markdown(f"<div class='es-grid'>{''.join(pick_card(p, odds_block(p)) for p in sel[:n_show])}</div>",
                            unsafe_allow_html=True)
                if len(sel) > n_show:
                    st.button(f"{tr('show_more')} ({len(sel) - n_show})", key="pk_more", width="stretch",
                              on_click=lambda: st.session_state.update(pk_n=n_show + 20))
            csv_button(pk, f"predlozi_{k_key}", "dl_picks")

# ---------- povrede / injuries page ----------
if PAGE == "injuries":
    render_injuries()

# ---------- pocetna / home ----------
if PAGE == "home":
    comp = comps[0]
    rnd, games = next_round_games(comp)
    data_sig = (len(df), int(df["gamecode"].max()), len(INJ), BOOK_FILE.get("fetched"), len(BOOK))
    picks = round_picks(comp, ("Points", "TotalRebounds", "Assistances"), lang, data_sig) if rnd else []
    labels = [p["label"] for p in picks]
    out_list = []
    if INJ_REPORT and rnd:
        round_teams = set(games["homecode"]) | set(games["awaycode"])
        for p in INJ_REPORT.get("players", []):
            code = ABBR.get((INJ_REPORT.get("comp", "E"), p.get("team")), p.get("team"))
            if code in round_teams and p.get("status") in ("out", "doubtful", "likely_out") \
                    and (INJ_REPORT.get("comp", "E"), p.get("gamecode")) not in played_codes:
                out_list.append((p.get("db_name") or p["name"], code, p["status"]))
    for pid, i in INJ.items():   # rucni unos (povrede.csv)
        if i["src"] == "manual" and i["status"] in INJ_HIDE:
            out_list.append((names_up.get(pid, pid), "", i["status"]))

    # kartica kola
    if rnd:
        first = games.iloc[0]
        when = day_time(first["date"], "").strip()
        _cnt = [("chip_fire", labels.count(tr("sig_fire"))), ("chip_ice", labels.count(tr("sig_ice"))),
                ("chip_out", sum(1 for o in out_list if o[2] == "out"))]
        chips = [tr(k, n=n) for k, n in _cnt if n]
        st.markdown(f"<div class='es-hero'><div class='t'>{esc(tr('home_next', r=rnd))} · {esc(liga)}</div>"
                    f"<div class='b'>{esc(when)} · <span>{esc(tr('home_games', n=len(games)))}</span></div>"
                    f"<div class='es-chips'>{''.join(f'<span class=es-chip>{esc(c)}</span>' for c in chips)}"
                    f"<span class='es-chip'>{esc(tr('chip_games', g=df['gamecode'].nunique(), p=df['player_id'].nunique()))}"
                    f"</span></div></div>", unsafe_allow_html=True)

        # utakmice
        section_head(tr("home_games_h"), tr("go_sched"), ("league", "sched"), key="games")
        cards = []
        for m in games.itertuples():
            proj, lab, line = game_total(comp, m.homecode, m.awaycode)
            tot = (f"{esc(tr('total_s'))} <b>{proj}</b> {esc(lab.split()[0])}" if proj else "")
            cards.append(f"<div class='es-game'><div class='d'>{esc(day_time(m.date, m.startime))}</div>"
                         f"<div class='m'>{esc(m.homecode)} – {esc(m.awaycode)}</div><div class='x'>{tot}</div></div>")
        st.markdown(f"<div class='es-games'>{''.join(cards)}</div>", unsafe_allow_html=True)

        # najjaci predlozi
        section_head(tr("home_picks_h"), tr("go_picks"), ("props", "picks"), key="picks", sub=tr("home_picks_note"))
        strong = sorted([p for p in picks if p["cls"] != "none"], key=lambda p: -abs(p["score"]))[:6]
        if strong:
            st.markdown(f"<div class='es-card'>{''.join(pick_row(p) for p in strong)}</div>", unsafe_allow_html=True)
        else:
            st.caption(tr("home_no_picks"))

        # ne igraju
        section_head(tr("home_inj_h"), tr("go_inj"), ("league", "injuries"), key="inj")
        if out_list:
            css = {"out": "s-out", "doubtful": "s-q", "likely_out": "s-l"}
            rows = "".join(f"<div class='es-row'><div class='es-main'><b>{esc(short_name(n) if ',' in n else n)}</b>"
                           f"{' · ' + esc(t) if t else ''}</div><span class='es-st {css.get(stt, 's-l')}'>"
                           f"{esc(tr('inj_' + stt))}</span></div>"
                           for n, t, stt in sorted(out_list, key=lambda o: (o[2] != "out", o[1]))[:8])
            st.markdown(f"<div class='es-card'>{rows}</div>", unsafe_allow_html=True)
        else:
            st.caption(tr("inj_none_round") if INJ_REPORT else tr("inj_none"))
    else:
        st.info(tr("no_next_round"))

    # u formi
    section_head(tr("home_form_h"), tr("go_form"), ("players", "leaders"), key="form", sub=tr("home_form_sub"))
    fr = []
    for pid, pg in df[df["comp"] == comp].sort_values(SORT).groupby("player_id"):
        if len(pg) >= 4 and pg["Minutes"].mean() >= 12:
            l3, sa = pg["Points"].tail(3).mean(), pg["Points"].mean()
            fr.append((l3 - sa, pg["player"].iloc[-1], pg["team"].iloc[-1], l3, sa))
    fr.sort(reverse=True)
    if fr:
        boxes = "".join(f"<div class='es-card'><div class='n'>{esc(short_name(n))} · {esc(t)}</div>"
                        f"<div class='v'>{d:+.1f}</div><div class='x'>{l3:.1f} vs {sa:.1f}</div></div>"
                        for d, n, t, l3, sa in fr[:4])
        st.markdown(f"<div class='es-form'>{boxes}</div>", unsafe_allow_html=True)

# ---------- linije kladionice / bookmaker lines ----------
if PAGE == "lines":
    _srcs = [tr("src_book"), tr("src_manual")]
    l_src = st.segmented_control(tr("source"), _srcs, default=_srcs[0] if BOOK else _srcs[1], key="lines_src",
                                 label_visibility="collapsed") or (_srcs[0] if BOOK else _srcs[1])
    results, bad = [], []
    if l_src == tr("src_book"):
        if BOOK_FILE.get("comp", "E") not in comps:
            st.info(tr("book_only_el"))
        elif not BOOK:
            st.info(tr("book_none"))
        else:
            _t = pd.to_datetime(BOOK_FILE.get("fetched"), utc=True, errors="coerce")
            _t = _t.tz_convert("Europe/Belgrade").strftime("%d.%m. %H:%M") if pd.notna(_t) else "?"
            st.caption(tr("book_note", t=_t))
            allr = book_results(lang, (BOOK_FILE.get("fetched"), len(BOOK), len(df), len(INJ)))
            _keys = [k for k in prop_stats if any(p["key"] == k for p in allr)]
            _opts = [tr("all_stats")] + [prop_stats[k] for k in _keys]
            b_stat = st.pills(stat_c, _opts, default=_opts[0], key="lines_bstat",
                              label_visibility="collapsed") or _opts[0]
            _show = [tr("show_all"), "Over", "Under", tr("show_strong"), "💰 " + tr("value")]
            b_show = st.segmented_control(tr("show"), _show, default=_show[0], key="lines_bshow",
                                          label_visibility="collapsed") or _show[0]
            results = [p for p in allr if b_stat == tr("all_stats") or prop_stats.get(p["key"]) == b_stat]
            if b_show == "Over":
                results = [p for p in results if p["score"] >= 25]
            elif b_show == "Under":
                results = [p for p in results if p["score"] <= -25]
            elif b_show == tr("show_strong"):
                results = [p for p in results if p["cls"] in ("fire", "ice")]
            elif b_show == _show[4]:
                results = [p for p in results if p["ev"] is not None and p["ev"] >= 0.05]
            labels = [p["label"] for p in results]
            st.markdown(tr("picks_count", f=labels.count(tr("sig_fire")), o=labels.count(tr("sig_over")),
                           u=labels.count(tr("sig_under")), i=labels.count(tr("sig_ice"))))
            if not results:
                st.info(tr("no_picks"))
    else:
        st.caption(tr("lines_note"))
        def make_example():
            """Primer od stvarnih igraca iz sledeceg kola: linija ≈ prosek, kvote 1.85 / 1.90."""
            rows_ = []
            for (comp_, pid_), g_ in df.sort_values(SORT).groupby(["comp", "player_id"]):
                if len(g_) >= 5 and g_["Minutes"].mean() >= 22 and next_game(comp_, g_["team"].iloc[-1]):
                    rows_.append((g_["Minutes"].mean(), g_))
            rows_.sort(key=lambda x: -x[0])
            out_ = []
            for (mins, g_), (key_, word) in zip(rows_[:5], [("Points", "poeni"), ("Points", "poeni"),
                                                             ("TotalRebounds", "skokovi"), ("Assistances", "asistencije"),
                                                             ("PRA", "PRA")]):
                ln = float(np.floor(g_[key_].mean()) + 0.5)
                out_.append(f"{short_name(g_['player'].iloc[-1])}, {word}, {ln:g}, 1.85, 1.90")
            return "\n".join(out_) or "Vezenkov, poeni, 17.5, 1.85, 1.90"

        EXAMPLE = make_example()

        def _set_lines(txt):
            st.session_state["lines_ta"] = txt
            st.session_state["lines_saved"] = txt

        if "lines_ta" not in st.session_state:
            st.session_state["lines_ta"] = st.session_state.get("lines_saved", "")
        st.text_area(tr("lines_input"), key="lines_ta", height=150, placeholder=EXAMPLE)
        st.session_state["lines_saved"] = st.session_state["lines_ta"]
        with st.container(key="row_linesbtn"):
            b1, b2 = st.columns(2)
            b1.button(tr("lines_example"), key="lines_ex", on_click=_set_lines, args=(EXAMPLE,))
            b2.button(tr("lines_clear"), key="lines_clr", on_click=_set_lines, args=("",))
        up = st.file_uploader(tr("lines_file"), type=["csv", "txt"], key="lines_up")
        text = st.session_state["lines_ta"]
        if up is not None:
            text += "\n" + up.getvalue().decode("utf-8-sig", errors="ignore")

        extra = {re.sub(r"[\s.+\-_/()]", "", LN.norm(v)): k for k, v in prop_stats.items()}
        rows = LN.parse_text(text, extra)
        if not rows:
            st.info(tr("lines_none"))
        else:
            last = df.sort_values(SORT).groupby(["comp", "player_id"])
            roster = [(pid, g["player"].iloc[-1], g["team"].iloc[-1], float(g["Minutes"].mean()))
                      for (comp_, pid), g in last]
            comp_of = {pid: comp_ for (comp_, pid), _ in last}
            for r in rows:
                if r.get("error"):
                    bad.append(f"{r['raw']} ({tr('stat_unknown') if r['error'] == 'stat' else tr('player_unknown')})")
                    continue
                pid = LN.match_player(r["name"], roster, r["team"])
                if not pid:
                    bad.append(f"{r['raw']} ({tr('player_unknown')})")
                    continue
                key = r["stat"]
                if key not in df.columns:
                    bad.append(f"{r['raw']} ({tr('stat_unknown')})")
                    continue
                e = eval_line(comp_of[pid], pid, key, float(r["line"]), r["over"], r["under"])
                if e is None:
                    bad.append(f"{r['raw']} ({tr('stat_unknown')})")
                    continue
                results.append(e)
            st.success(tr("lines_count", n=len(results))) if results else None
            if bad:
                st.warning(tr("lines_unmatched", n=len(bad), x=" · ".join(bad)))
    if results:
        srt = st.segmented_control(tr("lines_sort"), [tr("sort_value"), tr("sort_signal")],
                                   default=tr("sort_value"), key="lines_sort", label_visibility="collapsed")
        if srt == tr("sort_signal"):
            results.sort(key=lambda p: -abs(p["score"]))
        else:
            results.sort(key=lambda p: -(p["ev"] if p["ev"] is not None else -9))
        st.caption(tr("value_help"))

        if st.toggle(tr("as_table"), key="lines_table"):
            tbl = pd.DataFrame([{
                tr("player"): p["player"], tr("team"): p["team"], stat_c: p["stat"], tr("line_s"): p["line"],
                tr("sig"): p["label"], tr("sig_score"): p["score"], "Over": p["over"], "Under": p["under"],
                tr("book_p"): round(100 * p["p_book"]) if p["p_book"] is not None else None,
                tr("our_p"): round(100 * p["p_our"]) if p["p_our"] is not None else None,
                tr("best_side"): p["ev_side"],
                tr("value"): round(100 * p["ev"], 1) if p["ev"] is not None else None,
                tr("opponent"): p["opp"], tr("inj_col"): p["inj"]} for p in results])
            st.dataframe(tbl, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(tbl)),
                         column_config={tr("book_p"): st.column_config.NumberColumn(format="%d%%"),
                                        tr("our_p"): st.column_config.NumberColumn(format="%d%%"),
                                        tr("value"): st.column_config.NumberColumn(format="%+.1f%%"),
                                        tr("sig_score"): st.column_config.NumberColumn(format="%+d")})
            csv_button(tbl, "linije_procena", "dl_lines")
        else:
            n_show = st.session_state.get("lines_n", 30)
            st.markdown(f"<div class='es-grid'>{''.join(pick_card(p, odds_block(p)) for p in results[:n_show])}</div>",
                        unsafe_allow_html=True)
            if len(results) > n_show:
                st.button(f"{tr('show_more')} ({len(results) - n_show})", key="lines_more", width="stretch",
                          on_click=lambda: st.session_state.update(lines_n=n_show + 30))
