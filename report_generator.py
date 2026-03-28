"""
Voxa — Générateur de rapport PDF v2.0
======================================
Génère un rapport GEO Score complet depuis les DB existantes.
Charte graphique Voxa 2026 : dark navy + cyan + violet.

Usage :
    python3 report_generator.py --slug psg
    python3 report_generator.py --slug betclic
    python3 report_generator.py --slug betclic --month 2026-03

Sortie : Voxa_Report_{NOM}_{MOIS}.pdf
"""

import os
import sys
import argparse
import sqlite3
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# ── ReportLab ────────────────────────────────────────────────
from reportlab.lib              import colors
from reportlab.lib.pagesizes    import A4
from reportlab.lib.styles       import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units        import mm, cm
from reportlab.lib.enums        import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus         import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, HRFlowable,
                                        PageBreak, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics         import renderPDF

# ── Voxa Palette ─────────────────────────────────────────────
NAVY   = colors.HexColor("#0A2540")
DARK   = colors.HexColor("#0D1117")
CARD   = colors.HexColor("#1A1F2E")
CYAN   = colors.HexColor("#00E5FF")
VIOLET = colors.HexColor("#7B4DFF")
NEON   = colors.HexColor("#00FFAA")
WHITE  = colors.HexColor("#F8F9FA")
GREY   = colors.HexColor("#A8B8C8")
GREY3  = colors.HexColor("#5A7A8A")
RED    = colors.HexColor("#FF4B6E")
BORDER = colors.HexColor("#1E2A3A")

def score_color(s):
    if s is None: return GREY3
    if s >= 70:   return NEON
    if s >= 45:   return CYAN
    return RED

# ── DB helpers ────────────────────────────────────────────────
CLIENTS = {
    "psg": {
        "db":      BASE_DIR / "voxa.db",
        "name":    "PSG",
        "full":    "Paris Saint-Germain",
        "primary": "OM",
        "vertical":"sport",
        "markets": ["fr", "en"],
    },
    "betclic": {
        "db":      BASE_DIR / "voxa_betclic.db",
        "name":    "Betclic",
        "full":    "Betclic",
        "primary": "Betclic",
        "vertical":"bet",
        "markets": ["fr", "pt", "fr-ci", "pl"],
    },
}

def get_data(slug: str, month: str = None):
    cfg = CLIENTS[slug]
    conn = sqlite3.connect(str(cfg["db"]))
    conn.row_factory = sqlite3.Row

    # Dernier run (ou run du mois spécifié)
    if month:
        run_date = conn.execute(
            "SELECT MAX(run_date) as d FROM runs WHERE run_date LIKE ?",
            (f"{month}%",)
        ).fetchone()["d"]
    else:
        run_date = conn.execute("SELECT MAX(run_date) as d FROM runs").fetchone()["d"]

    if not run_date:
        conn.close()
        return None

    primary = cfg["primary"]

    # GEO Score global
    score_row = conn.execute("""
        SELECT AVG(res.geo_score) as avg, COUNT(DISTINCT r.id) as n
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.run_date=?
    """, (run_date,)).fetchone()

    # Score par langue
    by_lang = conn.execute("""
        SELECT r.language, AVG(res.geo_score) as avg
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.run_date=?
        GROUP BY r.language ORDER BY avg DESC
    """, (run_date,)).fetchall()

    # Score par catégorie
    by_cat = conn.execute("""
        SELECT p.category, AVG(res.geo_score) as avg, COUNT(*) as n
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN prompts p ON r.prompt_id=p.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.run_date=?
        GROUP BY p.category ORDER BY avg ASC
    """, (run_date,)).fetchall()

    # NSS
    nss_rows = conn.execute("""
        SELECT res.sentiment, COUNT(*) as n
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.run_date=?
        GROUP BY res.sentiment
    """, (run_date,)).fetchall()
    nss_counts = {r["sentiment"]: r["n"] for r in nss_rows}
    total_nss = sum(nss_counts.values()) or 1
    nss = round((nss_counts.get("positive",0) - nss_counts.get("negative",0)) / total_nss * 100)

    # Concurrents
    competitors = conn.execute("""
        SELECT b.name, b.is_primary, AVG(res.geo_score) as avg
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN brands b ON res.brand_id=b.id
        WHERE r.run_date=?
        GROUP BY b.id ORDER BY avg DESC LIMIT 12
    """, (run_date,)).fetchall()

    # Prompts faibles (top 5)
    weak = conn.execute("""
        SELECT p.text, p.category, AVG(res.geo_score) as avg
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN prompts p ON r.prompt_id=p.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.run_date=?
        GROUP BY p.id HAVING avg < 60
        ORDER BY avg ASC LIMIT 5
    """, (run_date,)).fetchall()

    # Historique
    history = conn.execute("""
        SELECT run_date, AVG(res.geo_score) as avg
        FROM results res JOIN runs r ON res.run_id=r.id
        JOIN brands b ON res.brand_id=b.id
        WHERE b.is_primary=1
        GROUP BY r.run_date ORDER BY r.run_date DESC LIMIT 12
    """).fetchall()

    conn.close()
    return {
        "slug":        slug,
        "cfg":         cfg,
        "run_date":    run_date,
        "month":       month or run_date[:7],
        "score":       round(score_row["avg"]) if score_row["avg"] else 0,
        "n_prompts":   score_row["n"],
        "by_lang":     [dict(r) for r in by_lang],
        "by_cat":      [dict(r) for r in by_cat],
        "nss":         nss,
        "nss_counts":  nss_counts,
        "competitors": [dict(r) for r in competitors],
        "weak":        [dict(r) for r in weak],
        "history":     [dict(r) for r in reversed(history)],
    }

# ── PDF Builders ──────────────────────────────────────────────

def score_bar_drawing(score: int, width: float = 200, height: float = 16) -> Drawing:
    d = Drawing(width, height)
    # Background
    d.add(Rect(0, 4, width, 8, fillColor=BORDER, strokeColor=None))
    # Fill
    fill_w = min(width * score / 100, width)
    fill_col = score_color(score)
    d.add(Rect(0, 4, fill_w, 8, fillColor=fill_col, strokeColor=None))
    return d


def mini_bar(value: float, max_val: float, width: float, col) -> Drawing:
    d = Drawing(width, 10)
    d.add(Rect(0, 2, width, 6, fillColor=BORDER, strokeColor=None))
    w = min(width * value / max(max_val, 1), width)
    d.add(Rect(0, 2, w, 6, fillColor=col, strokeColor=None))
    return d


def generate_report(slug: str, month: str = None) -> str:
    data = get_data(slug, month)
    if not data:
        print(f"  ✗ Aucune donnée pour {slug}")
        return ""

    cfg  = data["cfg"]
    out  = BASE_DIR / f"Voxa_Report_{cfg['name']}_{data['month']}.pdf"

    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=16*mm, bottomMargin=16*mm,
    )

    styles = getSampleStyleSheet()
    s = {
        "h1":    ParagraphStyle("h1",    fontName="Helvetica-Bold",  fontSize=22, textColor=WHITE,   spaceAfter=4),
        "h2":    ParagraphStyle("h2",    fontName="Helvetica-Bold",  fontSize=14, textColor=CYAN,    spaceAfter=8, spaceBefore=16),
        "h3":    ParagraphStyle("h3",    fontName="Helvetica-Bold",  fontSize=11, textColor=WHITE,   spaceAfter=6),
        "body":  ParagraphStyle("body",  fontName="Helvetica",       fontSize=10, textColor=GREY,    spaceAfter=4, leading=14),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold",  fontSize=8,  textColor=GREY3,   spaceAfter=2, wordWrap="LTR"),
        "small": ParagraphStyle("small", fontName="Helvetica",       fontSize=8,  textColor=GREY3),
        "score": ParagraphStyle("score", fontName="Helvetica-Bold",  fontSize=48, textColor=score_color(data["score"]), alignment=TA_CENTER),
        "tag":   ParagraphStyle("tag",   fontName="Helvetica-Bold",  fontSize=9,  textColor=CYAN),
    }

    story = []
    W_pt  = A4[0] - 40*mm  # usable width

    # ── COVER ──────────────────────────────────────────────────
    # Header dark band
    header = Drawing(W_pt, 80)
    header.add(Rect(0, 0, W_pt, 80, fillColor=NAVY, strokeColor=None))
    # Gradient accent line
    header.add(Rect(0, 77, W_pt, 3, fillColor=CYAN, strokeColor=None))
    # Title
    header.add(String(16, 50, "VOXA", fontName="Helvetica-Bold", fontSize=24, fillColor=CYAN))
    header.add(String(16, 32, "GEO INTELLIGENCE", fontName="Helvetica-Bold", fontSize=9,
                     fillColor=colors.HexColor("#5A7A8A")))
    header.add(String(16, 14, f"Rapport mensuel · {cfg['full']} · {data['month']}",
                     fontName="Helvetica", fontSize=10, fillColor=GREY))
    # Date right
    header.add(String(W_pt - 100, 14, f"Généré le {date.today().strftime('%d/%m/%Y')}",
                     fontName="Helvetica", fontSize=9, fillColor=GREY3))
    story.append(header)
    story.append(Spacer(1, 8*mm))

    # ── KPI HERO ───────────────────────────────────────────────
    story.append(Paragraph("SCORE GEO GLOBAL", s["label"]))

    hero = Drawing(W_pt, 100)
    hero.add(Rect(0, 0, W_pt, 100, fillColor=CARD, strokeColor=BORDER, strokeWidth=1))

    # Score principal
    sc_col = score_color(data["score"])
    hero.add(String(W_pt/2 - 20, 48, str(data["score"]),
                   fontName="Helvetica-Bold", fontSize=52, fillColor=sc_col))
    hero.add(String(W_pt/2 + 34, 58, "/100",
                   fontName="Helvetica-Bold", fontSize=18, fillColor=GREY3))
    hero.add(String(W_pt/2 - 20, 28, cfg["primary"],
                   fontName="Helvetica-Bold", fontSize=12, fillColor=WHITE))
    hero.add(String(W_pt/2 - 20, 12, f"{data['n_prompts']} prompts · {data['run_date']}",
                   fontName="Helvetica", fontSize=9, fillColor=GREY3))

    # NSS
    nss_col = NEON if data["nss"] >= 0 else RED
    hero.add(String(W_pt - 120, 68, "NET SENTIMENT",
                   fontName="Helvetica-Bold", fontSize=8, fillColor=GREY3))
    hero.add(String(W_pt - 120, 50, f"{'+' if data['nss'] >= 0 else ''}{data['nss']}%",
                   fontName="Helvetica-Bold", fontSize=24, fillColor=nss_col))

    # Vertical badge
    vert_col = CYAN if cfg["vertical"] == "sport" else VIOLET
    hero.add(Rect(16, 70, 60, 18, fillColor=vert_col, strokeColor=None, rx=4))
    hero.add(String(22, 75, cfg["vertical"].upper(),
                   fontName="Helvetica-Bold", fontSize=9, fillColor=DARK))

    story.append(hero)
    story.append(Spacer(1, 6*mm))

    # ── SCORES PAR MARCHÉ ──────────────────────────────────────
    if data["by_lang"]:
        story.append(Paragraph("SCORES PAR MARCHÉ", s["h2"]))

        lang_labels = {"fr":"🇫🇷 France","en":"🇬🇧 Anglais","pt":"🇵🇹 Portugal",
                      "pl":"🇵🇱 Pologne","fr-ci":"🇨🇮 Côte d'Ivoire"}
        max_score = max(r["avg"] for r in data["by_lang"])

        tbl_data = [["Marché", "Score", "", "Positionnement"]]
        for r in data["by_lang"]:
            sc_v = round(r["avg"])
            label = lang_labels.get(r["language"], r["language"].upper())
            bar = mini_bar(r["avg"], 100, 120, score_color(sc_v))
            lbl = "Leader" if sc_v >= 70 else ("Compétitif" if sc_v >= 45 else "À améliorer")
            tbl_data.append([label, f"{sc_v}/100", bar, lbl])

        t = Table(tbl_data, colWidths=[80, 55, 130, 90])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),  NAVY),
            ("TEXTCOLOR",   (0,0), (-1,0),  GREY3),
            ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0),  8),
            ("BACKGROUND",  (0,1), (-1,-1), CARD),
            ("TEXTCOLOR",   (0,1), (-1,-1), WHITE),
            ("FONTNAME",    (0,1), (0,-1),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,1), (-1,-1), 10),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [CARD, colors.HexColor("#0F1520")]),
            ("GRID",        (0,0), (-1,-1), 0.5, BORDER),
            ("PADDING",     (0,0), (-1,-1), 8),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(KeepTogether([t, Spacer(1, 4*mm)]))

    # ── SCORES PAR CATÉGORIE ───────────────────────────────────
    if data["by_cat"]:
        story.append(Paragraph("SCORES PAR CATÉGORIE DE PROMPT", s["h2"]))

        cat_labels = {
            "discovery":     "Découverte",
            "comparison":    "Comparatif",
            "transactional": "Transactionnel",
            "reputation":    "Réputation",
            "brand":         "Marque",
            "odds":          "Cotes",
            "regulation":    "Régulation",
            "experience":    "Expérience",
        }
        tbl_data = [["Catégorie", "Score", "Barre", "Statut"]]
        for r in data["by_cat"]:
            sc_v = round(r["avg"])
            lbl  = cat_labels.get(r["category"], r["category"].title())
            bar  = mini_bar(r["avg"], 100, 120, score_color(sc_v))
            status = "✓ Fort" if sc_v >= 70 else ("~ Moyen" if sc_v >= 45 else "✗ Prioritaire")
            tbl_data.append([lbl, f"{sc_v}/100", bar, status])

        t = Table(tbl_data, colWidths=[100, 55, 130, 70])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),  NAVY),
            ("TEXTCOLOR",   (0,0), (-1,0),  GREY3),
            ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0),  8),
            ("BACKGROUND",  (0,1), (-1,-1), CARD),
            ("TEXTCOLOR",   (0,1), (-1,-1), WHITE),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [CARD, colors.HexColor("#0F1520")]),
            ("GRID",        (0,0), (-1,-1), 0.5, BORDER),
            ("PADDING",     (0,0), (-1,-1), 8),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(KeepTogether([t, Spacer(1, 4*mm)]))

    # ── BENCHMARK CONCURRENTS ──────────────────────────────────
    if data["competitors"]:
        story.append(Paragraph("BENCHMARK CONCURRENTS", s["h2"]))

        tbl_data = [["Marque", "GEO Score", "Barre"]]
        for c in data["competitors"]:
            sc_v = round(c["avg"])
            is_p = c["is_primary"]
            bar  = mini_bar(c["avg"], 100, 150, CYAN if is_p else VIOLET)
            tbl_data.append([
                c["name"] + (" ★" if is_p else ""),
                f"{sc_v}/100",
                bar,
            ])

        t = Table(tbl_data, colWidths=[120, 65, 170])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),  NAVY),
            ("TEXTCOLOR",   (0,0), (-1,0),  GREY3),
            ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0),  8),
            ("BACKGROUND",  (0,1), (-1,-1), CARD),
            ("TEXTCOLOR",   (0,1), (-1,-1), WHITE),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [CARD, colors.HexColor("#0F1520")]),
            ("FONTNAME",    (0,1), (0,-1),  "Helvetica-Bold"),
            ("GRID",        (0,0), (-1,-1), 0.5, BORDER),
            ("PADDING",     (0,0), (-1,-1), 8),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(KeepTogether([t, Spacer(1, 4*mm)]))

    # ── PROMPTS PRIORITAIRES ───────────────────────────────────
    if data["weak"]:
        story.append(PageBreak())
        story.append(Paragraph("OPPORTUNITÉS GEO — PROMPTS PRIORITAIRES", s["h2"]))
        story.append(Paragraph(
            "Ces prompts ont un score < 60/100. Ils représentent des opportunités d'optimisation "
            "directe via du contenu structuré (FAQ, Schema JSON-LD).",
            s["body"]
        ))
        story.append(Spacer(1, 4*mm))

        for i, w in enumerate(data["weak"], 1):
            sc_v = round(w["avg"])
            item = Drawing(W_pt, 50)
            item.add(Rect(0, 0, W_pt, 50, fillColor=CARD, strokeColor=BORDER, strokeWidth=1))
            item.add(Rect(0, 0, 4, 50, fillColor=RED, strokeColor=None))
            item.add(String(14, 32, f"{i}. {w['text'][:90]}",
                           fontName="Helvetica-Bold", fontSize=10, fillColor=WHITE))
            item.add(String(14, 16, f"Catégorie : {w['category']} · Score actuel : {sc_v}/100",
                           fontName="Helvetica", fontSize=9, fillColor=GREY3))
            item.add(String(W_pt - 80, 28, f"{sc_v}/100",
                           fontName="Helvetica-Bold", fontSize=18, fillColor=RED))
            story.append(item)
            story.append(Spacer(1, 3*mm))

    # ── RECOMMANDATIONS ────────────────────────────────────────
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("RECOMMANDATIONS ACTIONNABLES", s["h2"]))

    recos = [
        ("Schema FAQPage", "Ajoutez un bloc FAQ JSON-LD sur vos pages principales. Impact estimé : +10-20 pts sur les prompts découverte et réputation."),
        ("Contenu éditorial", "Créez 2-3 articles optimisés par mois avec les mots-clés identifiés dans les prompts faibles. Les LLMs citent les sources récentes en priorité."),
        ("Schema Organization", "Vérifiez et enrichissez votre balisage Schema Organization (nom, URL, sameAs, description). Base minimum pour toute visibilité IA."),
    ]
    if data["by_cat"]:
        worst = min(data["by_cat"], key=lambda x: x["avg"])
        cat_lbl = worst["category"].title()
        recos.insert(0, (f"Priorité : {cat_lbl}",
                        f"La catégorie {cat_lbl} ({round(worst['avg'])}/100) est votre point faible. "
                        f"Focus sur du contenu spécifique à ce type de requête."))

    for title, body_text in recos[:4]:
        item = Drawing(W_pt, 44)
        item.add(Rect(0, 0, W_pt, 44, fillColor=CARD, strokeColor=BORDER, strokeWidth=1))
        item.add(Rect(0, 0, 4, 44, fillColor=CYAN, strokeColor=None))
        item.add(String(14, 28, title, fontName="Helvetica-Bold", fontSize=11, fillColor=CYAN))
        item.add(String(14, 10, body_text[:100] + ("..." if len(body_text) > 100 else ""),
                       fontName="Helvetica", fontSize=9, fillColor=GREY))
        story.append(item)
        story.append(Spacer(1, 3*mm))

    # ── FOOTER ─────────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    footer = Drawing(W_pt, 24)
    footer.add(Line(0, 23, W_pt, 23, strokeColor=BORDER, strokeWidth=1))
    footer.add(String(0, 8, "Voxa GEO Intelligence · Sharper Media · luc@sharper-media.com",
                     fontName="Helvetica", fontSize=8, fillColor=GREY3))
    footer.add(String(W_pt - 160, 8, f"Confidentiel · {cfg['full']} · {data['month']}",
                     fontName="Helvetica", fontSize=8, fillColor=GREY3))
    story.append(footer)

    doc.build(story, onFirstPage=lambda c,d: None, onLaterPages=lambda c,d: None)
    print(f"  ✓ Rapport généré : {out}")
    return str(out)


# ── CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa — Rapport PDF v2.0")
    parser.add_argument("--slug",  required=True, choices=list(CLIENTS.keys()),
                        help="Client : psg ou betclic")
    parser.add_argument("--month", default=None,
                        help="Mois YYYY-MM (défaut = dernier run)")
    args = parser.parse_args()
    generate_report(args.slug, args.month)