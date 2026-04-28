"""
Voxa — Dashboard Générique v2.0
================================
Dashboard Dash unique paramétré par config JSON.
Remplace dashboard.py (PSG) et dashboard_betclic.py (Betclic).

Usage direct :
    python3 dashboard_generic.py --slug psg --port 8050
    python3 dashboard_generic.py --slug betclic --port 8051

Intégration wsgi.py :
    from dashboard_generic import make_dashboard
    app = make_dashboard("psg")
    psg_server = app.server
"""

import os
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output

import theme as T
from theme import (P, C1, C2, NG, BG, BG2, BG3, BD, BD2, W, T2, T3, RED, GRD,
                   FONTS_URL, DASH_CSS, score_color, score_label,
                   card_style, card_title_style, kpi_value_style, badge_style,
                   FONT_BODY)

BASE_DIR = Path(__file__).parent.resolve()


# ─────────────────────────────────────────────
# DB HELPERS (génériques)
# ─────────────────────────────────────────────

def _resolve_db_path(slug: str) -> str:
    """Résout le chemin DB : d'abord voxa_db.CLIENTS_CONFIG, puis voxa_{slug}.db."""
    try:
        import voxa_db as vdb
        cfg = vdb.CLIENTS_CONFIG.get(slug)
        if cfg and cfg["db"].exists():
            return str(cfg["db"])
    except Exception:
        pass
    return str(BASE_DIR / f"voxa_{slug}.db")


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_scores(db_path: str, language: str = None) -> pd.DataFrame:
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""
        params = [language] if language and language != "all" else []
        rows = conn.execute(f"""
            SELECT b.name, b.is_primary, AVG(r.geo_score) as score,
                   AVG(r.mentioned) as mention_rate, AVG(r.mention_count) as freq
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
              AND ru.is_demo = 0 {where}
            GROUP BY b.id ORDER BY score DESC
        """, params).fetchall()
        if not rows:
            rows = conn.execute(f"""
                SELECT b.name, b.is_primary, AVG(r.geo_score) as score,
                       AVG(r.mentioned) as mention_rate, AVG(r.mention_count) as freq
                FROM results r
                JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                JOIN prompts p ON ru.prompt_id = p.id
                WHERE ru.run_date = (SELECT MAX(run_date) FROM runs) {where}
                GROUP BY b.id ORDER BY score DESC
            """, params).fetchall()
    finally:
        conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def load_scores_by_category(db_path: str, brand: str, language: str = None) -> dict:
    conn = _conn(db_path)
    try:
        where_lang = "AND p.language = ?" if language and language != "all" else ""
        params = [brand] + ([language] if language and language != "all" else [])
        rows = conn.execute(f"""
            SELECT p.category, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? AND ru.is_demo = 0
              AND ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
              {where_lang}
            GROUP BY p.category
        """, params).fetchall()
    finally:
        conn.close()
    return {r["category"]: round(r["score"]) for r in rows}


def load_history(db_path: str, brand: str, n_weeks: int = 10) -> list:
    conn = _conn(db_path)
    try:
        rows = conn.execute("""
            SELECT ru.run_date, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            WHERE b.name = ? AND ru.is_demo = 0
            GROUP BY ru.run_date ORDER BY ru.run_date ASC LIMIT ?
        """, (brand, n_weeks)).fetchall()
        if not rows:
            rows = conn.execute("""
                SELECT ru.run_date, AVG(r.geo_score) as score
                FROM results r JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                WHERE b.name = ?
                GROUP BY ru.run_date ORDER BY ru.run_date ASC LIMIT ?
            """, (brand, n_weeks)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_prompts(db_path: str, brand: str, language: str = None, limit: int = 20) -> list:
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""
        params = [brand] + ([language] if language and language != "all" else []) + [limit]
        rows = conn.execute(f"""
            SELECT p.text, p.category, p.language,
                   AVG(r.geo_score) as score, AVG(r.mentioned) as mention
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? AND ru.is_demo = 0 {where}
            GROUP BY p.id ORDER BY score ASC LIMIT ?
        """, params).fetchall()
        if not rows:
            rows = conn.execute(f"""
                SELECT p.text, p.category, p.language,
                       AVG(r.geo_score) as score, AVG(r.mentioned) as mention
                FROM results r JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                JOIN prompts p ON ru.prompt_id = p.id
                WHERE b.name = ? {where}
                GROUP BY p.id ORDER BY score ASC LIMIT ?
            """, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_last_run_date(db_path: str) -> str:
    conn = _conn(db_path)
    try:
        row = conn.execute("SELECT MAX(run_date) as d FROM runs").fetchone()
    finally:
        conn.close()
    return row["d"] if row and row["d"] else str(date.today())


def load_markets(db_path: str) -> list:
    conn = _conn(db_path)
    try:
        rows = conn.execute("SELECT DISTINCT language FROM prompts ORDER BY language").fetchall()
    finally:
        conn.close()
    return [r["language"] for r in rows]


def load_nss(db_path: str, brand: str, language: str = None) -> int:
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""
        params = [brand] + ([language] if language and language != "all" else [])
        rows = conn.execute(f"""
            SELECT r.sentiment FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? AND ru.is_demo = 0 {where}
        """, params).fetchall()
    finally:
        conn.close()
    sents = [r["sentiment"] for r in rows]
    if not sents:
        return 0
    return round((sents.count("positive") - sents.count("negative")) / len(sents) * 100)


def load_gap_analysis(db_path: str, language: str = None) -> pd.DataFrame:
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""
        params = [language] if language and language != "all" else []
        rows = conn.execute(f"""
            SELECT b.name, p.category, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE ru.is_demo = 0
              AND ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0) {where}
            GROUP BY b.name, p.category
        """, params).fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    data = {}
    for r in rows:
        data.setdefault(r["name"], {})[r["category"]] = round(r["score"])
    return pd.DataFrame(data).T


# ─────────────────────────────────────────────
# RECOMMENDATIONS ENGINE
# ─────────────────────────────────────────────

def generate_recommendations(db_path, brand, vertical, language=None, cat_labels=None):
    recos = []
    cat_labels = cat_labels or {}
    cat_scores = load_scores_by_category(db_path, brand, language)
    if cat_scores:
        worst_cat = min(cat_scores, key=cat_scores.get)
        best_cat  = max(cat_scores, key=cat_scores.get)
        gap = cat_scores[best_cat] - cat_scores[worst_cat]
        if gap >= 30:
            recos.append({"priority": "haute", "icon": "⚠",
                "title": f"Écart critique : {cat_labels.get(worst_cat, worst_cat)} ({cat_scores[worst_cat]}) vs {cat_labels.get(best_cat, best_cat)} ({cat_scores[best_cat]})",
                "body": f"Écart de {gap} pts. Enrichir le contenu éditorial et FAQ sur \"{cat_labels.get(worst_cat, worst_cat)}\"."})
        elif cat_scores[worst_cat] < 40:
            recos.append({"priority": "haute", "icon": "⚠",
                "title": f"Faible score en {cat_labels.get(worst_cat, worst_cat)} : {cat_scores[worst_cat]}/100",
                "body": f"Les LLMs ne citent quasiment pas {brand} sur ces requêtes. Angle mort à combler."})

    df_all = load_scores(db_path, language)
    if not df_all.empty:
        pr = df_all[df_all["name"] == brand]
        if not pr.empty:
            rank = df_all.index.get_loc(pr.index[0]) + 1
            leader = df_all.iloc[0]
            if rank > 1:
                delta = round(leader["score"] - pr["score"].values[0])
                recos.append({"priority": "moyenne", "icon": "◎",
                    "title": f"{brand} #{rank}/{len(df_all)} — {delta} pts derrière {leader['name']}",
                    "body": f"Analyser les sources web des LLMs pour {leader['name']} et produire du contenu équivalent."})
            else:
                recos.append({"priority": "info", "icon": "✓",
                    "title": f"{brand} #1 — position dominante",
                    "body": f"Leader GEO avec {round(pr['score'].values[0])}/100. Maintenir via monitoring hebdomadaire."})

    absent_prompts = load_prompts(db_path, brand, language, limit=50)
    if absent_prompts:
        absent = [p for p in absent_prompts if p.get("mention", 0) < 0.5]
        if absent:
            pct = round(len(absent) / len(absent_prompts) * 100)
            recos.append({"priority": "haute" if pct >= 40 else "moyenne", "icon": "✗",
                "title": f"{brand} absent de {len(absent)}/{len(absent_prompts)} réponses ({pct}%)",
                "body": f"Créer du contenu structuré (Schema JSON-LD, FAQ) pour ces requêtes."})

    if not recos:
        recos.append({"priority": "info", "icon": "✓",
            "title": "Bonne performance globale",
            "body": f"{brand} affiche de bons scores. Continuer le monitoring."})
    return recos


# ─────────────────────────────────────────────
# FACTORY — crée une app Dash par config
# ─────────────────────────────────────────────

def make_dashboard(slug: str, standalone: bool = False) -> dash.Dash:
    """Crée et retourne une app Dash complète pour un slug donné.
    
    Args:
        slug: identifiant client (psg, betclic, reims...)
        standalone: True pour test local (pas de préfixe URL),
                    False pour prod via DispatcherMiddleware wsgi.py
    """

    # ── Charger la config ──────────────────────
    config_path = BASE_DIR / "configs" / f"{slug}.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        try:
            import voxa_db as vdb
            vc = vdb.CLIENTS_CONFIG[slug]
            cfg = {"slug": slug, "client_name": vc["name"],
                   "primary_brand": vc["primary"], "vertical": vc["vertical"],
                   "markets": vc["markets"]}
        except Exception:
            raise FileNotFoundError(f"Ni config JSON ni voxa_db pour '{slug}'")

    db_path     = _resolve_db_path(slug)
    brand       = cfg["primary_brand"]
    client_name = cfg["client_name"]
    vertical    = cfg.get("vertical", "sport")

    LANG_FLAGS = {"fr": "🇫🇷", "en": "🇬🇧", "pt": "🇵🇹", "pl": "🇵🇱",
                  "fr-ci": "🇨🇮", "fr_ligue2": "🇫🇷"}
    CAT_LABELS = {
        "discovery": "Notoriété", "comparison": "Comparaison",
        "reputation": "Réputation", "transactional": "Transactionnel",
        "visibility": "Visibilité", "brand": "Image", "odds": "Cotes",
        "regulation": "Régulation", "payment": "Paiement",
        "worldcup": "Coupe du Monde",
    }

    # ── App Dash ──────────────────────────────
    # En standalone (test local), pas de préfixe → routes à /
    # En production (wsgi.py DispatcherMiddleware), préfixe /{slug}/
    prefix = "/" if standalone else f"/{slug}/"

    app = dash.Dash(
        __name__, server=True,
        requests_pathname_prefix=prefix,
        external_stylesheets=[dbc.themes.BOOTSTRAP, FONTS_URL],
        suppress_callback_exceptions=True,
        title=f"Voxa · {client_name}",
    )
    app.index_string = app.index_string.replace("</head>", T.DASH_CSS + "</head>")

    def card(children, extra=None):
        return html.Div(children, style={**card_style(), **(extra or {})})

    def ctitle(text):
        return html.Div(text, style={
            "fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
            "letterSpacing": "2px", "color": T3, "marginBottom": 14,
            "fontFamily": FONT_BODY})

    # ── Données initiales ─────────────────────
    markets_from_db = load_markets(db_path)
    has_multi_markets = len(markets_from_db) >= 3
    market_opts = [{"label": "🌐 Tous", "value": "all"}] + [
        {"label": f"{LANG_FLAGS.get(m,'🌐')} {m.upper()}", "value": m}
        for m in markets_from_db]

    topbar = T.make_topbar(client_name=client_name, vertical=vertical,
        right_children=[
            html.A("↓ CSV", id=f"export-{slug}", href=f"{prefix}export/csv",
                   style={"padding": "6px 12px", "borderRadius": 8,
                          "border": f"1px solid {BD}", "background": BG3,
                          "fontSize": 12, "fontWeight": 600, "color": T2,
                          "textDecoration": "none"})])

    tab_s  = {"fontSize": 11, "fontWeight": 700, "letterSpacing": "1px", "color": T3}
    tab_sa = {"color": C1}
    tabs_list = []
    if has_multi_markets:
        tabs_list.append(dbc.Tab(label="VUE GÉNÉRALE", tab_id="overview",
                                 label_style=tab_s, active_label_style=tab_sa))
    tabs_list += [
        dbc.Tab(label="CLASSEMENT", tab_id="ranking", label_style=tab_s, active_label_style=tab_sa),
        dbc.Tab(label="ACTIONS", tab_id="actions", label_style=tab_s, active_label_style=tab_sa),
        dbc.Tab(label="INSIGHTS", tab_id="insights", label_style=tab_s, active_label_style=tab_sa),
    ]
    tabs_list += [
        dbc.Tab(label="PROMPTS", tab_id="prompts", label_style=tab_s, active_label_style=tab_sa),
        dbc.Tab(label="BIBLIOTHÈQUE", tab_id="library", label_style=tab_s, active_label_style=tab_sa),
    ]

    # ── Layout ────────────────────────────────
    app.layout = html.Div([
        topbar,
        html.Div([dbc.Row([dbc.Col([
            html.Div("MARCHÉ", style={"fontSize": 10, "fontWeight": 700,
                                       "letterSpacing": "2px", "color": T3, "marginBottom": 8}),
            dbc.RadioItems(id=f"market-{slug}", options=market_opts, value="all",
                           inline=True, style={"color": T2, "fontSize": 13}),
        ], width=12)])], style={"background": BG3, "border": f"1px solid {BD}",
            "borderRadius": 12, "padding": "18px 24px", "margin": "20px 24px 0"}),
        html.Div(id=f"hero-{slug}", style={"padding": "16px 24px 0"}),
        dbc.Tabs(tabs_list, id=f"tabs-{slug}", active_tab="overview" if has_multi_markets else "ranking",
                 style={"margin": "20px 24px 0", "borderBottom": f"1px solid {BD}"}),
        html.Div(id=f"content-{slug}", style={"padding": "16px 24px 24px"}),
        html.Div([
            html.Span("✓ Prompt library verticale · données propriétaires · historique indépendant"),
            html.Span(["Voxa GEO Intelligence · ",
                html.A("luc@sharper-media.com", href="mailto:luc@sharper-media.com",
                       style={"color": C1, "textDecoration": "none"})]),
        ], style={"background": f"rgba(0,229,255,0.03)", "borderTop": f"1px solid {BD}",
                  "padding": "12px 32px", "fontSize": 11, "color": T3,
                  "display": "flex", "justifyContent": "space-between", "fontFamily": FONT_BODY}),
    ])

    # ── Hero KPI ──────────────────────────────
    @app.callback(Output(f"hero-{slug}", "children"), Input(f"market-{slug}", "value"))
    def update_hero(market):
        lang = None if market == "all" else market
        df = load_scores(db_path, lang)
        hist = load_history(db_path, brand)
        nss = load_nss(db_path, brand, lang)
        primary = df[df["name"] == brand] if not df.empty else pd.DataFrame()
        sc_val = round(primary["score"].iloc[0]) if not primary.empty else 0
        nss_col = NG if nss >= 0 else RED
        return card([dbc.Row([
            dbc.Col([
                html.Div(str(sc_val), style={"fontSize": 52, "fontWeight": 900,
                    "color": score_color(sc_val), "lineHeight": "1"}),
                html.Div("/100", style={"fontSize": 14, "color": T3, "fontWeight": 600}),
                html.Div(score_label(sc_val), style={"fontSize": 12, "fontWeight": 700,
                    "color": score_color(sc_val), "marginTop": 4}),
                html.Div(f"GEO Score · {brand}", style={"fontSize": 10, "fontWeight": 700,
                    "letterSpacing": "2px", "color": T3, "marginTop": 8, "textTransform": "uppercase"}),
            ], width=3),
            dbc.Col([dbc.Row([
                dbc.Col([
                    html.Div(f"{nss:+d}%", style={"fontSize": 22, "fontWeight": 800, "color": nss_col}),
                    html.Div("NET SENTIMENT", style={"fontSize": 10, "color": T3, "fontWeight": 700, "letterSpacing": "1px"}),
                ], width=4),
                dbc.Col([
                    html.Div(str(len(hist)), style={"fontSize": 22, "fontWeight": 800, "color": C1}),
                    html.Div("RUNS", style={"fontSize": 10, "color": T3, "fontWeight": 700, "letterSpacing": "1px"}),
                ], width=4),
                dbc.Col([
                    html.Div(str(round(primary["mention_rate"].iloc[0]*100))+"%"
                             if not primary.empty else "—",
                             style={"fontSize": 22, "fontWeight": 800, "color": C1}),
                    html.Div("MENTIONS", style={"fontSize": 10, "color": T3, "fontWeight": 700, "letterSpacing": "1px"}),
                ], width=4),
            ])], width=9),
        ])], {"marginBottom": 0})

    # ── Tab routing ───────────────────────────
    @app.callback(Output(f"content-{slug}", "children"),
                  Input(f"tabs-{slug}", "active_tab"), Input(f"market-{slug}", "value"))
    def update_content(tab, market):
        lang = None if market == "all" else market
        if tab == "ranking":  return _tab_ranking(lang)
        if tab == "insights": return _tab_insights(lang)
        if tab == "actions":  return _tab_actions()
        if tab == "overview": return _tab_overview(lang)
        if tab == "prompts":  return _tab_prompts(lang)
        if tab == "library":  return _tab_library(lang)
        return html.Div()

    # ── TAB: Classement ───────────────────────
    def _tab_ranking(lang):
        df = load_scores(db_path, lang)
        hist = load_history(db_path, brand)
        if not df.empty:
            colors = [C1 if row["is_primary"] else T3 for _, row in df.iterrows()]
            bar = go.Figure(go.Bar(x=df["score"].round().astype(int), y=df["name"],
                orientation="h", marker_color=colors,
                text=df["score"].round().astype(int).astype(str)+"/100", textposition="auto",
                textfont={"size": 12, "color": BG, "family": FONT_BODY},
            )).update_layout(height=max(200, len(df)*40), margin=dict(l=0,r=10,t=0,b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, range=[0,100], showticklabels=False, zeroline=False),
                yaxis=dict(tickfont={"size":12, "color":T2, "family":FONT_BODY}),
                font={"family":FONT_BODY}, showlegend=False)
            bar_c = card([ctitle("CLASSEMENT CONCURRENTS"),
                          dcc.Graph(figure=bar, config={"displayModeBar": False})])
        else:
            bar_c = card([ctitle("CLASSEMENT"), html.Div("Pas de données.", style={"color":T3,"fontSize":12})])

        if hist and len(hist) > 1:
            line = go.Figure(go.Scatter(
                x=[h["run_date"] for h in hist], y=[round(h["score"]) for h in hist],
                mode="lines+markers", line=dict(color=C1,width=2), marker=dict(color=C1,size=6),
                fill="tozeroy", fillcolor="rgba(0,229,255,0.06)", hovertemplate="%{y}/100<extra></extra>",
            )).update_layout(height=200, margin=dict(l=0,r=10,t=0,b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, tickfont={"size":10,"color":T3,"family":FONT_BODY}),
                yaxis=dict(range=[0,100], showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                           tickfont={"size":10,"color":T3}), font={"family":FONT_BODY})
            line_c = card([ctitle(f"ÉVOLUTION · {brand.upper()}"),
                           dcc.Graph(figure=line, config={"displayModeBar": False})])
        else:
            line_c = card([ctitle(f"ÉVOLUTION · {brand.upper()}"),
                           html.Div("Données insuffisantes.", style={"color":T3,"fontSize":12})])
        return dbc.Row([dbc.Col(bar_c, width=6), dbc.Col(line_c, width=6)], style={"marginTop":16})

    # ── TAB: Insights ─────────────────────────
    def _tab_insights(lang):
        PS = {
            "haute":   {"border": RED, "bg": "rgba(255,75,110,0.06)",
                        "bbg": "rgba(255,75,110,0.12)", "bcol": RED},
            "moyenne": {"border": C1,  "bg": "rgba(0,229,255,0.04)",
                        "bbg": "rgba(0,229,255,0.10)",  "bcol": C1},
            "info":    {"border": NG,  "bg": "rgba(0,255,170,0.04)",
                        "bbg": "rgba(0,255,170,0.10)",  "bcol": NG},
        }
        def reco_ui(icon, prio, title, body_t, impact=None, prompt_t=None):
            ps = PS.get(prio, PS["info"])
            return html.Div([
                html.Div([
                    html.Span(icon, style={"fontSize":15,"marginRight":8}),
                    html.Span(prio.upper(), style={"fontSize":9,"fontWeight":800,"letterSpacing":"1.5px",
                        "padding":"2px 8px","borderRadius":20,"background":ps["bbg"],"color":ps["bcol"],
                        "marginRight":10,"fontFamily":FONT_BODY}),
                    html.Span(title, style={"fontSize":13,"fontWeight":700,"color":W,"fontFamily":FONT_BODY}),
                    *([html.Span(f"+{impact:.0f} pts", style={"fontSize":10,"color":T3,"marginLeft":10})] if impact else []),
                ], style={"marginBottom":6}),
                html.Div(body_t, style={"fontSize":12,"color":T2,"lineHeight":"1.7","paddingLeft":22,"fontFamily":FONT_BODY}),
                *([html.Div(f"Prompt : « {prompt_t[:80]}… »", style={"fontSize":10,"color":T3,"paddingLeft":22,"marginTop":4,"fontStyle":"italic"})] if prompt_t else []),
            ], style={"borderLeft":f"3px solid {ps['border']}","background":ps["bg"],
                      "borderRadius":"0 10px 10px 0","padding":"12px 18px","marginBottom":10})

        recos = generate_recommendations(db_path, brand, vertical, lang, CAT_LABELS)
        reco_cards = [reco_ui(r.get("icon","💡"), r["priority"], r["title"], r["body"]) for r in recos]

        alert_block = db_block = html.Div()
        try:
            import voxa_db as vdb
            db_alerts = vdb.get_alerts(slug, unread_only=True)
            db_recos = vdb.get_recommendations(slug)
            SS = {"critical":{"i":"⚠","b":RED,"bg":"rgba(255,75,110,0.06)"},
                  "warning":{"i":"◎","b":C1,"bg":"rgba(0,229,255,0.04)"},
                  "info":{"i":"✓","b":NG,"bg":"rgba(0,255,170,0.04)"}}
            if db_alerts:
                aitems = []
                for a in db_alerts:
                    ss = SS.get(a.get("severity","info"), SS["info"])
                    aitems.append(html.Div([
                        html.Div([html.Span(ss["i"], style={"marginRight":8,"fontSize":12,"color":ss["b"],"fontWeight":800}),
                                  html.Span(a["title"], style={"fontWeight":700,"color":W,"fontSize":13}),
                                  html.Span(f"  {a['created_at'][:10]}", style={"fontSize":10,"color":T3,"marginLeft":10})],
                                 style={"marginBottom":3}),
                        html.Div(a["body"], style={"fontSize":12,"color":T2,"paddingLeft":20,"lineHeight":1.5}),
                    ], style={"padding":"10px 14px","marginBottom":8,"background":ss["bg"],
                              "borderRadius":8,"borderLeft":f"3px solid {ss['b']}"}))
                alert_block = card([ctitle("ALERTES ACTIVES"), *aitems], {"marginBottom":16})
            if db_recos:
                pm = {"high":"haute","medium":"moyenne","low":"info"}
                dcards = [reco_ui("💡", pm.get(r.get("priority"),"moyenne"), r.get("title",""),
                                  r.get("body",""), impact=r.get("impact_score"), prompt_t=r.get("prompt_text"))
                          for r in db_recos]
                db_block = card([ctitle("RECOMMANDATIONS GEO — ACTIONS PRIORITAIRES"), *dcards,
                    html.Div("Générées après chaque run tracker.", style={"fontSize":11,"color":T3,"marginTop":8,"fontStyle":"italic"})],
                    {"marginBottom":16})
        except Exception:
            pass

        gap_section = html.Div("Données insuffisantes.", style={"color":T3,"fontSize":12,"padding":"12px 0"})
        gap_df = load_gap_analysis(db_path, lang)
        if not gap_df.empty:
            cat_cols = [c for c in gap_df.columns if c in CAT_LABELS]
            brand_sc = gap_df.loc[brand] if brand in gap_df.index else pd.Series()
            hdr = [html.Th("", style={"width":130,"padding":"8px 12px"})] + [
                html.Th(CAT_LABELS.get(c,c), style={"fontSize":10,"fontWeight":700,"textTransform":"uppercase",
                    "letterSpacing":"1px","color":T3,"textAlign":"center","padding":"8px 12px","background":BG})
                for c in cat_cols]
            rows = []
            for b in gap_df.index:
                is_p = (b == brand)
                cells = [html.Td(b, style={"fontWeight":800 if is_p else 600,"fontSize":13,
                    "color":C1 if is_p else W,"padding":"10px 12px",
                    "background":"rgba(0,229,255,0.04)" if is_p else BG3})]
                for c in cat_cols:
                    val = int(gap_df.loc[b,c]) if c in gap_df.columns else 0
                    if is_p: bg_c, col = "rgba(0,229,255,0.08)", C1
                    else:
                        d = val - (int(brand_sc[c]) if c in brand_sc.index else 0)
                        if d > 10: bg_c, col = "rgba(255,75,110,0.08)", RED
                        elif d < -10: bg_c, col = "rgba(0,255,170,0.08)", NG
                        else: bg_c, col = BG3, T2
                    cells.append(html.Td(str(val), style={"textAlign":"center","fontSize":14,
                        "fontWeight":800 if is_p else 600,"color":col,"background":bg_c,"padding":"10px 12px"}))
                rows.append(html.Tr(cells, style={"borderBottom":f"1px solid {BD}"}))
            gap_section = dbc.Table([html.Thead(html.Tr(hdr), style={"borderBottom":f"2px solid {BD}"}),
                                     html.Tbody(rows)], bordered=False, hover=False, style={"fontFamily":FONT_BODY})

        mkt_lbl = lang.upper() if lang else "TOUS MARCHÉS"
        return html.Div([alert_block,
            card([ctitle(f"RECOMMANDATIONS · {mkt_lbl}"), *(reco_cards or [
                html.Div("Aucune recommandation critique.", style={"color":T3,"fontSize":12})])], {"marginBottom":16}),
            db_block,
            card([ctitle(f"GAP ANALYSIS · {brand.upper()} VS CONCURRENTS"),
                html.Div([
                    html.Span("",style={"display":"inline-block","width":8,"height":8,"borderRadius":3,
                        "background":"rgba(0,255,170,0.4)","marginRight":4}),
                    html.Span(f"{brand} devant",style={"fontSize":10,"color":NG,"marginRight":16}),
                    html.Span("",style={"display":"inline-block","width":8,"height":8,"borderRadius":3,
                        "background":"rgba(255,75,110,0.4)","marginRight":4}),
                    html.Span("Concurrent devant",style={"fontSize":10,"color":RED}),
                ], style={"marginBottom":12}),
                gap_section])])

    # ── TAB: Actions (Pack Hebdo) ─────────────
    def _tab_actions():
        try:
            from action_pack import get_latest_pack, get_pack_history
        except ImportError:
            return card([html.Div("Module action_pack non disponible.",
                                  style={"color": T3, "fontSize": 12})])

        pack = get_latest_pack(slug)
        history = get_pack_history(slug, limit=8)

        # ── Pack actuel ──
        if not pack or not pack.get("items"):
            pack_section = card([
                ctitle("PACK ACTIONS HEBDO"),
                html.Div([
                    html.Div("Aucun pack généré cette semaine.", style={
                        "fontSize": 13, "color": T3, "marginBottom": 12}),
                    html.Div("Lancez la commande pour générer le premier pack :", style={
                        "fontSize": 12, "color": T3, "marginBottom": 8}),
                    html.Code("python3 action_pack.py --slug " + slug + " --iterate",
                              style={"fontSize": 12, "padding": "8px 14px", "display": "block",
                                     "background": BG, "borderRadius": 8, "color": C1}),
                ]),
            ], {"marginBottom": 16})
        else:
            week_label = pack.get("week", "")
            items_ui = []
            for item in pack["items"]:
                sc_cur  = item.get("score_current", 0)
                sc_pred = item.get("score_predicted", 0)
                delta   = sc_pred - sc_cur
                status  = item.get("status", "pending")
                prompt  = item.get("prompt_text", "")
                content = item.get("content", "")
                jsonld  = item.get("jsonld_schema", "")
                n_iter  = item.get("n_iterations", 1)
                cat     = item.get("category", "")
                lang    = item.get("language", "")

                # Styles par priorité
                if delta >= 40:
                    border_col, bg_col, prio_label = RED, "rgba(255,75,110,0.05)", "HAUTE"
                elif delta >= 20:
                    border_col, bg_col, prio_label = C1, "rgba(0,229,255,0.04)", "MOYENNE"
                else:
                    border_col, bg_col, prio_label = NG, "rgba(0,255,170,0.04)", "INFO"

                # Status badge
                if status == "implemented":
                    status_badge = html.Span("✓ IMPLÉMENTÉ", style={
                        "fontSize": 9, "fontWeight": 800, "padding": "2px 8px",
                        "borderRadius": 20, "background": "rgba(0,255,170,0.12)",
                        "color": NG, "marginLeft": 10})
                elif status == "measured":
                    sc_real = item.get("score_real", 0)
                    diff = sc_real - sc_pred
                    diff_col = NG if diff >= -5 else RED
                    status_badge = html.Span(f"MESURÉ : {sc_real}/100 ({diff:+d} vs prédit)", style={
                        "fontSize": 9, "fontWeight": 800, "padding": "2px 8px",
                        "borderRadius": 20, "background": f"rgba(0,255,170,0.12)",
                        "color": diff_col, "marginLeft": 10})
                else:
                    status_badge = html.Span("EN ATTENTE", style={
                        "fontSize": 9, "fontWeight": 800, "padding": "2px 8px",
                        "borderRadius": 20, "background": "rgba(168,184,200,0.12)",
                        "color": T3, "marginLeft": 10})

                item_ui = html.Div([
                    # Header : priorité + prompt + status
                    html.Div([
                        html.Span(prio_label, style={
                            "fontSize": 9, "fontWeight": 800, "letterSpacing": "1.5px",
                            "padding": "2px 8px", "borderRadius": 20,
                            "background": f"rgba({','.join(str(int(border_col.lstrip('#')[i:i+2], 16)) for i in (0,2,4))},0.12)" if border_col.startswith("#") else bg_col,
                            "color": border_col, "marginRight": 10, "fontFamily": FONT_BODY}),
                        html.Span(f"[{cat}] " if cat else "", style={
                            "fontSize": 10, "color": T3, "marginRight": 4}),
                        html.Span(prompt[:80] + ("..." if len(prompt) > 80 else ""), style={
                            "fontSize": 13, "fontWeight": 700, "color": W, "fontFamily": FONT_BODY}),
                        status_badge,
                    ], style={"marginBottom": 8}),

                    # Scores
                    html.Div([
                        html.Span(f"Score actuel : ", style={"fontSize": 12, "color": T3}),
                        html.Span(f"{sc_cur}/100", style={
                            "fontSize": 14, "fontWeight": 800, "color": score_color(sc_cur), "marginRight": 16}),
                        html.Span(" → ", style={"fontSize": 14, "color": T3, "marginRight": 16}),
                        html.Span(f"Prédit : ", style={"fontSize": 12, "color": T3}),
                        html.Span(f"{sc_pred}/100", style={
                            "fontSize": 14, "fontWeight": 800, "color": score_color(sc_pred), "marginRight": 16}),
                        html.Span(f"(+{delta})", style={
                            "fontSize": 12, "fontWeight": 700, "color": NG}),
                        html.Span(f" · {n_iter} itération{'s' if n_iter > 1 else ''}", style={
                            "fontSize": 10, "color": T3, "marginLeft": 12}),
                    ], style={"marginBottom": 10}),

                    # Contenu + JSON-LD
                    html.Details([
                        html.Summary("Voir le contenu optimisé + JSON-LD", style={
                            "fontSize": 12, "color": C1, "cursor": "pointer",
                            "fontWeight": 600, "fontFamily": FONT_BODY}),
                        html.Div([
                            html.Div("CONTENU OPTIMISÉ", style={
                                "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
                                "color": T3, "marginBottom": 6, "marginTop": 10}),
                            html.Pre(content, style={
                                "fontSize": 12, "color": T2, "lineHeight": "1.6",
                                "background": BG, "padding": "12px 14px",
                                "borderRadius": 8, "border": f"1px solid {BD}",
                                "whiteSpace": "pre-wrap", "fontFamily": FONT_BODY,
                                "maxHeight": 200, "overflowY": "auto"}),
                            *([ html.Div([
                                html.Div("JSON-LD (copier dans <head>)", style={
                                    "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
                                    "color": T3, "marginBottom": 6, "marginTop": 12}),
                                html.Pre(jsonld, style={
                                    "fontSize": 11, "color": C1, "lineHeight": "1.4",
                                    "background": BG, "padding": "12px 14px",
                                    "borderRadius": 8, "border": f"1px solid rgba(0,229,255,0.2)",
                                    "whiteSpace": "pre-wrap", "fontFamily": "'JetBrains Mono', monospace",
                                    "maxHeight": 250, "overflowY": "auto"}),
                            ]) ] if jsonld else []),
                        ]),
                    ], style={"marginTop": 4}),
                ], style={
                    "borderLeft": f"3px solid {border_col}", "background": bg_col,
                    "borderRadius": "0 10px 10px 0",
                    "padding": "14px 18px", "marginBottom": 12})

                items_ui.append(item_ui)

            pack_section = card([
                ctitle(f"PACK ACTIONS · SEMAINE {week_label}"),
                html.Div(f"Généré le {pack.get('created_at', '')[:10]} · {pack['n_items']} actions",
                         style={"fontSize": 11, "color": T3, "marginBottom": 14}),
                *items_ui,
            ], {"marginBottom": 16})

        # ── Historique des packs précédents ──
        hist_section = html.Div()
        if history and len(history) > 0:
            hist_rows = []
            for h in history:
                avg_cur  = round(h.get("avg_current") or 0)
                avg_pred = round(h.get("avg_predicted") or 0)
                avg_real = round(h.get("avg_real") or 0) if h.get("avg_real") else "—"
                n_impl   = h.get("n_implemented", 0)
                n_items  = h.get("n_items", 0)

                accuracy = ""
                if isinstance(avg_real, int) and avg_pred > 0:
                    diff = avg_real - avg_pred
                    accuracy = f"{diff:+d}"

                hist_rows.append(html.Tr([
                    html.Td(h.get("week", ""), style={"padding": "8px 12px", "fontWeight": 700, "color": C1, "fontSize": 12}),
                    html.Td(f"{n_impl}/{n_items}", style={"padding": "8px 12px", "color": T2, "fontSize": 12}),
                    html.Td(str(avg_cur), style={"padding": "8px 12px", "color": score_color(avg_cur), "fontWeight": 700, "fontSize": 13}),
                    html.Td(str(avg_pred), style={"padding": "8px 12px", "color": C1, "fontWeight": 700, "fontSize": 13}),
                    html.Td(str(avg_real), style={"padding": "8px 12px", "color": NG if isinstance(avg_real, int) else T3, "fontWeight": 700, "fontSize": 13}),
                    html.Td(accuracy, style={"padding": "8px 12px", "color": NG if accuracy.startswith("+") or accuracy == "" else RED, "fontWeight": 700, "fontSize": 12}),
                ], style={"borderBottom": f"1px solid {BD}"}))

            hist_section = card([
                ctitle("HISTORIQUE DES PACKS"),
                dbc.Table([
                    html.Thead(html.Tr([
                        *[html.Th(h, style={
                            "fontSize": 10, "fontWeight": 700, "letterSpacing": "1.5px",
                            "textTransform": "uppercase", "color": T3,
                            "padding": "8px 12px", "background": BG})
                          for h in ["Semaine", "Implémenté", "Avant", "Prédit", "Réel", "Δ préd."]]
                    ]), style={"borderBottom": f"2px solid {BD}"}),
                    html.Tbody(hist_rows),
                ], bordered=False, hover=False, style={"fontFamily": FONT_BODY}),
                html.Div(
                    "Le score réel est mesuré 4 semaines après implémentation.",
                    style={"fontSize": 11, "color": T3, "marginTop": 8, "fontStyle": "italic"}),
            ])

        return html.Div([pack_section, hist_section], style={"marginTop": 16})

    # ── TAB: Multi-Marchés ────────────────────
    def _tab_overview(lang):
        # Score (filtré par marché si sélectionné)
        all_df = load_scores(db_path, lang)
        brand_row = all_df[all_df["name"] == brand] if not all_df.empty else pd.DataFrame()
        global_score = round(brand_row["score"].iloc[0]) if not brand_row.empty else 0
        global_rank = all_df.index.get_loc(brand_row.index[0]) + 1 if not brand_row.empty else "—"
        n_brands = len(all_df)
        show_markets = [lang] if lang else markets_from_db

        # Score par marché
        mcards = []
        for mkt in show_markets:
            df = load_scores(db_path, mkt)
            pr = df[df["name"] == brand] if not df.empty else pd.DataFrame()
            sc = round(pr["score"].iloc[0]) if not pr.empty else 0
            rank = df.index.get_loc(pr.index[0]) + 1 if not pr.empty else "—"
            mcards.append(html.Div([
                html.Div(LANG_FLAGS.get(mkt,"🌐"), style={"fontSize":24,"marginBottom":6}),
                html.Div(str(sc), style={"fontSize":36,"fontWeight":800,"color":score_color(sc),"lineHeight":"1"}),
                html.Div("/100", style={"fontSize":10,"color":T3}),
                html.Div(mkt.upper(), style={"fontSize":11,"fontWeight":700,"color":T2,"marginTop":4}),
                html.Div(f"#{rank}/{len(df)}", style={"fontSize":10,"color":T3,"marginTop":2}),
            ], style={"border":f"1px solid {BD}","borderRadius":12,"padding":"20px","textAlign":"center","flex":1}))

        # Top concurrents
        comp_rows = []
        for i, (_, row) in enumerate(all_df.head(7).iterrows(), 1):
            is_brand = row["name"] == brand
            sc = round(row["score"])
            comp_rows.append(html.Div([
                html.Span(f"#{i}", style={"fontSize":12,"fontWeight":700,"color":C1 if is_brand else T3,
                                          "width":30,"display":"inline-block"}),
                html.Span(f"{'★ ' if is_brand else ''}{row['name']}", style={
                    "fontSize":13,"fontWeight":800 if is_brand else 600,
                    "color":C1 if is_brand else W,"width":180,"display":"inline-block"}),
                html.Div(style={"display":"inline-block","width":f"{sc*1.5}px","height":8,
                                "background":C1 if is_brand else "rgba(168,184,200,0.3)",
                                "borderRadius":4,"marginRight":10,"verticalAlign":"middle"}),
                html.Span(f"{sc}/100", style={"fontSize":13,"fontWeight":800 if is_brand else 600,
                                              "color":score_color(sc)}),
            ], style={"padding":"6px 0","borderBottom":f"1px solid {BD}" if not is_brand else f"1px solid rgba(0,229,255,0.2)",
                      "background":"rgba(0,229,255,0.04)" if is_brand else "transparent"}))

        mkt_label = LANG_FLAGS.get(lang,"") + " " + (lang.upper() if lang else "TOUS MARCHÉS")

        return html.Div([
            card([
                html.Div([
                    html.Div([
                        html.Div(f"GEO SCORE · {mkt_label}", style={"fontSize":10,"fontWeight":700,
                                 "letterSpacing":"2px","color":T3,"marginBottom":8}),
                        html.Div([
                            html.Span(str(global_score), style={"fontSize":52,"fontWeight":800,
                                       "color":score_color(global_score),"lineHeight":"1"}),
                            html.Span("/100", style={"fontSize":16,"color":T3,"marginLeft":4}),
                        ]),
                        html.Div(f"#{global_rank} sur {n_brands} concurrents",
                                 style={"fontSize":12,"color":T3,"marginTop":6}),
                    ], style={"flex":"0 0 200px"}),
                    html.Div(comp_rows, style={"flex":"1","marginLeft":40}),
                ], style={"display":"flex","alignItems":"flex-start"}),
            ], {"marginBottom":16}),
            card([ctitle(f"SCORE PAR MARCHÉ · {len(show_markets)} MARCHÉ{'S' if len(show_markets)>1 else ''}"),
                  html.Div(mcards, style={"display":"flex","gap":16,"flexWrap":"wrap"})]),
        ], style={"marginTop":16})

    # ── TAB: Prompts ──────────────────────────
    def _tab_prompts(lang):
        prompts = load_prompts(db_path, brand, lang, limit=30)
        if not prompts:
            return card([html.Div("Pas de données.", style={"color":T3,"fontSize":12})])
        rows = []
        for p in prompts:
            sc = round(p["score"]); col = score_color(sc)
            rows.append(html.Tr([
                html.Td(html.Span(CAT_LABELS.get(p["category"],p["category"]),
                    style={**badge_style(col),"fontSize":10}), style={"padding":"10px 12px"}),
                html.Td(LANG_FLAGS.get(p["language"],""), style={"padding":"10px 8px","fontSize":14}),
                html.Td(p["text"], style={"padding":"10px 12px","fontSize":12,"color":T2}),
                html.Td(str(sc), style={"padding":"10px 12px","fontWeight":800,"color":col,"fontSize":14,"textAlign":"center"}),
            ], style={"borderBottom":f"1px solid {BD}"}))
        return card([ctitle("ANALYSE PAR PROMPT — du plus faible au plus fort"),
            dbc.Table([html.Thead(html.Tr([
                *[html.Th(h, style={"fontSize":10,"fontWeight":700,"letterSpacing":"1.5px",
                    "textTransform":"uppercase","color":T3,"padding":"8px 12px","background":BG})
                  for h in ["Catégorie","","Prompt","Score"]]]),
                style={"borderBottom":f"2px solid {BD}"}),
                html.Tbody(rows)], bordered=False, hover=False, style={"fontFamily":FONT_BODY})
        ], {"marginTop":16})

    # ── TAB: Bibliothèque ─────────────────────
    def _tab_library(lang):
        prompts = load_prompts(db_path, brand, lang, limit=50)
        if not prompts:
            return card([html.Div("Pas de données.", style={"color":T3,"fontSize":12})])
        cats = {}
        for p in prompts:
            cats.setdefault(CAT_LABELS.get(p["category"],p["category"]), []).append(p)
        blocks = []
        for cat, ps in cats.items():
            items = [html.Li(f"{LANG_FLAGS.get(p['language'],'')} {p['text']}",
                style={"fontSize":12,"color":T2,"marginBottom":6,"listStyle":"none","paddingLeft":8,
                       "borderLeft":f"2px solid {score_color(round(p['score']))}"}) for p in ps]
            blocks.append(html.Div([
                html.Div(cat.upper(), style={"fontSize":10,"fontWeight":700,"color":T3,"letterSpacing":"2px","marginBottom":10}),
                html.Ul(items, style={"padding":0,"margin":0})], style={"marginBottom":20}))
        return card([ctitle("BIBLIOTHÈQUE PROMPTS"), *blocks], {"marginTop":16})

    # ── Export CSV ────────────────────────────
    @app.server.route(f"/export/csv")
    def export_csv():
        from flask import request, Response
        import io, csv
        lang = request.args.get("market") or request.args.get("lang")
        df = load_scores(db_path, lang)
        if df.empty:
            return Response("Pas de données", mimetype="text/plain")
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Marque","Score","Mention%","Fréquence","Primaire"])
        for _, r in df.iterrows():
            w.writerow([r["name"], round(r["score"]), round(r.get("mention_rate",0)*100),
                        round(r.get("freq",0),1), bool(r["is_primary"])])
        return Response(out.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=voxa_{slug}_{lang or 'all'}_{date.today()}.csv"})

    return app


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Voxa Dashboard Générique v2")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--port", type=int, default=8051)
    args = parser.parse_args()
    app = make_dashboard(args.slug, standalone=True)
    print(f"\n✓ Dashboard {args.slug} → http://localhost:{args.port}/\n")
    app.run(debug=True, port=args.port)