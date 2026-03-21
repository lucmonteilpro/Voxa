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

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DB_PATH       = "voxa.db"
CLIENT_NAME   = "OM"
PRIMARY_BRAND = "OM"
ALL_BRANDS    = ["OM", "PSG", "OL", "Monaco"]

CLUB_COLORS = {
    "OM":     "#009EE0",
    "PSG":    "#DA291C",
    "OL":     "#1E3888",
    "Monaco": "#E8171C",
}

CATEGORY_LABELS = {
    "discovery":     "Découverte",
    "comparison":    "Comparatif",
    "transactional": "Transactionnel",
    "reputation":    "Réputation",
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
            showarrow=False, font=dict(size=13, color="#9ca3af"),
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
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=8, r=8, t=8, b=8),
        height=220,
        font=dict(family="Syne, sans-serif", size=11, color="#6b7280"),
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%d %b"),
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6", zeroline=False, range=[0, 105]),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    return fig


def build_bar_chart(scores_df: pd.DataFrame) -> go.Figure:
    if scores_df.empty:
        return go.Figure()
    fig = go.Figure()
    for _, row in scores_df.iterrows():
        is_p = row["brand"] == PRIMARY_BRAND
        color = "#4f46e5" if is_p else CLUB_COLORS.get(row["brand"], "#9ca3af")
        opacity = 1.0 if is_p else 0.45
        fig.add_trace(go.Bar(
            x=[row["geo_score"]],
            y=[row["brand"]],
            orientation="h",
            marker=dict(color=color, opacity=opacity, line=dict(width=0)),
            hovertemplate=f"<b>{row['brand']}</b> : {row['geo_score']:.0f}/100<extra></extra>",
            showlegend=False,
        ))
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=4, r=4, t=4, b=4),
        height=max(160, len(scores_df) * 52),
        barmode="overlay",
        xaxis=dict(range=[0, 105], showgrid=True, gridcolor="#f3f4f6",
                   zeroline=False, tickfont=dict(size=11)),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=13, family="Syne, sans-serif")),
        font=dict(family="Syne, sans-serif"),
        bargap=0.35,
    )
    return fig

# ─────────────────────────────────────────────
# COMPONENT BUILDERS
# ─────────────────────────────────────────────

def hero_section(scores_df: pd.DataFrame, lang: str) -> html.Div:
    if scores_df.empty:
        return html.Div("Aucune donnée — lance : python3 tracker.py --demo",
                        style={"color": "#9ca3af", "padding": "24px"})

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
            font=dict(size=24, color=sc, family="Syne, sans-serif"),
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
                            "textTransform": "uppercase", "color": "#9ca3af",
                            "marginBottom": 6}),
            html.Div(label, style={"fontSize": 24, "fontWeight": 800,
                                   "letterSpacing": "-0.5px", "color": sc,
                                   "marginBottom": 4}),
            html.Div(f"Mesuré sur {n_prompts} prompts · Claude Haiku · {date.today().strftime('%d %b %Y')}",
                     style={"fontSize": 12, "color": "#9ca3af", "marginBottom": 20}),

            # KPIs
            html.Div([
                html.Div([
                    html.Div(f"#{primary_rank}",
                             style={"fontSize": 24, "fontWeight": 800, "lineHeight": "1",
                                    "color": "#111827"}),
                    html.Div(f"/{len(scores_df)} concurrents",
                             style={"fontSize": 11, "color": "#9ca3af", "display": "inline",
                                    "fontWeight": 400}),
                    html.Div("Classement", style={"fontSize": 10, "fontWeight": 700,
                                                   "textTransform": "uppercase",
                                                   "letterSpacing": "1px",
                                                   "color": "#9ca3af", "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb",
                                "margin": "0 28px"}),
                html.Div([
                    html.Div(str(primary_mentions),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": "#111827"}),
                    html.Div("Mentions", style={"fontSize": 10, "fontWeight": 700,
                                                "textTransform": "uppercase",
                                                "letterSpacing": "1px",
                                                "color": "#9ca3af", "marginTop": 3}),
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
                                                     "color": "#9ca3af", "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#e5e7eb",
                                "margin": "0 28px"}),
                html.Div([
                    html.Div(str(n_prompts),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": "#111827"}),
                    html.Div("Prompts", style={"fontSize": 10, "fontWeight": 700,
                                               "textTransform": "uppercase",
                                               "letterSpacing": "1px",
                                               "color": "#9ca3af", "marginTop": 3}),
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
        return [html.Div("Aucun résultat pour ces filtres.",
                         style={"color": "#9ca3af", "padding": "16px 0",
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
                  "negative": "#dc2626"}.get(sent, "#9ca3af")
        sent_bg = {"positive": "#dcfce7", "neutral": "#fef3c7",
                   "negative": "#fee2e2"}.get(sent, "#f3f4f6")
        cat_styles = {
            "discovery":     ("Découverte",    "#4f46e5", "#eef2ff"),
            "comparison":    ("Comparatif",    "#0369a1", "#e0f2fe"),
            "transactional": ("Transactionnel","#15803d", "#dcfce7"),
            "reputation":    ("Réputation",    "#92400e", "#fef3c7"),
        }
        cat_label, cat_color, cat_bg = cat_styles.get(
            row["category"], (row["category"], "#6b7280", "#f3f4f6"))

        raw_block = []
        raw = str(row.get("raw_response", "") or "")
        if raw and raw != "nan" and len(raw) > 10:
            raw_block = [html.Div(
                raw[:350] + "…",
                style={"marginTop": 10, "paddingTop": 10,
                       "borderTop": "1px solid #f3f4f6",
                       "fontSize": 11, "color": "#6b7280",
                       "lineHeight": "1.8",
                       "fontFamily": "'DM Mono', monospace"}
            )]

        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(icon, style={"color": ic, "fontWeight": 800,
                                           "marginRight": 8, "fontSize": 13}),
                    html.Span(row["prompt"],
                              style={"fontSize": 13, "color": "#111827",
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
                                     "background": "#f3f4f6", "color": "#6b7280",
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
                html.Div("/100", style={"fontSize": 10, "color": "#9ca3af"}),
            ], style={"textAlign": "right", "flexShrink": 0, "paddingLeft": 16}),
        ], style={
            "display": "flex", "alignItems": "flex-start", "gap": 16,
            "border": "1px solid #e5e7eb", "borderRadius": 12,
            "padding": "16px 20px", "marginBottom": 10, "background": "white",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
        }))
    return cards


def compare_table(df: pd.DataFrame) -> dbc.Table:
    if df.empty:
        return html.Div("Pas de données", style={"color": "#9ca3af"})
    rows = []
    for _, r in df.iterrows():
        is_p  = r["brand"] == PRIMARY_BRAND
        dc    = "#16a34a" if r["delta"] > 0 else "#dc2626" if r["delta"] < 0 else "#9ca3af"
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
       style={"fontSize": 13, "fontFamily": "Syne, sans-serif"})

# ─────────────────────────────────────────────
# DASH APP
# ─────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        FONTS,
    ],
    suppress_callback_exceptions=True,
    title="Voxa · GEO Intelligence",
)
server = app.server  # Pour PythonAnywhere

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
            "fontSize": 15, "fontWeight": 800, "color": "white", "flexShrink": 0,
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
                               "border": "1px solid #e5e7eb", "background": "white",
                               "fontFamily": "Syne, sans-serif", "fontSize": 12,
                               "fontWeight": 600, "cursor": "pointer"}),
            html.Button("🇬🇧 EN", id="btn-en", n_clicks=0,
                        style={"padding": "5px 12px", "borderRadius": "0 8px 8px 0",
                               "border": "1px solid #e5e7eb", "borderLeft": "none",
                               "background": "white",
                               "fontFamily": "Syne, sans-serif", "fontSize": 12,
                               "fontWeight": 600, "cursor": "pointer"}),
        ], style={"display": "flex"}),
        html.A("↓ Export CSV", id="export-link", href="/export/csv?lang=fr",
               style={"padding": "6px 14px", "borderRadius": 8,
                      "border": "1px solid #e5e7eb", "background": "white",
                      "fontSize": 12, "fontWeight": 600, "color": "#6b7280",
                      "textDecoration": "none"}),
        html.Div([
            "Client : ",
            html.Strong(CLIENT_NAME),
        ], style={"background": "#f9fafb", "border": "1px solid #e5e7eb",
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
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="Analyse par prompt", tab_id="prompts",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="Bibliothèque prompts", tab_id="library",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
            dbc.Tab(label="À propos", tab_id="about",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase",
                                 "letterSpacing": "0.8px",
                                 "fontFamily": "Syne, sans-serif"}),
        ], id="tabs", active_tab="classement",
           style={"marginBottom": 20, "fontFamily": "Syne, sans-serif"}),
        html.Div(id="tab-content"),
    ], style={"maxWidth": 1280, "margin": "0 auto",
              "padding": "28px 32px 60px",
              "fontFamily": "Syne, sans-serif"}),
], style={"background": "#f4f5f9", "minHeight": "100vh"})

# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@callback(Output("store-lang", "data"),
          Input("btn-fr", "n_clicks"),
          Input("btn-en", "n_clicks"),
          prevent_initial_call=True)
def switch_lang(n_fr, n_en):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "fr"
    return "en" if "btn-en" in ctx.triggered[0]["prop_id"] else "fr"


@callback(Output("export-link", "href"),
          Input("store-lang", "data"))
def update_export(lang):
    return f"/export/csv?lang={lang}"


@callback(Output("demo-banner", "children"),
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


@callback(Output("demo-badge", "children"),
          Input("store-lang", "data"))
def update_demo_badge(_):
    if has_demo_data():
        return html.Span("Démo", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "#fef3c7", "color": "#d97706",
        })
    return None


@callback(Output("hero", "children"),
          Input("store-lang", "data"))
def update_hero(lang):
    return hero_section(load_latest_scores(lang), lang)


@callback(Output("tab-content", "children"),
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
                ], style={"background": "white", "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=5),

                # Évolution
                dbc.Col(html.Div([
                    html.Div(f"Évolution GEO Score · {PRIMARY_BRAND}", className="card-title-voxa"),
                    dcc.Graph(figure=build_history_chart(lang),
                              config={"displayModeBar": False}),
                ], style={"background": "white", "border": "1px solid #e5e7eb",
                           "borderRadius": 12, "padding": 24,
                           "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"}),
                width=7),
            ], className="mb-4"),

            dbc.Row([
                # FR vs EN
                dbc.Col(html.Div([
                    html.Div("Visibilité FR vs EN", className="card-title-voxa"),
                    compare_table(compare_df),
                ], style={"background": "white", "border": "1px solid #e5e7eb",
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
                                            "color": "#9ca3af", "marginBottom": 6}),
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
                             style={"fontSize": 11, "color": "#9ca3af", "marginTop": 10}),
                ], style={"background": "white", "border": "1px solid #e5e7eb",
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
                    style={"width": 200, "fontFamily": "Syne, sans-serif",
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
                    style={"width": 180, "fontFamily": "Syne, sans-serif",
                           "fontSize": 13},
                ),
                html.Div(id="prompt-count",
                         style={"fontSize": 12, "color": "#9ca3af",
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
                cc, cbg = cat_styles.get(row["category"], ("#6b7280", "#f3f4f6"))
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
                            else html.Span("—", style={"color": "#9ca3af"})),
                ]))

        return html.Div([
            html.Div([
                "Prompt Library · ", html.Strong(CLIENT_NAME),
                f" · {len(df_lib)} prompts · 🇫🇷 {n_fr} · 🇬🇧 {n_en}",
            ], style={"fontSize": 11, "fontWeight": 700,
                      "textTransform": "uppercase", "letterSpacing": "1.5px",
                      "color": "#9ca3af", "marginBottom": 16}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th(""), html.Th("Catégorie"),
                    html.Th("Prompt"), html.Th("Runs"),
                ], style={"fontSize": 10, "fontWeight": 700,
                          "textTransform": "uppercase",
                          "letterSpacing": "1px", "color": "#9ca3af"})),
                html.Tbody(rows),
            ], bordered=False, hover=True,
               style={"fontFamily": "Syne, sans-serif"}),
        ], style={"background": "white", "border": "1px solid #e5e7eb",
                  "borderRadius": 12, "padding": 24,
                  "boxShadow": "0 1px 3px rgba(0,0,0,0.06)"})

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
                    html.Div(body, style={"fontSize": 12, "color": "#6b7280",
                                          "lineHeight": "1.7"}),
                ], style={"border": "1px solid #e5e7eb", "borderRadius": 12,
                           "padding": 20, "background": "white",
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
                    html.Span(k, style={"width": 100, "color": "#9ca3af",
                                        "fontFamily": "'DM Mono', monospace",
                                        "fontSize": 12, "display": "inline-block"}),
                    html.Span(v, style={"color": "#111827",
                                        "fontFamily": "'DM Mono', monospace",
                                        "fontSize": 12,
                                        "fontStyle": "italic" if "hashés" in v else "normal"}),
                ], style={"marginBottom": 8}) for k, v in tech_rows],
            ], style={"background": "#f9fafb", "border": "1px solid #e5e7eb",
                      "borderRadius": 12, "padding": 20}),
        ])

    return html.Div()


@callback(
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

@server.route("/export/csv")
def export_csv():
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

app.index_string = app.index_string.replace(
    "</head>",
    """<style>
    body { font-family: 'Syne', sans-serif !important; }
    .card-title-voxa {
        font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 1.5px; color: #9ca3af; margin-bottom: 16px;
    }
    .nav-tabs .nav-link {
        color: #9ca3af !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        font-family: 'Syne', sans-serif;
    }
    .nav-tabs .nav-link.active {
        color: #4f46e5 !important;
        border-bottom: 2px solid #4f46e5 !important;
        background: transparent !important;
    }
    .nav-tabs { border-bottom: 1px solid #e5e7eb !important; }
    .Select-control { font-family: 'Syne', sans-serif !important; }
    </style></head>"""
)

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8050)