"""
Voxa — Shared Flask server v2.0
================================
Serveur Flask partagé par toutes les apps Dash.
Contient : auth, /demo, /login, /register, /logout,
           /health, API endpoints, routes admin.

Les apps Dash l'importent ainsi :
    from server import server
    app = dash.Dash(__name__, server=server, ...)
"""

import os
import json
import secrets
import threading
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import (Flask, request, redirect, url_for,
                   jsonify, render_template_string, Response, send_file)
from flask_login import (LoginManager, UserMixin,
                         login_user, logout_user,
                         login_required, current_user)
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).parent.resolve()

import voxa_db as vdb

# ── Flask setup ──────────────────────────────────────────────
server = Flask(__name__)
server.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

bcrypt = Bcrypt(server)
lm = LoginManager(server)
lm.login_view    = "login"
lm.login_message = "Connectez-vous pour accéder à votre espace."

# ── Palette ──────────────────────────────────────────────────
N="#0B1D3A"; G="#B8962E"; GL="#F5EDD5"; BG="#F4F5F9"
W="#FFFFFF"; BD="#E5E7EB"; T2="#4B5563"; T3="#9CA3AF"
GRN="#16A34A"; RED="#DC2626"

MODEL_H = "claude-haiku-4-5-20251001"

def sc(s):
    if s is None: return T3
    return GRN if s >= 70 else ("#D97706" if s >= 45 else RED)

# ── User model ───────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, d):
        self.id       = d["id"]
        self.email    = d["email"]
        self.name     = d["name"]
        self.plan     = d["plan"]
        self.is_admin = bool(d.get("is_admin", 0))
        self.api_key  = d.get("api_key", "")

@lm.user_loader
def load_user(uid):
    d = vdb.get_account_by_id(int(uid))
    return User(d) if d else None

# ── CSS minimal (pages auth/demo uniquement) ─────────────────
CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:{BG};color:#111}}
.tb{{height:52px;background:{W};border-bottom:1px solid {BD};
     display:flex;align-items:center;justify-content:space-between;padding:0 24px}}
.logo{{display:flex;align-items:center;gap:8px;text-decoration:none;color:{N}}}
.lb{{width:28px;height:28px;background:{G};border-radius:7px;
     display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;color:{N}}}
.ln{{font-weight:800;font-size:16px;letter-spacing:-.5px}}
.card{{background:{W};border:1px solid {BD};border-radius:12px;padding:28px;
       box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.h1{{font-size:22px;font-weight:800;color:{N};margin-bottom:6px}}
.lbl{{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{T3}}}
.fi{{width:100%;padding:9px 13px;border:1px solid {BD};border-radius:8px;
     font-size:14px;color:#111;outline:none;font-family:inherit;margin-bottom:12px}}
.fi:focus{{border-color:{N}}}
.fs{{width:100%;padding:9px 13px;border:1px solid {BD};border-radius:8px;
     font-size:14px;background:{W};font-family:inherit;outline:none;margin-bottom:12px}}
.btn{{display:inline-flex;align-items:center;justify-content:center;
      padding:10px 20px;border-radius:8px;font-size:14px;font-weight:600;
      cursor:pointer;border:none;width:100%;transition:opacity .15s;text-decoration:none}}
.btn:hover{{opacity:.85}}
.bp{{background:{N};color:{W}}}
.bg2{{background:{G};color:{W}}}
.bo{{background:transparent;color:{N};border:1px solid {BD};width:auto;padding:7px 14px}}
.ae{{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px}}
.ae.err{{background:#FEE2E2;color:#991B1B}}
.ae.ok{{background:#DCFCE7;color:#166534}}
.ae.inf{{background:{GL};color:#7C5B1A}}
.kc{{background:{W};border:1px solid {BD};border-radius:10px;padding:16px;text-align:center}}
.kv{{font-size:30px;font-weight:800;line-height:1;margin-bottom:4px}}
.kl{{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:{T3}}}
.dv{{border:none;border-top:1px solid {BD};margin:16px 0}}
.tag{{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}}
.ts{{background:#EEF2FF;color:#4F46E5}}
.tb2{{background:#FEF3C7;color:#92400E}}
.tp{{background:#FCE7F3;color:#831843}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.g4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.sbar{{height:7px;background:{BD};border-radius:4px;overflow:hidden}}
.sbari{{height:100%;border-radius:4px}}
@media(max-width:600px){{.g2,.g4{{grid-template-columns:1fr 1fr}}}}
</style>"""

def topbar(show_right=True):
    right = ""
    if show_right and current_user.is_authenticated:
        right = f"""<div style="display:flex;align-items:center;gap:12px;font-size:13px">
          <span style="color:{T3}">👋 {current_user.name.split()[0]}</span>
          <a href="/psg/" style="color:{T2};font-weight:500">PSG</a>
          <a href="/betclic/" style="color:{T2};font-weight:500">Betclic</a>
          <a href="/demo" style="color:{T2};font-weight:500">Demo</a>
          <a href="/settings" style="color:{T2};font-weight:500">⚙ Paramètres</a>
          <a href="/logout" class="bo" style="color:{RED};padding:5px 12px;font-size:12px">Déconnexion</a>
        </div>"""
    elif show_right:
        right = f"""<div style="display:flex;align-items:center;gap:10px">
          <a href="/demo" style="font-size:13px;color:{T2};">Demo live</a>
          <a href="/login" style="font-size:13px;color:{T2};">Connexion</a>
          <a href="/register" class="btn bg2" style="width:auto;padding:7px 14px;font-size:12px">Démarrer →</a>
        </div>"""
    return f"""<header class="tb">
      <a href="/" class="logo"><div class="lb">V</div><span class="ln">voxa</span></a>
      {right}</header>"""

def pg(title, body):
    return f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Voxa</title>{CSS}</head><body>
{topbar()}<div style="padding:32px;max-width:480px;margin:0 auto">{body}</div>
</body></html>"""

def pg_wide(title, body):
    return f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Voxa</title>{CSS}</head><body>
{topbar()}<div style="padding:32px;max-width:900px;margin:0 auto">{body}</div>
</body></html>"""

# ── AUTH ROUTES ──────────────────────────────────────────────

@server.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/")
    err = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd   = request.form.get("password", "")
        d = vdb.get_account_by_email(email)
        if d and vdb.check_password(pwd, d["password_hash"]):
            login_user(User(d), remember=True)
            c = vdb.conn_accounts()
            c.execute("UPDATE accounts SET last_login=? WHERE id=?",
                      (datetime.utcnow().isoformat(), d["id"]))
            c.commit(); c.close()
            nxt = request.args.get("next", "/")
            return redirect(nxt)
        err = "Email ou mot de passe incorrect."
    body = f"""
    <div style="margin-top:20px">
      <div class="lbl" style="margin-bottom:8px">CONNEXION</div>
      <div class="h1" style="margin-bottom:20px">Accéder à Voxa</div>
      {"" if not err else f'<div class="ae err">{err}</div>'}
      <form method="POST">
        <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Email</label>
        <input name="email" type="email" class="fi" placeholder="vous@example.com" required autofocus>
        <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Mot de passe</label>
        <input name="password" type="password" class="fi" placeholder="••••••••" required>
        <button type="submit" class="btn bp" style="margin-top:4px">Se connecter →</button>
      </form>
      <hr class="dv">
      <div style="text-align:center;font-size:13px;color:{T3}">
        Pas de compte ? <a href="/register" style="color:{G};font-weight:600">Démarrer gratuitement</a>
      </div>
    </div>"""
    return pg("Connexion", body)


@server.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect("/")
    err = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd   = request.form.get("password", "")
        name  = request.form.get("name", "").strip()
        if len(pwd) < 8:
            err = "Mot de passe : 8 caractères minimum."
        elif vdb.get_account_by_email(email):
            err = "Un compte existe déjà avec cet email."
        else:
            aid = vdb.create_account(email, pwd, name, "trial")
            d = vdb.get_account_by_id(aid)
            login_user(User(d), remember=True)
            return redirect("/demo")
    body = f"""
    <div style="margin-top:20px">
      <div class="lbl" style="margin-bottom:8px">CRÉER UN COMPTE</div>
      <div class="h1" style="margin-bottom:6px">Démarrer gratuitement</div>
      <div style="font-size:13px;color:{T3};margin-bottom:20px">Sans carte bancaire</div>
      {"" if not err else f'<div class="ae err">{err}</div>'}
      <form method="POST">
        <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Nom</label>
        <input name="name" class="fi" placeholder="Prénom Nom" required autofocus>
        <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Email</label>
        <input name="email" type="email" class="fi" placeholder="vous@example.com" required>
        <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Mot de passe</label>
        <input name="password" type="password" class="fi" placeholder="8 caractères minimum" required>
        <button type="submit" class="btn bg2" style="margin-top:4px">Créer mon compte →</button>
      </form>
      <div style="text-align:center;font-size:13px;color:{T3};margin-top:14px">
        Déjà un compte ? <a href="/login" style="color:{G};font-weight:600">Se connecter</a>
      </div>
    </div>"""
    return pg("Créer un compte", body)


@server.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


# ── DEMO PUBLIQUE ────────────────────────────────────────────

@server.route("/demo", methods=["GET", "POST"])
def demo():
    brand = request.form.get("brand", "").strip() if request.method == "POST" else ""
    vert  = request.form.get("vertical", "sport")
    mkt   = request.form.get("market", "fr")
    vote_html = score_html = ""

    if brand:
        # Competitive intelligence vote
        from voxa_engine import competitive_vote
        vote = competitive_vote(brand, vert, mkt)
        if vote.get("competitors"):
            chips = "".join(
                f'<span style="padding:4px 10px;background:{BG};border:1px solid {BD};'
                f'border-radius:20px;font-size:12px;color:{T2};margin:3px">{cx}</span>'
                for cx in vote["competitors"])
            vote_html = f"""<div class="card" style="margin-bottom:16px">
              <div class="lbl" style="margin-bottom:10px">CONCURRENTS DÉTECTÉS DANS L'IA · {brand.upper()}</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">{chips}</div>
              <div style="font-size:11px;color:{T3};margin-top:10px">
                Marques les plus souvent citées avec <strong>{brand}</strong> par les LLMs.
              </div></div>"""

        # Score préliminaire
        score_html = _demo_geo_score(brand, vert, mkt)

    verts = [("sport","⚽ Sport"),("bet","🎰 Betting"),("politics","🗳 Politics")]
    mkts  = [("fr","🇫🇷 France"),("en","🇬🇧 Anglais"),("pt","🇵🇹 Portugal")]

    vr = "".join(
        f'<label style="display:flex;align-items:center;gap:5px;font-size:13px;cursor:pointer">'
        f'<input type="radio" name="vertical" value="{v}" {"checked" if v==vert else ""}> {n}</label>'
        for v,n in verts)
    mr = "".join(
        f'<option value="{v}" {"selected" if v==mkt else ""}>{n}</option>'
        for v,n in mkts)

    body = f"""
    <div style="text-align:center;margin-bottom:28px">
      <div class="lbl" style="margin-bottom:8px">DEMO LIVE · GRATUIT</div>
      <div class="h1" style="font-size:26px;margin-bottom:6px">Votre marque dans ChatGPT et Perplexity</div>
      <div style="font-size:13px;color:{T2}">Concurrents détectés + GEO Score — en 30 secondes.</div>
    </div>
    <div class="card" style="margin-bottom:18px">
      <form method="POST">
        <div class="g2" style="margin-bottom:12px">
          <div>
            <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Marque</label>
            <input name="brand" class="fi" style="margin-bottom:0"
                   value="{brand}" placeholder="PSG, Betclic, Macron..." required autofocus>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Marché</label>
            <select name="market" class="fs" style="margin-bottom:0">{mr}</select>
          </div>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:8px">Verticale</label>
          <div style="display:flex;gap:16px">{vr}</div>
        </div>
        <button type="submit" class="btn bg2">Analyser →</button>
      </form>
    </div>
    {vote_html}{score_html}
    <div class="card" style="text-align:center;background:{N}">
      <div style="font-weight:800;font-size:17px;color:{W};margin-bottom:6px">Tracker votre marque chaque semaine ?</div>
      <div style="color:rgba(255,255,255,.6);font-size:13px;margin-bottom:16px">Dashboard live · 4 LLMs · Alertes auto</div>
      <a href="/register" class="btn bg2" style="width:auto;padding:10px 22px">Démarrer gratuitement →</a>
    </div>"""

    return pg_wide("Demo live", body)


def _demo_geo_score(brand, vert, mkt):
    """
    Prompts neutres — la marque n'est PAS dans la question.
    Scoring multi-dimensionnel :
      Présence  40 pts : citée spontanément
      Position  30 pts : citée dans le premier tiers
      Sentiment 20 pts : ton positif autour de la mention
      Fréquence 10 pts : citée 2+ fois
    """
    import re as _re

    pm = {
        "sport": [
            "Quels sont les meilleurs clubs de football en France en 2025 ? Donne un top 5.",
            "Quel club de Ligue 1 recommandes-tu pour un fan de foot français ?",
            "Quels clubs européens ont la meilleure réputation internationale en ce moment ?",
        ],
        "bet": [
            "Quels sont les meilleurs sites de paris sportifs en France en 2025 ? Top 5.",
            "Quel opérateur de paris sportifs est le plus fiable pour les cotes et les paiements ?",
            "Quel site de paris recommandes-tu pour parier sur la Ligue 1 et la Champions League ?",
        ],
        "politics": [
            "Quelles personnalités politiques françaises sont les plus influentes et citées en 2025 ?",
            "Quels partis et candidats français sont les plus présents dans l'actualité politique récente ?",
            "Qui sont les figures politiques françaises incontournables en ce moment ?",
        ],
    }
    lang_overrides = {
        "en": {
            "sport": [
                "What are the best football clubs in Europe right now? List the top 5.",
                "Which Ligue 1 club would you recommend to a football fan?",
                "Which European clubs have the best international reputation currently?",
            ],
            "bet": [
                "What are the best sports betting sites in Europe in 2025? Top 5.",
                "Which sports betting operator is most reliable for odds and payouts?",
                "Which betting site would you recommend for Champions League betting?",
            ],
            "politics": [
                "Who are the most influential and frequently cited French politicians in 2025?",
                "Which French parties and candidates are most prominent in current affairs?",
                "Who are the unavoidable French political figures right now?",
            ],
        },
        "pt": {
            "bet": [
                "Quais são os melhores sites de apostas desportivas em Portugal em 2025? Top 5.",
                "Qual operador de apostas é mais confiável para odds e pagamentos?",
                "Qual site de apostas recomendas para apostar na Liga Portugal?",
            ],
            "sport": [
                "Quais são os melhores clubes de futebol em Portugal em 2025? Top 5.",
                "Qual clube recomendas a um adepto de futebol português?",
                "Quais clubes têm melhor reputação europeia atualmente?",
            ],
        },
    }

    lang = mkt.split("-")[0] if "-" in mkt else mkt
    if lang in lang_overrides and vert in lang_overrides[lang]:
        prompts = lang_overrides[lang][vert]
    else:
        prompts = pm.get(vert, pm["sport"])

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return f'<div class="ae inf">Mode démo — <a href="/register" style="color:{G};font-weight:600">Créez un compte</a> pour les résultats live.</div>'
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        return ""

    pos_w = {
        "sport":    ["meilleur","recommandé","excellent","top","incontournable","référence",
                     "populaire","champion","solide","qualité","performant"],
        "bet":      ["fiable","sécurisé","agréé","recommandé","meilleur","leader","reconnu",
                     "sérieux","réputé","certifié","légal","officiel"],
        "politics": ["influent","reconnu","populaire","représentatif","crédible",
                     "incontournable","figure","leader","important","engagé"],
    }.get(vert, ["meilleur","recommandé","top","fiable","reconnu"])

    neg_w = {
        "sport":    ["relégué","mauvais","décevant","faible","problème"],
        "bet":      ["illégal","frauduleux","risqué","éviter","interdit","arnaque","non agréé"],
        "politics": ["controversé","scandale","condamné","extrémiste","marginal"],
    }.get(vert, ["mauvais","éviter","problème","faible"])

    results = []; total = 0
    brand_lower = brand.lower()

    for pt in prompts:
        try:
            r = client.messages.create(
                model=MODEL_H, max_tokens=350,
                system="Tu réponds de façon factuelle et concise. Tu fournis des listes claires quand demandé.",
                messages=[{"role":"user","content":pt}]
            )
            ans = r.content[0].text

            # Nettoyage markdown
            ans_c = _re.sub(r'\*\*(.+?)\*\*', r'\1', ans)
            ans_c = _re.sub(r'\*(.+?)\*',     r'\1', ans_c)
            ans_c = _re.sub(r'^#{1,3}\s+',    '',    ans_c, flags=_re.MULTILINE)
            ans_c = ans_c.strip()
            ans_l = ans_c.lower()

            # Présence (40 pts)
            occ      = ans_l.count(brand_lower)
            presence = occ > 0

            # Position (30 pts) — premier tiers
            first_idx = ans_l.find(brand_lower)
            early     = presence and first_idx <= len(ans_l) // 3

            # Sentiment (20 pts) — fenêtre 100 chars autour de la mention
            ctx = ans_l[max(0,first_idx-100):first_idx+100+len(brand_lower)] if presence else ans_l
            sent_p = any(w in ctx for w in pos_w)
            sent_n = any(w in ctx for w in neg_w)
            sentiment = "positive" if sent_p and not sent_n else ("negative" if sent_n else "neutral")

            # Fréquence (10 pts)
            frequent = occ >= 2

            score = max(0, min(100,
                (40 if presence  else 0) +
                (30 if early     else 0) +
                (20 if sentiment == "positive" else (-10 if sentiment == "negative" else 0)) +
                (10 if frequent  else 0)
            ))
            total += score
            results.append({"prompt":pt,"answer":ans_c[:300]+"..." if len(ans_c)>300 else ans_c,
                            "mentioned":presence,"early":early,"sentiment":sentiment,
                            "occurrences":occ,"score":score})
        except Exception as ex:
            results.append({"prompt":pt,"answer":str(ex),"mentioned":False,
                           "early":False,"sentiment":"neutral","occurrences":0,"score":0})

    avg = round(total / max(len(results), 1))
    clr = sc(avg)
    lbl = "Excellent" if avg >= 70 else ("Moyen" if avg >= 40 else "Faible")
    tip = {"Excellent": "Votre marque est bien ancrée dans les réponses IA.",
           "Moyen":     "Des actions GEO peuvent améliorer ce score significativement.",
           "Faible":    "Votre marque est quasi absente des LLMs — opportunité GEO majeure."}[lbl]

    rows = ""
    for r in results:
        if r["mentioned"]:
            badge = f'<span style="color:{GRN};font-size:11px;font-weight:700">✓ {"TÔT" if r["early"] else "CITÉE"}</span>'
        else:
            badge = f'<span style="color:{RED};font-size:11px;font-weight:700">✗ ABSENTE</span>'
        sent_col = GRN if r["sentiment"]=="positive" else (RED if r["sentiment"]=="negative" else T3)
        sent_ico = "😊" if r["sentiment"]=="positive" else ("😟" if r["sentiment"]=="negative" else "😐")
        opp = "" if r["mentioned"] else f'<div style="font-size:11px;color:{RED};margin-top:6px">⚠ Marque absente — opportunité GEO directe.</div>'

        rows += (
            f'<div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid {BD}">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            f'<div style="font-size:12px;color:{T3};font-style:italic;flex:1">"{r["prompt"]}"</div>'
            f'<div style="display:flex;gap:6px;align-items:center;flex-shrink:0;margin-left:12px">'
            f'{badge}<span style="font-size:11px;color:{sent_col}">{sent_ico}</span>'
            f'<span style="font-weight:800;font-size:16px;color:{sc(r["score"])}">{r["score"]}</span>'
            f'</div></div>'
            f'<div style="font-size:13px;color:#374151;line-height:1.6;background:{BG};padding:10px 12px;border-radius:8px">{r["answer"]}</div>'
            f'{opp}</div>'
        )

    breakdown = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0 14px">'
        + "".join(
            f'<div style="text-align:center;padding:8px 4px;background:{BG};border-radius:8px">'
            f'<div style="font-size:11px;font-weight:700;color:{N}">{nm}</div>'
            f'<div style="font-size:10px;color:{T3}">{pts} pts max</div></div>'
            for nm, pts in [("Présence","40"),("Position","30"),("Sentiment","20"),("Fréquence","10")]
        )
        + '</div>'
    )

    return (
        f'<div class="card" style="margin-bottom:16px">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">'
        f'<div><div class="lbl">GEO SCORE · {brand.upper()} · {mkt.upper()}</div>'
        f'<div style="font-size:32px;font-weight:800;color:{clr};margin-top:4px;line-height:1">'
        f'{avg}<span style="font-size:16px;color:{T3}">/100</span>'
        f'<span style="font-size:13px;font-weight:600;color:{clr};margin-left:8px">{lbl}</span></div>'
        f'<div style="font-size:12px;color:{T2};margin-top:4px">{tip}</div></div>'
        f'<div style="text-align:right;font-size:11px;color:{T3};flex-shrink:0;margin-left:16px">'
        f'Claude Haiku · {len(results)} prompts neutres<br>'
        f'<a href="/register" style="color:{G};font-weight:600">Tracking complet 4 LLMs →</a></div></div>'
        f'{breakdown}'
        f'<hr style="border:none;border-top:1px solid {BD};margin-bottom:14px">'
        f'{rows}</div>'
    )

# ── API publique ─────────────────────────────────────────────

def _api_auth(f):
    @wraps(f)
    def d(*a, **kw):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "X-API-Key header required"}), 401
        acc = vdb.get_account_by_api_key(key)
        if not acc:
            return jsonify({"error": "Invalid API key"}), 401
        request.api_account = acc
        return f(*a, **kw)
    return d


@server.route("/api/v1/vote")
def api_vote():
    """Public — competitive intelligence vote."""
    brand = request.args.get("brand", "")
    if not brand:
        return jsonify({"error": "brand required"}), 400
    from voxa_engine import competitive_vote
    return jsonify(competitive_vote(
        brand,
        request.args.get("vertical", "sport"),
        request.args.get("market", "fr")
    ))


@server.route("/api/v1/score")
@_api_auth
def api_score():
    slug = request.args.get("slug", "")
    if slug not in vdb.CLIENTS_CONFIG:
        return jsonify({"error": "slug must be 'psg' or 'betclic'"}), 400
    return jsonify({
        "client":      vdb.CLIENTS_CONFIG[slug]["name"],
        "score":       vdb.get_score(slug),
        "nss":         vdb.get_nss(slug),
        "by_market":   vdb.get_score_by_market(slug),
        "competitors": vdb.get_competitors(slug, top=8),
    })


@server.route("/api/v1/benchmark")
@_api_auth
def api_benchmark():
    """Classement comparatif PSG vs Betclic."""
    result = {}
    for slug in vdb.CLIENTS_CONFIG:
        result[slug] = {
            "score":     vdb.get_score(slug)["score"],
            "nss":       vdb.get_nss(slug),
            "by_market": vdb.get_score_by_market(slug),
        }
    return jsonify(result)


@server.route("/api/v1/history")
@_api_auth
def api_history():
    slug = request.args.get("slug", "")
    if slug not in vdb.CLIENTS_CONFIG:
        return jsonify({"error": "slug required"}), 400
    return jsonify({
        "client":  vdb.CLIENTS_CONFIG[slug]["name"],
        "history": vdb.get_history(slug, n_weeks=request.args.get("weeks", 12, type=int)),
    })


# ── HEALTH ───────────────────────────────────────────────────

@server.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "version":   "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        **vdb.status(),
    })


# ── SETTINGS ─────────────────────────────────────────────────

@server.route("/settings")
@login_required
def settings():
    acc = vdb.get_account_by_id(current_user.id)
    api_key = acc["api_key"] if acc else "—"

    endpoints = [
        ("GET", "/api/v1/vote?brand=Betclic&vertical=bet", "Public — aucune clé requise"),
        ("GET", "/api/v1/score?slug=betclic",              "Score + NSS + concurrents"),
        ("GET", "/api/v1/benchmark",                       "Comparatif tous clients"),
        ("GET", "/api/v1/history?slug=psg&weeks=12",       "Historique GEO Score"),
    ]

    rows_ep = "".join(
        f'<tr style="border-bottom:1px solid {BD}">'
        f'<td style="padding:8px 12px;font-size:11px;font-weight:700;color:#4F46E5;font-family:monospace">{m}</td>'
        f'<td style="padding:8px 12px;font-size:12px;font-family:monospace;color:{N}">{ep}</td>'
        f'<td style="padding:8px 12px;font-size:11px;color:{T3}">{desc}</td>'
        f'</tr>'
        for m, ep, desc in endpoints
    )

    body = f"""
    <div style="margin-bottom:28px">
      <div class="lbl" style="margin-bottom:6px">PARAMÈTRES</div>
      <div class="h1">Votre compte</div>
    </div>

    <!-- Compte -->
    <div class="card" style="margin-bottom:18px">
      <div style="padding:20px 24px;border-bottom:1px solid {BD}">
        <div class="lbl" style="margin-bottom:12px">INFORMATIONS</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div>
            <div style="font-size:11px;color:{T3};margin-bottom:3px">Nom</div>
            <div style="font-weight:600;color:{N}">{current_user.name}</div>
          </div>
          <div>
            <div style="font-size:11px;color:{T3};margin-bottom:3px">Email</div>
            <div style="font-weight:600;color:{N}">{current_user.email}</div>
          </div>
          <div>
            <div style="font-size:11px;color:{T3};margin-bottom:3px">Plan</div>
            <div style="display:inline-block;background:#EEF2FF;color:#4F46E5;
                 font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px">
              {current_user.plan.upper()}
            </div>
          </div>
          <div>
            <div style="font-size:11px;color:{T3};margin-bottom:3px">Accès dashboards</div>
            <div style="display:flex;gap:8px">
              <a href="/psg/" style="font-size:12px;font-weight:600;color:{N};
                   background:{BD};padding:4px 10px;border-radius:6px">PSG →</a>
              <a href="/betclic/" style="font-size:12px;font-weight:600;color:{N};
                   background:{BD};padding:4px 10px;border-radius:6px">Betclic →</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Clé API -->
    <div class="card" style="margin-bottom:18px">
      <div style="padding:20px 24px">
        <div class="lbl" style="margin-bottom:12px">CLÉ API</div>
        <div style="background:{BG};border:1px solid {BD};border-radius:8px;
             padding:12px 16px;font-family:monospace;font-size:13px;
             color:{N};word-break:break-all;margin-bottom:8px;
             display:flex;justify-content:space-between;align-items:center">
          <span id="apikey">{api_key}</span>
          <button onclick="navigator.clipboard.writeText('{api_key}');this.textContent='✓ Copié!';setTimeout(()=>this.textContent='Copier',2000)"
                  style="border:none;background:{G};color:white;padding:5px 12px;
                         border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;
                         flex-shrink:0;margin-left:12px">Copier</button>
        </div>
        <div style="font-size:11px;color:{T3}">
          Header : <code style="background:{BG};padding:2px 6px;border-radius:4px">X-API-Key: {api_key[:20]}...</code>
        </div>
      </div>
    </div>

    <!-- API Endpoints -->
    <div class="card">
      <div style="padding:20px 24px">
        <div class="lbl" style="margin-bottom:12px">ENDPOINTS API</div>
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="border-bottom:2px solid {BD}">
              <th style="text-align:left;padding:6px 12px;font-size:10px;font-weight:700;
                   letter-spacing:1px;text-transform:uppercase;color:{T3}">Méthode</th>
              <th style="text-align:left;padding:6px 12px;font-size:10px;font-weight:700;
                   letter-spacing:1px;text-transform:uppercase;color:{T3}">Endpoint</th>
              <th style="text-align:left;padding:6px 12px;font-size:10px;font-weight:700;
                   letter-spacing:1px;text-transform:uppercase;color:{T3}">Description</th>
            </tr>
          </thead>
          <tbody>{rows_ep}</tbody>
        </table>
        <div style="margin-top:14px;padding:12px 16px;background:{BG};
             border-radius:8px;font-size:12px;color:{T2}">
          <strong>Exemple curl :</strong><br>
          <code style="font-size:11px">curl -H "X-API-Key: {api_key[:20]}..." https://lucsharper.pythonanywhere.com/api/v1/score?slug=betclic</code>
        </div>
      </div>
    </div>"""

    return pg_wide("Paramètres", body)


# ── ENTRY POINT (test local uniquement) ─────────────────────
if __name__ == "__main__":
    vdb.init_accounts_db()
    print("\n  VOXA server.py v2.0 — test direct")
    print("  http://localhost:5001/health")
    print("  http://localhost:5001/demo")
    print("  http://localhost:5001/login\n")
    server.run(debug=True, port=5001)