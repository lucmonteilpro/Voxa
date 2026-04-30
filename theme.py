"""
Voxa — Design System v2.0 (LIGHT MODE)
========================================
Source unique de vérité pour tous les tokens de design.
Importé par : server.py, app_router.py, dashboard_generic.py

Changements v1 → v2 :
- Bascule complète en light mode (fini le dark)
- Nouvelle palette : fond #F7F8FA, cards blanches, accents cyan/violet conservés
- Cyan principal assombri : #00E5FF → #00B8D4 (lisible sur blanc)
- Texte principal #F8F9FA → #0D1117 (inversion)
- Bordures très claires #E5E8EC
- Nouveaux composants : make_sidebar(), make_kpi_card(), make_filter_bar()

API conservée à 100% — tous les anciens noms (P, C1, C2, BG, BG3,
make_topbar, score_color...) fonctionnent. dashboard_generic.py et
server.py n'ont besoin d'aucune modification pour tourner.

Usage :
    from theme import P, CSS_FLASK, FONTS_URL, LOGO_SVG, DASH_CSS
    from theme import score_color, BRAND_COLORS_PSG, BRAND_COLORS_BET
    from theme import make_topbar, make_sidebar, make_kpi_card, make_filter_bar
"""

# ─────────────────────────────────────────────────────────────
# PALETTE VOXA V2 — LIGHT MODE
# ─────────────────────────────────────────────────────────────
P = {
    # Backgrounds
    "bg":        "#F7F8FA",  # Background principal (page)
    "bg2":       "#F1F2F4",  # Hover rows, items secondaires
    "bg3":       "#FFFFFF",  # Cartes
    "bg_accent": "#E0F4F7",  # Background icône cyan (10% c1)
    "bg_accent2":"#EFE9FF",  # Background icône violet (10% c2)
    "bg_warn":   "#FEF3C7",  # Background icône warning
    "bg_ok":     "#DCFCE7",  # Background icône succès
    "bg_err":    "#FEE2E2",  # Background icône erreur

    # Navy (anciennement bg dark) → maintenant utilisé pour texte fort si besoin
    "navy":      "#0D1117",

    # Accents IA
    "c1":  "#00B8D4",  # Cyan IA — accents, scores, liens actifs (assombri pour light)
    "c2":  "#7B4DFF",  # Violet — CTA, highlights (inchangé, marche bien sur blanc)
    "ng":  "#10B981",  # Vert succès (plus naturel que le neon précédent)

    # Bordures
    "bd":  "#E5E8EC",  # Bordure standard (très claire)
    "bd2": "#D1D5DB",  # Bordure hover / secondaire

    # Texte
    "w":   "#0D1117",  # Texte principal (light mode = foncé)
    "t2":  "#4B5563",  # Texte secondaire
    "t3":  "#9CA3AF",  # Texte tertiaire / labels

    # Alertes
    "red":  "#EF4444",  # Erreur / score faible
    "red2": "#991B1B",  # Texte erreur (plus foncé pour contraste sur bg_err)
    "warn": "#F59E0B",  # Warning

    # Gradients (identité Voxa — usage parcimonieux : logo, CTA principal)
    "grd":   "linear-gradient(135deg, #00B8D4, #7B4DFF)",
    "grd_r": "linear-gradient(135deg, #7B4DFF, #00B8D4)",
}

# Aliases courts pour les f-strings Python (rétrocompatibilité v1)
N    = P["navy"]
C1   = P["c1"]
C2   = P["c2"]
NG   = P["ng"]
BG   = P["bg"]
BG2  = P["bg2"]
BG3  = P["bg3"]
BD   = P["bd"]
BD2  = P["bd2"]
W    = P["w"]
T2   = P["t2"]
T3   = P["t3"]
RED  = P["red"]
GRN  = P["ng"]
GRD  = P["grd"]

# Nouveaux aliases v2
BG_ACCENT  = P["bg_accent"]
BG_ACCENT2 = P["bg_accent2"]
BG_WARN    = P["bg_warn"]
BG_OK      = P["bg_ok"]
BG_ERR     = P["bg_err"]
WARN       = P["warn"]
RED2       = P["red2"]

# ─────────────────────────────────────────────────────────────
# TYPOGRAPHIE (inchangé)
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
# LOGO SVG (V neural wireframe — adapté light mode, glow retiré)
# ─────────────────────────────────────────────────────────────
LOGO_SVG = f"""<svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="vg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="{C1}"/>
            <stop offset="100%" stop-color="{C2}"/>
        </linearGradient>
    </defs>
    <path d="M4 4 L14 22 L24 4" stroke="url(#vg)" stroke-width="2" fill="none"/>
    <circle cx="4" cy="4" r="2.5" fill="{C1}"/>
    <circle cx="14" cy="22" r="3" fill="url(#vg)"/>
    <circle cx="24" cy="4" r="2.5" fill="{C2}"/>
    <circle cx="9" cy="13" r="1.5" fill="{C1}" opacity="0.7"/>
    <circle cx="19" cy="13" r="1.5" fill="{C2}" opacity="0.7"/>
    <line x1="9" y1="13" x2="19" y2="13" stroke="url(#vg)" stroke-width="0.8" opacity="0.5"/>
    <line x1="4" y1="4" x2="9" y2="13" stroke="url(#vg)" stroke-width="0.8" opacity="0.5"/>
    <line x1="19" y1="13" x2="24" y2="4" stroke="url(#vg)" stroke-width="0.8" opacity="0.5"/>
</svg>"""

LOGO_ICON_DASH = {
    "width": 32, "height": 32,
    "background": GRD,
    "borderRadius": 8,
    "display": "flex", "alignItems": "center", "justifyContent": "center",
    "fontSize": 15, "fontWeight": 800,
    "color": "#FFFFFF", "flexShrink": 0,
}

LOGO_TEXT_STYLE = {
    "fontWeight": 700, "fontSize": 18, "letterSpacing": "-0.5px",
    "color": W,
}

LOGO_TAG_STYLE = {
    "fontSize": 9, "fontWeight": 600, "letterSpacing": "1.5px",
    "textTransform": "uppercase", "padding": "3px 8px",
    "borderRadius": 12,
    "background": BG_ACCENT,
    "color": "#006B7A",
    "border": "none",
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
  --bg-accent:{BG_ACCENT};--bg-accent2:{BG_ACCENT2};
  --bd:{BD};--bd2:{BD2};
  --w:{W};--t2:{T2};--t3:{T3};
  --red:{RED};--warn:{WARN};
  --grd:{GRD};
  --shadow:0 1px 2px rgba(13,17,23,0.04), 0 4px 12px rgba(13,17,23,0.04);
  --font:'{FONT_BODY}';
  --mono:{FONT_MONO};
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--w);font-family:var(--font);min-height:100vh;-webkit-font-smoothing:antialiased}}
a{{text-decoration:none;color:inherit}}

/* ── TOPBAR ── */
.tb{{
  height:56px;background:rgba(255,255,255,0.95);border-bottom:0.5px solid var(--bd);
  backdrop-filter:blur(12px);display:flex;align-items:center;
  justify-content:space-between;padding:0 28px;
  position:sticky;top:0;z-index:100;
}}
.logo{{display:flex;align-items:center;gap:10px}}
.logo-text{{
  font-size:18px;font-weight:700;letter-spacing:-.5px;color:var(--w);
}}
.logo-tag{{
  font-size:9px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;
  padding:3px 8px;border-radius:12px;
  background:var(--bg-accent);color:#006B7A;
}}

/* ── BOUTONS ── */
.btn{{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  padding:9px 18px;border-radius:8px;font-size:13px;font-weight:600;
  cursor:pointer;border:none;transition:all .15s;text-decoration:none;font-family:var(--font);
}}
.btn:hover{{transform:translateY(-1px);}}
.bp{{background:var(--grd);color:#FFFFFF;box-shadow:0 2px 8px rgba(0,184,212,0.25);}}
.bp:hover{{box-shadow:0 4px 12px rgba(0,184,212,0.35);}}
.bg2btn{{background:var(--c1);color:#FFFFFF;}}
.bo{{background:transparent;color:var(--c1);border:1px solid var(--c1);width:auto;padding:7px 14px;}}
.bo:hover{{background:var(--bg-accent);}}
.bsm{{padding:6px 12px;font-size:12px;}}
.blg{{padding:12px 24px;font-size:14px;}}

/* ── CARTES ── */
.card{{background:var(--bg3);border:0.5px solid var(--bd);border-radius:12px;box-shadow:var(--shadow);padding:24px;}}
.card-glow{{border-color:var(--c1);box-shadow:0 0 0 1px rgba(0,184,212,0.15);}}

/* ── TYPOGRAPHIE ── */
.h1{{font-size:26px;font-weight:700;letter-spacing:-.5px;color:var(--w);margin-bottom:6px;}}
.h2{{font-size:19px;font-weight:600;color:var(--w);}}
.h3{{font-size:15px;font-weight:600;color:var(--w);}}
.lbl{{font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--t3);}}
.gradient-text{{
  background:var(--grd);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text;font-weight:700;
}}

/* ── FORMULAIRES ── */
.fi{{
  width:100%;padding:10px 14px;background:var(--bg3);
  border:0.5px solid var(--bd);border-radius:8px;font-size:14px;
  color:var(--w);outline:none;font-family:var(--font);margin-bottom:12px;
  transition:border-color .15s, box-shadow .15s;
}}
.fi:focus{{border-color:var(--c1);box-shadow:0 0 0 3px rgba(0,184,212,0.15);}}
.fi::placeholder{{color:var(--t3);}}
.fs{{
  width:100%;padding:10px 14px;background:var(--bg3);
  border:0.5px solid var(--bd);border-radius:8px;font-size:14px;
  color:var(--w);font-family:var(--font);outline:none;margin-bottom:12px;
}}

/* ── ALERTES ── */
.ae{{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px;border-left:3px solid;}}
.ae.err{{background:{BG_ERR};color:{RED2};border-color:{RED};}}
.ae.ok {{background:{BG_OK};color:#065F46;border-color:{NG};}}
.ae.inf{{background:{BG_ACCENT};color:#006B7A;border-color:{C1};}}
.ae.warn{{background:{BG_WARN};color:#92400E;border-color:{WARN};}}

/* ── KPI CARDS ── */
.kc{{background:var(--bg3);border:0.5px solid var(--bd);border-radius:8px;padding:14px;text-align:left;transition:border-color .15s;}}
.kc:hover{{border-color:var(--bd2);}}
.kv{{font-size:24px;font-weight:600;line-height:1;margin-bottom:4px;color:var(--w);}}
.kl{{font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--t3);}}

/* ── MISC ── */
.dv{{border:none;border-top:0.5px solid var(--bd);margin:16px 0;}}
.tag{{display:inline-block;padding:3px 9px;border-radius:12px;font-size:11px;font-weight:600;}}
.ts {{background:{BG_ACCENT};color:#006B7A;}}
.tb2{{background:{BG_ACCENT2};color:#5A2EBF;}}
.tp {{background:{BG_OK};color:#065F46;}}
.terr{{background:{BG_ERR};color:{RED2};}}

.g2 {{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
.g4 {{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}}

.sbar{{height:6px;background:var(--bg2);border-radius:4px;overflow:hidden;}}
.sbari{{height:100%;border-radius:4px;background:var(--grd);}}

code{{font-family:var(--mono);background:var(--bg-accent);padding:2px 6px;border-radius:4px;font-size:12px;color:#006B7A;}}

::-webkit-scrollbar{{width:8px;height:8px;}}
::-webkit-scrollbar-track{{background:var(--bg);}}
::-webkit-scrollbar-thumb{{background:var(--bd);border-radius:4px;}}
::-webkit-scrollbar-thumb:hover{{background:var(--bd2);}}

@media(max-width:600px){{.g2,.g4{{grid-template-columns:1fr 1fr;}}}}
</style>"""

# ─────────────────────────────────────────────────────────────
# CSS DASHBOARDS DASH (light mode complet, override Bootstrap)
# ─────────────────────────────────────────────────────────────
DASH_CSS = f"""<link href="{FONTS_URL}" rel="stylesheet">
<style>

/* ── BOOTSTRAP 5 OVERRIDE — LIGHT MODE ────────────────────── */
:root {{
  --vx-c1:{C1}; --vx-c2:{C2}; --vx-ng:{NG};
  --vx-bg:{BG}; --vx-bg2:{BG2}; --vx-bg3:{BG3};
  --vx-bd:{BD}; --vx-bd2:{BD2};
  --vx-w:{W}; --vx-t2:{T2}; --vx-t3:{T3};
  --vx-red:{RED}; --vx-warn:{WARN};
  --vx-bg-accent:{BG_ACCENT}; --vx-bg-accent2:{BG_ACCENT2};
  --vx-bg-ok:{BG_OK}; --vx-bg-err:{BG_ERR}; --vx-bg-warn:{BG_WARN};

  --bs-body-bg:{BG}; --bs-body-color:{W};
  --bs-card-bg:{BG3}; --bs-card-border-color:{BD}; --bs-card-color:{W};
  --bs-border-color:{BD};
  --bs-table-bg:{BG3}; --bs-table-color:{W}; --bs-table-border-color:{BD};
  --bs-table-hover-bg:{BG2}; --bs-table-striped-bg:{BG2};
  --bs-input-bg:{BG3}; --bs-input-color:{W}; --bs-input-border-color:{BD};
  --bs-link-color:{C1}; --bs-link-hover-color:#006B7A;
  --bs-nav-link-color:{T2}; --bs-nav-tabs-border-color:{BD};
  --bs-dropdown-bg:{BG3}; --bs-dropdown-border-color:{BD}; --bs-dropdown-color:{W};
  --bs-secondary-bg:{BG2}; --bs-tertiary-bg:{BG};
  --bs-emphasis-color:{W}; --bs-secondary-color:{T2}; --bs-tertiary-color:{T3};
  --bs-modal-bg:{BG3}; --bs-modal-border-color:{BD};
  --bs-accordion-bg:{BG3}; --bs-accordion-border-color:{BD}; --bs-accordion-color:{W};
  --bs-list-group-bg:{BG3}; --bs-list-group-border-color:{BD}; --bs-list-group-color:{W};
}}

/* ── BASE ── */
html, body {{
  background:{BG}!important; color:{W}!important;
  font-family:{FONT_BODY}!important; -webkit-font-smoothing:antialiased;
}}
#react-entry-point, ._dash-loading {{ background:{BG}!important; }}

/* ── CARDS ── */
.card {{
  background:{BG3}!important; border:0.5px solid {BD}!important;
  border-radius:8px!important;
  box-shadow:0 1px 2px rgba(13,17,23,0.04), 0 4px 12px rgba(13,17,23,0.04)!important;
}}
.card-body, .card-header, .card-footer {{ background:transparent!important; color:{W}!important; border-color:{BD}!important; }}

/* ── CONTAINERS ── */
.container, .container-fluid, .row {{ background:transparent!important; }}

/* ── TABS (utilisé en transition, mais sera remplacé par sidebar) ── */
.nav-tabs {{ border-bottom:0.5px solid {BD}!important; background:transparent!important; }}
.nav-tabs .nav-link {{
  color:{T2}!important; border:none!important;
  border-bottom:2px solid transparent!important; background:transparent!important;
  font-family:{FONT_BODY}!important; font-weight:500;
  transition:color 0.15s, border-color 0.15s;
}}
.nav-tabs .nav-link:hover {{ color:{W}!important; }}
.nav-tabs .nav-link.active {{
  color:{C1}!important; border-bottom:2px solid {C1}!important; background:transparent!important;
}}

/* ── FORMS ── */
.form-control, .form-select {{
  background:{BG3}!important; border:0.5px solid {BD}!important; color:{W}!important;
  border-radius:8px!important;
}}
.form-control:focus, .form-select:focus {{
  background:{BG3}!important; border-color:{C1}!important;
  box-shadow:0 0 0 3px rgba(0,184,212,0.15)!important; color:{W}!important;
}}
.form-control::placeholder {{ color:{T3}!important; opacity:1; }}
.form-check-label {{ color:{T2}!important; }}
.form-check-input:checked {{ background-color:{C1}!important; border-color:{C1}!important; }}

/* ── SELECT (react-select v1 Dash) ── */
.Select-control {{
  background:{BG3}!important; border:0.5px solid {BD}!important; color:{W}!important;
  font-family:{FONT_BODY}!important; border-radius:8px!important;
}}
.Select-placeholder, .Select-value-label {{ color:{T2}!important; }}
.Select-input>input {{ color:{W}!important; background:transparent!important; }}
.Select-arrow {{ border-top-color:{T3}!important; }}
.Select-menu-outer {{
  background:{BG3}!important; border:0.5px solid {BD}!important;
  box-shadow:0 8px 24px rgba(13,17,23,0.1)!important; z-index:9999;
}}
.Select-option {{ background:{BG3}!important; color:{W}!important; }}
.Select-option:hover, .Select-option.is-focused {{ background:{BG_ACCENT}!important; color:#006B7A!important; }}
.Select-option.is-selected {{ background:{BG_ACCENT}!important; color:#006B7A!important; font-weight:600; }}
.is-open>.Select-control {{ border-color:{C1}!important; }}

/* ── TABLES ── */
.table {{ color:{W}!important; border-color:{BD}!important; }}
.table th {{
  color:{T3}!important; font-size:10px; font-weight:600; letter-spacing:1.5px;
  text-transform:uppercase; background:{BG}!important;
  border-bottom:0.5px solid {BD}!important; padding:10px 14px;
}}
.table td {{ border-color:{BD}!important; padding:10px 14px; vertical-align:middle; color:{W}; }}
.table tbody tr:hover {{ background:{BG2}!important; }}
.table > :not(caption) > * > * {{ background-color:transparent!important; }}
.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td {{
  background:{BG3}!important; color:{W}!important; border-color:{BD}!important;
}}
.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th {{
  background:{BG}!important; color:{T3}!important; border-color:{BD}!important;
}}

/* ── PLOTLY ── */
.js-plotly-plot .plotly .bg, .plotly-graph-div {{ background:transparent!important; }}
.modebar {{ background:transparent!important; }}
.modebar-btn path {{ fill:{T3}!important; }}

/* ── BADGE/CARD TITLE ── */
.card-title-voxa {{
  font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:1.5px;
  color:{T3}; margin-bottom:14px; font-family:{FONT_BODY};
}}

/* ── FOOTER ── */
.voxa-footer {{
  background:{BG3}; border-top:0.5px solid {BD}; padding:12px 32px;
  font-size:11px; color:{T3}; display:flex; justify-content:space-between;
  align-items:center; font-family:{FONT_BODY};
}}
.voxa-footer a {{ color:{C1}; text-decoration:none; }}

/* ── SCROLLBAR ── */
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:{BG}; }}
::-webkit-scrollbar-thumb {{ background:{BD}; border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:{BD2}; }}

/* ── RADIO BUTTONS & CHECKBOXES ───────────────────────────── */
input[type="radio"] {{
  accent-color: {C1} !important;
  width: 15px; height: 15px; cursor: pointer;
}}
input[type="checkbox"] {{
  accent-color: {C1} !important;
}}
.form-check-input[type="radio"] {{
  background-color: {BG3} !important;
  border: 2px solid {BD2} !important;
}}
.form-check-input[type="radio"]:checked {{
  background-color: {C1} !important;
  border-color: {C1} !important;
}}
.form-check-label {{ color: {T2} !important; font-family: {FONT_BODY} !important; }}

/* ── BUTTONS dark (renommé "secondary" en pratique) ─────────── */
button:not(.btn):not([class*="modebar"]):not(.voxa-nav-item) {{
  background: {BG3} !important;
  color: {T2} !important;
  border: 0.5px solid {BD} !important;
  border-radius: 8px !important;
  font-family: {FONT_BODY} !important;
}}
button:not(.btn):not(.voxa-nav-item):hover {{
  border-color: {C1} !important; color: {C1} !important;
  background: {BG_ACCENT} !important;
}}

/* ── SIDEBAR NAV (nouveau v2) ─────────────────────────────── */
.voxa-nav-section {{
  font-size: 9px; color: {T3}; text-transform: uppercase;
  letter-spacing: 1.5px; margin: 16px 8px 6px 8px; font-weight: 600;
  font-family: {FONT_BODY};
}}
.voxa-nav-item {{
  display: block; padding: 7px 12px; color: {T2}; border-radius: 6px;
  font-size: 13px; font-weight: 500; text-decoration: none;
  font-family: {FONT_BODY}; cursor: pointer;
  transition: background 0.15s, color 0.15s;
  background: transparent !important; border: none !important;
}}
.voxa-nav-item:hover {{
  background: {BG2} !important; color: {W} !important;
}}
.voxa-nav-item.active {{
  background: {C1} !important; color: #FFFFFF !important;
}}
.voxa-nav-item.active:hover {{
  background: #006B7A !important;
}}
</style>"""

# ─────────────────────────────────────────────────────────────
# COULEURS MARQUES (dashboards) — inchangées
# ─────────────────────────────────────────────────────────────
BRAND_COLORS_PSG = {
    "OM":             "#009EE0",
    "PSG":            "#004170",
    "OL":             "#1A1A1A",
    "AS Monaco":      "#DC052D",
    "Stade Rennais":  "#DA291C",
    "RC Lens":        "#FEBE10",
    "LOSC":           "#C8102E",
    "OGC Nice":       "#C20000",
    "Montpellier":    "#FB090B",
    "Stade Brestois": "#E32221",
    "Real Madrid":    "#FEBE10",
    "Barcelona":      "#A50044",
    "Bayern Munich":  "#DC052D",
    "Man City":       "#6CABDD",
    "Arsenal":        "#EF0107",
    "Liverpool":      "#C8102E",
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
# HELPERS — inchangés (mêmes signatures)
# ─────────────────────────────────────────────────────────────
def score_color(score) -> str:
    """Retourne la couleur hex correspondant au score GEO."""
    if score is None: return T3
    if score >= 70:   return NG    # Vert — excellent
    if score >= 45:   return C1    # Cyan — moyen
    return RED                      # Rouge — faible


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
        "background": BG3, "border": f"0.5px solid {BD}",
        "borderRadius": 8, "padding": 16,
        "boxShadow": "0 1px 2px rgba(13,17,23,0.04), 0 4px 12px rgba(13,17,23,0.04)",
    }
    if extra:
        base.update(extra)
    return base


def card_title_style() -> dict:
    return {
        "fontSize": 10, "fontWeight": 600, "textTransform": "uppercase",
        "letterSpacing": "1.5px", "color": T3, "marginBottom": 12,
        "fontFamily": FONT_BODY,
    }


def kpi_value_style(color: str = None) -> dict:
    return {
        "fontSize": 24, "fontWeight": 600, "lineHeight": 1,
        "color": color or W, "marginBottom": 4,
        "fontFamily": FONT_BODY,
    }


def badge_style(color: str = C1, bg_opacity: float = 0.12) -> dict:
    """Badge tag générique."""
    hex_to_rgb = lambda h: tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    try:
        r, g, b = hex_to_rgb(color)
        bg = f"rgba({r},{g},{b},{bg_opacity})"
    except Exception:
        bg = "rgba(0,184,212,0.12)"
    return {
        "display": "inline-block", "padding": "3px 9px",
        "borderRadius": 12, "fontSize": 11, "fontWeight": 600,
        "background": bg, "color": color,
    }


# ─────────────────────────────────────────────────────────────
# COMPOSANTS DASH RÉUTILISABLES (existants, adaptés light)
# ─────────────────────────────────────────────────────────────
def make_topbar(client_name: str, vertical: str = "sport",
                right_children=None):
    """
    Topbar standardisée Voxa — à utiliser dans tous les dashboards.

    Paramètres :
      client_name   : ex "Betclic", "PSG"
      vertical      : "sport" | "bet" | "politics"
      right_children: liste de composants Dash additionnels (boutons, etc.)
    """
    from dash import html

    vert_colors = {
        "sport":    (C1, BG_ACCENT),
        "bet":      (C1, BG_ACCENT),
        "politics": (C2, BG_ACCENT2),
    }
    accent, tag_bg = vert_colors.get(vertical, vert_colors["sport"])

    logo = html.A([
        html.Div("V", style={
            "width": 32, "height": 32,
            "background": GRD,
            "borderRadius": 8,
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "fontSize": 15, "fontWeight": 800, "color": "#FFFFFF",
            "flexShrink": 0,
        }),
        html.Span("voxa", style={
            "fontWeight": 700, "fontSize": 18, "letterSpacing": "-.5px",
            "color": W,
        }),
        html.Span("GEO INTELLIGENCE", style={
            "fontSize": 9, "fontWeight": 600, "letterSpacing": "1.5px",
            "textTransform": "uppercase", "padding": "3px 8px",
            "borderRadius": 12, "background": tag_bg,
            "color": "#006B7A" if accent == C1 else "#5A2EBF",
        }),
    ], href="/", style={"display": "flex", "alignItems": "center", "gap": 10,
                        "textDecoration": "none"})

    right = html.Div(
        (right_children or []) + [
            html.Div([
                "Client : ", html.Strong(client_name, style={"color": C1}),
            ], style={
                "background": BG2, "border": f"0.5px solid {BD}",
                "borderRadius": 8, "padding": "5px 12px",
                "fontSize": 12, "color": T2, "fontFamily": FONT_BODY,
            }),
        ],
        style={"display": "flex", "alignItems": "center", "gap": 12}
    )

    return html.Div([logo, right], style={
        "display": "flex", "alignItems": "center", "justifyContent": "space-between",
        "height": 56, "padding": "0 28px",
        "background": "rgba(255,255,255,0.95)",
        "borderBottom": f"0.5px solid {BD}",
        "backdropFilter": "blur(12px)",
        "position": "sticky", "top": 0, "zIndex": 1000,
        "fontFamily": FONT_BODY,
    })


def make_btn_dark(label: str, **kwargs):
    """Bouton style Voxa secondary (nom 'dark' conservé pour compat v1)."""
    from dash import html
    style = {
        "padding": "6px 14px", "borderRadius": 8,
        "border": f"0.5px solid {BD}", "background": BG3,
        "fontFamily": FONT_BODY, "fontSize": 12, "fontWeight": 500,
        "cursor": "pointer", "color": T2, "transition": "all 0.15s",
    }
    style.update(kwargs.get("style", {}))
    return html.Button(label, style=style, **{k: v for k, v in kwargs.items() if k != "style"})


def make_btn_primary(label: str, **kwargs):
    """Bouton CTA gradient Voxa."""
    from dash import html
    style = {
        "padding": "7px 16px", "borderRadius": 8, "border": "none",
        "background": GRD, "fontFamily": FONT_BODY,
        "fontSize": 12, "fontWeight": 600, "cursor": "pointer",
        "color": "#FFFFFF", "transition": "all 0.15s",
        "boxShadow": "0 2px 8px rgba(0,184,212,0.25)",
    }
    style.update(kwargs.get("style", {}))
    return html.Button(label, style=style, **{k: v for k, v in kwargs.items() if k != "style"})


# ─────────────────────────────────────────────────────────────
# NOUVEAUX COMPOSANTS V2 — Sidebar, KPI cards, Filter bar
# ─────────────────────────────────────────────────────────────

# Structure de navigation par défaut (3 sections Meikai-like)
NAV_STRUCTURE = [
    {
        "section": "Monitor",
        "items": [
            {"id": "overview",    "label": "Overview",    "tab": "tab-overview"},
            {"id": "prompts",     "label": "Prompts",     "tab": "tab-prompts"},
            {"id": "citations",   "label": "Citations",   "tab": "tab-citations"},
            {"id": "competitors", "label": "Concurrents", "tab": "tab-competitors"},
        ]
    },
    {
        "section": "Improve",
        "items": [
            {"id": "actions",       "label": "Pack Action", "tab": "tab-actions"},
            {"id": "optimizations", "label": "JSON-LD",     "tab": "tab-optimizations"},
            {"id": "scanner",       "label": "Site Scanner","tab": "tab-scanner"},
        ]
    },
    {
        "section": "Discover",
        "items": [
            {"id": "library", "label": "Bibliothèque", "tab": "tab-library"},
            {"id": "markets", "label": "Marchés",      "tab": "tab-markets"},
        ]
    },
]


def make_sidebar(active_item: str = "overview", structure: list = None):
    """
    Sidebar de navigation latérale Voxa V2 — 3 sections (Monitor / Improve / Discover).

    Paramètres :
      active_item : id de l'item actif (ex: "overview", "prompts", "actions")
      structure   : liste optionnelle pour override la structure NAV_STRUCTURE par défaut

    Retour :
      html.Div compatible Dash, à placer en colonne gauche du layout.

    Usage :
      from theme import make_sidebar
      sidebar = make_sidebar(active_item="prompts")
    """
    from dash import html

    nav = structure or NAV_STRUCTURE
    blocks = []

    for sec in nav:
        # Header de section
        blocks.append(html.Div(sec["section"], className="voxa-nav-section"))
        # Items
        for item in sec["items"]:
            is_active = item["id"] == active_item
            classes = "voxa-nav-item active" if is_active else "voxa-nav-item"
            blocks.append(html.A(
                item["label"],
                href=f"#{item.get('tab', item['id'])}",
                className=classes,
                id=f"nav-{item['id']}",
            ))

    return html.Div(blocks, style={
        "width": 180,
        "padding": "16px 12px",
        "background": BG,
        "borderRight": f"0.5px solid {BD}",
        "minHeight": "calc(100vh - 56px)",
        "fontFamily": FONT_BODY,
    })


# Bibliothèque d'icônes SVG inline (paths uniquement, pas le <svg> wrapper)
ICONS = {
    "score":      '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "mention":    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "voice":      '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "sentiment":  '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
    "prompt":     '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    "trend_up":   '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "trend_down": '<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>',
    "scan":       '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/>',
    "globe":      '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "spark":      '<path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>',
    "user":       '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "filter":     '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
}


def _svg_icon(path: str, color: str = None, size: int = 14) -> str:
    """Construit un SVG complet à partir d'un path et d'une couleur."""
    stroke = color or C1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>')


def _svg_to_img(svg_str: str, size: int = 14):
    """Encode un SVG en data URI base64 pour html.Img (compatible Dash)."""
    from dash import html
    import base64
    encoded = base64.b64encode(svg_str.encode("utf-8")).decode("ascii")
    return html.Img(
        src=f"data:image/svg+xml;base64,{encoded}",
        style={"width": size, "height": size, "display": "block"},
    )


def make_kpi_card(label: str, value, icon_key: str = None,
                  change: str = None, change_positive: bool = True,
                  accent_color: str = None):
    """
    Card KPI Voxa V2 — icône colorée, valeur, label, delta.

    Paramètres :
      label           : texte court en bas (ex "GEO score")
      value           : valeur principale (str ou int)
      icon_key        : clé de la lib ICONS (ex "score", "mention", "voice")
                        ou string SVG path complet
                        ou None (pas d'icône)
      change          : delta texte (ex "+2.3%", "-0.5%") ou None
      change_positive : True (vert) ou False (rouge)
      accent_color    : couleur de l'icône (par défaut C1 cyan)

    Retour :
      html.Div compatible Dash.

    Usage :
      from theme import make_kpi_card
      card = make_kpi_card("GEO score", 48, icon_key="score", change="+2.3%")
      card2 = make_kpi_card("Mentions", "3.29", icon_key="mention",
                            change="+12", accent_color=C2)
    """
    from dash import html

    accent = accent_color or C1
    icon_bg_map = {C1: BG_ACCENT, C2: BG_ACCENT2, WARN: BG_WARN,
                   NG: BG_OK, RED: BG_ERR}
    icon_bg = icon_bg_map.get(accent, BG_ACCENT)

    children = []
    header_children = []

    # Icône (à gauche)
    if icon_key:
        # Si c'est une clé de la lib, utilise le path correspondant ; sinon assume que c'est déjà un path
        path = ICONS.get(icon_key, icon_key)
        svg_str = _svg_icon(path, color=accent, size=14)
        icon_img = _svg_to_img(svg_str, size=14)
        header_children.append(html.Div(icon_img, style={
            "width": 28, "height": 28, "background": icon_bg,
            "borderRadius": 6, "display": "flex",
            "alignItems": "center", "justifyContent": "center",
            "flexShrink": 0,
        }))

    # Delta (à droite)
    if change:
        change_color = NG if change_positive else RED
        header_children.append(html.Span(change, style={
            "fontSize": 11, "color": change_color, "fontWeight": 600,
            "marginLeft": "auto",
        }))

    if header_children:
        children.append(html.Div(header_children, style={
            "display": "flex", "alignItems": "center",
            "justifyContent": "space-between", "marginBottom": 8,
        }))

    # Valeur
    children.append(html.Div(str(value), style={
        "fontSize": 24, "fontWeight": 600, "lineHeight": 1,
        "color": W, "marginBottom": 4, "fontFamily": FONT_BODY,
    }))

    # Label
    children.append(html.Div(label, style={
        "fontSize": 10, "fontWeight": 600, "letterSpacing": "1px",
        "textTransform": "uppercase", "color": T3, "fontFamily": FONT_BODY,
    }))

    return html.Div(children, style={
        "background": BG3, "border": f"0.5px solid {BD}",
        "borderRadius": 8, "padding": 14,
        "fontFamily": FONT_BODY,
    })


def make_filter_bar(filters: list):
    """
    Barre de filtres top sticky Voxa V2.

    Paramètres :
      filters : liste de dicts avec format
                [{"id": "topic-filter", "label": "Tous les topics", "options": [...]}]
                Si options vide, un simple span est rendu (placeholder visuel).

    Retour :
      html.Div compatible Dash.

    Usage :
      from theme import make_filter_bar
      bar = make_filter_bar([
          {"id": "topic-filter", "label": "Tous les topics"},
          {"id": "llm-filter", "label": "Tous les LLMs"},
          {"id": "date-filter", "label": "30 jours"},
      ])
    """
    from dash import html, dcc

    children = []
    for f in filters:
        if f.get("options"):
            children.append(dcc.Dropdown(
                id=f["id"],
                options=f["options"],
                value=f.get("default"),
                placeholder=f["label"],
                clearable=False,
                style={
                    "minWidth": 140, "fontSize": 12,
                    "fontFamily": FONT_BODY,
                },
            ))
        else:
            # Placeholder statique
            children.append(html.Span(
                f["label"] + " ▾",
                style={
                    "padding": "5px 12px", "border": f"0.5px solid {BD}",
                    "borderRadius": 6, "fontSize": 12, "color": T2,
                    "background": BG3, "fontFamily": FONT_BODY,
                    "cursor": "pointer",
                },
            ))

    return html.Div(children, style={
        "display": "flex", "alignItems": "center", "gap": 8,
        "padding": "12px 28px",
        "background": BG, "borderBottom": f"0.5px solid {BD}",
        "position": "sticky", "top": 56, "zIndex": 999,
        "fontFamily": FONT_BODY,
    })


# ─────────────────────────────────────────────────────────────
# DEBUG / SELF-TEST
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Voxa Design System v2.0 (LIGHT MODE) ===")
    print(f"Background page  : {BG}")
    print(f"Background cards : {BG3}")
    print(f"Texte principal  : {W}")
    print(f"Cyan primary     : {C1}")
    print(f"Violet secondary : {C2}")
    print(f"Vert succès      : {NG}")
    print(f"Rouge erreur     : {RED}")
    print(f"Fonts            : {FONTS_URL[:60]}...")
    print()
    print(f"Score 80 → {score_color(80)} ({score_label(80)})")
    print(f"Score 50 → {score_color(50)} ({score_label(50)})")
    print(f"Score 30 → {score_color(30)} ({score_label(30)})")
    print()
    print(f"BRAND_COLORS_BET : {len(BRAND_COLORS_BET)} marques")
    print(f"BRAND_COLORS_PSG : {len(BRAND_COLORS_PSG)} marques")
    print(f"NAV_STRUCTURE    : {sum(len(s['items']) for s in NAV_STRUCTURE)} items "
          f"sur {len(NAV_STRUCTURE)} sections")
    print()
    print("OK — theme.py v2 prêt")