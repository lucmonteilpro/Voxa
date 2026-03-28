"""
Voxa — Design System v1.0
==========================
Source unique de vérité pour tous les tokens de design.
Importé par : server.py, app_router.py, dashboard.py, dashboard_betclic.py

Usage :
    from theme import P, CSS_FLASK, FONTS_URL, LOGO_SVG, DASH_CSS
    from theme import score_color, BRAND_COLORS_PSG, BRAND_COLORS_BET
"""

# ─────────────────────────────────────────────────────────────
# PALETTE VOXA 2026
# ─────────────────────────────────────────────────────────────
# Dark mode · Neural · Gradient cyan → violet

P = {
    # Backgrounds
    "bg":   "#0D1117",   # Background principal (dark)
    "bg2":  "#121212",   # Cartes niveau 1
    "bg3":  "#1A1F2E",   # Cartes niveau 2 (plus claire)
    "navy": "#0A2540",   # Primary dark (headers, hero)

    # Accents IA
    "c1":   "#00E5FF",   # Cyan IA — accents, scores, liens actifs
    "c2":   "#7B4DFF",   # Violet — CTA, highlights
    "ng":   "#00FFAA",   # Neon vert — succès, scores élevés

    # Bordures
    "bd":   "#1E2A3A",   # Bordure standard
    "bd2":  "#2A3A4A",   # Bordure hover

    # Texte
    "w":    "#F8F9FA",   # Texte principal clair
    "t2":   "#A8B8C8",   # Texte secondaire
    "t3":   "#5A7A8A",   # Texte tertiaire / labels

    # Alertes
    "red":  "#FF4B6E",   # Erreur / score faible
    "red2": "#FF8FA0",   # Texte erreur (plus clair)

    # Gradients
    "grd":  "linear-gradient(135deg, #00E5FF, #7B4DFF)",
    "grd_r":"linear-gradient(135deg, #7B4DFF, #00E5FF)",
}

# Aliases courts pour les f-strings Python (usage interne server.py)
N   = P["navy"]
C1  = P["c1"]
C2  = P["c2"]
NG  = P["ng"]
BG  = P["bg"]
BG2 = P["bg2"]
BG3 = P["bg3"]
BD  = P["bd"]
BD2 = P["bd2"]
W   = P["w"]
T2  = P["t2"]
T3  = P["t3"]
RED = P["red"]
GRN = P["ng"]   # Succès = neon vert
GRD = P["grd"]


# ─────────────────────────────────────────────────────────────
# TYPOGRAPHIE
# ─────────────────────────────────────────────────────────────

FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)

FONT_BODY = "Inter, system-ui, sans-serif"
FONT_MONO = "'JetBrains Mono', monospace"


# ─────────────────────────────────────────────────────────────
# LOGO SVG (V neural wireframe)
# ─────────────────────────────────────────────────────────────

LOGO_SVG = f"""<svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="vg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{C1}"/>
      <stop offset="100%" stop-color="{C2}"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="1.5" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <g filter="url(#glow)">
    <path d="M4 4 L14 22 L24 4" stroke="url(#vg)" stroke-width="2.5" fill="none" opacity="0.5"/>
    <path d="M4 4 L14 22 L24 4" stroke="url(#vg)" stroke-width="2" fill="none"/>
    <circle cx="4"  cy="4"  r="2.5" fill="{C1}" opacity="0.9"/>
    <circle cx="14" cy="22" r="3"   fill="url(#vg)"/>
    <circle cx="24" cy="4"  r="2.5" fill="{C2}" opacity="0.9"/>
    <circle cx="9"  cy="13" r="1.8" fill="{C1}" opacity="0.6"/>
    <circle cx="19" cy="13" r="1.8" fill="{C2}" opacity="0.6"/>
    <line x1="9"  y1="13" x2="19" y2="13" stroke="url(#vg)" stroke-width="0.8" opacity="0.4"/>
    <line x1="4"  y1="4"  x2="9"  y2="13" stroke="url(#vg)" stroke-width="0.8" opacity="0.4"/>
    <line x1="19" y1="13" x2="24" y2="4"  stroke="url(#vg)" stroke-width="0.8" opacity="0.4"/>
  </g>
</svg>"""

LOGO_ICON_DASH = {
    "width": 32, "height": 32,
    "background": GRD,
    "borderRadius": 8,
    "display": "flex", "alignItems": "center", "justifyContent": "center",
    "fontSize": 15, "fontWeight": 900,
    "color": BG, "flexShrink": 0,
    "boxShadow": f"0 0 12px rgba(0,229,255,0.4)",
}

LOGO_TEXT_STYLE = {
    "fontWeight": 800, "fontSize": 18, "letterSpacing": "-0.5px",
    "background": GRD,
    "WebkitBackgroundClip": "text",
    "WebkitTextFillColor": "transparent",
}

LOGO_TAG_STYLE = {
    "fontSize": 8, "fontWeight": 700, "letterSpacing": "2px",
    "textTransform": "uppercase", "padding": "3px 9px",
    "borderRadius": 20,
    "background": f"rgba(0,229,255,0.1)",
    "color": C1,
    "border": f"1px solid rgba(0,229,255,0.2)",
}


# ─────────────────────────────────────────────────────────────
# CSS FLASK PAGES (server.py — /demo, /login, /settings...)
# ─────────────────────────────────────────────────────────────

CSS_FLASK = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{FONTS_URL}" rel="stylesheet">
<style>
:root{{
  --c1:{C1};--c2:{C2};--ng:{NG};
  --bg:{BG};--bg2:{BG2};--bg3:{BG3};--navy:{N};
  --bd:{BD};--bd2:{BD2};
  --w:{W};--t2:{T2};--t3:{T3};
  --red:{RED};
  --grd:{GRD};
  --shadow:0 4px 24px rgba(0,229,255,0.06);
  --font:'{FONT_BODY}';
  --mono:{FONT_MONO};
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--w);font-family:var(--font);min-height:100vh}}
a{{text-decoration:none;color:inherit}}

/* ── TOPBAR ── */
.tb{{
  height:56px;background:rgba(13,17,23,.95);border-bottom:1px solid var(--bd);
  backdrop-filter:blur(12px);display:flex;align-items:center;
  justify-content:space-between;padding:0 28px;
  position:sticky;top:0;z-index:100;
}}
.logo{{display:flex;align-items:center;gap:10px}}
.logo-text{{
  font-size:18px;font-weight:800;letter-spacing:-.5px;
  background:var(--grd);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text;
}}
.logo-tag{{
  font-size:8px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  padding:3px 8px;border-radius:20px;
  background:rgba(0,229,255,.1);color:var(--c1);
  border:1px solid rgba(0,229,255,.2);
}}

/* ── BOUTONS ── */
.btn{{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  padding:9px 18px;border-radius:8px;font-size:13px;font-weight:600;
  cursor:pointer;border:none;transition:all .2s;text-decoration:none;font-family:var(--font);
}}
.btn:hover{{transform:translateY(-1px);opacity:.9}}
.bp{{background:var(--grd);color:var(--bg);}}
.bg2{{background:var(--grd);color:var(--bg);}}
.bo{{background:transparent;color:var(--c1);border:1px solid rgba(0,229,255,.3);width:auto;padding:7px 14px;}}
.bo:hover{{background:rgba(0,229,255,.08);}}
.bsm{{padding:6px 12px;font-size:12px;}}
.blg{{padding:12px 24px;font-size:14px;}}

/* ── CARTES ── */
.card{{background:var(--bg3);border:1px solid var(--bd);border-radius:12px;box-shadow:var(--shadow);padding:24px;}}
.card-glow{{border-color:rgba(0,229,255,.2);box-shadow:0 0 0 1px rgba(0,229,255,.1);}}

/* ── TYPOGRAPHIE ── */
.h1{{font-size:26px;font-weight:800;letter-spacing:-.5px;color:var(--w);margin-bottom:6px;}}
.h2{{font-size:19px;font-weight:700;color:var(--w);}}
.h3{{font-size:15px;font-weight:700;color:var(--w);}}
.lbl{{font-size:10px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;color:var(--t3);}}
.gradient-text{{
  background:var(--grd);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text;font-weight:800;
}}

/* ── FORMULAIRES ── */
.fi{{
  width:100%;padding:10px 14px;background:rgba(255,255,255,.04);
  border:1px solid var(--bd2);border-radius:8px;font-size:14px;
  color:var(--w);outline:none;font-family:var(--font);margin-bottom:12px;
  transition:border-color .2s;
}}
.fi:focus{{border-color:var(--c1);background:rgba(0,229,255,.04);}}
.fi::placeholder{{color:var(--t3);}}
.fs{{
  width:100%;padding:10px 14px;background:rgba(255,255,255,.04);
  border:1px solid var(--bd2);border-radius:8px;font-size:14px;
  color:var(--w);font-family:var(--font);outline:none;margin-bottom:12px;
}}

/* ── ALERTES ── */
.ae{{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px;border-left:3px solid;}}
.ae.err{{background:rgba(255,75,110,.1);color:{RED};border-color:{RED};}}
.ae.ok {{background:rgba(0,255,170,.08);color:{NG};border-color:{NG};}}
.ae.inf{{background:rgba(0,229,255,.08);color:{C1};border-color:{C1};}}

/* ── KPI CARDS ── */
.kc{{background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:18px;text-align:center;transition:border-color .2s;}}
.kc:hover{{border-color:var(--bd2);}}
.kv{{font-size:32px;font-weight:800;line-height:1;margin-bottom:4px;}}
.kl{{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--t3);}}

/* ── MISC ── */
.dv{{border:none;border-top:1px solid var(--bd);margin:16px 0;}}
.tag{{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700;}}
.ts {{background:rgba(0,229,255,.12);color:{C1};border:1px solid rgba(0,229,255,.2);}}
.tb2{{background:rgba(123,77,255,.12);color:#A07EFF;border:1px solid rgba(123,77,255,.2);}}
.tp {{background:rgba(0,255,170,.1);color:{NG};border:1px solid rgba(0,255,170,.2);}}
.g2 {{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
.g4 {{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}}
.sbar{{height:6px;background:rgba(255,255,255,.08);border-radius:4px;overflow:hidden;}}
.sbari{{height:100%;border-radius:4px;background:var(--grd);}}
code{{font-family:var(--mono);background:rgba(0,229,255,.06);padding:2px 6px;border-radius:4px;font-size:12px;color:var(--c1);}}
::-webkit-scrollbar{{width:6px;}}
::-webkit-scrollbar-track{{background:var(--bg);}}
::-webkit-scrollbar-thumb{{background:var(--bd2);border-radius:3px;}}
@media(max-width:600px){{.g2,.g4{{grid-template-columns:1fr 1fr;}}}}
</style>"""


# ─────────────────────────────────────────────────────────────
# CSS DASHBOARDS DASH (injecté via app.index_string)
# ─────────────────────────────────────────────────────────────

DASH_CSS = f"""<link href="{FONTS_URL}" rel="stylesheet">
<style>
:root{{--c1:{C1};--c2:{C2};--ng:{NG};--bg:{BG};--bg3:{BG3};--bd:{BD};--w:{W};--t2:{T2};--t3:{T3};}}
html,body{{background:{BG}!important;color:{W}!important;font-family:{FONT_BODY}!important;}}
.card-title-voxa{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:{T3};margin-bottom:16px;}}
.nav-tabs .nav-link{{color:{T3}!important;border:none!important;border-bottom:2px solid transparent!important;font-family:{FONT_BODY};}}
.nav-tabs .nav-link.active{{color:{C1}!important;border-bottom:2px solid {C1}!important;background:transparent!important;}}
.nav-tabs{{border-bottom:1px solid {BD}!important;}}
.Select-control{{font-family:{FONT_BODY}!important;background:{BG3}!important;color:{W}!important;border-color:{BD}!important;}}
.Select-menu-outer{{background:{BG3}!important;border-color:{BD}!important;}}
.Select-option{{background:{BG3}!important;color:{W}!important;}}
.Select-option:hover,.Select-option.is-focused{{background:{BD}!important;}}
.Select-value-label{{color:{W}!important;}}
table{{color:{W}!important;}}
th{{color:{T3}!important;border-bottom:1px solid {BD}!important;background:{BG}!important;}}
td{{border-color:{BD}!important;}}
tr:hover td{{background:rgba(0,229,255,0.03)!important;}}
.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td{{
  background:{BG3}!important;color:{W}!important;border-color:{BD}!important;
}}
.voxa-footer{{
  background:rgba(0,229,255,0.03);border-top:1px solid {BD};
  padding:12px 32px;font-size:11px;color:{T3};
  display:flex;justify-content:space-between;align-items:center;
  font-family:{FONT_BODY};
}}
.voxa-footer a{{color:{C1};text-decoration:none;}}
::-webkit-scrollbar{{width:6px;}}
::-webkit-scrollbar-track{{background:{BG};}}
::-webkit-scrollbar-thumb{{background:{BD2};border-radius:3px;}}
</style>"""


# ─────────────────────────────────────────────────────────────
# COULEURS MARQUES (dashboards)
# ─────────────────────────────────────────────────────────────

BRAND_COLORS_PSG = {
    "OM":           "#009EE0",
    "PSG":          "#004170",
    "OL":           "#FFFFFF",
    "AS Monaco":    "#DC052D",
    "Stade Rennais":"#DA291C",
    "RC Lens":      "#FEBE10",
    "LOSC":         "#C8102E",
    "OGC Nice":     "#C20000",
    "Montpellier":  "#FB090B",
    "Stade Brestois":"#E32221",
    "Real Madrid":  "#FEBE10",
    "Barcelona":    "#A50044",
    "Bayern Munich":"#DC052D",
    "Man City":     "#6CABDD",
    "Arsenal":      "#EF0107",
    "Liverpool":    "#C8102E",
}

BRAND_COLORS_BET = {
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


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def score_color(score) -> str:
    """Retourne la couleur hex correspondant au score GEO."""
    if score is None: return T3
    if score >= 70:   return NG    # Neon vert — excellent
    if score >= 45:   return C1    # Cyan — moyen
    return RED                     # Rouge — faible


def score_label(score) -> str:
    """Retourne le label texte correspondant au score GEO."""
    if score is None: return "—"
    if score >= 70:   return "Excellent"
    if score >= 45:   return "Moyen"
    return "Faible"


def vertical_color(vertical: str) -> str:
    """Couleur d'accent par verticale."""
    return {
        "sport":    C1,
        "bet":      "#E63946",
        "politics": C2,
    }.get(vertical, C1)


# ─────────────────────────────────────────────────────────────
# STYLES DASH RÉUTILISABLES
# ─────────────────────────────────────────────────────────────

def card_style(extra: dict = None) -> dict:
    base = {
        "background": BG3, "border": f"1px solid {BD}",
        "borderRadius": 12, "padding": 24,
        "boxShadow": "0 4px 24px rgba(0,229,255,0.06)",
    }
    if extra:
        base.update(extra)
    return base


def card_title_style() -> dict:
    return {
        "fontSize": 10, "fontWeight": 700, "textTransform": "uppercase",
        "letterSpacing": "2px", "color": T3, "marginBottom": 14,
        "fontFamily": FONT_BODY,
    }


def kpi_value_style(color: str = None) -> dict:
    return {
        "fontSize": 32, "fontWeight": 800, "lineHeight": 1,
        "color": color or C1, "marginBottom": 4,
        "fontFamily": FONT_BODY,
    }


def badge_style(color: str = C1, bg_opacity: float = 0.12) -> dict:
    """Badge tag générique."""
    import re
    hex_to_rgb = lambda h: tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0,2,4))
    try:
        r, g, b = hex_to_rgb(color)
        bg = f"rgba({r},{g},{b},{bg_opacity})"
        border = f"rgba({r},{g},{b},0.2)"
    except Exception:
        bg = "rgba(0,229,255,0.12)"; border = "rgba(0,229,255,0.2)"
    return {
        "display": "inline-block", "padding": "3px 9px",
        "borderRadius": 20, "fontSize": 11, "fontWeight": 700,
        "background": bg, "color": color,
        "border": f"1px solid {border}",
    }


if __name__ == "__main__":
    print("=== Voxa Design System ===")
    print(f"Couleurs principales : bg={BG}, c1={C1}, c2={C2}, ng={NG}")
    print(f"Fonts : {FONTS_URL[:60]}...")
    print(f"Score 80 → {score_color(80)} ({score_label(80)})")
    print(f"Score 50 → {score_color(50)} ({score_label(50)})")
    print(f"Score 30 → {score_color(30)} ({score_label(30)})")
    print(f"BRAND_COLORS_BET : {len(BRAND_COLORS_BET)} marques")
    print(f"BRAND_COLORS_PSG : {len(BRAND_COLORS_PSG)} marques")
    print("OK — theme.py prêt")