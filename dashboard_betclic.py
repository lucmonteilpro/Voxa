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

import theme as T
from theme import (P, C1, C2, NG, BG, BG3, BD, W, T2, T3, RED, GRD,
                   FONTS_URL, DASH_CSS, score_color, score_label,
                   card_style, card_title_style, kpi_value_style,
                   badge_style, BRAND_COLORS_BET)

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

BRAND_COLORS = T.BRAND_COLORS_BET  # depuis theme.py

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


def load_scores(market: str, category: str = "all", llm: str = "all") -> pd.DataFrame:
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
    if llm != "all":
        q += " AND ru.llm = ?"
        params.append(llm)
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


def load_history(market: str, category: str = "all", llm: str = "all") -> pd.DataFrame:
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
    if llm != "all":
        q += " AND ru.llm = ?"
        params.append(llm)
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
               SUBSTR(ru.raw_response, 1, 800) AS raw_response
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


def load_available_llms() -> list:
    """Retourne la liste des LLMs présents dans la DB."""
    conn = get_conn()
    if not conn:
        return []
    rows = conn.execute("SELECT DISTINCT llm FROM runs ORDER BY llm").fetchall()
    conn.close()
    return [r[0] for r in rows]


def has_demo_data() -> bool:
    conn = get_conn()
    if not conn:
        return False
    n = conn.execute("SELECT COUNT(*) FROM runs WHERE is_demo=1").fetchone()[0]
    conn.close()
    return n > 0


def load_gap_analysis(market: str) -> pd.DataFrame:
    """Score Betclic vs chaque concurrent, par catégorie. Retourne un pivot table."""
    conn = get_conn()
    if not conn:
        return pd.DataFrame()
    q = """
        SELECT b.name AS brand, p.category, AVG(r.geo_score) AS geo_score
        FROM results r
        JOIN brands  b  ON r.brand_id  = b.id
        JOIN runs    ru ON r.run_id    = ru.id
        JOIN prompts p  ON ru.prompt_id = p.id
        WHERE p.language = ? AND ru.run_date = (SELECT MAX(run_date) FROM runs)
        GROUP BY b.name, p.category
    """
    df = pd.read_sql_query(q, conn, params=(market,))
    conn.close()
    if df.empty:
        return df
    competitors = COMPETITORS_BY_MARKET.get(market, [])
    valid = [PRIMARY_BRAND] + competitors
    df = df[df["brand"].isin(valid)]
    pivot = df.pivot_table(index="brand", columns="category", values="geo_score", aggfunc="mean")
    pivot = pivot.round(0).fillna(0).astype(int)
    # Tri par score moyen décroissant
    pivot["_avg"] = pivot.mean(axis=1)
    pivot = pivot.sort_values("_avg", ascending=False).drop(columns="_avg")
    return pivot


def generate_recommendations(market: str) -> list:
    """Analyse les données et génère des recommandations actionnables."""
    recos = []
    market_label = MARKETS.get(market, market)

    # 1. Scores par catégorie — identifier la plus faible
    cat_scores = {}
    for ck, cv in CATEGORY_LABELS.items():
        df = load_scores(market, ck)
        if df.empty:
            cat_scores[ck] = 0
            continue
        pr = df[df["brand"] == PRIMARY_BRAND]
        cat_scores[ck] = round(pr["geo_score"].values[0]) if not pr.empty else 0

    if cat_scores:
        worst_cat = min(cat_scores, key=cat_scores.get)
        best_cat  = max(cat_scores, key=cat_scores.get)
        worst_score = cat_scores[worst_cat]
        best_score  = cat_scores[best_cat]
        gap = best_score - worst_score

        if gap >= 30:
            recos.append({
                "priority": "haute",
                "icon": "⚠",
                "title": f"Écart critique : {CATEGORY_LABELS[worst_cat]} ({worst_score}/100) vs {CATEGORY_LABELS[best_cat]} ({best_score}/100)",
                "body": f"L'écart de {gap} points entre ces deux catégories révèle un déficit de contenu sur les requêtes \"{CATEGORY_LABELS[worst_cat]}\". Recommandation : enrichir le contenu éditorial et les pages FAQ sur ce thème pour alimenter les LLMs.",
            })
        elif worst_score < 40:
            recos.append({
                "priority": "haute",
                "icon": "⚠",
                "title": f"Faible score en {CATEGORY_LABELS[worst_cat]} : {worst_score}/100",
                "body": f"Les LLMs ne citent quasiment pas Betclic sur les requêtes \"{CATEGORY_LABELS[worst_cat]}\" en {market_label}. C'est un angle mort à combler en priorité.",
            })

    # 2. Rang vs concurrent principal
    df_all = load_scores(market)
    if not df_all.empty:
        pr = df_all[df_all["brand"] == PRIMARY_BRAND]
        if not pr.empty:
            rank = int(pr.index[0]) + 1
            n_brands = len(df_all)
            leader = df_all.iloc[0]
            if rank > 1:
                delta = round(leader["geo_score"] - pr["geo_score"].values[0])
                recos.append({
                    "priority": "moyenne",
                    "icon": "◎",
                    "title": f"Betclic #{rank}/{n_brands} — {delta} points derrière {leader['brand']}",
                    "body": f"{leader['brand']} domine les réponses IA en {market_label}. Analyser les sources web que les LLMs utilisent pour citer {leader['brand']} et produire du contenu équivalent ou supérieur.",
                })
            else:
                recos.append({
                    "priority": "info",
                    "icon": "✓",
                    "title": f"Betclic #1 en {market_label} — position dominante",
                    "body": f"Betclic est le leader GEO en {market_label} avec {round(pr['geo_score'].values[0])}/100. Maintenir l'avance en suivant l'évolution hebdomadaire.",
                })

    # 3. Prompts où Betclic est absent
    df_detail = load_prompt_detail(market)
    if not df_detail.empty:
        absent = df_detail[df_detail["mentioned"] == 0]
        n_absent = len(absent)
        n_total  = len(df_detail)
        if n_absent > 0:
            pct = round(n_absent / n_total * 100)
            worst_cats = absent["category"].value_counts()
            main_cat = worst_cats.index[0] if len(worst_cats) > 0 else ""
            cat_label = CATEGORY_LABELS.get(main_cat, main_cat)
            recos.append({
                "priority": "haute" if pct >= 40 else "moyenne",
                "icon": "✗",
                "title": f"Betclic absent de {n_absent}/{n_total} réponses ({pct}%)",
                "body": f"La catégorie la plus touchée est \"{cat_label}\". Chaque réponse sans mention = un utilisateur potentiel qui ne voit pas Betclic. Priorité : créer du contenu structuré (Schema JSON-LD, FAQ) pour ces requêtes.",
            })

    # 4. Sentiment global
    if not df_all.empty:
        pr = df_all[df_all["brand"] == PRIMARY_BRAND]
        if not pr.empty:
            nss = pr["net_sentiment"].values[0]
            if nss < 20:
                recos.append({
                    "priority": "moyenne",
                    "icon": "◐",
                    "title": f"Net Sentiment Score faible : {nss:+.0f}%",
                    "body": "Les LLMs ne qualifient pas suffisamment Betclic en termes positifs. Enrichir les pages produit avec des termes comme \"fiable\", \"leader\", \"sécurisé\", \"agréé\" pour influencer le sentiment des réponses IA.",
                })

    # 5. Si aucune recommandation → message positif
    if not recos:
        recos.append({
            "priority": "info",
            "icon": "✓",
            "title": "Bonne performance globale",
            "body": f"Betclic affiche de bons scores sur toutes les catégories en {market_label}. Continuer le monitoring pour détecter les variations.",
        })

    return recos

# ─────────────────────────────────────────────
# COLORS & HELPERS
# ─────────────────────────────────────────────

def score_color(s):
    if s >= 70: return "#00FFAA"
    if s >= 45: return "#F59E0B"
    return "#FF4B6E"


# ─────────────────────────────────────────────
# CHART BUILDERS
# ─────────────────────────────────────────────

def build_bar_chart(scores_df: pd.DataFrame) -> go.Figure:
    if scores_df.empty:
        return go.Figure()
    df = scores_df.sort_values("geo_score", ascending=True).reset_index(drop=True)
    colors   = ["#00E5FF" if r["brand"] == PRIMARY_BRAND
                else BRAND_COLORS.get(r["brand"], T.T3)
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
        paper_bgcolor=T.W, plot_bgcolor=T.W,
        margin=dict(l=4, r=40, t=4, b=4),
        height=max(180, len(df) * 36),
        xaxis=dict(range=[0, 105], showgrid=True, gridcolor="#0D1117",
                   zeroline=False, tickfont=dict(size=11)),
        yaxis=dict(showgrid=False, zeroline=False, automargin=True,
                   tickfont=dict(size=12, family=T.FONT_BODY)),
        font=dict(family=T.FONT_BODY),
        bargap=0.3,
    )
    return fig


def build_history_chart(market: str, category: str = "all", llm: str = "all") -> go.Figure:
    df = load_history(market, category, llm)
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
            line=dict(color="#00E5FF", width=2.5, shape="spline"),
            marker=dict(color="#00E5FF", size=7),
            fill="tozeroy", fillcolor="rgba(79,70,229,0.08)",
            hovertemplate="<b>%{x}</b><br>Score : %{y}/100<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor=T.W, plot_bgcolor=T.W,
        margin=dict(l=8, r=8, t=8, b=8), height=200,
        font=dict(family=T.FONT_BODY, size=11, color=T.T2),
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%d %b"),
        yaxis=dict(showgrid=True, gridcolor="#0D1117",
                   zeroline=False, range=[0, 105]),
    )
    return fig


def build_radar_chart() -> go.Figure:
    """Radar Betclic sur les 3 catégories × 4 marchés."""
    categories = list(CATEGORY_LABELS.values())
    cat_keys   = list(CATEGORY_LABELS.keys())
    fig = go.Figure()
    colors_map = {
        "fr":    "#00E5FF",
        "pt":    "#00FFAA",
        "fr-ci": "#F59E0B",
        "pl":    "#FF4B6E",
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
            angularaxis=dict(tickfont=dict(size=12, family=T.FONT_BODY)),
            bgcolor=T.W,
        ),
        showlegend=True,
        legend=dict(font=dict(family=T.FONT_BODY, size=11)),
        paper_bgcolor=T.W,
        margin=dict(l=40, r=40, t=20, b=20),
        height=300,
        font=dict(family=T.FONT_BODY),
    )
    return fig

# ─────────────────────────────────────────────
# COMPONENT BUILDERS
# ─────────────────────────────────────────────

def card(children, style_extra=None):
    style = {
        "background": T.W, "border": "1px solid #e5e7eb",
        "borderRadius": 12, "padding": 24,
        "boxShadow": "0 1px 3px rgba(0,0,0,0.06)",
    }
    if style_extra:
        style.update(style_extra)
    return html.Div(children, style=style)


def card_title(text):
    return html.Div(text, style={
        "fontSize": 11, "fontWeight": 700, "textTransform": "uppercase",
        "letterSpacing": "1.5px", "color": T.T3, "marginBottom": 16,
    })


def hero_section(market: str, category: str = "all", llm: str = "all") -> html.Div:
    scores_df = load_scores(market, category, llm)
    label_market = MARKETS.get(market, market)

    if scores_df.empty:
        return html.Div(
            f"Aucune donnée pour {label_market} — lance : python3 tracker_betclic.py --demo",
            style={"color": T.T3, "padding": "24px"})

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
    nss_color  = "#00FFAA" if primary_nss >= 0 else "#FF4B6E"
    nss_label  = f"+{primary_nss:.0f}%" if primary_nss >= 0 else f"{primary_nss:.0f}%"
    cat_label  = CATEGORY_LABELS.get(category, "Toutes catégories") if category != "all" else "Toutes catégories"

    ring_fig = go.Figure(go.Pie(
        values=[primary_score, max(100 - primary_score, 0)],
        hole=0.78, sort=False, direction="clockwise", rotation=90,
        marker=dict(colors=[sc, "#0D1117"], line=dict(width=0)),
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
        html.Div(
            dcc.Graph(figure=ring_fig, config={"displayModeBar": False},
                      style={"width": 130, "height": 130}),
            style={"flexShrink": 0}
        ),
        html.Div([
            html.Div(
                f"{label_market} · {cat_label}",
                style={"fontSize": 11, "fontWeight": 700, "letterSpacing": "1.5px",
                       "textTransform": "uppercase", "color": T.T3, "marginBottom": 6}),
            html.Div(label_score,
                     style={"fontSize": 24, "fontWeight": 800, "letterSpacing": "-0.5px",
                            "color": sc, "marginBottom": 4}),
            html.Div(
                f"Mesuré sur {n_prompts} prompts · Claude Haiku · {date.today().strftime('%d %b %Y')}",
                style={"fontSize": 12, "color": T.T3, "marginBottom": 20}),
            html.Div([
                html.Div([
                    html.Div(f"#{primary_rank}",
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": T.W,
                                    "display": "inline"}),
                    html.Span(f"/{len(scores_df)}",
                              style={"fontSize": 14, "color": T.T3}),
                    html.Div("Classement",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#1E2A3A", "margin": "0 28px"}),
                html.Div([
                    html.Div(str(primary_mentions),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": T.W}),
                    html.Div("Mentions",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#1E2A3A", "margin": "0 28px"}),
                html.Div([
                    html.Div(nss_label,
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": nss_color}),
                    html.Div("Net Sentiment",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": T.T3, "marginTop": 3}),
                ]),
                html.Div(style={"width": 1, "background": "#1E2A3A", "margin": "0 28px"}),
                html.Div([
                    html.Div(str(n_prompts),
                             style={"fontSize": 24, "fontWeight": 800,
                                    "lineHeight": "1", "color": T.W}),
                    html.Div("Prompts",
                             style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                                    "letterSpacing": "1px", "color": T.T3, "marginTop": 3}),
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
        return [html.Div("Aucun résultat.", style={"color": T.T3, "padding": "16px 0", "fontSize": 13})]
    cards = []
    for _, row in df.iterrows():
        sc    = score_color(row["geo_score"])
        icon  = "✓" if row["mentioned"] else "✗"
        ic    = "#00FFAA" if row["mentioned"] else "#FF4B6E"
        cat_styles = {
            "visibility": ("Visibilité",      "#00E5FF", "rgba(0,229,255,0.10)"),
            "brand":      ("Image de marque", "#00E5FF", "rgba(0,229,255,0.08)"),
            "odds":       ("Cotes",           "#F59E0B", "rgba(245,158,11,0.15)"),
            "regulation": ("Régulation",      "#00FFAA", "rgba(0,255,170,0.10)"),
            "payment":    ("Paiement",        "#7B4DFF", "rgba(123,77,255,0.10)"),
        }
        cat_label, cat_color, cat_bg = cat_styles.get(
            row["category"], (row["category"], T.T2, "#0D1117"))
        pos   = {"early": "↑ Début", "mid": "→ Milieu", "late": "↓ Fin"}.get(row.get("position"), "—")
        sent  = row.get("sentiment") or "—"
        sc_s  = {"positive": "#00FFAA", "neutral": "#F59E0B", "negative": "#FF4B6E"}.get(sent, T.T3)
        bg_s  = {"positive": "rgba(0,255,170,0.10)", "neutral": "rgba(245,158,11,0.15)", "negative": "rgba(255,75,110,0.10)"}.get(sent, "#0D1117")
        raw   = str(row.get("raw_response", "") or "")
        raw_block = []
        if raw and raw != "nan" and len(raw) > 10:
            raw_block = [html.Div(raw[:600] + ("…" if len(raw) > 600 else ""), style={
                "marginTop": 10, "paddingTop": 10,
                "borderTop": "1px solid #f3f4f6",
                "fontSize": 11, "color": T.T2,
                "lineHeight": "1.8", "fontFamily": "'DM Mono', monospace",
            })]
        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(icon, style={"color": ic, "fontWeight": 800, "marginRight": 8}),
                    html.Span(row["prompt"], style={"fontSize": 13, "color": T.W, "lineHeight": "1.5"}),
                ], style={"marginBottom": 10}),
                html.Div([
                    html.Span(cat_label, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 10px",
                        "borderRadius": 20, "background": cat_bg, "color": cat_color,
                        "textTransform": "uppercase", "letterSpacing": "0.5px", "marginRight": 6}),
                    html.Span(pos, style={
                        "fontSize": 10, "fontWeight": 600, "padding": "3px 10px",
                        "borderRadius": 20, "background": "#0D1117", "color": T.T2, "marginRight": 6}),
                    html.Span(sent, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 10px",
                        "borderRadius": 20, "background": bg_s, "color": sc_s, "marginRight": 6}),
                    html.Span(f"{int(row['mentions'])}× mention", style={
                        "fontSize": 10, "fontWeight": 600, "padding": "3px 10px",
                        "borderRadius": 20, "background": "rgba(0,229,255,0.10)", "color": "#00E5FF"}),
                ]),
            ] + raw_block, style={"flex": 1}),
            html.Div([
                html.Div(f"{row['geo_score']:.0f}",
                         style={"fontSize": 30, "fontWeight": 800, "color": sc,
                                "letterSpacing": "-1px", "lineHeight": "1"}),
                html.Div("/100", style={"fontSize": 10, "color": T.T3}),
            ], style={"textAlign": "right", "flexShrink": 0, "paddingLeft": 16}),
        ], style={
            "display": "flex", "alignItems": "flex-start", "gap": 16,
            "border": "1px solid #e5e7eb", "borderRadius": 12,
            "padding": "16px 20px", "marginBottom": 10, "background": T.W,
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
            "fontSize": 15, "fontWeight": 800, "color": T.W, "flexShrink": 0,
        }),
        html.Span("voxa", style={"fontWeight": 800, "fontSize": 18, "letterSpacing": "-0.5px"}),
        html.Span("Betclic · GEO Intelligence", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "rgba(255,75,110,0.06)", "color": "#e63946",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": 10}),

    html.Div([
        html.Div(id="demo-badge-b"),
        html.A("↓ Export CSV", id="export-link-b", href="/export/betclic/csv?market=fr",
               style={"padding": "6px 14px", "borderRadius": 8,
                      "border": "1px solid #e5e7eb", "background": T.W,
                      "fontSize": 12, "fontWeight": 600, "color": T.T2,
                      "textDecoration": "none"}),
        html.Div(["Client : ", html.Strong(CLIENT_NAME)],
                 style={"background": T.BG, "border": "1px solid #e5e7eb",
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

# Sélecteurs marché + catégorie
CONTROLS = html.Div([
    html.Div([
        html.Div("Marché", style={"fontSize": 10, "fontWeight": 700,
                                   "textTransform": "uppercase", "letterSpacing": "1px",
                                   "color": T.T3, "marginBottom": 6}),
        dcc.RadioItems(
            id="market-select",
            options=[{"label": v, "value": k} for k, v in MARKETS.items()],
            value="fr",
            inline=True,
            inputStyle={"marginRight": 4},
            labelStyle={"marginRight": 16, "fontSize": 13, "fontWeight": 600,
                        "cursor": "pointer", "fontFamily": T.FONT_BODY},
        ),
    ]),
    html.Div([
        html.Div("Catégorie", style={"fontSize": 10, "fontWeight": 700,
                                      "textTransform": "uppercase", "letterSpacing": "1px",
                                      "color": T.T3, "marginBottom": 6}),
        dcc.RadioItems(
            id="cat-select",
            options=[{"label": "Toutes", "value": "all"}] +
                    [{"label": v, "value": k} for k, v in CATEGORY_LABELS.items()],
            value="all",
            inline=True,
            inputStyle={"marginRight": 4},
            labelStyle={"marginRight": 16, "fontSize": 13, "fontWeight": 600,
                        "cursor": "pointer", "fontFamily": T.FONT_BODY},
        ),
    ]),
    html.Div([
        html.Div("LLM", style={"fontSize": 10, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "1px",
                                 "color": T.T3, "marginBottom": 6}),
        dcc.Dropdown(
            id="llm-select",
            options=[{"label": "Tous les LLMs", "value": "all"}],
            value="all", clearable=False,
            style={"width": 200, "fontFamily": T.FONT_BODY, "fontSize": 13},
        ),
    ]),
], style={
    "background": T.W, "border": "1px solid #e5e7eb",
    "borderRadius": 12, "padding": "16px 24px",
    "marginBottom": 20, "display": "flex", "gap": 40, "alignItems": "flex-start",
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
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Insights & Recommandations", tab_id="insights",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Vue synthèse 4 marchés", tab_id="overview",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Analyse par prompt",     tab_id="prompts",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
            dbc.Tab(label="Bibliothèque prompts",   tab_id="library",
                    label_style={"fontSize": 12, "fontWeight": 700,
                                 "textTransform": "uppercase", "letterSpacing": "0.8px",
                                 "fontFamily": T.FONT_BODY}),
        ], id="tabs-b", active_tab="classement",
           style={"marginBottom": 20, "fontFamily": T.FONT_BODY}),
        html.Div(id="tab-content-b"),
    ], style={"maxWidth": 1280, "margin": "0 auto",
              "padding": "28px 32px 60px",
              "fontFamily": T.FONT_BODY}),
], style={"background": "#0D1117", "minHeight": "100vh"})

# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@app.callback(Output("demo-banner-b", "children"), Input("store-market", "data"))
def update_banner(_):
    if has_demo_data():
        return html.Div([
            html.Span("◈ ", style={"color": "#F59E0B"}),
            "Données simulées (mode démo) — non représentatives d'un run API réel",
        ], style={"background": "rgba(245,158,11,0.08)", "borderTop": "1px solid #fde68a",
                  "padding": "7px 32px", "fontSize": 11, "color": "#F59E0B"})
    return None


@app.callback(Output("demo-badge-b", "children"), Input("store-market", "data"))
def update_badge(_):
    if has_demo_data():
        return html.Span("Démo", style={
            "fontSize": 9, "fontWeight": 700, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 9px",
            "borderRadius": 20, "background": "rgba(245,158,11,0.15)", "color": "#F59E0B"})
    return None


@app.callback(Output("export-link-b", "href"), Input("market-select", "value"))
def update_export(market):
    return f"/export/betclic/csv?market={market or 'fr'}"


@app.callback(Output("llm-select", "options"), Input("store-market", "data"))
def populate_llm_dropdown(_):
    llms = load_available_llms()
    opts = [{"label": "Tous les LLMs", "value": "all"}]
    llm_labels = {
        "claude-haiku-4-5-20251001": "Claude Haiku",
        "gpt-4o-mini":               "GPT-4o mini",
        "sonar":                     "Perplexity Sonar",
    }
    for llm in llms:
        label = llm_labels.get(llm, llm)
        opts.append({"label": label, "value": llm})
    return opts


@app.callback(Output("hero-b", "children"),
          Input("market-select", "value"),
          Input("cat-select", "value"),
          Input("llm-select", "value"))
def update_hero(market, cat, llm):
    return hero_section(market or "fr", cat or "all", llm or "all")


@app.callback(Output("tab-content-b", "children"),
          Input("tabs-b", "active_tab"),
          Input("market-select", "value"),
          Input("cat-select", "value"),
          Input("llm-select", "value"))
def render_tab(active_tab, market, cat, llm):
    market = market or "fr"
    cat    = cat or "all"
    llm    = llm or "all"
    scores_df = load_scores(market, cat, llm)

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
                    dcc.Graph(figure=build_history_chart(market, cat, llm),
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
                                                "color": T.T3, "marginBottom": 6}),
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
                                           "color": "#00E5FF"}),
                                html.Div("/100", style={"fontSize": 10, "color": T.T3}),
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
                                            "color": T.T3, "marginBottom": 6}),
                            html.Div(
                                (f"+{row['net_sentiment']:.0f}%"
                                 if row["net_sentiment"] >= 0
                                 else f"{row['net_sentiment']:.0f}%"),
                                style={"fontSize": 22, "fontWeight": 800,
                                       "color": "#00FFAA" if row["net_sentiment"] >= 0
                                               else "#FF4B6E"}),
                        ], style={
                            "border": "1px solid #e5e7eb", "borderRadius": 10,
                            "padding": "12px 14px", "textAlign": "center", "flex": 1,
                        })
                        for _, row in scores_df.iterrows()
                        if not scores_df.empty
                    ], style={"display": "flex", "gap": 8, "flexWrap": "wrap"}),
                    html.Div("NSS = (prompts positifs − négatifs) / total × 100",
                             style={"fontSize": 11, "color": T.T3, "marginTop": 10}),
                ]), width=6),
            ]),
        ])

    elif active_tab == "insights":
        recos = generate_recommendations(market)
        gap_df = load_gap_analysis(market)

        # Construire les cartes de recommandation
        priority_styles = {
            "haute":   {"border": "#FF4B6E", "bg": "rgba(255,75,110,0.08)", "badge_bg": "rgba(255,75,110,0.10)", "badge_color": "#FF4B6E"},
            "moyenne": {"border": "#F59E0B", "bg": "rgba(245,158,11,0.08)", "badge_bg": "rgba(245,158,11,0.15)", "badge_color": "#F59E0B"},
            "info":    {"border": "#00FFAA", "bg": "rgba(0,255,170,0.06)", "badge_bg": "rgba(0,255,170,0.10)", "badge_color": "#00FFAA"},
        }
        reco_cards = []
        for reco in recos:
            ps = priority_styles.get(reco["priority"], priority_styles["info"])
            reco_cards.append(html.Div([
                html.Div([
                    html.Span(reco["icon"], style={"fontSize": 18, "marginRight": 10}),
                    html.Span(reco["priority"].upper(), style={
                        "fontSize": 9, "fontWeight": 800, "letterSpacing": "1.5px",
                        "padding": "2px 8px", "borderRadius": 20,
                        "background": ps["badge_bg"], "color": ps["badge_color"],
                        "marginRight": 10}),
                    html.Span(reco["title"], style={
                        "fontSize": 14, "fontWeight": 700, "color": T.W}),
                ], style={"marginBottom": 8}),
                html.Div(reco["body"], style={
                    "fontSize": 13, "color": "#A8B8C8", "lineHeight": "1.7",
                    "paddingLeft": 28}),
            ], style={
                "borderLeft": f"3px solid {ps['border']}",
                "background": ps["bg"],
                "borderRadius": "0 10px 10px 0",
                "padding": "16px 20px", "marginBottom": 12,
            }))

        # Construire le gap analysis table
        gap_section = html.Div("Pas de données pour le gap analysis.",
                               style={"color": T.T3, "fontSize": 13})
        if not gap_df.empty:
            # En-tête
            cat_cols = [c for c in gap_df.columns if c in CATEGORY_LABELS]
            header = [html.Th("", style={"width": 140})] + [
                html.Th(CATEGORY_LABELS.get(c, c), style={
                    "fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                    "letterSpacing": "1px", "color": T.T3, "textAlign": "center",
                    "padding": "8px 12px"})
                for c in cat_cols
            ]
            # Score Betclic pour calcul des écarts
            betclic_scores = {}
            if PRIMARY_BRAND in gap_df.index:
                for c in cat_cols:
                    betclic_scores[c] = gap_df.loc[PRIMARY_BRAND, c] if c in gap_df.columns else 0
            # Lignes
            rows = []
            for brand in gap_df.index:
                is_primary = brand == PRIMARY_BRAND
                cells = [html.Td(brand, style={
                    "fontWeight": 800 if is_primary else 600,
                    "fontSize": 13,
                    "color": BRAND_COLORS.get(brand, T.W) if is_primary else T.W,
                    "padding": "10px 12px"})]
                for c in cat_cols:
                    val = int(gap_df.loc[brand, c]) if c in gap_df.columns else 0
                    if is_primary:
                        bg = "rgba(0,229,255,0.10)"
                        color = "#00E5FF"
                    else:
                        delta = val - betclic_scores.get(c, 0)
                        if delta > 10:
                            bg = "rgba(255,75,110,0.10)"
                            color = "#FF4B6E"
                        elif delta < -10:
                            bg = "rgba(0,255,170,0.10)"
                            color = "#00FFAA"
                        else:
                            bg = T.BG
                            color = T.T2
                    cells.append(html.Td(str(val), style={
                        "textAlign": "center", "fontSize": 14,
                        "fontWeight": 800 if is_primary else 600,
                        "color": color, "background": bg,
                        "padding": "10px 12px", "borderRadius": 6}))
                rows.append(html.Tr(cells))

            gap_section = dbc.Table([
                html.Thead(html.Tr(header)),
                html.Tbody(rows),
            ], bordered=False, hover=True, style={"fontFamily": T.FONT_BODY})

        # ── Recommandations persistantes depuis voxa_db ──────
        try:
            import voxa_db as vdb
            db_recos = vdb.get_recommendations("betclic")
            db_alerts = vdb.get_alerts("betclic", unread_only=True)
        except Exception:
            db_recos = []; db_alerts = []

        # Alertes actives
        alert_section = html.Div()
        if db_alerts:
            alert_items = [html.Div([
                html.Span({"critical":"🔴","warning":"🟡","info":"🟢"}.get(a.get("severity","info"),"🟢"),
                          style={"marginRight": 6}),
                html.Strong(a["title"]), f" — {a['body']}",
                html.Span(f"  {a['created_at'][:10]}", style={"fontSize":10,"color":T.T3,"marginLeft":8}),
            ], style={"fontSize":12,"padding":"8px 12px","marginBottom":6,
                      "background":"rgba(245,158,11,0.08)","borderRadius":8,"borderLeft":"3px solid #d97706"})
            for a in db_alerts]
            alert_section = card([
                card_title("ALERTES ACTIVES"),
                html.Div(alert_items),
            ])

        # Recos persistantes
        db_reco_cards = []
        for r in db_recos:
            pr_map = {"high":"haute","medium":"moyenne","low":"info"}
            prio = pr_map.get(r.get("priority","medium"), "moyenne")
            ps = priority_styles.get(prio, priority_styles["moyenne"])
            impact = r.get("impact_score", 0)
            db_reco_cards.append(html.Div([
                html.Div([
                    html.Span("💡", style={"fontSize": 16, "marginRight": 8}),
                    html.Span(prio.upper(), style={
                        "fontSize": 9, "fontWeight": 800, "letterSpacing": "1.5px",
                        "padding": "2px 8px", "borderRadius": 20,
                        "background": ps["badge_bg"], "color": ps["badge_color"],
                        "marginRight": 8}),
                    html.Span(r.get("title",""), style={
                        "fontSize": 13, "fontWeight": 700, "color": T.W}),
                    *([ html.Span(f"+{impact:.0f} pts estimés",
                        style={"fontSize":10,"color":T.T3,"marginLeft":8})] if impact else []),
                ], style={"marginBottom": 6}),
                html.Div(r.get("body",""), style={
                    "fontSize": 12, "color": "#A8B8C8", "lineHeight": "1.7",
                    "paddingLeft": 24}),
                *([ html.Div(f"Prompt : « {r['prompt_text'][:80]}… »",
                    style={"fontSize":10,"color":T.T3,"marginTop":4,
                           "paddingLeft":24,"fontStyle":"italic"})
                   ] if r.get("prompt_text") else []),
            ], style={
                "borderLeft": f"3px solid {ps['border']}",
                "background": ps["bg"],
                "borderRadius": "0 10px 10px 0",
                "padding": "14px 18px", "marginBottom": 10,
            }))

        db_section = html.Div()
        if db_reco_cards:
            db_section = dbc.Row([
                dbc.Col(card([
                    card_title("RECOMMANDATIONS GEO — ACTIONS PRIORITAIRES"),
                    html.Div(db_reco_cards),
                    html.Div("Générées automatiquement après chaque run tracker.",
                        style={"fontSize":11,"color":T.T3,"marginTop":12,"fontStyle":"italic"}),
                ]), width=12),
            ], className="mb-4")

        return html.Div([
            alert_section,
            dbc.Row([
                dbc.Col(card([
                    card_title(f"Recommandations · {MARKETS.get(market, market)}"),
                    html.Div(reco_cards),
                ]), width=12),
            ], className="mb-4"),
            db_section,
            dbc.Row([
                dbc.Col(card([
                    card_title(f"Gap Analysis · Betclic vs concurrents · {MARKETS.get(market, market)}"),
                    html.Div([
                        html.Div([
                            html.Span("", style={
                                "display": "inline-block", "width": 10, "height": 10,
                                "borderRadius": 3, "background": "rgba(0,255,170,0.10)", "marginRight": 4}),
                            html.Span("Betclic devant", style={"fontSize": 10, "color": "#00FFAA", "marginRight": 16}),
                            html.Span("", style={
                                "display": "inline-block", "width": 10, "height": 10,
                                "borderRadius": 3, "background": "rgba(255,75,110,0.10)", "marginRight": 4}),
                            html.Span("Concurrent devant", style={"fontSize": 10, "color": "#FF4B6E"}),
                        ], style={"marginBottom": 12}),
                        gap_section,
                    ]),
                ]), width=12),
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
                                            "marginBottom": 8, "color": T.W}),
                            html.Div(str(row["geo_score"]),
                                     style={"fontSize": 36, "fontWeight": 800,
                                            "color": score_color(row["geo_score"]),
                                            "letterSpacing": "-1px", "lineHeight": "1"}),
                            html.Div("/100", style={"fontSize": 10, "color": T.T3}),
                            html.Div(f"#{row.get('rank', '—')}/{row.get('n_brands', '—')}",
                                     style={"fontSize": 11, "color": T.T3,
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
                    card_title("Radar Betclic — 5 catégories × 4 marchés"),
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
                    style={"width": 220, "fontFamily": T.FONT_BODY, "fontSize": 13}),
                dcc.Dropdown(
                    id="filter-sent-b",
                    options=[
                        {"label": "Tous sentiments", "value": "all"},
                        {"label": "Positif",         "value": "positive"},
                        {"label": "Neutre",          "value": "neutral"},
                        {"label": "Négatif",         "value": "negative"},
                    ],
                    value="all", clearable=False,
                    style={"width": 180, "fontFamily": T.FONT_BODY, "fontSize": 13}),
                html.Div(id="prompt-count-b",
                         style={"fontSize": 12, "color": T.T3, "alignSelf": "center"}),
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
                    "visibility": ("#00E5FF", "rgba(0,229,255,0.10)", "Visibilité"),
                    "brand":      ("#00E5FF", "rgba(0,229,255,0.08)", "Image de marque"),
                    "odds":       ("#F59E0B", "rgba(245,158,11,0.15)", "Cotes"),
                    "regulation": ("#00FFAA", "rgba(0,255,170,0.10)", "Régulation"),
                    "payment":    ("#7B4DFF", "rgba(123,77,255,0.10)", "Paiement"),
                }
                cc, cbg, clabel = cat_styles.get(row["category"], (T.T2, "#0D1117", row["category"]))
                rows.append(html.Tr([
                    html.Td(flag, style={"fontSize": 13}),
                    html.Td(html.Span(clabel, style={
                        "fontSize": 10, "fontWeight": 700, "padding": "3px 9px",
                        "borderRadius": 20, "background": cbg, "color": cc,
                        "textTransform": "uppercase", "letterSpacing": "0.5px"})),
                    html.Td(row["text"], style={"fontSize": 13}),
                    html.Td(html.Span(str(row["n_runs"]),
                                     style={"fontSize": 11, "fontWeight": 700,
                                            "color": "#00E5FF", "background": "rgba(0,229,255,0.10)",
                                            "padding": "2px 8px", "borderRadius": 20})
                            if row["n_runs"]
                            else html.Span("—", style={"color": T.T3})),
                ]))
        return card([
            html.Div(
                f"Prompt Library · {CLIENT_NAME} · {len(df_lib)} prompts · 4 marchés",
                style={"fontSize": 11, "fontWeight": 700, "textTransform": "uppercase",
                       "letterSpacing": "1.5px", "color": T.T3, "marginBottom": 16}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Marché"), html.Th("Catégorie"),
                    html.Th("Prompt"), html.Th("Runs"),
                ], style={"fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
                          "letterSpacing": "1px", "color": T.T3})),
                html.Tbody(rows),
            ], bordered=False, hover=True,
               style={"fontFamily": T.FONT_BODY}),
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

app.index_string = app.index_string.replace("</head>", T.DASH_CSS + "</head>")

# Footer moat
app.layout.children.append(
    html.Div([
        html.Span("✓ Prompt library verticale bet · données propriétaires · historique indépendant de votre agence"),
        html.Span([
            "Voxa GEO Intelligence · ",
            html.A("luc@sharper-media.com",
                   href="mailto:luc@sharper-media.com",
                   style={"color": "#00E5FF", "textDecoration": "none"}),
        ]),
    ], className="voxa-footer")
)

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8051)