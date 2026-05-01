"""
Voxa — Dashboard Générique v2.1
================================
Dashboard Dash unique paramétré par config JSON.
Remplace dashboard.py (PSG) et dashboard_betclic.py (Betclic).

v2.1 (2026-04-30) — Light mode + sidebar layout :
- Layout horizontal : sidebar gauche + content droite (au lieu de tabs horizontales)
- 4 KPI cards séparées avec icônes colorées (au lieu d'1 hero monolithique)
- Filter bar sticky compact horizontal
- Couleurs / classes CSS pilotées par theme.py V2 (light mode)
- Logique métier (callbacks, _tab_*, DB) inchangée

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
from dash import html, dcc, Input, Output, State, ALL, callback_context

import theme as T
from theme import (P, C1, C2, NG, BG, BG2, BG3, BD, BD2, W, T2, T3, RED, GRD,
                   FONTS_URL, DASH_CSS, score_color, score_label,
                   card_style, card_title_style, kpi_value_style, badge_style,
                   FONT_BODY, BG_ACCENT, BG_ACCENT2, BG_OK, BG_ERR)

BASE_DIR = Path(__file__).parent.resolve()

# ─────────────────────────────────────────────
# Recommandations : ne se basent que sur les runs UI (≥ 1er mai 2026)
# Les runs antérieures (API) restent visibles dans le dashboard pour les
# scores agrégés, mais ne contribuent pas aux recommandations actionnables.
# ─────────────────────────────────────────────
RECO_CUTOFF_DATE = "2026-05-01"


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


def load_scores(db_path: str, language: str = None,
                since_date: str = None) -> pd.DataFrame:
    """Charge les scores agrégés par marque.

    Args:
        since_date: si fourni (ex: '2026-05-01'), ne considère que les runs
                     >= cette date. Utilisé par les recommandations pour ne se
                     baser que sur les données UI réelles (post-bascule).
    """
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""
        params = [language] if language and language != "all" else []

        date_filter = ""
        if since_date:
            date_filter = "AND ru.run_date >= ?"
            params = params + [since_date]

        rows = conn.execute(f"""
            SELECT b.name, b.is_primary, AVG(r.geo_score) as score,
                   AVG(r.mentioned) as mention_rate, AVG(r.mention_count) as freq
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
              AND ru.is_demo = 0 {where} {date_filter}
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
                WHERE ru.run_date = (SELECT MAX(run_date) FROM runs) {where} {date_filter}
                GROUP BY b.id ORDER BY score DESC
            """, params).fetchall()
    finally:
        conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def load_scores_by_category(db_path: str, brand: str, language: str = None,
                              since_date: str = None) -> dict:
    """Charge les scores moyens par catégorie de prompt.

    Args:
        since_date: si fourni, filtre les runs >= cette date.
    """
    conn = _conn(db_path)
    try:
        where_lang = "AND p.language = ?" if language and language != "all" else ""
        params = [brand] + ([language] if language and language != "all" else [])

        date_filter = ""
        if since_date:
            date_filter = "AND ru.run_date >= ?"
            params = params + [since_date]

        rows = conn.execute(f"""
            SELECT p.category, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? AND ru.is_demo = 0
              AND ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
              {where_lang} {date_filter}
            GROUP BY p.category
        """, params).fetchall()
    finally:
        conn.close()
    return {r["category"]: round(r["score"]) for r in rows}


def load_history(db_path: str, brand: str, n_weeks: int = 90, lang: str = None) -> list:
    conn = _conn(db_path)
    try:
        lang_where = "AND ru.language = ?" if lang else ""
        params = [brand, lang, n_weeks] if lang else [brand, n_weeks]
        rows = conn.execute(f"""
            SELECT ru.run_date, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            WHERE b.name = ? AND ru.is_demo = 0 {lang_where}
            GROUP BY ru.run_date ORDER BY ru.run_date ASC LIMIT ?
        """, params).fetchall()
        if not rows:
            params_fb = [brand, lang, n_weeks] if lang else [brand, n_weeks]
            rows = conn.execute(f"""
                SELECT ru.run_date, AVG(r.geo_score) as score
                FROM results r JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                WHERE b.name = ? {lang_where}
                GROUP BY ru.run_date ORDER BY ru.run_date ASC LIMIT ?
            """, params_fb).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_prompts(db_path: str, brand: str, language: str = None,
                  limit: int = 20, since_date: str = None) -> list:
    """Charge les prompts avec leur score moyen pour une marque.

    Args:
        since_date: si fourni, filtre les runs >= cette date.
    """
    conn = _conn(db_path)
    try:
        where = "AND p.language = ?" if language and language != "all" else ""

        date_filter = ""
        date_params = []
        if since_date:
            date_filter = "AND ru.run_date >= ?"
            date_params = [since_date]

        params = ([brand]
                  + ([language] if language and language != "all" else [])
                  + date_params
                  + [limit])

        rows = conn.execute(f"""
            SELECT p.text, p.category, p.language,
                   AVG(r.geo_score) as score, AVG(r.mentioned) as mention
            FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? AND ru.is_demo = 0 {where} {date_filter}
            GROUP BY p.id ORDER BY score ASC LIMIT ?
        """, params).fetchall()
        if not rows:
            rows = conn.execute(f"""
                SELECT p.text, p.category, p.language,
                       AVG(r.geo_score) as score, AVG(r.mentioned) as mention
                FROM results r JOIN runs ru ON r.run_id = ru.id
                JOIN brands b ON r.brand_id = b.id
                JOIN prompts p ON ru.prompt_id = p.id
                WHERE b.name = ? {where} {date_filter}
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
    """Génère les recommandations pour le tab Insights.

    IMPORTANT : ne se base que sur les runs >= RECO_CUTOFF_DATE (1er mai 2026),
    c'est-à-dire les runs UI réelles (post-bascule). Les anciennes runs API
    sont visibles dans les autres vues (KPI, classement, évolution) mais ne
    contribuent pas aux recommandations actionnables.
    """
    recos = []
    cat_labels = cat_labels or {}

    cat_scores = load_scores_by_category(db_path, brand, language,
                                          since_date=RECO_CUTOFF_DATE)
    if cat_scores:
        worst_cat = min(cat_scores, key=cat_scores.get)
        best_cat = max(cat_scores, key=cat_scores.get)
        gap = cat_scores[best_cat] - cat_scores[worst_cat]
        if gap >= 30:
            recos.append({"priority": "haute", "icon": "⚠",
                          "title": f"Écart critique : {cat_labels.get(worst_cat, worst_cat)} ({cat_scores[worst_cat]}) vs {cat_labels.get(best_cat, best_cat)} ({cat_scores[best_cat]})",
                          "body": f"Écart de {gap} pts. Enrichir le contenu éditorial et FAQ sur \"{cat_labels.get(worst_cat, worst_cat)}\"."})
        elif cat_scores[worst_cat] < 40:
            recos.append({"priority": "haute", "icon": "⚠",
                          "title": f"Faible score en {cat_labels.get(worst_cat, worst_cat)} : {cat_scores[worst_cat]}/100",
                          "body": f"Les LLMs ne citent quasiment pas {brand} sur ces requêtes. Angle mort à combler."})

    df_all = load_scores(db_path, language, since_date=RECO_CUTOFF_DATE)
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

    absent_prompts = load_prompts(db_path, brand, language, limit=50,
                                    since_date=RECO_CUTOFF_DATE)
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
                      "body": f"{brand} affiche de bons scores depuis le {RECO_CUTOFF_DATE}. Continuer le monitoring."})

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

    db_path = _resolve_db_path(slug)
    brand = cfg["primary_brand"]
    client_name = cfg["client_name"]
    vertical = cfg.get("vertical", "sport")

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
            "fontSize": 10, "fontWeight": 600, "textTransform": "uppercase",
            "letterSpacing": "1.5px", "color": T3, "marginBottom": 12,
            "fontFamily": FONT_BODY})

    # ── Données initiales ─────────────────────
    markets_from_db = load_markets(db_path)
    has_multi_markets = len(markets_from_db) >= 3
    market_opts = [{"label": "🌐 Tous", "value": "all"}] + [
        {"label": f"{LANG_FLAGS.get(m,'🌐')} {m.upper()}", "value": m}
        for m in markets_from_db]

    # ── Topbar ──
    topbar = T.make_topbar(client_name=client_name, vertical=vertical,
                           right_children=[
                               html.A("↓ CSV", id=f"export-{slug}", href=f"{prefix}export/csv",
                                      style={"padding": "6px 12px", "borderRadius": 8,
                                             "border": f"0.5px solid {BD}", "background": BG3,
                                             "fontSize": 12, "fontWeight": 600, "color": T2,
                                             "textDecoration": "none"})])

    # ── Sidebar : structure 3 sections (MONITOR / IMPROVE / DISCOVER) ──
    # Définition de la structure sidebar : liste de (section_label, items)
    # Chaque item : (tab_id, label) — l'ordre détermine l'affichage
    sidebar_structure = [
        ("MONITOR", [
            *([("overview", "Vue générale")] if has_multi_markets else []),
            ("ranking", "Classement"),
            ("prompts", "Prompts"),
        ]),
        ("IMPROVE", [
            ("actions", "Pack Action"),
            ("insights", "Insights"),
        ]),
        ("DISCOVER", [
            ("library", "Bibliothèque"),
        ]),
    ]

    # Tab par défaut au démarrage
    default_tab = "overview" if has_multi_markets else "ranking"

    # Construction des éléments de la sidebar
    def _build_sidebar_items():
        children = []
        for section_label, items in sidebar_structure:
            children.append(html.Div(section_label, className="voxa-nav-section"))
            for tab_id, label in items:
                children.append(html.Div(
                    label,
                    id={"type": f"nav-{slug}", "tab": tab_id},
                    className="voxa-nav-item active" if tab_id == default_tab else "voxa-nav-item",
                    n_clicks=0,
                ))
        return children

    sidebar_children = _build_sidebar_items()

    # ── Filter bar (compact horizontal sticky) ──
    filter_bar = html.Div([
        html.Span("Marché :", style={
            "fontSize": 10, "fontWeight": 600,
            "color": T3, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "marginRight": 8}),
        dbc.RadioItems(
            id=f"market-{slug}",
            options=market_opts, value="all",
            inline=True,
            inputStyle={"marginRight": 4},
            labelStyle={"color": T2, "fontSize": 12, "marginRight": 12, "cursor": "pointer"},
        ),
    ], className="voxa-filter-bar")

    # ── Footer ──
    footer = html.Div([
        html.Span("✓ Prompt library verticale · données propriétaires · historique indépendant"),
        html.Span(["Voxa GEO Intelligence · ",
                   html.A("luc@sharper-media.com", href="mailto:luc@sharper-media.com",
                          style={"color": C1, "textDecoration": "none"})]),
    ], style={"background": BG3, "borderTop": f"0.5px solid {BD}",
              "padding": "12px 32px", "fontSize": 11, "color": T3,
              "display": "flex", "justifyContent": "space-between",
              "fontFamily": FONT_BODY})

    # ── Layout horizontal sidebar + content ──
    app.layout = html.Div([
        # Store qui maintient le tab actif
        dcc.Store(id=f"active-tab-{slug}", data=default_tab),
        topbar,
        filter_bar,
        html.Div([
            # Sidebar à gauche : structure custom avec sections
            html.Div(sidebar_children, className="voxa-sidebar"),
            # Content area à droite
            html.Div([
                html.Div(id=f"hero-{slug}", style={"padding": "20px 28px 0"}),
                html.Div(id=f"content-{slug}", style={"padding": "16px 28px 24px"}),
            ], className="voxa-content"),
        ], className="voxa-app"),
        footer,
    ])

    # ── Hero KPI : 4 cards séparées avec icônes colorées ──
    @app.callback(Output(f"hero-{slug}", "children"), Input(f"market-{slug}", "value"))
    def update_hero(market):
        lang = None if market == "all" else market
        df = load_scores(db_path, lang)
        hist = load_history(db_path, brand, lang=lang)
        nss = load_nss(db_path, brand, lang)
        primary = df[df["name"] == brand] if not df.empty else pd.DataFrame()
        sc_val = round(primary["score"].iloc[0]) if not primary.empty else 0
        mention_pct = (round(primary["mention_rate"].iloc[0] * 100)
                       if not primary.empty else 0)

        # Couleurs accent par KPI
        sc_accent = score_color(sc_val) if score_color(sc_val) != T3 else C1
        nss_accent = NG if nss >= 0 else RED

        return dbc.Row([
            dbc.Col(T.make_kpi_card(
                label=f"GEO score · {brand}",
                value=f"{sc_val}/100",
                icon_key="score",
                accent_color=sc_accent,
            ), width=3),
            dbc.Col(T.make_kpi_card(
                label="Net sentiment",
                value=f"{nss:+d}%",
                icon_key="sentiment",
                accent_color=nss_accent,
            ), width=3),
            dbc.Col(T.make_kpi_card(
                label="Runs analysés",
                value=str(len(hist)),
                icon_key="prompt",
                accent_color=C1,
            ), width=3),
            dbc.Col(T.make_kpi_card(
                label="Taux de mentions",
                value=f"{mention_pct}%",
                icon_key="mention",
                accent_color=C2,
            ), width=3),
        ], className="g-2", style={"marginBottom": 16})

    # ── Sidebar callbacks (3 callbacks pour gérer la nav custom) ──
    # 1) Click sur un nav-item → met à jour le store active-tab
    @app.callback(
        Output(f"active-tab-{slug}", "data"),
        Input({"type": f"nav-{slug}", "tab": ALL}, "n_clicks"),
        State({"type": f"nav-{slug}", "tab": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _on_nav_click(n_clicks_list, ids):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update
        # Récupérer l'item cliqué (parsing du dict-id JSON)
        triggered_prop = ctx.triggered[0]["prop_id"]
        if not triggered_prop or triggered_prop == ".":
            return dash.no_update
        # Vérifier qu'un click a vraiment eu lieu (filtre les n_clicks=None initiaux)
        if not any(n_clicks_list):
            return dash.no_update
        triggered_id = json.loads(triggered_prop.split(".")[0])
        return triggered_id["tab"]

    # 2) Mise à jour de la classe CSS active sur les nav-items
    @app.callback(
        Output({"type": f"nav-{slug}", "tab": ALL}, "className"),
        Input(f"active-tab-{slug}", "data"),
        State({"type": f"nav-{slug}", "tab": ALL}, "id"),
    )
    def _update_active_class(active_tab, ids):
        return [
            "voxa-nav-item active" if id_["tab"] == active_tab else "voxa-nav-item"
            for id_ in ids
        ]

    # 3) Routing du contenu (logique métier inchangée, l'input vient du store)
    @app.callback(
        Output(f"content-{slug}", "children"),
        Input(f"active-tab-{slug}", "data"),
        Input(f"market-{slug}", "value"),
    )
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
        hist = load_history(db_path, brand, lang=lang)

        if not df.empty:
            colors = [C1 if row["is_primary"] else T3 for _, row in df.iterrows()]
            bar = go.Figure(go.Bar(x=df["score"].round().astype(int), y=df["name"],
                                   orientation="h", marker_color=colors,
                                   text=df["score"].round().astype(int).astype(str) + "/100",
                                   textposition="auto",
                                   textfont={"size": 12, "color": "#FFFFFF", "family": FONT_BODY},
                                   )).update_layout(
                height=max(200, len(df) * 40), margin=dict(l=0, r=10, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, range=[0, 100], showticklabels=False, zeroline=False),
                yaxis=dict(tickfont={"size": 12, "color": T2, "family": FONT_BODY}),
                font={"family": FONT_BODY}, showlegend=False)
            bar_c = card([ctitle("CLASSEMENT CONCURRENTS"),
                          dcc.Graph(figure=bar, config={"displayModeBar": False})])
        else:
            bar_c = card([ctitle("CLASSEMENT"),
                          html.Div("Pas de données.", style={"color": T3, "fontSize": 12})])

        if hist and len(hist) > 1:
            line = go.Figure(go.Scatter(
                x=[h["run_date"] for h in hist], y=[round(h["score"]) for h in hist],
                mode="lines+markers", line=dict(color=C1, width=2),
                marker=dict(color=C1, size=6),
                fill="tozeroy", fillcolor="rgba(0,184,212,0.08)",
                hovertemplate="%{y}/100<extra></extra>",
            )).update_layout(
                height=200, margin=dict(l=0, r=10, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, tickfont={"size": 10, "color": T3, "family": FONT_BODY}),
                yaxis=dict(range=[0, 100], showgrid=True, gridcolor="rgba(13,17,23,0.04)",
                           tickfont={"size": 10, "color": T3}),
                font={"family": FONT_BODY})
            line_c = card([ctitle(f"ÉVOLUTION · {brand.upper()}"),
                           dcc.Graph(figure=line, config={"displayModeBar": False})])
        else:
            line_c = card([ctitle(f"ÉVOLUTION · {brand.upper()}"),
                           html.Div("Données insuffisantes.", style={"color": T3, "fontSize": 12})])

        return dbc.Row([dbc.Col(bar_c, width=6), dbc.Col(line_c, width=6)],
                       style={"marginTop": 16})

    # ── TAB: Insights ─────────────────────────
    def _tab_insights(lang):
        PS = {
            "haute":   {"border": RED, "bg": BG_ERR, "bbg": "rgba(239,68,68,0.12)", "bcol": RED},
            "moyenne": {"border": C1,  "bg": BG_ACCENT, "bbg": "rgba(0,184,212,0.12)", "bcol": C1},
            "info":    {"border": NG,  "bg": BG_OK, "bbg": "rgba(16,185,129,0.12)", "bcol": NG},
        }

        def reco_ui(icon, prio, title, body_t, impact=None, prompt_t=None):
            ps = PS.get(prio, PS["info"])
            return html.Div([
                html.Div([
                    html.Span(icon, style={"fontSize": 15, "marginRight": 8}),
                    html.Span(prio.upper(), style={
                        "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
                        "padding": "2px 8px", "borderRadius": 12,
                        "background": ps["bbg"], "color": ps["bcol"],
                        "marginRight": 10, "fontFamily": FONT_BODY}),
                    html.Span(title, style={
                        "fontSize": 13, "fontWeight": 600, "color": W,
                        "fontFamily": FONT_BODY}),
                    *([html.Span(f"+{impact:.0f} pts",
                                 style={"fontSize": 10, "color": T3, "marginLeft": 10})]
                      if impact else []),
                ], style={"marginBottom": 6}),
                html.Div(body_t, style={
                    "fontSize": 12, "color": T2, "lineHeight": "1.7",
                    "paddingLeft": 22, "fontFamily": FONT_BODY}),
                *([html.Div(f"Prompt : « {prompt_t[:80]}… »",
                            style={"fontSize": 10, "color": T3, "paddingLeft": 22,
                                   "marginTop": 4, "fontStyle": "italic"})] if prompt_t else []),
            ], style={"borderLeft": f"3px solid {ps['border']}", "background": ps["bg"],
                      "borderRadius": "0 8px 8px 0", "padding": "12px 18px", "marginBottom": 10})

        recos = generate_recommendations(db_path, brand, vertical, lang, CAT_LABELS)
        reco_cards = [reco_ui(r.get("icon", "💡"), r["priority"], r["title"], r["body"]) for r in recos]

        alert_block = db_block = html.Div()
        try:
            import voxa_db as vdb
            db_alerts = vdb.get_alerts(slug, unread_only=True)
            db_recos = vdb.get_recommendations(slug)
            SS = {"critical": {"i": "⚠", "b": RED, "bg": BG_ERR},
                  "warning":  {"i": "◎", "b": C1, "bg": BG_ACCENT},
                  "info":     {"i": "✓", "b": NG, "bg": BG_OK}}
            if db_alerts:
                aitems = []
                for a in db_alerts:
                    ss = SS.get(a.get("severity", "info"), SS["info"])
                    aitems.append(html.Div([
                        html.Div([html.Span(ss["i"],
                                            style={"marginRight": 8, "fontSize": 12,
                                                   "color": ss["b"], "fontWeight": 700}),
                                  html.Span(a["title"],
                                            style={"fontWeight": 600, "color": W, "fontSize": 13}),
                                  html.Span(f" {a['created_at'][:10]}",
                                            style={"fontSize": 10, "color": T3, "marginLeft": 10})],
                                 style={"marginBottom": 3}),
                        html.Div(a["body"],
                                 style={"fontSize": 12, "color": T2, "paddingLeft": 20,
                                        "lineHeight": 1.5}),
                    ], style={"padding": "10px 14px", "marginBottom": 8, "background": ss["bg"],
                              "borderRadius": 8, "borderLeft": f"3px solid {ss['b']}"}))
                alert_block = card([ctitle("ALERTES ACTIVES"), *aitems], {"marginBottom": 16})
            if db_recos:
                pm = {"high": "haute", "medium": "moyenne", "low": "info"}
                dcards = [reco_ui("💡", pm.get(r.get("priority"), "moyenne"), r.get("title", ""),
                                  r.get("body", ""), impact=r.get("impact_score"),
                                  prompt_t=r.get("prompt_text"))
                          for r in db_recos]
                db_block = card([ctitle("RECOMMANDATIONS GEO — ACTIONS PRIORITAIRES"), *dcards,
                                 html.Div("Générées après chaque run tracker.",
                                          style={"fontSize": 11, "color": T3, "marginTop": 8,
                                                 "fontStyle": "italic"})], {"marginBottom": 16})
        except Exception:
            pass

        gap_section = html.Div("Données insuffisantes.",
                               style={"color": T3, "fontSize": 12, "padding": "12px 0"})
        gap_df = load_gap_analysis(db_path, lang)
        if not gap_df.empty:
            cat_cols = [c for c in gap_df.columns if c in CAT_LABELS]
            brand_sc = gap_df.loc[brand] if brand in gap_df.index else pd.Series()
            hdr = [html.Th("", style={"width": 130, "padding": "8px 12px"})] + [
                html.Th(CAT_LABELS.get(c, c),
                        style={"fontSize": 10, "fontWeight": 600, "textTransform": "uppercase",
                               "letterSpacing": "1px", "color": T3, "textAlign": "center",
                               "padding": "8px 12px", "background": BG})
                for c in cat_cols]
            rows = []
            for b in gap_df.index:
                is_p = (b == brand)
                cells = [html.Td(b, style={"fontWeight": 700 if is_p else 500, "fontSize": 13,
                                           "color": C1 if is_p else W, "padding": "10px 12px",
                                           "background": BG_ACCENT if is_p else BG3})]
                for c in cat_cols:
                    val = int(gap_df.loc[b, c]) if c in gap_df.columns else 0
                    if is_p:
                        bg_c, col = BG_ACCENT, C1
                    else:
                        d = val - (int(brand_sc[c]) if c in brand_sc.index else 0)
                        if d > 10:
                            bg_c, col = BG_ERR, RED
                        elif d < -10:
                            bg_c, col = BG_OK, NG
                        else:
                            bg_c, col = BG3, T2
                    cells.append(html.Td(str(val),
                                         style={"textAlign": "center", "fontSize": 14,
                                                "fontWeight": 700 if is_p else 500,
                                                "color": col, "background": bg_c,
                                                "padding": "10px 12px"}))
                rows.append(html.Tr(cells, style={"borderBottom": f"0.5px solid {BD}"}))
            gap_section = dbc.Table([html.Thead(html.Tr(hdr),
                                                style={"borderBottom": f"1px solid {BD}"}),
                                     html.Tbody(rows)],
                                    bordered=False, hover=False,
                                    style={"fontFamily": FONT_BODY})

        mkt_lbl = lang.upper() if lang else "TOUS MARCHÉS"
        return html.Div([
            alert_block,
            card([ctitle(f"RECOMMANDATIONS · {mkt_lbl}"),
                  *(reco_cards or [html.Div("Aucune recommandation critique.",
                                            style={"color": T3, "fontSize": 12})])],
                 {"marginBottom": 16}),
            db_block,
            card([ctitle(f"GAP ANALYSIS · {brand.upper()} VS CONCURRENTS"),
                  html.Div([
                      html.Span("", style={"display": "inline-block", "width": 8, "height": 8,
                                           "borderRadius": 3, "background": NG, "marginRight": 4}),
                      html.Span(f"{brand} devant",
                                style={"fontSize": 10, "color": NG, "marginRight": 16}),
                      html.Span("", style={"display": "inline-block", "width": 8, "height": 8,
                                           "borderRadius": 3, "background": RED, "marginRight": 4}),
                      html.Span("Concurrent devant", style={"fontSize": 10, "color": RED}),
                  ], style={"marginBottom": 12}),
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

        if not pack or not pack.get("items"):
            pack_section = card([
                ctitle("PACK ACTIONS HEBDO"),
                html.Div([
                    html.Div("Aucun pack généré cette semaine.",
                             style={"fontSize": 13, "color": T3, "marginBottom": 12}),
                    html.Div("Lancez la commande pour générer le premier pack :",
                             style={"fontSize": 12, "color": T3, "marginBottom": 8}),
                    html.Code("python3 action_pack.py --slug " + slug + " --iterate",
                             style={"fontSize": 12, "padding": "8px 14px", "display": "block",
                                    "background": BG, "borderRadius": 8, "color": C1}),
                ]),
            ], {"marginBottom": 16})
        else:
            week_label = pack.get("week", "")
            items_ui = []
            for item in pack["items"]:
                sc_cur = item.get("score_current", 0)
                sc_pred = item.get("score_predicted", 0)
                delta = sc_pred - sc_cur
                status = item.get("status", "pending")
                prompt = item.get("prompt_text", "")
                content = item.get("content", "")
                jsonld = item.get("jsonld_schema", "")
                n_iter = item.get("n_iterations", 1)
                cat = item.get("category", "")

                if delta >= 40:
                    border_col, bg_col, prio_label = RED, BG_ERR, "HAUTE"
                elif delta >= 20:
                    border_col, bg_col, prio_label = C1, BG_ACCENT, "MOYENNE"
                else:
                    border_col, bg_col, prio_label = NG, BG_OK, "INFO"

                if status == "implemented":
                    status_badge = html.Span("✓ IMPLÉMENTÉ", style={
                        "fontSize": 9, "fontWeight": 700, "padding": "2px 8px",
                        "borderRadius": 12, "background": BG_OK,
                        "color": NG, "marginLeft": 10})
                elif status == "measured":
                    sc_real = item.get("score_real", 0)
                    diff = sc_real - sc_pred
                    diff_col = NG if diff >= -5 else RED
                    status_badge = html.Span(
                        f"MESURÉ : {sc_real}/100 ({diff:+d} vs prédit)",
                        style={"fontSize": 9, "fontWeight": 700, "padding": "2px 8px",
                               "borderRadius": 12, "background": BG_OK,
                               "color": diff_col, "marginLeft": 10})
                else:
                    status_badge = html.Span("EN ATTENTE", style={
                        "fontSize": 9, "fontWeight": 700, "padding": "2px 8px",
                        "borderRadius": 12, "background": BG2,
                        "color": T3, "marginLeft": 10})

                item_ui = html.Div([
                    html.Div([
                        html.Span(prio_label, style={
                            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
                            "padding": "2px 8px", "borderRadius": 12,
                            "background": bg_col, "color": border_col,
                            "marginRight": 10, "fontFamily": FONT_BODY}),
                        html.Span(f"[{cat}] " if cat else "",
                                  style={"fontSize": 10, "color": T3, "marginRight": 4}),
                        html.Span(prompt[:80] + ("..." if len(prompt) > 80 else ""),
                                  style={"fontSize": 13, "fontWeight": 600, "color": W,
                                         "fontFamily": FONT_BODY}),
                        status_badge,
                    ], style={"marginBottom": 8}),
                    html.Div([
                        html.Span("Score actuel : ", style={"fontSize": 12, "color": T3}),
                        html.Span(f"{sc_cur}/100",
                                  style={"fontSize": 14, "fontWeight": 700,
                                         "color": score_color(sc_cur), "marginRight": 16}),
                        html.Span(" → ", style={"fontSize": 14, "color": T3, "marginRight": 16}),
                        html.Span("Prédit : ", style={"fontSize": 12, "color": T3}),
                        html.Span(f"{sc_pred}/100",
                                  style={"fontSize": 14, "fontWeight": 700,
                                         "color": score_color(sc_pred), "marginRight": 16}),
                        html.Span(f"(+{delta})",
                                  style={"fontSize": 12, "fontWeight": 600, "color": NG}),
                        html.Span(f" · {n_iter} itération{'s' if n_iter > 1 else ''}",
                                  style={"fontSize": 10, "color": T3, "marginLeft": 12}),
                    ], style={"marginBottom": 10}),
                    html.Details([
                        html.Summary("Voir le contenu optimisé + JSON-LD",
                                     style={"fontSize": 12, "color": C1, "cursor": "pointer",
                                            "fontWeight": 600, "fontFamily": FONT_BODY}),
                        html.Div([
                            html.Div("CONTENU OPTIMISÉ",
                                     style={"fontSize": 9, "fontWeight": 600,
                                            "letterSpacing": "1.5px", "color": T3,
                                            "marginBottom": 6, "marginTop": 10}),
                            html.Pre(content,
                                     style={"fontSize": 12, "color": T2, "lineHeight": "1.6",
                                            "background": BG, "padding": "12px 14px",
                                            "borderRadius": 8, "border": f"0.5px solid {BD}",
                                            "whiteSpace": "pre-wrap", "fontFamily": FONT_BODY,
                                            "maxHeight": 200, "overflowY": "auto"}),
                            *([html.Div([
                                html.Div("JSON-LD (copier dans <head>)",
                                         style={"fontSize": 9, "fontWeight": 600,
                                                "letterSpacing": "1.5px", "color": T3,
                                                "marginBottom": 6, "marginTop": 12}),
                                html.Pre(jsonld,
                                         style={"fontSize": 11, "color": "#006B7A",
                                                "lineHeight": "1.4", "background": BG,
                                                "padding": "12px 14px", "borderRadius": 8,
                                                "border": f"0.5px solid {BD}",
                                                "whiteSpace": "pre-wrap",
                                                "fontFamily": "'JetBrains Mono', monospace",
                                                "maxHeight": 250, "overflowY": "auto"}),
                            ])] if jsonld else []),
                        ]),
                    ], style={"marginTop": 4}),
                ], style={"borderLeft": f"3px solid {border_col}", "background": bg_col,
                          "borderRadius": "0 8px 8px 0",
                          "padding": "14px 18px", "marginBottom": 12})
                items_ui.append(item_ui)

            pack_section = card([
                ctitle(f"PACK ACTIONS · SEMAINE {week_label}"),
                html.Div(f"Généré le {pack.get('created_at', '')[:10]} · {pack['n_items']} actions",
                         style={"fontSize": 11, "color": T3, "marginBottom": 14}),
                *items_ui,
            ], {"marginBottom": 16})

        hist_section = html.Div()
        if history and len(history) > 0:
            hist_rows = []
            for h in history:
                avg_cur = round(h.get("avg_current") or 0)
                avg_pred = round(h.get("avg_predicted") or 0)
                avg_real = round(h.get("avg_real") or 0) if h.get("avg_real") else "—"
                n_impl = h.get("n_implemented", 0)
                n_items = h.get("n_items", 0)
                accuracy = ""
                if isinstance(avg_real, int) and avg_pred > 0:
                    diff = avg_real - avg_pred
                    accuracy = f"{diff:+d}"
                hist_rows.append(html.Tr([
                    html.Td(h.get("week", ""),
                            style={"padding": "8px 12px", "fontWeight": 600,
                                   "color": C1, "fontSize": 12}),
                    html.Td(f"{n_impl}/{n_items}",
                            style={"padding": "8px 12px", "color": T2, "fontSize": 12}),
                    html.Td(str(avg_cur),
                            style={"padding": "8px 12px", "color": score_color(avg_cur),
                                   "fontWeight": 600, "fontSize": 13}),
                    html.Td(str(avg_pred),
                            style={"padding": "8px 12px", "color": C1,
                                   "fontWeight": 600, "fontSize": 13}),
                    html.Td(str(avg_real),
                            style={"padding": "8px 12px",
                                   "color": NG if isinstance(avg_real, int) else T3,
                                   "fontWeight": 600, "fontSize": 13}),
                    html.Td(accuracy,
                            style={"padding": "8px 12px",
                                   "color": NG if accuracy.startswith("+") or accuracy == "" else RED,
                                   "fontWeight": 600, "fontSize": 12}),
                ], style={"borderBottom": f"0.5px solid {BD}"}))

            hist_section = card([
                ctitle("HISTORIQUE DES PACKS"),
                dbc.Table([
                    html.Thead(html.Tr([
                        *[html.Th(h, style={
                            "fontSize": 10, "fontWeight": 600, "letterSpacing": "1.5px",
                            "textTransform": "uppercase", "color": T3,
                            "padding": "8px 12px", "background": BG})
                          for h in ["Semaine", "Implémenté", "Avant", "Prédit", "Réel", "Δ préd."]]
                    ]), style={"borderBottom": f"1px solid {BD}"}),
                    html.Tbody(hist_rows),
                ], bordered=False, hover=False, style={"fontFamily": FONT_BODY}),
                html.Div("Le score réel est mesuré 4 semaines après implémentation.",
                         style={"fontSize": 11, "color": T3, "marginTop": 8, "fontStyle": "italic"}),
            ])

        return html.Div([pack_section, hist_section], style={"marginTop": 16})

    # ── TAB: Vue générale (multi-marchés) ─────
    def _tab_overview(lang):
        all_df = load_scores(db_path, lang)
        brand_row = all_df[all_df["name"] == brand] if not all_df.empty else pd.DataFrame()
        global_score = round(brand_row["score"].iloc[0]) if not brand_row.empty else 0
        global_rank = all_df.index.get_loc(brand_row.index[0]) + 1 if not brand_row.empty else "—"
        n_brands = len(all_df)
        show_markets = [lang] if lang else markets_from_db

        mcards = []
        for mkt in show_markets:
            df = load_scores(db_path, mkt)
            pr = df[df["name"] == brand] if not df.empty else pd.DataFrame()
            sc = round(pr["score"].iloc[0]) if not pr.empty else 0
            rank = df.index.get_loc(pr.index[0]) + 1 if not pr.empty else "—"
            mcards.append(html.Div([
                html.Div(LANG_FLAGS.get(mkt, "🌐"), style={"fontSize": 24, "marginBottom": 6}),
                html.Div(str(sc),
                         style={"fontSize": 32, "fontWeight": 600,
                                "color": score_color(sc), "lineHeight": "1"}),
                html.Div("/100", style={"fontSize": 10, "color": T3}),
                html.Div(mkt.upper(),
                         style={"fontSize": 11, "fontWeight": 600,
                                "color": T2, "marginTop": 4}),
                html.Div(f"#{rank}/{len(df)}",
                         style={"fontSize": 10, "color": T3, "marginTop": 2}),
            ], style={"border": f"0.5px solid {BD}", "borderRadius": 8,
                      "padding": "20px", "textAlign": "center", "flex": 1,
                      "background": BG3}))

        comp_rows = []
        for i, (_, row) in enumerate(all_df.head(7).iterrows(), 1):
            is_brand = row["name"] == brand
            sc = round(row["score"])
            comp_rows.append(html.Div([
                html.Span(f"#{i}", style={"fontSize": 12, "fontWeight": 600,
                                          "color": C1 if is_brand else T3,
                                          "width": 30, "display": "inline-block"}),
                html.Span(f"{'★ ' if is_brand else ''}{row['name']}",
                          style={"fontSize": 13, "fontWeight": 700 if is_brand else 500,
                                 "color": C1 if is_brand else W,
                                 "width": 180, "display": "inline-block"}),
                html.Div(style={"display": "inline-block", "width": f"{sc * 1.5}px",
                                "height": 8, "background": C1 if is_brand else BG2,
                                "borderRadius": 4, "marginRight": 10,
                                "verticalAlign": "middle"}),
                html.Span(f"{sc}/100",
                          style={"fontSize": 13, "fontWeight": 700 if is_brand else 500,
                                 "color": score_color(sc)}),
            ], style={"padding": "6px 0",
                      "borderBottom": f"0.5px solid {BD}",
                      "background": BG_ACCENT if is_brand else "transparent"}))

        mkt_label = LANG_FLAGS.get(lang, "") + " " + (lang.upper() if lang else "TOUS MARCHÉS")
        return html.Div([
            card([
                html.Div([
                    html.Div([
                        html.Div(f"GEO SCORE · {mkt_label}",
                                 style={"fontSize": 10, "fontWeight": 600,
                                        "letterSpacing": "1.5px", "color": T3,
                                        "marginBottom": 8}),
                        html.Div([
                            html.Span(str(global_score),
                                      style={"fontSize": 48, "fontWeight": 600,
                                             "color": score_color(global_score),
                                             "lineHeight": "1"}),
                            html.Span("/100",
                                      style={"fontSize": 16, "color": T3, "marginLeft": 4}),
                        ]),
                        html.Div(f"#{global_rank} sur {n_brands} concurrents",
                                 style={"fontSize": 12, "color": T3, "marginTop": 6}),
                    ], style={"flex": "0 0 200px"}),
                    html.Div(comp_rows, style={"flex": "1", "marginLeft": 40}),
                ], style={"display": "flex", "alignItems": "flex-start"}),
            ], {"marginBottom": 16}),
            card([ctitle(f"SCORE PAR MARCHÉ · {len(show_markets)} MARCHÉ{'S' if len(show_markets) > 1 else ''}"),
                  html.Div(mcards, style={"display": "flex", "gap": 16, "flexWrap": "wrap"})]),
        ], style={"marginTop": 16})

    # ── TAB: Prompts ──────────────────────────
    def _tab_prompts(lang):
        prompts = load_prompts(db_path, brand, lang, limit=30)
        if not prompts:
            return card([html.Div("Pas de données.", style={"color": T3, "fontSize": 12})])
        rows = []
        for p in prompts:
            sc = round(p["score"])
            col = score_color(sc)
            rows.append(html.Tr([
                html.Td(html.Span(CAT_LABELS.get(p["category"], p["category"]),
                                  style={**badge_style(col), "fontSize": 10}),
                        style={"padding": "10px 12px"}),
                html.Td(LANG_FLAGS.get(p["language"], ""),
                        style={"padding": "10px 8px", "fontSize": 14}),
                html.Td(p["text"],
                        style={"padding": "10px 12px", "fontSize": 12, "color": T2}),
                html.Td(str(sc),
                        style={"padding": "10px 12px", "fontWeight": 700, "color": col,
                               "fontSize": 14, "textAlign": "center"}),
            ], style={"borderBottom": f"0.5px solid {BD}"}))
        return card([
            ctitle("ANALYSE PAR PROMPT — du plus faible au plus fort"),
            dbc.Table([
                html.Thead(html.Tr([
                    *[html.Th(h, style={"fontSize": 10, "fontWeight": 600,
                                        "letterSpacing": "1.5px", "textTransform": "uppercase",
                                        "color": T3, "padding": "8px 12px", "background": BG})
                      for h in ["Catégorie", "", "Prompt", "Score"]]
                ]), style={"borderBottom": f"1px solid {BD}"}),
                html.Tbody(rows)
            ], bordered=False, hover=False, style={"fontFamily": FONT_BODY})
        ], {"marginTop": 16})

    # ── TAB: Bibliothèque ─────────────────────
    def _tab_library(lang):
        prompts = load_prompts(db_path, brand, lang, limit=50)
        if not prompts:
            return card([html.Div("Pas de données.", style={"color": T3, "fontSize": 12})])
        cats = {}
        for p in prompts:
            cats.setdefault(CAT_LABELS.get(p["category"], p["category"]), []).append(p)
        blocks = []
        for cat, ps in cats.items():
            items = [html.Li(f"{LANG_FLAGS.get(p['language'], '')} {p['text']}",
                             style={"fontSize": 12, "color": T2, "marginBottom": 6,
                                    "listStyle": "none", "paddingLeft": 8,
                                    "borderLeft": f"2px solid {score_color(round(p['score']))}"})
                     for p in ps]
            blocks.append(html.Div([
                html.Div(cat.upper(),
                         style={"fontSize": 10, "fontWeight": 600, "color": T3,
                                "letterSpacing": "1.5px", "marginBottom": 10}),
                html.Ul(items, style={"padding": 0, "margin": 0})
            ], style={"marginBottom": 20}))
        return card([ctitle("BIBLIOTHÈQUE PROMPTS"), *blocks], {"marginTop": 16})

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
        w.writerow(["Marque", "Score", "Mention%", "Fréquence", "Primaire"])
        for _, r in df.iterrows():
            w.writerow([r["name"], round(r["score"]),
                        round(r.get("mention_rate", 0) * 100),
                        round(r.get("freq", 0), 1), bool(r["is_primary"])])
        return Response(out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition":
                                 f"attachment;filename=voxa_{slug}_{lang or 'all'}_{date.today()}.csv"})

    return app


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Voxa Dashboard Générique v2.1")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--port", type=int, default=8051)
    args = parser.parse_args()
    app = make_dashboard(args.slug, standalone=True)
    print(f"\n✓ Dashboard {args.slug} → http://localhost:{args.port}/\n")
    app.run(debug=True, port=args.port)