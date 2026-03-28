"""
Voxa — GEO Dashboard v4.0  (Dash + Bootstrap)
Usage :
    python3 dashboard.py
    Ouvre http://localhost:8050

Deploy PythonAnywhere :
    Web tab → WSGI → from dashboard import server as application
"""

import sqlite3
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback

import theme as T
from theme import (P, C1, C2, NG, BG, BG3, BD, W, T2, T3, RED, GRD,
                   FONTS_URL, DASH_CSS, score_color, score_label,
                   card_style, card_title_style, kpi_value_style,
                   badge_style, BRAND_COLORS_PSG)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "voxa.db")
CLIENT_NAME   = "PSG"
PRIMARY_BRAND = "PSG"
ALL_BRANDS    = [
    "PSG", "OM", "Monaco", "OL",
    "Manchester City", "Arsenal", "Liverpool", "Chelsea",
    "Manchester United", "Tottenham", "Newcastle",
    "Real Madrid", "Barcelona", "Atletico Madrid",
    "Bayern Munich", "Borussia Dortmund", "Bayer Leverkusen",
    "Juventus", "Inter Milan", "AC Milan", "Napoli",
    "Benfica", "Porto", "Ajax", "Sevilla",
    "Flamengo", "River Plate", "Al-Hilal",
    "Aston Villa", "West Ham", "Roma",
]

CLUB_COLORS = {
    "PSG":               "#DA291C",
    "OM":                "#009EE0",
    "Monaco":            "#E8171C",
    "OL":                "#1E3888",
    "Real Madrid":       "#FEBE10",
    "Barcelona":         "#A50044",
    "Manchester City":   "#6CABDD",
    "Liverpool":         "#C8102E",
    "Arsenal":           "#EF0107",
    "Chelsea":           "#034694",
    "Manchester United": "#DA291C",
    "Tottenham":         "#132257",
    "Newcastle":         "#241F20",
    "Bayern Munich":     "#DC052D",
    "Borussia Dortmund": "#FDE100",
    "Bayer Leverkusen":  "#E32221",
    "Juventus":          "#000000",
    "Inter Milan":       "#010E80",
    "AC Milan":          "#FB090B",
    "Napoli":            "#087AC8",
    "Atletico Madrid":   "#C1272D",
    "Benfica":           "#C20000",
    "Porto":             "#00437A",
    "Ajax":              "#D2122E",
    "Sevilla":           "#E53427",
    "Flamengo":          "#CC0000",
    "River Plate":       "#CC0000",
    "Al-Hilal":          "#1A6BB5",
    "Aston Villa":       "#670E36",
    "West Ham":          "#7A263A",
    "Roma":              "#8E1F2F",
}

CATEGORY_LABELS = {
    "discovery":     "Découverte",
    "comparison":    "Comparatif",
    "transactional": "Transactionnel",
    "reputation":    "Réputation",
}

FONTS = FONTS_URL  # depuis theme.py

# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def get_conn():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_latest_scores(lang: str) -> pd.DataFrame:
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT b.name AS brand,
               AVG(r.geo_score)   AS geo_score,
               COUNT(*)           AS n_prompts,
               SUM(r.mentioned)   AS n_mentions,
               SUM(CASE WHEN r.sentiment='positive' THEN 1 ELSE 0 END) AS pos_count,
               SUM(CASE WHEN r.sentiment='negative' THEN 1 ELSE 0 END) AS neg_count,
               ru.run_date
        FROM results r
        JOIN brands  b  ON r.brand_id  = b.id
        JOIN runs    ru ON r.run_id    = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE p.language = ?
        GROUP BY b.name, ru.run_date
        ORDER BY ru.run_date DESC, geo_score DESC
    """
    df = pd.read_sql_query(q, conn, params=(lang,))
    conn.close()
    if df.empty:
        return df
    latest = df["run_date"].max()
    df = df[df["run_date"] == latest].drop_duplicates("brand")
    df["net_sentiment"] = ((df["pos_count"] - df["neg_count"]) / df["n_prompts"].clip(lower=1) * 100).round(1)
    return df.sort_values("geo_score", ascending=False).reset_index(drop=True)


def load_history(brand: str, lang: str) -> pd.DataFrame:
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT ru.run_date AS date, AVG(r.geo_score) AS geo_score
        FROM results r
        JOIN brands  b  ON r.brand_id  = b.id
        JOIN runs    ru ON r.run_id    = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE b.name = ? AND p.language = ?
        GROUP BY ru.run_date
        ORDER BY ru.run_date ASC
    """
    df = pd.read_sql_query(q, conn, params=(brand, lang))
    conn.close()
    return df


def load_prompt_detail(lang: str, category: str = "all", sentiment: str = "all") -> pd.DataFrame:
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT p.text AS prompt, p.category,
               r.mentioned, r.mention_count AS mentions,
               r.position, r.sentiment, r.geo_score,
               ru.run_date, ru.is_demo,
               SUBSTR(ru.raw_response, 1, 400) AS raw_response
        FROM results r
        JOIN brands  b  ON r.brand_id  = b.id
        JOIN runs    ru ON r.run_id    = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE b.name = ? AND p.language = ?
    """
    params = [PRIMARY_BRAND, lang]
    if category != "all":
        q += " AND p.category = ?"
        params.append(category)
    if sentiment != "all":
        q += " AND r.sentiment = ?"
        params.append(sentiment)
    q += " ORDER BY ru.run_date DESC, r.geo_score DESC"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if not df.empty:
        df = df[df["run_date"] == df["run_date"].max()]
    return df


def load_prompt_library() -> pd.DataFrame:
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT p.text, p.language, p.category, COUNT(r.id) AS n_runs
        FROM prompts p
        JOIN clients c ON p.client_id = c.id
        LEFT JOIN runs    ru ON ru.prompt_id = p.id
        LEFT JOIN results r  ON r.run_id     = ru.id
        WHERE c.name = ?
        GROUP BY p.id
        ORDER BY p.language, p.category, p.text
    """
    df = pd.read_sql_query(q, conn, params=(CLIENT_NAME,))
    conn.close()
    return df


def load_compare() -> pd.DataFrame:
    fr = load_latest_scores("fr").set_index("brand")["geo_score"] if not load_latest_scores("fr").empty else pd.Series(dtype=float)
    en = load_latest_scores("en").set_index("brand")["geo_score"] if not load_latest_scores("en").empty else pd.Series(dtype=float)
    rows = []
    for brand in ALL_BRANDS:
        sfr = round(fr.get(brand, 0) or 0, 1)
        sen = round(en.get(brand, 0) or 0, 1)
        rows.append({"brand": brand, "score_fr": sfr, "score_en": sen, "delta": round(sfr - sen, 1)})
    return pd.DataFrame(rows)


def has_demo_data() -> bool:
    conn = get_conn()
    if not conn:
        return False
    n = conn.execute("SELECT COUNT(*) FROM runs WHERE is_demo=1").fetchone()[0]
    conn.close()
    return n > 0

# ─────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────

def score_color(s):
    if s >= 70: return "#16a34a"
    if s >= 45: return "#d97706"
    return "#dc2626"

# ─────────────────────────────────────────────
# CHART BUILDERS
# ─────────────────────────────────────────────

def build_history_chart(lang: str) -> go.Figure:
    df = load_history(PRIMARY_BRAND, lang)
    fig = go.Figure()
    if df.empty or len(df) < 2:
        fig.add_annotation(
            text="Lance plusieurs runs pour voir l'évolution",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=13, color=T.T3),
        )
    else:
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["geo_score"].round(1),
            mode="lines+markers",
            line=dict(color="#4f46e5", width=2.5, shape="spline"),
            marker=dict(color="#4f46e5", size=7),
            fill="tozeroy",
            fillcolor="rgba(79,70,229,0.08)",
            hovertemplate="<b>%{x}</b><br>Score : %{y}/100<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor=T.W, plot_bgcolor=T.W,
        margin=dict(l=8, r=8, t=8, b=8),
        height=220,
        font=dict(family=T.FONT_BODY, size=11, color=T.T2),
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%d %b"),
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6", zeroline=False, range=[0, 105]),
        hoverlabel=dict(bgcolor=T.W, font_size=12),
    )
    return fig


def build_bar_chart(scores_df: pd.DataFrame) -> go.Figure:
    if scores_df.empty:
        return go.Figure()

    # Trier par score croissant (Plotly affiche de bas en haut → #1 en haut)
    df = scores_df.sort_values("geo_score", ascending=True).reset_index(drop=True)

    colors  = ["#4f46e5" if r["brand"] == PRIMARY_BRAND
               else CLUB_COLORS.get(r["brand"], T.T3)
               for _, r in df.iterrows()]
    opacities = [1.0 if r["brand"] == PRIMARY_BRAND else 0.5
                 for _, r in df.iterrows()]

    fig = go.Figure(go.Bar(
        x=df["geo_score"],
        y=df["brand"],
        orientation="h",
        marker=dict(
            color=colors,
            opacity=opacities,
            line=dict(width=0),
        ),
        hovertemplate="<b>%{y}</b> : %{x:.0f}/100<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        paper_bgcolor=T.W, plot_bgcolor=T.W,
        margin=dict(l=4, r=60, t=4, b=4),
        height=max(200, len(df) * 28),
        xaxis=dict(range=[0, 105], showgrid=True, gridcolor="#f3f4f6",
                   zeroline=False, tickfont=dict(size=11)),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=12, family=T.FONT_BODY),
                   automargin=True),
        font=dict(family=T.FONT_BODY),
        bargap=0.25,
    )
    return fig

# ─────────────────────────────────────────────
# COMPONENT BUILDERS
# ─────────────────────────────────────────────

def hero_section(scores_df: pd.DataFrame, lang: str) -> html.Div:
    if scores_df.empty:
        return html.Div("Aucune donnée — lance : python3 tracker.py --demo",
                        style={"color": T.T3, "padding": "24px"})

    pr = scores_df[scores_df["brand"] == PRIMARY_BRAND]
    primary_score    = round(pr["geo_score"].values[0]) if not pr.empty else 0
    primary_rank     = int(pr.index[0]) + 1 if not pr.empty else 0
    primary_mentions = int(pr["n_mentions"].values[0]) if not pr.empty else 0
    primary_nss      = pr["net_sentiment"].values[0] if not pr.empty else 0
    n_prompts        = int(pr["n_prompts"].values[0]) if not pr.empty else 0
    sc               = score_color(primary_score)
    label            = ("Bonne visibilité IA" if primary_score >= 70
                        else "Visibilité partielle" if primary_score >= 45
                        else "Faible visibilité")
    flag      = "🇫🇷" if lang == "fr" else "🇬🇧"
    nss_color = "#16a34a" if primary_nss >= 0 else "#dc2626"
    nss_label = f"+{primary_nss:.0f}%" if primary_nss >= 0 else f"{primary_nss:.0f}%"

    ring_fig = go.Figure(go.Pie(
        values=[primary_score, max(100 - primary_score, 0)],
        hole=0.78, sort=False, direction="clockwise", rotation=90,
        marker=dict(colors=[sc, "#f3f4f6"], line=dict(width=0)),
        hoverinfo="skip", textinfo="none",
    ))
    ring_fig.update_layout(
        showlegend=False, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        width=130, height=130,
        annotations=[dict(
            text=f"<b>{primary_score}</b><br>/100",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font=dict(size=24, color=sc, family=T.FONT_BODY),
        )],
    )

    return html.Div([
        # Ring
        html.Div(
            dcc.Graph(figure=ring_fig, config={"displayModeBar": False},
                      style={"width": 130, "height": 130}),
            style={"flexShrink": 0}
        ),

        # Meta
        html.Div([
            html.Div(f"{flag} GEO Score · {PRIMARY_BRAND} · {lang.upper()}",
                     style={"fontSize": 11, "fontWeight": 700, "letterSpacing": "1.5px",
                            "textTransform": "uppercase", "color": T.T3,
                            "marginBottom": 6}),
            html.Div(label, style={"fontSize": 24, "fontWeight": 800,
                                   "letterSpacing": "-0.5px", "color": sc,
                                   "marginBottom": 4}),
            html.Div(f"Mesuré sur {n_prompts} prompts · Claude Haiku · {date.today().strftime('%d %b %Y')}",
                     style={"fontSize": 12, "color": T.T3, "marginBottom": 20}),

            # KPIs
            html.Div([
                html.Div([
                    html.Div(f"#{primary_rank}",
                             style={"fontSize": 24, "fontWeight": 800, "lineHeight": "1",
                                    "color": T.W}),
                    html.Div(f"/{len(scores_df)} concurrents",
                             style={"fontSize": 11, "color": T.T3, "display": "inline",
                                    "fontWeight": 400}),
                    html.Div("Classement", style={"fontSize": 10, "fontWeight": 700,
                                                   "textTransform": "uppercase",
                                                   "letterSpacing": "1px",
                                                   "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb",
                                "margin": "0 28px"}),
                html.Div([
                    html.Div(str(primary_mentions),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": T.W}),
                    html.Div("Mentions", style={"fontSize": 10, "fontWeight": 700,
                                                "textTransform": "uppercase",
                                                "letterSpacing": "1px",
                                                "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb",
                                "margin": "0 28px"}),
                html.Div([
                    html.Div(nss_label,
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": nss_color}),
                    html.Div("Net Sentiment", style={"fontSize": 10, "fontWeight": 700,
                                                     "textTransform": "uppercase",
                                                     "letterSpacing": "1px",
                                                     "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb",
                                "margin": "0 28px"}),
                html.Div([
                    html.Div(str(n_prompts),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": T.W}),
                    html.Div("Prompts", style={"fontSize": 10, "fontWeight": 700,
                                               "textTransform": "uppercase",
                                               "letterSpacing": "1px",
                                               "color": T.T3, "marginTop": 3}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"flex": 1}),
    ], style={
        "display": "flex", "alignItems": "center", "gap": 48,
        "background": T.W, "border": "1px solid #e5e7eb",
        "borderRadius": 12, "padding": "28px 32px",
        "marginBottom": 20, "boxShadow": "0 1px 3px rgba(0,0,0,0.07)",
    })


def prompt_cards(df: pd.DataFrame) -> list:
    if df.empty:
        return [html.Div("Aucun résultat pour ces filtres.",
                         style={"color": T.T3, "padding": "16px 0",
                                "fontSize": 13})]
    cards = []
    for _, row in df.iterrows():
        sc    = score_color(row["geo_score"])
        icon  = "✓" if row["mentioned"] else "✗"
        ic    = "#16a34a" if row["mentioned"] else "#dc2626"
        cat   = CATEGORY_LABELS.get(row["category"], row["category"])
        pos   = {"early": "↑ Début", "mid": "→ Milieu", "late": "↓ Fin"}.get(
                    row.get("position"), "—")
        sent  = row.get("sentiment") or "—"
        sent_c = {"positive": "#16a34a", "neutral": "#d97706",
                  "negative": "#dc2626"}.get(sent, T.T3)
        sent_bg = {"positive": "#dcfce7", "neutral": "#fef3c7",
                   "negative": "#fee2e2"}.get(sent, "#f3f4f6")
        cat_styles = {
            "discovery":     ("Découverte",    "#4f46e5", "#eef2ff"),
            "comparison":    ("Comparatif",    "#0369a1", "#e0f2fe"),
            "transactional": ("Transactionnel","#15803d", "#dcfce7"),
            "reputation":    ("Réputation",    "#92400e", "#fef3c7"),
        }
        cat_label, cat_color, cat_bg = cat_styles.get(
            row["category"], (row["category"], T.T2, "#f3f4f6"))

        raw_block = []
        raw = str(row.get("raw_response", "") or "")
        if raw and raw != "nan" and len(raw) > 10:
            raw_block = [html.Div(
                raw[:350] + "…",
                style={"marginTop": 10, "paddingTop": 10,
                       "borderTop": "1px solid #f3f4f6",
                       "fontSize": 11, "color": T.T2,
                       "lineHeight": "1.8",
                       "fontFamily": "'DM Mono', monospace"}
            )]

        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(icon, style={"color": ic, "fontWeight": 800,
                                           "marginRight": 8, "fontSize": 13}),
                    html.Span(row["prompt"],
                              style={"fontSize": 13, "color": T.W,
                                     "lineHeight": "1.5"}),
                ], style={"marginBottom": 10}),
                html.Div([
                    html.Span(cat_label,
                              style={"fontSize": 10, "fontWeight": 700,
                                     "padding": "3px 10px", "borderRadius": 20,
                                     "background": cat_bg, "color": cat_color,
                                     "textTransform": "uppercase",
                                     "letterSpacing": "0.5px", "marginRight": 6}),
                    html.Span(pos,
                              style={"fontSize": 10, "fontWeight": 600,
                                     "padding": "3px 10px", "borderRadius": 20,
                                     "background": "#f3f4f6", "color": T.T2,
                                     "marginRight": 6}),
                    html.Span(sent,
                              style={"fontSize": 10, "fontWeight": 700,
                                     "padding": "3px 10px", "borderRadius": 20,
                                     "background": sent_bg, "color": sent_c,
                                     "marginRight": 6}),
                    html.Span(f"{int(row['mentions'])}× mention",
                              style={"fontSize": 10, "fontWeight": 600,
                                     "padding": "3px 10px", "borderRadius": 20,
                                     "background": "#eef2ff", "color": "#4f46e5"}),
                ]),
            ] + raw_block, style={"flex": 1}),

            html.Div([
                html.Div(f"{row['geo_score']:.0f}",
                         style={"fontSize": 30, "fontWeight": 800,
                                "color": sc, "letterSpacing": "-1px",
                                "lineHeight": "1"}),
                html.Div("/100", style={"fontSize": 10, "color": T.T3}),
            ], style={"textAlign": "right", "flexShrink": 0, "paddingLeft": 16}),
        ], style={
            "display": "flex", "alignItems": "flex-start", "gap": 16,
            "border": "1px solid #e5e7eb", "borderRadius": 12,
            "padding": "16px 20px", "marginBottom": 10, "background": T.W,
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        }))
    return cards


def compare_table(df: pd.DataFrame) -> dbc.Table:
    if df.empty:
        return html.Div("Pas de données", style={"color": T.T3})
    rows = []
    for _, r in df.iterrows():
        is_p  = r["brand"] == PRIMARY_BRAND
        dc    = "#16a34a" if r["delta"] > 0 else "#dc2626" if r["delta"] < 0 else T.T3
        dl    = f"+{r['delta']:.0f}" if r["delta"] > 0 else f"{r['delta']:.0f}"
        rows.append(html.Tr([
            html.Td(f"{r['brand']} {'★' if is_p else ''}",
                    style={"fontWeight": 700 if is_p else 400}),
            html.Td(f"{r['score_fr']:.0f}",
                    style={"fontWeight": 700,
                           "color": score_color(r["score_fr"])}),
            html.Td(f"{r['score_en']:.0f}",
                    style={"fontWeight": 700,
                           "color": score_color(r["score_en"])}),
            html.Td(dl, style={"fontWeight": 700, "color": dc}),
        ], style={"fontWeight": 700 if is_p else 400}))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Marque"), html.Th("🇫🇷 FR"),
            html.Th("🇬🇧 EN"),  html.Th("Δ"),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, size="sm",
       style={"fontSize": 13, "fontFamily": T.FONT_BODY})

# ─────────────────────────────────────────────
# DASH APP
# ─────────────────────────────────────────────

app = dash.Dash(
    __name__,
    requests_pathname_prefix="/psg/",
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        FONTS,
    ],
    suppress_callback_exceptions=True,
    title="Voxa · PSG · GEO Intelligence",
)
server = app.server

# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────

TOPBAR = html.Div([
    # Left
    html.Div([
        html.Div("V", style={
            "width": 32, "height": 32, "borderRadius": 8,
            "background": "linear-gradient(135deg,#4f46e5,#7c3aed)",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "fontSize": 15, "fontWeight": 800, "color": T.W, "flexShrink": 0,
        }),
        html.Span("voxa", style={"fontWeight": 800, "fontSize": 18,
                                  "letterSpacing": "-0.5px"}),
        html.Span("GEO Intelligence", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "#eef2ff", "color": "#4f46e5",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": 10}),

    # Right
    html.Div([
        html.Div(id="demo-badge"),
        html.Div([
            html.Button("🇫🇷 FR", id="btn-fr", n_clicks=0,
                        style={"padding": "5px 12px", "borderRadius": "8px 0 0 8px",
                               "border": "1px solid #e5e7eb", "background": T.W,
                               "fontFamily": T.FONT_BODY, "fontSize": 12,
                               "fontWeight": 600, "cursor": "pointer"}),
            html.Button("🇬🇧 EN", id="btn-en", n_clicks=0,
                        style={"padding": "5px 12px", "borderRadius": "0 8px 8px 0",
                               "border": "1px solid #e5e7eb", "borderLeft": "none",
                               "background": T.W,
                               "fontFamily": T.FONT_BODY, "fontSize": 12,
                               "fontWeight": 600, "cursor": "pointer"}),
        ], style={"display": "flex"}),
        html.A("↓ Export CSV", id="export-link", href="/export/psg/csv?lang=fr",
               style={"padding": "6px 14px", "borderRadius": 8,
                      "border": "1px solid #e5e7eb", "background": T.W,
                      "fontSize": 12, "fontWeight": 600, "color": T.T2,
                      "textDecoration": "none"}),
        html.Div([
            "Client : ",
            html.Strong(CLIENT_NAME),
        ], style={"background": T.BG, "border": "1px solid #e5e7eb",
                  "borderRadius": 8, "padding": "5px 12px",
                  "fontSize": 12, "color": T.T2}),
    ], style={"display": "flex", "alignItems": "center", "gap": 12}),
], style={
    "display": "flex", "alignItems": "center", "justifyContent": "space-between",
    "height": 56, "padding": "0 32px",
    "background": T.W, "borderBottom": "1px solid #e5e7eb",
    "position": "sticky", "top": 0, "zIndex": 100,
    "fontFamily": T.FONT_BODY,
})


app.layout = html.Div([
    dcc.Store(id="store-lang", data="fr"),
    TOPBAR,
    html.Div(id="demo-banner"),
    html.Div([
        html.Div(id="hero"),
        dbc.Tabs([
            dbc.Tab(label="Classement & Évolution", tab_id="classement",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Analyse par prompt", tab_id="prompts",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Recommandations", tab_id="recommendations",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY,
                                 "color": "#B8962E"}),
            dbc.Tab(label="Bibliothèque prompts", tab_id="library",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="À propos", tab_id="about",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
        ], id="tabs", active_tab="classement",
           style={"marginBottom": 20, "fontFamily": T.FONT_BODY}),
        html.Div(id="tab-content"),
    ], style={"maxWidth": 1280, "margin": "0 auto",
              "padding": "28px 32px 60px",
              "fontFamily": T.FONT_BODY}),
], style={"background": "#f4f5f9", "minHeight": "100vh"})

# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@app.callback(Output("store-lang", "data"),
          Input("btn-fr", "n_clicks"),
          Input("btn-en", "n_clicks"),
          prevent_initial_call=True)
def switch_lang(n_fr, n_en):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "fr"
    return "en" if "btn-en" in ctx.triggered[0]["prop_id"] else "fr"


@app.callback(Output("export-link", "href"),
          Input("store-lang", "data"))
def update_export(lang):
    return f"/export/psg/csv?lang={lang}"


@app.callback(Output("demo-banner", "children"),
          Input("store-lang", "data"))
def update_banner(_):
    if has_demo_data():
        return html.Div([
            html.Span("◈ ", style={"color": "#d97706"}),
            "Données simulées (mode démo) — non représentatives d'un run API réel",
        ], style={
            "background": "#fffbeb", "borderTop": "1px solid #fde68a",
            "padding": "7px 32px", "fontSize": 11, "color": "#92400e",
        })
    return None


@app.callback(Output("demo-badge", "children"),
          Input("store-lang", "data"))
def update_demo_badge(_):
    if has_demo_data():
        return html.Span("Démo", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "#fef3c7", "color": "#d97706",
        })
    return None


@app.callback(Output("hero", "children"),
          Input("store-lang", "data"))
def update_hero(lang):
    return hero_section(load_latest_scores(lang), lang)


@app.callback(Output("tab-content", "children"),
          Input("tabs", "active_tab"),
          Input("store-lang", "data"))
def render_tab(active_tab, lang):
    scores_df = load_latest_scores(lang)
    compare_df = load_compare()

    if active_tab == "classement":
        return html.Div([
            dbc.Row([
                # Classement
                dbc.Col(html.Div([
                    html.Div("Classement concurrents", className="card-title-voxa"),
                    dcc.Graph(figure=build_bar_chart(scores_df),
                              config={"displayModeBar": False}),
                ], style={"background": T.W, "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=5),

                # Évolution
                dbc.Col(html.Div([
                    html.Div(f"Évolution GEO Score · {PRIMARY_BRAND}", className="card-title-voxa"),
                    dcc.Graph(figure=build_history_chart(lang),
                              config={"displayModeBar": False}),
                ], style={"background": T.W, "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=7),
            ], className="mb-4"),

            dbc.Row([
                # FR vs EN
                dbc.Col(html.Div([
                    html.Div("Visibilité FR vs EN", className="card-title-voxa"),
                    compare_table(compare_df),
                ], style={"background": T.W, "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=6),

                # NSS
                dbc.Col(html.Div([
                    html.Div("Net Sentiment Score", className="card-title-voxa"),
                    html.Div([
                        html.Div([
                            html.Div(row["brand"],
                                     style={"fontSize": 11, "fontWeight": 700,
                                            "textTransform": "uppercase",
                                            "letterSpacing": "1px",
                                            "color": T.T3, "marginBottom": 6}),
                            html.Div(
                                (f"+{row['net_sentiment']:.0f}%" if row["net_sentiment"] >= 0
                                 else f"{row['net_sentiment']:.0f}%"),
                                style={"fontSize": 26, "fontWeight": 800,
                                       "color": "#16a34a" if row["net_sentiment"] >= 0 else "#dc2626"}),
                        ], style={
                            "border": "1px solid #e5e7eb", "borderRadius": 10,
                            "padding": "14px 16px", "textAlign": "center",
                            "flex": 1,
                        })
                        for _, row in scores_df.iterrows()
                    ], style={"display": "flex", "gap": 10, "flexWrap": "wrap"}),
                    html.Div("NSS = (prompts positifs − négatifs) / total × 100",
                             style={"fontSize": 11, "color": T.T3, "marginTop": 10}),
                ], style={"background": T.W, "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=6),
            ]),
        ])

    elif active_tab == "prompts":
        return html.Div([
            html.Div([
                dcc.Dropdown(
                    id="filter-cat",
                    options=[{"label": "Toutes catégories", "value": "all"}] +
                            [{"label": v, "value": k} for k, v in CATEGORY_LABELS.items()],
                    value="all", clearable=False,
                    style={"width": 200, "fontFamily": T.FONT_BODY,
                           "fontSize": 13},
                ),
                dcc.Dropdown(
                    id="filter-sent",
                    options=[
                        {"label": "Tous sentiments", "value": "all"},
                        {"label": "Positif",         "value": "positive"},
                        {"label": "Neutre",          "value": "neutral"},
                        {"label": "Négatif",         "value": "negative"},
                    ],
                    value="all", clearable=False,
                    style={"width": 180, "fontFamily": T.FONT_BODY,
                           "fontSize": 13},
                ),
                html.Div(id="prompt-count",
                         style={"fontSize": 12, "color": T.T3,
                                "alignSelf": "center"}),
            ], style={"display": "flex", "gap": 12, "marginBottom": 16,
                      "alignItems": "center"}),
            html.Div(id="prompt-list"),
        ])

    elif active_tab == "library":
        df_lib = load_prompt_library()
        n_fr = len(df_lib[df_lib["language"] == "fr"]) if not df_lib.empty else 0
        n_en = len(df_lib[df_lib["language"] == "en"]) if not df_lib.empty else 0
        rows = []
        if not df_lib.empty:
            for _, row in df_lib.iterrows():
                flag = "🇫🇷" if row["language"] == "fr" else "🇬🇧"
                cat_styles = {
                    "discovery":     ("#4f46e5", "#eef2ff"),
                    "comparison":    ("#0369a1", "#e0f2fe"),
                    "transactional": ("#15803d", "#dcfce7"),
                    "reputation":    ("#92400e", "#fef3c7"),
                }
                cc, cbg = cat_styles.get(row["category"], (T.T2, "#f3f4f6"))
                cat_label = CATEGORY_LABELS.get(row["category"], row["category"])
                rows.append(html.Tr([
                    html.Td(flag, style={"fontSize": 18}),
                    html.Td(html.Span(cat_label, style={
                        "fontSize": 10, "fontWeight": 700,
                        "padding": "3px 9px", "borderRadius": 20,
                        "background": cbg, "color": cc,
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    })),
                    html.Td(row["text"], style={"fontSize": 13}),
                    html.Td(html.Span(str(row["n_runs"]) if row["n_runs"] else "—",
                                     style={"fontSize": 11, "fontWeight": 700,
                                            "color": "#4f46e5",
                                            "background": "#eef2ff",
                                            "padding": "2px 8px",
                                            "borderRadius": 20}) if row["n_runs"]
                            else html.Span("—", style={"color": T.T3})),
                ]))

        return html.Div([
            html.Div([
                "Prompt Library · ", html.Strong(CLIENT_NAME),
                f" · {len(df_lib)} prompts · 🇫🇷 {n_fr} · 🇬🇧 {n_en}",
            ], style={"fontSize": 11, "fontWeight": 700,
                      "textTransform": "uppercase", "letterSpacing": "1.5px",
                      "color": T.T3, "marginBottom": 16}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th(""), html.Th("Catégorie"),
                    html.Th("Prompt"), html.Th("Runs"),
                ], style={"fontSize": 10, "fontWeight": 700,
                          "textTransform": "uppercase",
                          "letterSpacing": "1px", "color": T.T3})),
                html.Tbody(rows),
            ], bordered=False, hover=True,
               style={"fontFamily": T.FONT_BODY}),
        ], style={"background": T.W, "border": "1px solid #e5e7eb",
                  "borderRadius": 12, "padding": 24,
                  "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"})

    elif active_tab == "recommendations":
        # ── Recommandations depuis voxa_db ──────────────────
        try:
            import voxa_db as vdb
            recos = vdb.get_recommendations("psg")
            alerts = vdb.get_alerts("psg", unread_only=True)
        except Exception:
            recos = []; alerts = []

        # ── Recommandations dynamiques basées sur les données live ──
        live_recos = []
        scores_df_r = load_latest_scores(lang)
        if not scores_df_r.empty:
            pr = scores_df_r[scores_df_r["brand"] == PRIMARY_BRAND]
            if not pr.empty:
                score_val = round(pr["geo_score"].values[0])
                rank = int(pr.index[0]) + 1
                n_total = len(scores_df_r)
                leader = scores_df_r.iloc[0]

                if rank > 1:
                    delta = round(leader["geo_score"] - pr["geo_score"].values[0])
                    live_recos.append({
                        "priority": "haute", "icon": "◎",
                        "title": f"{PRIMARY_BRAND} #{rank}/{n_total} — {delta} pts derrière {leader['brand']}",
                        "body": f"{leader['brand']} domine les réponses IA. Analyser les contenus web que les LLMs utilisent pour le citer et produire du contenu équivalent.",
                    })
                else:
                    live_recos.append({
                        "priority": "info", "icon": "✓",
                        "title": f"{PRIMARY_BRAND} #1 — position dominante ({score_val}/100)",
                        "body": "Position de leader confirmée. Maintenir l'avance en produisant du contenu régulier et en renforçant le balisage Schema sur le site officiel.",
                    })

                if score_val < 50:
                    live_recos.append({
                        "priority": "haute", "icon": "⚠",
                        "title": f"GEO Score faible : {score_val}/100",
                        "body": "Les LLMs citent peu votre club. Actions prioritaires : page FAQ structurée, Schema SportsEvent sur le site officiel, communiqués de presse réguliers avec Schema Article.",
                    })
                elif score_val < 70:
                    live_recos.append({
                        "priority": "moyenne", "icon": "◐",
                        "title": f"GEO Score à améliorer : {score_val}/100",
                        "body": "Score intermédiaire. Enrichir les pages Résultats et Histoire du club avec du contenu structuré. Ajouter Schema Organization + SportsEvent sur toutes les pages matchs.",
                    })

        priority_styles = {
            "haute":   {"border": "#dc2626", "bg": "#fef2f2", "badge_bg": "#fee2e2", "badge_color": "#dc2626"},
            "moyenne": {"border": "#d97706", "bg": "#fffbeb", "badge_bg": "#fef3c7", "badge_color": "#92400e"},
            "info":    {"border": "#16a34a", "bg": "#f0fdf4", "badge_bg": "#dcfce7", "badge_color": "#15803d"},
        }

        def reco_card(reco, is_persistent=False):
            ps = priority_styles.get(reco.get("priority","info"), priority_styles["info"])
            impact = reco.get("impact_score") or reco.get("impact", 0)
            impact_badge = html.Span(f"+{impact:.0f} pts estimés",
                style={"fontSize": 10, "color": T.T3, "marginLeft": 8}) if impact else None
            return html.Div([
                html.Div([
                    html.Span(reco.get("icon","💡"), style={"fontSize": 16, "marginRight": 8}),
                    html.Span(reco.get("priority","info").upper(), style={
                        "fontSize": 9, "fontWeight": 800, "letterSpacing": "1.5px",
                        "padding": "2px 8px", "borderRadius": 20,
                        "background": ps["badge_bg"], "color": ps["badge_color"],
                        "marginRight": 8}),
                    html.Span(reco.get("title",""), style={
                        "fontSize": 13, "fontWeight": 700, "color": T.W}),
                    *([impact_badge] if impact_badge else []),
                ], style={"marginBottom": 6}),
                html.Div(reco.get("body",""), style={
                    "fontSize": 12, "color": "#4b5563", "lineHeight": "1.7",
                    "paddingLeft": 24}),
                *([html.Div(f"Prompt : « {reco['prompt_text'][:80]}… »", style={
                    "fontSize": 10, "color": T.T3, "marginTop": 4, "paddingLeft": 24,
                    "fontStyle": "italic"}) if reco.get("prompt_text") else html.Div()]),
            ], style={
                "borderLeft": f"3px solid {ps['border']}",
                "background": ps["bg"],
                "borderRadius": "0 10px 10px 0",
                "padding": "14px 18px", "marginBottom": 10,
            })

        # Alertes actives
        alert_section = html.Div()
        if alerts:
            alert_items = [html.Div([
                html.Span({"critical":"🔴","warning":"🟡","info":"🟢"}.get(a.get("severity","info"),"🟢"),
                          style={"marginRight": 6}),
                html.Strong(a["title"]), f" — {a['body']}",
                html.Span(f"  {a['created_at'][:10]}", style={"fontSize":10,"color":T.T3,"marginLeft":8}),
            ], style={"fontSize":12,"padding":"8px 12px","marginBottom":6,
                      "background":"#fffbeb","borderRadius":8,"borderLeft":"3px solid #d97706"})
            for a in alerts]
            alert_section = html.Div([
                html.Div("ALERTES ACTIVES", style={"fontSize":10,"fontWeight":700,
                    "letterSpacing":"1.5px","color":T.T3,"marginBottom":10}),
                *alert_items,
            ], style={"marginBottom":20})

        all_recos = live_recos + [
            {"priority": r.get("priority","medium"), "icon": "💡",
             "title": r.get("title",""), "body": r.get("body",""),
             "prompt_text": r.get("prompt_text"), "impact_score": r.get("impact_score")}
            for r in recos
        ]
        if not all_recos:
            all_recos = [{"priority":"info","icon":"✓",
                          "title":"Bonne performance globale",
                          "body":"Aucune alerte critique détectée. Continuez le monitoring hebdomadaire pour détecter les variations."}]

        return html.Div([
            alert_section,
            html.Div("RECOMMANDATIONS", style={"fontSize":10,"fontWeight":700,
                "letterSpacing":"1.5px","color":T.T3,"marginBottom":10}),
            *[reco_card(r) for r in all_recos],
            html.Div("Les recommandations sont générées automatiquement après chaque run. Relancez un tracker pour actualiser.",
                style={"fontSize":11,"color":T.T3,"marginTop":16,"fontStyle":"italic"}),
        ], style={"background":T.W,"border":"1px solid #e5e7eb",
                  "borderRadius":12,"padding":24,"boxShadow":"0 1px 3px rgba(0,0,0,0.06)"})

    elif active_tab == "about":
        about_items = [
            ("◈", "Tracker LLM",
             "Voxa envoie des centaines de prompts aux LLMs et mesure si votre marque est citée. Multi-LLM en V2 : ChatGPT, Gemini, Perplexity."),
            ("◎", "GEO Score",
             "Score 0–100 : présence (40pts) + position dans la réponse (30pts) + sentiment (20pts) + fréquence (10pts)."),
            ("◐", "Multi-langue",
             "Score FR ≠ Score EN. Les LLMs citent différemment selon la langue. Voxa mesure votre visibilité sur chaque marché."),
            ("◑", "Net Sentiment Score",
             "Ratio (prompts positifs − négatifs) / total. KPI stratégique pour les CMOs et directeurs marketing."),
        ]
        tech_rows = [
            ("LLM actif",  "Claude Haiku (Anthropic)"),
            ("LLMs V2",    "GPT-4o-mini · Gemini Flash · Perplexity  ← hashés"),
            ("Base",       "SQLite → PostgreSQL (V2)"),
            ("Scheduler",  "PythonAnywhere cron daily"),
            ("Dashboard",  "Dash / Python → React (V2)"),
        ]
        return html.Div([
            dbc.Row([
                dbc.Col(html.Div([
                    html.Div(icon, style={"fontSize": 20, "marginBottom": 10}),
                    html.Div(title, style={"fontWeight": 700, "fontSize": 14,
                                           "marginBottom": 6}),
                    html.Div(body, style={"fontSize": 12, "color": T.T2,
                                          "lineHeight": "1.7"}),
                ], style={"border": "1px solid #e5e7eb", "borderRadius": 12,
                           "padding": 20, "background": T.W,
                           "height": "100%"}), width=6)
                for icon, title, body in about_items
            ], className="mb-4 g-3"),
            html.Div([
                html.Div("Stack technique · MVP", style={
                    "fontSize": 11, "fontWeight": 700,
                    "textTransform": "uppercase", "letterSpacing": "1px",
                    "color": "#4f46e5", "marginBottom": 12,
                }),
                *[html.Div([
                    html.Span(k, style={"width": 100, "color": T.T3,
                                        "fontFamily": "'DM Mono', monospace",
                                        "fontSize": 12, "display": "inline-block"}),
                    html.Span(v, style={"color": T.W,
                                        "fontFamily": "'DM Mono', monospace",
                                        "fontSize": 12,
                                        "fontStyle": "italic" if "hashés" in v else "normal"}),
                ], style={"marginBottom": 8}) for k, v in tech_rows],
            ], style={"background": T.BG, "border": "1px solid #e5e7eb",
                      "borderRadius": 12, "padding": 20}),
        ])

    return html.Div()


@app.callback(
    Output("prompt-list", "children"),
    Output("prompt-count", "children"),
    Input("filter-cat", "value"),
    Input("filter-sent", "value"),
    Input("store-lang", "data"),
)
def update_prompts(cat, sent, lang):
    df = load_prompt_detail(lang, cat or "all", sent or "all")
    n = len(df)
    label = f"{n} prompt{'s' if n > 1 else ''}"
    return prompt_cards(df), label

# ─────────────────────────────────────────────
# CSV EXPORT (Flask route via Dash server)
# ─────────────────────────────────────────────

from flask import request as flask_request, Response
import csv, io

@server.route("/export/psg/csv")
def export_csv_psg():
    lang = flask_request.args.get("lang", "fr")
    df   = load_prompt_detail(lang)
    out  = io.StringIO()
    cols = ["prompt", "category", "mentioned", "mentions",
            "position", "sentiment", "geo_score", "run_date"]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for _, row in df.iterrows():
        w.writerow({c: row.get(c, "") for c in cols})
    return Response(
        out.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment;filename=voxa_{PRIMARY_BRAND}_{lang}_{date.today()}.csv"}
    )

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────

app.index_string = app.index_string.replace("</head>", T.DASH_CSS + "</head>")

# Footer moat — ajouté dans le layout
app.layout.children.append(
    html.Div([
        html.Span("✓ Prompt library verticale sport · données propriétaires · historique indépendant de votre agence"),
        html.Span([
            "Voxa GEO Intelligence · ",
            html.A("luc@sharper-media.com",
                   href="mailto:luc@sharper-media.com",
                   style={"color": "#B8962E", "textDecoration": "none"}),
        ]),
    ], className="voxa-footer")
)

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8050)