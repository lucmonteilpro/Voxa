"""
Voxa — Dashboard Générique v1.0
================================
Un seul fichier Dash paramétré par config JSON.
Fonctionne pour Reims, Le Havre, ASSE, Monaco, et tous les futurs clients.

Usage direct :
    python3 dashboard_generic.py --config configs/reims.json --port 8051

Intégration wsgi.py :
    from dashboard_generic import make_dashboard
    reims_server = make_dashboard("reims").server
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output

import theme as T
from theme import (P, C1, C2, NG, BG, BG3, BD, W, T2, T3, RED, GRD,
                   FONTS_URL, DASH_CSS, score_color, score_label,
                   card_style, card_title_style, kpi_value_style, badge_style)

BASE_DIR = Path(__file__).parent.resolve()


# ─────────────────────────────────────────────
# DB HELPERS (génériques)
# ─────────────────────────────────────────────

def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_scores(db_path: str, language: str = None) -> pd.DataFrame:
    """Score moyen par marque sur le dernier run."""
    conn = _conn(db_path)
    where = "AND p.language = ?" if language and language != "all" else ""
    params = [language] if language and language != "all" else []
    rows = conn.execute(f"""
        SELECT b.name, b.is_primary, AVG(r.geo_score) as score,
               AVG(r.mentioned) as mention_rate,
               AVG(r.mention_count) as freq
        FROM results r
        JOIN runs ru    ON r.run_id = ru.id
        JOIN brands b   ON r.brand_id = b.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE ru.run_date = (SELECT MAX(run_date) FROM runs WHERE is_demo=0)
          AND ru.is_demo = 0
          {where}
        GROUP BY b.id
        ORDER BY score DESC
    """, params).fetchall()
    if not rows:
        # Fallback sur démo
        rows = conn.execute(f"""
            SELECT b.name, b.is_primary, AVG(r.geo_score) as score,
                   AVG(r.mentioned) as mention_rate, AVG(r.mention_count) as freq
            FROM results r
            JOIN runs ru  ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE ru.run_date = (SELECT MAX(run_date) FROM runs)
              {where}
            GROUP BY b.id ORDER BY score DESC
        """, params).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def load_history(db_path: str, brand: str, n_weeks: int = 10) -> list:
    conn = _conn(db_path)
    rows = conn.execute("""
        SELECT ru.run_date, AVG(r.geo_score) as score
        FROM results r
        JOIN runs ru  ON r.run_id = ru.id
        JOIN brands b ON r.brand_id = b.id
        WHERE b.name = ? AND ru.is_demo = 0
        GROUP BY ru.run_date ORDER BY ru.run_date ASC
        LIMIT ?
    """, (brand, n_weeks)).fetchall()
    if not rows:
        rows = conn.execute("""
            SELECT ru.run_date, AVG(r.geo_score) as score
            FROM results r
            JOIN runs ru  ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            WHERE b.name = ?
            GROUP BY ru.run_date ORDER BY ru.run_date ASC LIMIT ?
        """, (brand, n_weeks)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_prompts(db_path: str, brand: str, language: str = None, limit: int = 20) -> list:
    conn = _conn(db_path)
    where = "AND p.language = ?" if language and language != "all" else ""
    params = [brand, limit] if not (language and language != "all") else [brand, language, limit]
    rows = conn.execute(f"""
        SELECT p.text, p.category, p.language,
               AVG(r.geo_score) as score,
               AVG(r.mentioned) as mention
        FROM results r
        JOIN runs ru   ON r.run_id = ru.id
        JOIN brands b  ON r.brand_id = b.id
        JOIN prompts p ON ru.prompt_id = p.id
        WHERE b.name = ? AND ru.is_demo = 0
          {where}
        GROUP BY p.id ORDER BY score ASC LIMIT ?
    """, params).fetchall()
    if not rows:
        rows = conn.execute(f"""
            SELECT p.text, p.category, p.language,
                   AVG(r.geo_score) as score, AVG(r.mentioned) as mention
            FROM results r
            JOIN runs ru  ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? {where}
            GROUP BY p.id ORDER BY score ASC LIMIT ?
        """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_last_run_date(db_path: str) -> str:
    conn = _conn(db_path)
    row = conn.execute("SELECT MAX(run_date) as d FROM runs").fetchone()
    conn.close()
    return row["d"] if row and row["d"] else str(date.today())


def load_markets(db_path: str) -> list:
    conn = _conn(db_path)
    rows = conn.execute("SELECT DISTINCT language FROM prompts ORDER BY language").fetchall()
    conn.close()
    return [r["language"] for r in rows]


def load_nss(db_path: str, brand: str, language: str = None) -> int:
    """Net Sentiment Score = (positifs - négatifs) / total * 100."""
    conn = _conn(db_path)
    where = "AND p.language = ?" if language and language != "all" else ""
    params = [brand] + ([language] if language and language != "all" else [])
    rows = conn.execute(f"""
        SELECT r.sentiment
        FROM results r
        JOIN runs ru  ON r.run_id = ru.id
        JOIN brands b ON r.brand_id = b.id
        JOIN prompts p ON ru.prompt_id = p.id
        WHERE b.name = ? AND ru.is_demo = 0 {where}
    """, params).fetchall()
    if not rows:
        rows = conn.execute(f"""
            SELECT r.sentiment FROM results r
            JOIN runs ru ON r.run_id = ru.id
            JOIN brands b ON r.brand_id = b.id
            JOIN prompts p ON ru.prompt_id = p.id
            WHERE b.name = ? {where}
        """, params).fetchall()
    conn.close()
    sents = [r["sentiment"] for r in rows]
    if not sents:
        return 0
    pos = sents.count("positive")
    neg = sents.count("negative")
    return round((pos - neg) / len(sents) * 100)


# ─────────────────────────────────────────────
# FACTORY — crée une app Dash par config
# ─────────────────────────────────────────────

def make_dashboard(slug: str) -> dash.Dash:
    """
    Crée et retourne une app Dash complète pour un slug donné.
    Charge automatiquement la config depuis configs/{slug}.json
    et la DB depuis voxa_{slug}.db.
    """
    # Charger la config
    config_path = BASE_DIR / "configs" / f"{slug}.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config introuvable : {config_path}")
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    db_path    = str(BASE_DIR / f"voxa_{slug}.db")
    brand      = cfg["primary_brand"]
    client_name = cfg["client_name"]
    vertical   = cfg.get("vertical", "sport")
    division   = cfg.get("division", "ligue1")

    LANG_FLAGS = {"fr": "🇫🇷", "en": "🇬🇧", "pt": "🇵🇹", "pl": "🇵🇱",
                  "fr-ci": "🇨🇮", "fr_ligue2": "🇫🇷"}
    CAT_LABELS = {
        "discovery": "Notoriété", "comparison": "Comparaison",
        "reputation": "Réputation", "transactional": "Transactionnel",
        "visibility": "Visibilité", "brand": "Image", "odds": "Cotes",
        "regulation": "Régulation", "payment": "Paiement",
    }

    # ── App Dash ──────────────────────────────
    app = dash.Dash(
        __name__,
        server=True,
        requests_pathname_prefix=f"/{slug}/",
        external_stylesheets=[dbc.themes.BOOTSTRAP, FONTS_URL],
        suppress_callback_exceptions=True,
        title=f"Voxa · {client_name}",
    )
    app.index_string = app.index_string.replace("</head>", T.DASH_CSS + "</head>")

    # ── Helpers locaux ────────────────────────
    def card(children, extra=None):
        style = {**card_style(), **(extra or {})}
        return html.Div(children, style=style)

    def ctitle(text):
        return html.Div(text, style={
            "fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
            "letterSpacing": "2px", "color": T3, "marginBottom": 14,
            "fontFamily": T.FONT_BODY,
        })

    # ── Topbar ────────────────────────────────
    topbar = T.make_topbar(
        client_name=client_name,
        vertical=vertical,
        right_children=[
            html.A("↓ CSV", id=f"export-{slug}", href=f"/export/{slug}/csv",
                   style={"padding": "6px 12px", "borderRadius": 8,
                          "border": f"1px solid {BD}", "background": BG3,
                          "fontSize": 12, "fontWeight": 600, "color": T2,
                          "textDecoration": "none"}),
        ]
    )

    # ── Layout ────────────────────────────────
    markets_from_db = load_markets(db_path)
    market_opts = [{"label": f"{LANG_FLAGS.get(m,'🌐')} {m.upper()}", "value": m}
                   for m in markets_from_db]
    market_opts = [{"label": "🌐 Tous", "value": "all"}] + market_opts

    app.layout = html.Div([
        topbar,
        # Filtres
        html.Div([
            dbc.Row([
                dbc.Col([
                    html.Div("MARCHÉ", style={
                        "fontSize": 10, "fontWeight": 700, "letterSpacing": "2px",
                        "color": T3, "marginBottom": 8,
                    }),
                    dbc.RadioItems(
                        id=f"market-{slug}",
                        options=market_opts,
                        value="all",
                        inline=True,
                        className="dash-radioitems",
                        style={"color": T2, "fontSize": 13},
                    ),
                ], width=12),
            ]),
        ], style={"background": BG3, "border": f"1px solid {BD}",
                  "borderRadius": 12, "padding": "18px 24px", "margin": "20px 24px 0"}),

        # Hero KPI
        html.Div(id=f"hero-{slug}", style={"padding": "16px 24px 0"}),

        # Tabs
        dbc.Tabs([
            dbc.Tab(label="CLASSEMENT & ÉVOLUTION", tab_id="ranking",
                    label_style={"fontSize": 11, "fontWeight": 700,
                                 "letterSpacing": "1px", "color": T3},
                    active_label_style={"color": C1}),
            dbc.Tab(label="ANALYSE PAR PROMPT", tab_id="prompts",
                    label_style={"fontSize": 11, "fontWeight": 700,
                                 "letterSpacing": "1px", "color": T3},
                    active_label_style={"color": C1}),
            dbc.Tab(label="BIBLIOTHÈQUE PROMPTS", tab_id="library",
                    label_style={"fontSize": 11, "fontWeight": 700,
                                 "letterSpacing": "1px", "color": T3},
                    active_label_style={"color": C1}),
        ], id=f"tabs-{slug}", active_tab="ranking",
           style={"margin": "20px 24px 0",
                  "borderBottom": f"1px solid {BD}"}),

        html.Div(id=f"content-{slug}", style={"padding": "16px 24px 24px"}),

        # Footer moat
        html.Div([
            html.Span("✓ Prompt library verticale · Données propriétaires · "
                      "Historique indépendant de votre agence",
                      style={"fontSize": 11, "color": T3}),
            html.A("Voxa GEO Intelligence · luc@sharper-media.com",
                   href="mailto:luc@sharper-media.com",
                   style={"fontSize": 11, "color": C1, "textDecoration": "none"}),
        ], className="voxa-footer"),
    ], style={"background": BG, "minHeight": "100vh", "fontFamily": T.FONT_BODY})

    # ── Callbacks ─────────────────────────────

    @app.callback(
        Output(f"hero-{slug}", "children"),
        Input(f"market-{slug}", "value"),
    )
    def update_hero(market):
        lang = None if market == "all" else market
        df   = load_scores(db_path, lang)
        hist = load_history(db_path, brand)
        last = load_last_run_date(db_path)
        nss  = load_nss(db_path, brand, lang)

        primary = df[df["is_primary"] == 1] if not df.empty else pd.DataFrame()
        score_v = round(primary["score"].iloc[0]) if not primary.empty else 0
        n_prompts = "—"
        try:
            conn = _conn(db_path); n_prompts = conn.execute("SELECT COUNT(*) as n FROM prompts").fetchone()["n"]; conn.close()
        except: pass

        sc_col = score_color(score_v)
        sc_lbl = score_label(score_v)
        nss_col = NG if nss >= 0 else RED
        flag   = LANG_FLAGS.get(market, "🌐")
        mkt_label = f"{flag} {market.upper()}" if market != "all" else "🌐 TOUS MARCHÉS"

        return html.Div([
            dbc.Row([
                dbc.Col([
                    # Gauge mini
                    dcc.Graph(
                        figure=go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=score_v,
                            number={"font": {"size": 42, "color": sc_col,
                                             "family": T.FONT_BODY},
                                    "suffix": "/100"},
                            gauge={
                                "axis": {"range": [0, 100], "tickfont": {"size": 0}},
                                "bar": {"color": sc_col, "thickness": 0.25},
                                "bgcolor": BG3,
                                "borderwidth": 0,
                                "steps": [
                                    {"range": [0, 45],  "color": f"rgba(255,75,110,0.1)"},
                                    {"range": [45, 70], "color": f"rgba(0,229,255,0.1)"},
                                    {"range": [70, 100],"color": f"rgba(0,255,170,0.1)"},
                                ],
                            }
                        )).update_layout(
                            height=130, margin=dict(l=10, r=10, t=10, b=10),
                            paper_bgcolor="transparent", plot_bgcolor="transparent",
                            font={"family": T.FONT_BODY},
                        ),
                        config={"displayModeBar": False},
                        style={"height": 130},
                    ),
                ], width=3),
                dbc.Col([
                    html.Div(mkt_label, style={
                        "fontSize": 10, "fontWeight": 700, "letterSpacing": "2px",
                        "color": T3, "marginBottom": 6,
                    }),
                    html.Div(sc_lbl, style={
                        "fontSize": 22, "fontWeight": 800, "color": sc_col,
                        "marginBottom": 4,
                    }),
                    html.Div(f"Mesuré sur {n_prompts} prompts · {last}", style={
                        "fontSize": 12, "color": T3, "marginBottom": 16,
                    }),
                    dbc.Row([
                        dbc.Col([
                            html.Div(f"{nss:+d}%", style={
                                "fontSize": 22, "fontWeight": 800, "color": nss_col,
                            }),
                            html.Div("NET SENTIMENT", style={
                                "fontSize": 10, "color": T3, "fontWeight": 700,
                                "letterSpacing": "1px",
                            }),
                        ], width=4),
                        dbc.Col([
                            html.Div(str(len(hist)), style={
                                "fontSize": 22, "fontWeight": 800, "color": C1,
                            }),
                            html.Div("RUNS", style={
                                "fontSize": 10, "color": T3, "fontWeight": 700,
                                "letterSpacing": "1px",
                            }),
                        ], width=4),
                        dbc.Col([
                            html.Div(str(round(primary["mention_rate"].iloc[0] * 100)) + "%"
                                     if not primary.empty else "—", style={
                                "fontSize": 22, "fontWeight": 800, "color": C1,
                            }),
                            html.Div("MENTIONS", style={
                                "fontSize": 10, "color": T3, "fontWeight": 700,
                                "letterSpacing": "1px",
                            }),
                        ], width=4),
                    ]),
                ], width=9),
            ]),
        ], style={**card_style(), "marginBottom": 0})

    @app.callback(
        Output(f"content-{slug}", "children"),
        Input(f"tabs-{slug}", "active_tab"),
        Input(f"market-{slug}", "value"),
    )
    def update_content(tab, market):
        lang = None if market == "all" else market

        if tab == "ranking":
            return _tab_ranking(lang)
        elif tab == "prompts":
            return _tab_prompts(lang)
        elif tab == "library":
            return _tab_library(lang)
        return html.Div()

    def _tab_ranking(lang):
        df   = load_scores(db_path, lang)
        hist = load_history(db_path, brand)

        # Bar chart concurrents
        if not df.empty:
            colors = [C1 if row["is_primary"] else T3 for _, row in df.iterrows()]
            bar_fig = go.Figure(go.Bar(
                x=df["score"].round().astype(int),
                y=df["name"],
                orientation="h",
                marker_color=colors,
                text=df["score"].round().astype(int).astype(str) + "/100",
                textposition="auto",
                textfont={"size": 12, "color": BG, "family": T.FONT_BODY},
            )).update_layout(
                height=max(200, len(df) * 40),
                margin=dict(l=0, r=10, t=0, b=0),
                paper_bgcolor="transparent", plot_bgcolor="transparent",
                xaxis=dict(showgrid=False, range=[0, 100], tickfont={"size": 0},
                           zeroline=False),
                yaxis=dict(tickfont={"size": 12, "color": T2,
                                     "family": T.FONT_BODY}),
                font={"family": T.FONT_BODY},
                showlegend=False,
            )
            bar_card = card([
                ctitle("CLASSEMENT CONCURRENTS"),
                dcc.Graph(figure=bar_fig, config={"displayModeBar": False}),
            ])
        else:
            bar_card = card([ctitle("CLASSEMENT CONCURRENTS"),
                             html.Div("Pas encore de données live.", style={"color": T3, "fontSize": 12})])

        # Évolution
        if hist and len(hist) > 1:
            line_fig = go.Figure(go.Scatter(
                x=[h["run_date"] for h in hist],
                y=[round(h["score"]) for h in hist],
                mode="lines+markers",
                line=dict(color=C1, width=2),
                marker=dict(color=C1, size=6),
                fill="tozeroy",
                fillcolor=f"rgba(0,229,255,0.06)",
                hovertemplate="%{y}/100<extra></extra>",
            )).update_layout(
                height=200,
                margin=dict(l=0, r=10, t=0, b=0),
                paper_bgcolor="transparent", plot_bgcolor="transparent",
                xaxis=dict(showgrid=False, tickfont={"size": 10, "color": T3,
                                                      "family": T.FONT_BODY}),
                yaxis=dict(range=[0, 100], showgrid=True,
                           gridcolor=f"rgba(255,255,255,0.04)",
                           tickfont={"size": 10, "color": T3}),
                font={"family": T.FONT_BODY},
            )
            line_card = card([
                ctitle(f"ÉVOLUTION GEO SCORE · {brand.upper()}"),
                dcc.Graph(figure=line_fig, config={"displayModeBar": False}),
            ])
        else:
            line_card = card([
                ctitle(f"ÉVOLUTION GEO SCORE · {brand.upper()}"),
                html.Div("Données insuffisantes — premier run en cours.",
                         style={"color": T3, "fontSize": 12}),
            ])

        return dbc.Row([
            dbc.Col(bar_card, width=6),
            dbc.Col(line_card, width=6),
        ], style={"marginTop": 16})

    def _tab_prompts(lang):
        prompts = load_prompts(db_path, brand, lang, limit=30)
        if not prompts:
            return card([html.Div("Pas encore de données.", style={"color": T3, "fontSize": 12})])

        rows = []
        for p in prompts:
            sc = round(p["score"])
            col = score_color(sc)
            rows.append(html.Tr([
                html.Td(html.Span(CAT_LABELS.get(p["category"], p["category"]),
                                  style={**badge_style(col), "fontSize": 10}),
                        style={"padding": "10px 12px"}),
                html.Td(LANG_FLAGS.get(p["language"], ""), style={"padding": "10px 8px", "fontSize": 14}),
                html.Td(p["text"], style={"padding": "10px 12px", "fontSize": 12, "color": T2}),
                html.Td(str(sc), style={"padding": "10px 12px", "fontWeight": 800,
                                        "color": col, "fontSize": 14, "textAlign": "center"}),
            ], style={"borderBottom": f"1px solid {BD}"}))

        return card([
            ctitle("ANALYSE PAR PROMPT — du plus faible au plus fort"),
            dbc.Table([
                html.Thead(html.Tr([
                    *[html.Th(h, style={
                        "fontSize": 10, "fontWeight": 700, "letterSpacing": "1.5px",
                        "textTransform": "uppercase", "color": T3,
                        "padding": "8px 12px", "background": BG,
                    }) for h in ["Catégorie", "", "Prompt", "Score"]],
                ]), style={"borderBottom": f"2px solid {BD}"}),
                html.Tbody(rows),
            ], bordered=False, hover=False,
               style={"fontFamily": T.FONT_BODY}),
        ], {"marginTop": 16})

    def _tab_library(lang):
        prompts = load_prompts(db_path, brand, lang, limit=50)
        if not prompts:
            return card([html.Div("Pas encore de données.", style={"color": T3, "fontSize": 12})])

        cats = {}
        for p in prompts:
            c = CAT_LABELS.get(p["category"], p["category"])
            cats.setdefault(c, []).append(p)

        blocks = []
        for cat, ps in cats.items():
            items = [html.Li(f"{LANG_FLAGS.get(p['language'],'')} {p['text']}",
                             style={"fontSize": 12, "color": T2, "marginBottom": 6,
                                    "listStyle": "none", "paddingLeft": 8,
                                    "borderLeft": f"2px solid {score_color(round(p['score']))}"})
                     for p in ps]
            blocks.append(html.Div([
                html.Div(cat.upper(), style={
                    "fontSize": 10, "fontWeight": 700, "color": T3,
                    "letterSpacing": "2px", "marginBottom": 10,
                }),
                html.Ul(items, style={"padding": 0, "margin": 0}),
            ], style={"marginBottom": 20}))

        return card([ctitle("BIBLIOTHÈQUE PROMPTS"), *blocks], {"marginTop": 16})

    return app


# ─────────────────────────────────────────────
# WSGI FACTORY — expose un server par slug
# ─────────────────────────────────────────────

def get_server(slug: str):
    """Retourne le Flask server de l'app Dash pour un slug donné."""
    return make_dashboard(slug).server


# ─────────────────────────────────────────────
# CLI — test local
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa Dashboard Générique")
    parser.add_argument("--config", required=True, help="Chemin vers configs/{slug}.json")
    parser.add_argument("--port", type=int, default=8051)
    args = parser.parse_args()

    import re
    slug = re.sub(r'[^a-z0-9_-]', '', Path(args.config).stem)
    app  = make_dashboard(slug)
    print(f"\n✓ Dashboard {slug} → http://localhost:{args.port}/{slug}/\n")
    app.run(debug=False, port=args.port)