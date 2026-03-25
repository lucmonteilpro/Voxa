"""
Voxa — GEO Dashboard Betclic v1.0  (Dash + Bootstrap)
Usage :
    python3 dashboard_betclic.py
    Ouvre http://localhost:8051

Deploy PythonAnywhere :
    Web tab → WSGI → from dashboard_betclic import server as application
"""

import sqlite3
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "voxa_betclic.db")
CLIENT_NAME   = "Betclic"
PRIMARY_BRAND = "Betclic"

MARKETS = {
    "fr":    "🇫🇷 France",
    "pt":    "🇵🇹 Portugal",
    "fr-ci": "🇨🇮 Côte d'Ivoire",
    "pl":    "🇵🇱 Pologne",
}

COMPETITORS_BY_MARKET = {
    "fr":    ["Winamax", "FDJ", "PMU", "Unibet", "Bet365", "Parions Sport"],
    "pt":    ["Bet365", "Betway", "Solverde", "Casino Portugal", "Placard", "Bwin"],
    "fr-ci": ["1xBet", "Sportybet", "Betway", "PMU CI", "Ligabet"],
    "pl":    ["Fortuna", "STS", "Totolotek", "Betway", "Bet365", "LV BET"],
}

CATEGORY_LABELS = {
    "visibility": "Visibilité",
    "brand":      "Image de marque",
    "odds":       "Cotes",
    "regulation": "Régulation",
    "payment":    "Paiement",
}

BRAND_COLORS = {
    "Betclic":         "#E63946",
    "Winamax":         "#FF6B35",
    "FDJ":             "#0066CC",
    "PMU":             "#006633",
    "Unibet":          "#1A1A2E",
    "Bet365":          "#027B5B",
    "Parions Sport":   "#003189",
    "Betway":          "#00A651",
    "Solverde":        "#2E7D32",
    "Casino Portugal": "#C62828",
    "Placard":         "#1565C0",
    "Bwin":            "#E53935",
    "1xBet":           "#F44336",
    "Sportybet":       "#00897B",
    "PMU CI":          "#388E3C",
    "Ligabet":         "#7B1FA2",
    "Fortuna":         "#D32F2F",
    "STS":             "#1976D2",
    "Totolotek":       "#F57C00",
    "LV BET":          "#00796B",
}

FONTS = "https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&display=swap"

# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def get_conn():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_scores(market: str, category: str = "all") -> pd.DataFrame:
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
        JOIN brands  b  ON r.brand_id   = b.id
        JOIN runs    ru ON r.run_id     = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE p.language = ?
    """
    params = [market]
    if category != "all":
        q += " AND p.category = ?"
        params.append(category)
    q += " GROUP BY b.name, ru.run_date ORDER BY ru.run_date DESC, geo_score DESC"

    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    if df.empty:
        return df
    latest = df["run_date"].max()
    df = df[df["run_date"] == latest].drop_duplicates("brand")
    df["net_sentiment"] = (
        (df["pos_count"] - df["neg_count"]) / df["n_prompts"].clip(lower=1) * 100
    ).round(1)
    competitors = COMPETITORS_BY_MARKET.get(market, [])
    valid = [PRIMARY_BRAND] + competitors
    df = df[df["brand"].isin(valid)]
    return df.sort_values("geo_score", ascending=False).reset_index(drop=True)


def load_history(market: str, category: str = "all") -> pd.DataFrame:
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT ru.run_date AS date, AVG(r.geo_score) AS geo_score
        FROM results r
        JOIN brands  b  ON r.brand_id   = b.id
        JOIN runs    ru ON r.run_id     = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE b.name = ? AND p.language = ?
    """
    params = [PRIMARY_BRAND, market]
    if category != "all":
        q += " AND p.category = ?"
        params.append(category)
    q += " GROUP BY ru.run_date ORDER BY ru.run_date ASC"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    return df


def load_prompt_detail(market: str, category: str = "all", sentiment: str = "all") -> pd.DataFrame:
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
        JOIN brands  b  ON r.brand_id   = b.id
        JOIN runs    ru ON r.run_id     = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE b.name = ? AND p.language = ?
    """
    params = [PRIMARY_BRAND, market]
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


def load_market_overview() -> pd.DataFrame:
    """Score Betclic sur chaque marché pour la vue synthèse."""
    rows = []
    for market, label in MARKETS.items():
        df = load_scores(market)
        if df.empty:
            rows.append({"market": label, "market_key": market, "geo_score": 0, "rank": 0})
            continue
        pr = df[df["brand"] == PRIMARY_BRAND]
        score = round(pr["geo_score"].values[0]) if not pr.empty else 0
        rank  = int(pr.index[0]) + 1 if not pr.empty else 0
        rows.append({"market": label, "market_key": market,
                     "geo_score": score, "rank": rank, "n_brands": len(df)})
    return pd.DataFrame(rows)


def has_demo_data() -> bool:
    conn = get_conn()
    if not conn:
        return False
    n = conn.execute("SELECT COUNT(*) FROM runs WHERE is_demo=1").fetchone()[0]
    conn.close()
    return n > 0

# ─────────────────────────────────────────────
# COLORS & HELPERS
# ─────────────────────────────────────────────

def score_color(s):
    if s >= 70: return "#16a34a"
    if s >= 45: return "#d97706"
    return "#dc2626"


# ─────────────────────────────────────────────
# CHART BUILDERS
# ─────────────────────────────────────────────

def build_bar_chart(scores_df: pd.DataFrame) -> go.Figure:
    if scores_df.empty:
        return go.Figure()
    df = scores_df.sort_values("geo_score", ascending=True).reset_index(drop=True)
    colors   = ["#4f46e5" if r["brand"] == PRIMARY_BRAND
                else BRAND_COLORS.get(r["brand"], "#9ca3af")
                for _, r in df.iterrows()]
    opacities = [1.0 if r["brand"] == PRIMARY_BRAND else 0.5
                 for _, r in df.iterrows()]
    fig = go.Figure(go.Bar(
        x=df["geo_score"], y=df["brand"], orientation="h",
        marker=dict(color=colors, opacity=opacities, line=dict(width=0)),
        hovertemplate="<b>%{y}</b> : %{x:.0f}/100<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=4, r=40, t=4, b=4),
        height=max(180, len(df) * 36),
        xaxis=dict(range=[0, 105], showgrid=True, gridcolor="#f3f4f6",
                   zeroline=False, tickfont=dict(size=11)),
        yaxis=dict(showgrid=False, zeroline=False, automargin=True,
                   tickfont=dict(size=12, family="Syne, sans-serif")),
        font=dict(family="Syne, sans-serif"),
        bargap=0.3,
    )
    return fig


def build_history_chart(market: str, category: str = "all") -> go.Figure:
    df = load_history(market, category)
    fig = go.Figure()
    if df.empty or len(df) < 2:
        fig.add_annotation(
            text="Lance plusieurs runs pour voir l'évolution",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=13, color="#9ca3af"),
        )
    else:
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["geo_score"].round(1),
            mode="lines+markers",
            line=dict(color="#4f46e5", width=2.5, shape="spline"),
            marker=dict(color="#4f46e5", size=7),
            fill="tozeroy", fillcolor="rgba(79,70,229,0.08)",
            hovertemplate="<b>%{x}</b><br>Score : %{y}/100<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=8, r=8, t=8, b=8), height=200,
        font=dict(family="Syne, sans-serif", size=11, color="#6b7280"),
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%d %b"),
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6",
                   zeroline=False, range=[0, 105]),
    )
    return fig


def build_radar_chart() -> go.Figure:
    """Radar Betclic sur les 3 catégories × 4 marchés."""
    categories = list(CATEGORY_LABELS.values())
    cat_keys   = list(CATEGORY_LABELS.keys())
    fig = go.Figure()
    colors_map = {
        "fr":    "#4f46e5",
        "pt":    "#16a34a",
        "fr-ci": "#d97706",
        "pl":    "#dc2626",
    }
    for market, label in MARKETS.items():
        scores = []
        for cat in cat_keys:
            df = load_scores(market, cat)
            if df.empty:
                scores.append(0)
                continue
            pr = df[df["brand"] == PRIMARY_BRAND]
            scores.append(round(pr["geo_score"].values[0]) if not pr.empty else 0)
        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=label,
            line=dict(color=colors_map[market], width=2),
            fillcolor=colors_map[market],
            opacity=0.15,
        ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100],
                            tickfont=dict(size=10)),
            angularaxis=dict(tickfont=dict(size=12, family="Syne, sans-serif")),
            bgcolor="white",
        ),
        showlegend=True,
        legend=dict(font=dict(family="Syne, sans-serif", size=11)),
        paper_bgcolor="white",
        margin=dict(l=40, r=40, t=20, b=20),
        height=300,
        font=dict(family="Syne, sans-serif"),
    )
    return fig

# ─────────────────────────────────────────────
# COMPONENT BUILDERS
# ─────────────────────────────────────────────

def card(children, style_extra=None):
    style = {
        "background": "white", "border": "1px solid #e5e7eb",
        "borderRadius": 12, "padding": 24,
        "boxShadow": "0 1px 3px rgba(0,0,0,0.06)",
    }
    if style_extra:
        style.update(style_extra)
    return html.Div(children, style=style)


def card_title(text):
    return html.Div(text, style={
        "fontSize": 11, "fontWeight": 700, "textTransform": "uppercase",
        "letterSpacing": "1.5px", "color": "#9ca3af", "marginBottom": 16,
    })


def hero_section(market: str, category: str = "all") -> html.Div:
    scores_df = load_scores(market, category)
    label_market = MARKETS.get(market, market)

    if scores_df.empty:
        return html.Div(
            f"Aucune donnée pour {label_market} — lance : python3 tracker_betclic.py --demo",
            style={"color": "#9ca3af", "padding": "24px"})

    pr = scores_df[scores_df["brand"] == PRIMARY_BRAND]
    primary_score    = round(pr["geo_score"].values[0]) if not pr.empty else 0
    primary_rank     = int(pr.index[0]) + 1 if not pr.empty else 0
    primary_mentions = int(pr["n_mentions"].values[0]) if not pr.empty else 0
    primary_nss      = pr["net_sentiment"].values[0] if not pr.empty else 0
    n_prompts        = int(pr["n_prompts"].values[0]) if not pr.empty else 0
    sc               = score_color(primary_score)
    label_score      = ("Bonne visibilité IA" if primary_score >= 70
                        else "Visibilité partielle" if primary_score >= 45
                        else "Faible visibilité")
    nss_color  = "#16a34a" if primary_nss >= 0 else "#dc2626"
    nss_label  = f"+{primary_nss:.0f}%" if primary_nss >= 0 else f"{primary_nss:.0f}%"
    cat_label  = CATEGORY_LABELS.get(category, "Toutes catégories") if category != "all" else "Toutes catégories"

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
            font=dict(size=24, color=sc, family="Syne, sans-serif"),
        )],
    )

    return html.Div([
        html.Div(
            dcc.Graph(figure=ring_fig, config={"displayModeBar": False},
                      style={"width": 130, "height": 130}),
            style={"flexShrink": 0}
        ),
        html.Div([
            html.Div(
                f"{label_market} · {cat_label}",
                style={"fontSize": 11, "fontWeight": 700, "letterSpacing": "1.5px",
                       "textTransform": "uppercase", "color": "#9ca3af", "marginBottom": 6}),
            html.Div(label_score,
                     style={"fontSize": 24, "fontWeight": 800, "letterSpacing": "-0.5px",
                            "color": sc, "marginBottom": 4}),
            html.Div(
                f"Mesuré sur {n_prompts} prompts · Claude Haiku · {date.today().strftime('%d %b %Y')}",
                style={"fontSize": 12, "color": "#9ca3af", "marginBottom": 20}),
            html.Div([
                html.Div([
                    html.Div(f"#{primary_rank}",
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": "#111827",
                                    "display": "inline"}),
                    html.Span(f"/{len(scores_df)}",
                              style={"fontSize": 14, "color": "#9ca3af"}),
                    html.Div("Classement",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": "#9ca3af", "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb", "margin": "0 28px"}),
                html.Div([
                    html.Div(str(primary_mentions),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": "#111827"}),
                    html.Div("Mentions",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": "#9ca3af", "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb", "margin": "0 28px"}),
                html.Div([
                    html.Div(nss_label,
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": nss_color}),
                    html.Div("Net Sentiment",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": "#9ca3af", "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb", "margin": "0 28px"}),
                html.Div([
                    html.Div(str(n_prompts),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": "#111827"}),
                    html.Div("Prompts",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": "#9ca3af", "marginTop": 3}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"flex": 1}),
    ], style={
        "display": "flex", "alignItems": "center", "gap": 48,
        "background": "white", "border": "1px solid #e5e7eb",
        "borderRadius": 12, "padding": "28px 32px",
        "marginBottom": 20, "boxShadow": "0 1px 3px rgba(0,0,0,0.07)",
    })


def prompt_cards(df: pd.DataFrame) -> list:
    if df.empty:
        return [html.Div("Aucun résultat.", style={"color": "#9ca3af", "padding": "16px 0", "fontSize": 13})]
    cards = []
    for _, row in df.iterrows():
        sc    = score_color(row["geo_score"])
        icon  = "✓" if row["mentioned"] else "✗"
        ic    = "#16a34a" if row["mentioned"] else "#dc2626"
        cat_styles = {
            "visibility": ("Visibilité",      "#4f46e5", "#eef2ff"),
            "brand":      ("Image de marque", "#0369a1", "#e0f2fe"),
            "odds":       ("Cotes",           "#92400e", "#fef3c7"),
        }
        cat_label, cat_color, cat_bg = cat_styles.get(
            row["category"], (row["category"], "#6b7280", "#f3f4f6"))
        pos   = {"early": "↑ Début", "mid": "→ Milieu", "late": "↓ Fin"}.get(row.get("position"), "—")
        sent  = row.get("sentiment") or "—"
        sc_s  = {"positive": "#16a34a", "neutral": "#d97706", "negative": "#dc2626"}.get(sent, "#9ca3af")
        bg_s  = {"positive": "#dcfce7", "neutral": "#fef3c7", "negative": "#fee2e2"}.get(sent, "#f3f4f6")
        raw   = str(row.get("raw_response", "") or "")
        raw_block = []
        if raw and raw != "nan" and len(raw) > 10:
            raw_block = [html.Div(raw[:350] + "…", style={
                "marginTop": 10, "paddingTop": 10,
                "borderTop": "1px solid #f3f4f6",
                "fontSize": 11, "color": "#6b7280",
                "lineHeight": "1.8", "fontFamily": "'DM Mono', monospace",
            })]
        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(icon, style={"color": ic, "fontWeight": 800, "marginRight": 8}),
                    html.Span(row["prompt"], style={"fontSize": 13, "color": "#111827", "lineHeight": "1.5"}),
                ], style={"marginBottom": 10}),
                html.Div([
                    html.Span(cat_label, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 10px",
                        "borderRadius": 20, "background": cat_bg, "color": cat_color,
                        "textTransform": "uppercase", "letterSpacing": "0.5px", "marginRight": 6}),
                    html.Span(pos, style={
                        "fontSize": 10, "fontWeight": 600, "padding": "3px 10px",
                        "borderRadius": 20, "background": "#f3f4f6", "color": "#6b7280", "marginRight": 6}),
                    html.Span(sent, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 10px",
                        "borderRadius": 20, "background": bg_s, "color": sc_s, "marginRight": 6}),
                    html.Span(f"{int(row['mentions'])}× mention", style={
                        "fontSize": 10, "fontWeight": 600, "padding": "3px 10px",
                        "borderRadius": 20, "background": "#eef2ff", "color": "#4f46e5"}),
                ]),
            ] + raw_block, style={"flex": 1}),
            html.Div([
                html.Div(f"{row['geo_score']:.0f}",
                         style={"fontSize": 30, "fontWeight": 800, "color": sc,
                                "letterSpacing": "-1px", "lineHeight": "1"}),
                html.Div("/100", style={"fontSize": 10, "color": "#9ca3af"}),
            ], style={"textAlign": "right", "flexShrink": 0, "paddingLeft": 16}),
        ], style={
            "display": "flex", "alignItems": "flex-start", "gap": 16,
            "border": "1px solid #e5e7eb", "borderRadius": 12,
            "padding": "16px 20px", "marginBottom": 10, "background": "white",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        }))
    return cards

# ─────────────────────────────────────────────
# DASH APP
# ─────────────────────────────────────────────

app = dash.Dash(
    __name__,
    requests_pathname_prefix="/betclic/",
    external_stylesheets=[dbc.themes.BOOTSTRAP, FONTS],
    suppress_callback_exceptions=True,
    title="Voxa · Betclic GEO Intelligence",
)
server = app.server

# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────

TOPBAR = html.Div([
    html.Div([
        html.Div("V", style={
            "width": 32, "height": 32, "borderRadius": 8,
            "background": "linear-gradient(135deg,#e63946,#c1121f)",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "fontSize": 15, "fontWeight": 800, "color": "white", "flexShrink": 0,
        }),
        html.Span("voxa", style={"fontWeight": 800, "fontSize": 18, "letterSpacing": "-0.5px"}),
        html.Span("Betclic · GEO Intelligence", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "#fff0f0", "color": "#e63946",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": 10}),

    html.Div([
        html.Div(id="demo-badge-b"),
        html.A("↓ Export CSV", id="export-link-b", href="/export/betclic/csv?market=fr",
               style={"padding": "6px 14px", "borderRadius": 8,
                      "border": "1px solid #e5e7eb", "background": "white",
                      "fontSize": 12, "fontWeight": 600, "color": "#6b7280",
                      "textDecoration": "none"}),
        html.Div(["Client : ", html.Strong(CLIENT_NAME)],
                 style={"background": "#f9fafb", "border": "1px solid #e5e7eb",
                        "borderRadius": 8, "padding": "5px 12px",
                        "fontSize": 12, "color": "#6b7280"}),
    ], style={"display": "flex", "alignItems": "center", "gap": 12}),
], style={
    "display": "flex", "alignItems": "center", "justifyContent": "space-between",
    "height": 56, "padding": "0 32px",
    "background": "white", "borderBottom": "1px solid #e5e7eb",
    "position": "sticky", "top": 0, "zIndex": 100,
    "fontFamily": "Syne, sans-serif",
})

# Sélecteurs marché + catégorie
CONTROLS = html.Div([
    html.Div([
        html.Div("Marché", style={"fontSize": 10, "fontWeight": 700,
                                   "textTransform": "uppercase", "letterSpacing": "1px",
                                   "color": "#9ca3af", "marginBottom": 6}),
        dcc.RadioItems(
            id="market-select",
            options=[{"label": v, "value": k} for k, v in MARKETS.items()],
            value="fr",
            inline=True,
            inputStyle={"marginRight": 4},
            labelStyle={"marginRight": 16, "fontSize": 13, "fontWeight": 600,
                        "cursor": "pointer", "fontFamily": "Syne, sans-serif"},
        ),
    ]),
    html.Div([
        html.Div("Catégorie", style={"fontSize": 10, "fontWeight": 700,
                                      "textTransform": "uppercase", "letterSpacing": "1px",
                                      "color": "#9ca3af", "marginBottom": 6}),
        dcc.RadioItems(
            id="cat-select",
            options=[{"label": "Toutes", "value": "all"}] +
                    [{"label": v, "value": k} for k, v in CATEGORY_LABELS.items()],
            value="all",
            inline=True,
            inputStyle={"marginRight": 4},
            labelStyle={"marginRight": 16, "fontSize": 13, "fontWeight": 600,
                        "cursor": "pointer", "fontFamily": "Syne, sans-serif"},
        ),
    ]),
], style={
    "background": "white", "border": "1px solid #e5e7eb",
    "borderRadius": 12, "padding": "16px 24px",
    "marginBottom": 20, "display": "flex", "gap": 40,
    "boxShadow": "0 1px 3px rgba(0,0,0,0.04)",
})

app.layout = html.Div([
    dcc.Store(id="store-market", data="fr"),
    dcc.Store(id="store-cat",    data="all"),
    TOPBAR,
    html.Div(id="demo-banner-b"),
    html.Div([
        CONTROLS,
        html.Div(id="hero-b"),
        dbc.Tabs([
            dbc.Tab(label="Classement & Évolution", tab_id="classement",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="Vue synthèse 4 marchés", tab_id="overview",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="Analyse par prompt",     tab_id="prompts",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="Bibliothèque prompts",   tab_id="library",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
        ], id="tabs-b", active_tab="classement",
           style={"marginBottom": 20, "fontFamily": "Syne, sans-serif"}),
        html.Div(id="tab-content-b"),
    ], style={"maxWidth": 1280, "margin": "0 auto",
              "padding": "28px 32px 60px",
              "fontFamily": "Syne, sans-serif"}),
], style={"background": "#f4f5f9", "minHeight": "100vh"})

# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@app.callback(Output("demo-banner-b", "children"), Input("store-market", "data"))
def update_banner(_):
    if has_demo_data():
        return html.Div([
            html.Span("◈ ", style={"color": "#d97706"}),
            "Données simulées (mode démo) — non représentatives d'un run API réel",
        ], style={"background": "#fffbeb", "borderTop": "1px solid #fde68a",
                  "padding": "7px 32px", "fontSize": 11, "color": "#92400e"})
    return None


@app.callback(Output("demo-badge-b", "children"), Input("store-market", "data"))
def update_badge(_):
    if has_demo_data():
        return html.Span("Démo", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "#fef3c7", "color": "#d97706"})
    return None


@app.callback(Output("export-link-b", "href"), Input("market-select", "value"))
def update_export(market):
    return f"/export/betclic/csv?market={market or 'fr'}"


@app.callback(Output("hero-b", "children"),
          Input("market-select", "value"),
          Input("cat-select", "value"))
def update_hero(market, cat):
    return hero_section(market or "fr", cat or "all")


@app.callback(Output("tab-content-b", "children"),
          Input("tabs-b", "active_tab"),
          Input("market-select", "value"),
          Input("cat-select", "value"))
def render_tab(active_tab, market, cat):
    market = market or "fr"
    cat    = cat or "all"
    scores_df = load_scores(market, cat)

    if active_tab == "classement":
        return html.Div([
            dbc.Row([
                dbc.Col(card([
                    card_title("Classement concurrents"),
                    dcc.Graph(figure=build_bar_chart(scores_df),
                              config={"displayModeBar": False}),
                ]), width=5),
                dbc.Col(card([
                    card_title(f"Évolution GEO Score · {PRIMARY_BRAND}"),
                    dcc.Graph(figure=build_history_chart(market, cat),
                              config={"displayModeBar": False}),
                ]), width=7),
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(card([
                    card_title("Scores par catégorie · " + MARKETS.get(market, market)),
                    html.Div([
                        html.Div([
                            html.Div([
                                html.Div(CATEGORY_LABELS[ck],
                                         style={"fontSize": 11, "fontWeight": 700,
                                                "textTransform": "uppercase",
                                                "letterSpacing": "1px",
                                                "color": "#9ca3af", "marginBottom": 6}),
                                html.Div(
                                    str(round(load_scores(market, ck)[
                                        load_scores(market, ck)["brand"] == PRIMARY_BRAND
                                    ]["geo_score"].values[0]))
                                    if not load_scores(market, ck).empty
                                    and not load_scores(market, ck)[
                                        load_scores(market, ck)["brand"] == PRIMARY_BRAND
                                    ].empty
                                    else "—",
                                    style={"fontSize": 28, "fontWeight": 800,
                                           "color": "#4f46e5"}),
                                html.Div("/100", style={"fontSize": 10, "color": "#9ca3af"}),
                            ], style={
                                "border": "1px solid #e5e7eb", "borderRadius": 10,
                                "padding": "14px 16px", "textAlign": "center",
                                "flex": 1,
                            })
                        ])
                        for ck in CATEGORY_LABELS.keys()
                    ], style={"display": "flex", "gap": 12}),
                ]), width=6),
                dbc.Col(card([
                    card_title("Net Sentiment Score · concurrents"),
                    html.Div([
                        html.Div([
                            html.Div(row["brand"],
                                     style={"fontSize": 11, "fontWeight": 700,
                                            "textTransform": "uppercase",
                                            "letterSpacing": "1px",
                                            "color": "#9ca3af", "marginBottom": 6}),
                            html.Div(
                                (f"+{row['net_sentiment']:.0f}%"
                                 if row["net_sentiment"] >= 0
                                 else f"{row['net_sentiment']:.0f}%"),
                                style={"fontSize": 22, "fontWeight": 800,
                                       "color": "#16a34a" if row["net_sentiment"] >= 0
                                               else "#dc2626"}),
                        ], style={
                            "border": "1px solid #e5e7eb", "borderRadius": 10,
                            "padding": "12px 14px", "textAlign": "center", "flex": 1,
                        })
                        for _, row in scores_df.iterrows()
                        if not scores_df.empty
                    ], style={"display": "flex", "gap": 8, "flexWrap": "wrap"}),
                    html.Div("NSS = (prompts positifs − négatifs) / total × 100",
                             style={"fontSize": 11, "color": "#9ca3af", "marginTop": 10}),
                ]), width=6),
            ]),
        ])

    elif active_tab == "overview":
        overview_df = load_market_overview()
        return html.Div([
            dbc.Row([
                dbc.Col(card([
                    card_title("GEO Score Betclic · synthèse 4 marchés"),
                    html.Div([
                        html.Div([
                            html.Div(row["market"],
                                     style={"fontSize": 12, "fontWeight": 700,
                                            "marginBottom": 8, "color": "#111827"}),
                            html.Div(str(row["geo_score"]),
                                     style={"fontSize": 36, "fontWeight": 800,
                                            "color": score_color(row["geo_score"]),
                                            "letterSpacing": "-1px", "lineHeight": "1"}),
                            html.Div("/100", style={"fontSize": 10, "color": "#9ca3af"}),
                            html.Div(f"#{row.get('rank', '—')}/{row.get('n_brands', '—')}",
                                     style={"fontSize": 11, "color": "#9ca3af",
                                            "marginTop": 6}),
                        ], style={
                            "border": "1px solid #e5e7eb", "borderRadius": 12,
                            "padding": "20px", "textAlign": "center", "flex": 1,
                        })
                        for _, row in overview_df.iterrows()
                    ], style={"display": "flex", "gap": 16}),
                ]), width=12),
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(card([
                    card_title("Radar Betclic — visibilité / image / cotes × 4 marchés"),
                    dcc.Graph(figure=build_radar_chart(),
                              config={"displayModeBar": False}),
                ]), width=12),
            ]),
        ])

    elif active_tab == "prompts":
        return html.Div([
            html.Div([
                dcc.Dropdown(
                    id="filter-cat-b",
                    options=[{"label": "Toutes catégories", "value": "all"}] +
                            [{"label": v, "value": k} for k, v in CATEGORY_LABELS.items()],
                    value=cat, clearable=False,
                    style={"width": 220, "fontFamily": "Syne, sans-serif", "fontSize": 13}),
                dcc.Dropdown(
                    id="filter-sent-b",
                    options=[
                        {"label": "Tous sentiments", "value": "all"},
                        {"label": "Positif",         "value": "positive"},
                        {"label": "Neutre",          "value": "neutral"},
                        {"label": "Négatif",         "value": "negative"},
                    ],
                    value="all", clearable=False,
                    style={"width": 180, "fontFamily": "Syne, sans-serif", "fontSize": 13}),
                html.Div(id="prompt-count-b",
                         style={"fontSize": 12, "color": "#9ca3af", "alignSelf": "center"}),
            ], style={"display": "flex", "gap": 12, "marginBottom": 16, "alignItems": "center"}),
            html.Div(id="prompt-list-b"),
        ])

    elif active_tab == "library":
        df_lib = load_prompt_library()
        rows = []
        if not df_lib.empty:
            for _, row in df_lib.iterrows():
                flag = MARKETS.get(row["language"], row["language"])
                cat_styles = {
                    "visibility": ("#4f46e5", "#eef2ff", "Visibilité"),
                    "brand":      ("#0369a1", "#e0f2fe", "Image de marque"),
                    "odds":       ("#92400e", "#fef3c7", "Cotes"),
                    "regulation": ("#15803d", "#dcfce7", "Régulation"),
                    "payment":    ("#7e22ce", "#f3e8ff", "Paiement"),
                }
                cc, cbg, clabel = cat_styles.get(row["category"], ("#6b7280", "#f3f4f6", row["category"]))
                rows.append(html.Tr([
                    html.Td(flag, style={"fontSize": 13}),
                    html.Td(html.Span(clabel, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 9px",
                        "borderRadius": 20, "background": cbg, "color": cc,
                        "textTransform": "uppercase", "letterSpacing": "0.5px"})),
                    html.Td(row["text"], style={"fontSize": 13}),
                    html.Td(html.Span(str(row["n_runs"]),
                                     style={"fontSize": 11, "fontWeight": 700,
                                            "color": "#4f46e5", "background": "#eef2ff",
                                            "padding": "2px 8px", "borderRadius": 20})
                            if row["n_runs"]
                            else html.Span("—", style={"color": "#9ca3af"})),
                ]))
        return card([
            html.Div(
                f"Prompt Library · {CLIENT_NAME} · {len(df_lib)} prompts · 4 marchés",
                style={"fontSize": 11, "fontWeight": 700, "textTransform": "uppercase",
                       "letterSpacing": "1.5px", "color": "#9ca3af", "marginBottom": 16}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Marché"), html.Th("Catégorie"),
                    html.Th("Prompt"), html.Th("Runs"),
                ], style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                          "letterSpacing": "1px", "color": "#9ca3af"})),
                html.Tbody(rows),
            ], bordered=False, hover=True,
               style={"fontFamily": "Syne, sans-serif"}),
        ])

    return html.Div()


@app.callback(
    Output("prompt-list-b",  "children"),
    Output("prompt-count-b", "children"),
    Input("filter-cat-b",    "value"),
    Input("filter-sent-b",   "value"),
    Input("market-select",   "value"),
)
def update_prompts(cat, sent, market):
    df = load_prompt_detail(market or "fr", cat or "all", sent or "all")
    n  = len(df)
    return prompt_cards(df), f"{n} prompt{'s' if n > 1 else ''}"

# ─────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────

from flask import request as flask_request, Response
import csv, io

@server.route("/export/betclic/csv")
def export_csv_betclic():
    market = flask_request.args.get("market", "fr")
    df     = load_prompt_detail(market)
    out    = io.StringIO()
    cols   = ["prompt", "category", "mentioned", "mentions",
              "position", "sentiment", "geo_score", "run_date"]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for _, row in df.iterrows():
        w.writerow({c: row.get(c, "") for c in cols})
    return Response(
        out.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment;filename=voxa_betclic_{market}_{date.today()}.csv"})

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────

app.index_string = app.index_string.replace("</head>", """<style>
body { font-family: 'Syne', sans-serif !important; }
.nav-tabs .nav-link { color: #9ca3af !important; border: none !important;
    border-bottom: 2px solid transparent !important; font-family: 'Syne', sans-serif; }
.nav-tabs .nav-link.active { color: #e63946 !important;
    border-bottom: 2px solid #e63946 !important; background: transparent !important; }
.nav-tabs { border-bottom: 1px solid #e5e7eb !important; }
</style></head>""")

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8051)