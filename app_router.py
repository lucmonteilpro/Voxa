"""
Voxa — Router multi-client v1.0
Point d'entrée unique sur PythonAnywhere.

Affiche une page de sélection client, puis redirige vers
le bon dashboard (PSG ou Betclic).

Usage local :
    python3 app_router.py                  # port 8060
    python3 app_router.py --port 8080

PythonAnywhere WSGI :
    from app_router import server as application

Architecture :
    /           → sélection client
    /psg/       → dashboard PSG  (port interne 8050)
    /betclic/   → dashboard Betclic (port interne 8051)
    /health     → healthcheck JSON
"""

import os
import sys
import argparse
import sqlite3
from datetime import date, datetime

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

FONT = "https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&display=swap"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

C = {
    "navy":   "#0B1D3A",
    "gold":   "#B8962E",
    "goldL":  "#F5EDD5",
    "white":  "#FFFFFF",
    "bg":     "#F4F5F9",
    "border": "#E5E7EB",
    "text2":  "#4B5563",
    "text3":  "#9CA3AF",
    "green":  "#16A34A",
}

# Clients disponibles
CLIENTS = {
    "psg": {
        "name": "PSG",
        "label": "Paris Saint-Germain",
        "db": os.path.join(BASE_DIR, "voxa.db"),
        "url": "/psg/",
        "emoji": "⚽",
        "color": "#DA291C",
        "desc": "Suivi GEO Score · FR + EN · 31 clubs trackés",
    },
    "betclic": {
        "name": "Betclic",
        "label": "Betclic",
        "db": os.path.join(BASE_DIR, "voxa_betclic.db"),
        "url": "/betclic/",
        "emoji": "🎰",
        "color": "#E63946",
        "desc": "GEO Score · 4 marchés · FR PT CI PL · 48 prompts",
    },
}

# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def get_client_stats(client_key: str) -> dict:
    """Récupère les stats résumées d'un client depuis sa DB."""
    cfg = CLIENTS.get(client_key, {})
    db_path = cfg.get("db", "")
    stats = {"score": None, "rank": None, "last_run": None, "n_runs": 0}

    if not db_path or not os.path.exists(db_path):
        return stats

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Dernier run
        row = conn.execute(
            "SELECT run_date, COUNT(*) as n FROM runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            stats["last_run"] = row["run_date"]

        # Nombre total de runs
        row2 = conn.execute("SELECT COUNT(*) as n FROM runs").fetchone()
        stats["n_runs"] = row2["n"] if row2 else 0

        # GEO Score moyen sur le dernier run
        latest = conn.execute(
            "SELECT MAX(run_date) as d FROM runs"
        ).fetchone()
        if latest and latest["d"]:
            score_row = conn.execute("""
                SELECT AVG(res.geo_score) as avg_score
                FROM results res
                JOIN runs r ON res.run_id = r.id
                JOIN brands b ON res.brand_id = b.id
                WHERE b.is_primary = 1 AND r.run_date = ?
            """, (latest["d"],)).fetchone()
            if score_row and score_row["avg_score"]:
                stats["score"] = round(score_row["avg_score"])

        conn.close()
    except Exception:
        pass

    return stats


# ─────────────────────────────────────────────
# APP DASH
# ─────────────────────────────────────────────

from server import server  # serveur Flask partagé — auth, /demo, /health, API
app = dash.Dash(
    server=server,
    external_stylesheets=[dbc.themes.BOOTSTRAP, FONT],
    suppress_callback_exceptions=True,
    title="Voxa · GEO Intelligence",
)

# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────

def score_color(s):
    if s is None: return C["text3"]
    if s >= 70:   return C["green"]
    if s >= 45:   return "#D97706"
    return "#DC2626"


def client_card(key: str) -> html.Div:
    cfg = CLIENTS[key]
    stats = get_client_stats(key)
    sc = stats["score"]
    sc_color = score_color(sc)
    score_display = f"{sc}/100" if sc is not None else "—"
    last = stats["last_run"] or "Aucun run"
    n = stats["n_runs"]

    return html.Div([
        # Header coloré
        html.Div([
            html.Span(cfg["emoji"], style={"fontSize": 28, "marginRight": 12}),
            html.Div([
                html.Div(cfg["label"], style={"fontWeight": 800, "fontSize": 18, "color": C["white"]}),
                html.Div(cfg["desc"], style={"fontSize": 11, "color": "rgba(255,255,255,0.7)", "marginTop": 2}),
            ]),
        ], style={
            "display": "flex", "alignItems": "center",
            "background": cfg["color"], "borderRadius": "12px 12px 0 0",
            "padding": "16px 20px",
        }),

        # Body
        html.Div([
            html.Div([
                html.Div([
                    html.Span(score_display, style={
                        "fontSize": 36, "fontWeight": 800,
                        "color": sc_color, "lineHeight": "1",
                    }),
                    html.Div("GEO Score", style={
                        "fontSize": 10, "color": C["text3"], "fontWeight": 700,
                        "textTransform": "uppercase", "letterSpacing": "1px", "marginTop": 4,
                    }),
                ]),
                html.Div(style={"width": 1, "background": C["border"], "margin": "0 20px"}),
                html.Div([
                    html.Span(str(n), style={
                        "fontSize": 28, "fontWeight": 800, "color": C["navy"], "lineHeight": "1",
                    }),
                    html.Div("Runs total", style={
                        "fontSize": 10, "color": C["text3"], "fontWeight": 700,
                        "textTransform": "uppercase", "letterSpacing": "1px", "marginTop": 4,
                    }),
                ]),
                html.Div(style={"width": 1, "background": C["border"], "margin": "0 20px"}),
                html.Div([
                    html.Span(last, style={
                        "fontSize": 13, "fontWeight": 700, "color": C["navy"], "lineHeight": "1.2",
                    }),
                    html.Div("Dernier run", style={
                        "fontSize": 10, "color": C["text3"], "fontWeight": 700,
                        "textTransform": "uppercase", "letterSpacing": "1px", "marginTop": 4,
                    }),
                ]),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": 20}),

            html.A("Ouvrir le dashboard →", href=cfg["url"], style={
                "display": "block", "background": C["navy"],
                "color": C["white"], "borderRadius": 8,
                "padding": "12px 0", "textAlign": "center",
                "fontWeight": 700, "fontSize": 14, "textDecoration": "none",
                "letterSpacing": "0.5px",
            }),
        ], style={"padding": "20px 20px 16px"}),

    ], style={
        "border": f"1px solid {C['border']}", "borderRadius": 12,
        "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
        "background": C["white"], "marginBottom": 20,
    })


# ─────────────────────────────────────────────
# LANDING PAGE
# ─────────────────────────────────────────────

def landing_layout():
    today = date.today().strftime("%-d %B %Y")
    return html.Div([
        # Topbar
        html.Div([
            html.Div([
                html.Div("V", style={
                    "width": 34, "height": 34, "background": C["gold"],
                    "borderRadius": 8, "display": "flex",
                    "alignItems": "center", "justifyContent": "center",
                    "fontSize": 16, "fontWeight": 800, "color": C["navy"], "flexShrink": 0,
                }),
                html.Span("voxa", style={
                    "fontWeight": 800, "fontSize": 20, "letterSpacing": "-0.5px",
                    "color": C["navy"],
                }),
                html.Span("GEO Intelligence", style={
                    "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
                    "textTransform": "uppercase", "padding": "3px 9px",
                    "borderRadius": 20, "background": "#EEF2FF", "color": "#4F46E5",
                }),
            ], style={"display": "flex", "alignItems": "center", "gap": 10}),
            html.Div(today, style={"fontSize": 12, "color": C["text3"]}),
        ], style={
            "display": "flex", "alignItems": "center", "justifyContent": "space-between",
            "height": 56, "padding": "0 32px",
            "background": C["white"], "borderBottom": f"1px solid {C['border']}",
            "position": "sticky", "top": 0, "zIndex": 100,
            "fontFamily": "Syne, sans-serif",
        }),

        # Content
        html.Div([
            html.Div([
                html.Div("SÉLECTION CLIENT", style={
                    "fontSize": 10, "fontWeight": 700, "color": C["gold"],
                    "letterSpacing": "3px", "marginBottom": 8,
                }),
                html.Div("Choisissez un client", style={
                    "fontSize": 28, "fontWeight": 800, "color": C["navy"],
                    "marginBottom": 4, "letterSpacing": "-0.5px",
                }),
                html.Div(
                    f"GEO Intelligence · {len(CLIENTS)} client{'s' if len(CLIENTS) > 1 else ''} actif{'s' if len(CLIENTS) > 1 else ''}",
                    style={"fontSize": 14, "color": C["text3"], "marginBottom": 16},
                ),

                # Moat messaging
                html.Div([
                    html.Div([
                        html.Span(item, style={
                            "fontSize": 11, "color": C["text2"],
                            "display": "flex", "alignItems": "center", "gap": 6,
                        })
                        for item in [
                            "✓ Prompt library verticale sport · bet · politics",
                            "✓ Vos données vous appartiennent — indépendantes de votre agence",
                            "✓ Historique propriétaire — actif non duplicable",
                        ]
                    ], style={
                        "display": "flex", "flexDirection": "column", "gap": 6,
                        "background": C["goldL"], "borderRadius": 10,
                        "padding": "12px 16px", "marginBottom": 28,
                        "borderLeft": f"3px solid {C['gold']}",
                    }),
                ]),

                # Client cards
                *[client_card(k) for k in CLIENTS],

                # Quick actions
                html.Div([
                    html.Div("Actions rapides", style={
                        "fontSize": 12, "fontWeight": 700, "color": C["text3"],
                        "textTransform": "uppercase", "letterSpacing": "1px",
                        "marginBottom": 12,
                    }),
                    html.Div([
                        html.A("📋 Rapport PSG PDF", href="/report/psg", style={
                            "padding": "8px 16px", "borderRadius": 8,
                            "border": f"1px solid {C['border']}", "background": C["white"],
                            "fontSize": 12, "fontWeight": 600, "color": C["navy"],
                            "textDecoration": "none",
                        }),
                        html.A("📋 Rapport Betclic PDF", href="/report/betclic", style={
                            "padding": "8px 16px", "borderRadius": 8,
                            "border": f"1px solid {C['border']}", "background": C["white"],
                            "fontSize": 12, "fontWeight": 600, "color": C["navy"],
                            "textDecoration": "none",
                        }),
                        html.A("🏥 Healthcheck", href="/health", style={
                            "padding": "8px 16px", "borderRadius": 8,
                            "border": f"1px solid {C['border']}", "background": C["white"],
                            "fontSize": 12, "fontWeight": 600, "color": C["text3"],
                            "textDecoration": "none",
                        }),
                    ], style={"display": "flex", "gap": 12, "flexWrap": "wrap"}),
                ], style={
                    "background": C["white"], "border": f"1px solid {C['border']}",
                    "borderRadius": 12, "padding": "16px 20px",
                }),

            ], style={"maxWidth": 680, "margin": "0 auto"}),
        ], style={
            "padding": "40px 24px 80px",
            "background": C["bg"], "minHeight": "calc(100vh - 56px)",
            "fontFamily": "Syne, sans-serif",
        }),
    ])


app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div(id="page-content"),
])


@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def display_page(pathname):
    if pathname in ["/", None, ""]:
        return landing_layout()
    # Pour les autres routes, on redirige via un lien simple
    # (les dashboards PSG et Betclic tournent en WSGI séparés)
    return html.Div([
        html.H2("Route non gérée par le router principal."),
        html.P(f"Chemin : {pathname}"),
        html.A("← Retour", href="/"),
    ])


# ─────────────────────────────────────────────
# FLASK ROUTES ADDITIONNELLES
# ─────────────────────────────────────────────

# Routes Flask gérées par server.py (health, report, demo, login, API)
# app_router.py ne définit plus de routes Flask directement.


# ─────────────────────────────────────────────
# CSS GLOBAL
# ─────────────────────────────────────────────

app.index_string = app.index_string.replace("</head>", """<style>
body { font-family: 'Syne', sans-serif !important; }
a { transition: opacity 0.15s; }
a:hover { opacity: 0.8; }
</style></head>""")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8060)
    args = parser.parse_args()
    print(f"\n  VOXA · Router v1.0 · http://localhost:{args.port}\n")
    app.run(debug=True, port=args.port)