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
import re
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
import theme as T
from theme import (P, N, C1, C2, NG, BG, BG2, BG3, BD, BD2,
                   W, T2, T3, RED, GRN, GRD,
                   CSS_FLASK as CSS, LOGO_SVG, FONTS_URL,
                   score_color as sc, score_label)

# ── Flask setup ──────────────────────────────────────────────
server = Flask(__name__)
server.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

bcrypt = Bcrypt(server)
lm = LoginManager(server)
lm.login_view    = "login"
lm.login_message = "Connectez-vous pour accéder à votre espace."

MODEL_H = "claude-haiku-4-5-20251001"

# ── User model (Flask-Login) ──────────────────────────────────
class User(UserMixin):
    def __init__(self, d: dict):
        self.id       = d["id"]
        self.email    = d["email"]
        self.name     = d["name"]
        self.plan     = d.get("plan", "trial")
        self.is_admin = bool(d.get("is_admin", 0))
        self.api_key  = d.get("api_key", "")

@lm.user_loader
def load_user(uid: str):
    d = vdb.get_account_by_id(int(uid))
    return User(d) if d else None

def topbar(show_right=True):
    right = ""
    if show_right and current_user.is_authenticated:
        right = f'''<div style="display:flex;align-items:center;gap:14px;font-size:13px">
          <span style="color:{T3};font-size:12px">👋 {current_user.name.split()[0]}</span>
          <a href="/psg/"     style="color:{T2};font-weight:500">PSG</a>
          <a href="/betclic/" style="color:{T2};font-weight:500">Betclic</a>
          <a href="/demo"     style="color:{T2};font-weight:500">Demo</a>
          <a href="/settings" style="color:{T2};font-weight:500">⚙</a>
          <a href="/logout" class="btn bo bsm" style="color:{RED};border-color:rgba(255,75,110,.3)">Déconnexion</a>
        </div>'''
    elif show_right:
        right = f'''<div style="display:flex;align-items:center;gap:12px">
          <a href="/demo"         style="font-size:13px;color:{T2};font-weight:500">Demo live</a>
          <a href="/login"        style="font-size:13px;color:{T2};font-weight:500">Connexion</a>
          <a href="/contact-form" class="btn bg2 bsm">Audit gratuit →</a>
        </div>'''
    return f'''<header class="tb">
      <a href="/" class="logo">{LOGO_SVG}
        <span class="logo-text">voxa</span>
        <span class="logo-tag">GEO INTELLIGENCE</span>
      </a>{right}</header>'''

def pg(title, body):
    return f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Voxa</title>{CSS}</head><body>
{topbar()}<div style="padding:40px 24px;max-width:480px;margin:0 auto">{body}</div>
</body></html>"""

def pg_wide(title, body):
    return f"""<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Voxa</title>{CSS}</head><body>
{topbar()}<div style="padding:40px 24px;max-width:960px;margin:0 auto">{body}</div>
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
        Pas de compte ? <a href="/register" style="color:{C1};font-weight:600">Démarrer gratuitement</a>
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
        Déjà un compte ? <a href="/login" style="color:{C1};font-weight:600">Se connecter</a>
      </div>
    </div>"""
    return pg("Créer un compte", body)


@server.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@server.route("/contact-form", methods=["GET", "POST"])
def contact_form():
    """Formulaire de demande d'audit — accessible depuis le CTA bas de page."""
    if request.method == "POST":
        return redirect(url_for("contact"), code=307)  # POST → /contact

    body = f"""
    <div style="max-width:440px;margin:60px auto">
      <div style="text-align:center;margin-bottom:24px">
        <div class="lb" style="width:40px;height:40px;font-size:18px;margin:0 auto 10px">V</div>
        <div class="h1">Demander un audit gratuit</div>
        <div style="font-size:13px;color:{T3};margin-top:6px">
          Rapport PDF · 4 LLMs · Recommandations actionnables · Sous 24h
        </div>
      </div>
      <div class="card" style="padding:24px">
        <form method="POST" action="/contact">
          <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Votre marque</label>
          <input name="brand" class="fi" placeholder="PSG, Betclic, votre marque..." required autofocus>
          <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Votre nom</label>
          <input name="name" class="fi" placeholder="Prénom Nom">
          <label style="font-size:12px;font-weight:600;color:{T2};display:block;margin-bottom:5px">Email professionnel</label>
          <input name="email" type="email" class="fi" placeholder="vous@example.com" required>
          <input type="hidden" name="vertical" value="sport">
          <input type="hidden" name="score" value="">
          <button type="submit" class="btn bg2" style="margin-top:4px">
            Recevoir mon audit gratuit →
          </button>
        </form>
        <div style="text-align:center;font-size:11px;color:{T3};margin-top:12px">
          Sans engagement · Vos données vous appartiennent
        </div>
      </div>
    </div>"""
    return pg("Audit gratuit", body)


# ── DEMO PUBLIQUE ────────────────────────────────────────────

@server.route("/contact", methods=["POST"])
def contact():
    """Lead capture depuis la démo — envoie un email à Luc."""
    email  = request.form.get("email", "").strip()
    brand  = request.form.get("brand", "").strip()
    score  = request.form.get("score", "")
    vert   = request.form.get("vertical", "")
    name   = request.form.get("name", "").strip()

    if not email:
        return jsonify({"error": "Email requis"}), 400

    # Stocker le lead dans voxa_accounts.db
    try:
        c = vdb.conn_accounts()
        c.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT, name TEXT, brand TEXT,
            score TEXT, vertical TEXT,
            created_at TEXT DEFAULT (datetime('now')))""")
        c.execute("INSERT INTO leads (email,name,brand,score,vertical) VALUES (?,?,?,?,?)",
                  (email, name, brand, score, vert))
        c.commit()
        c.close()
    except Exception:
        pass

    # Email de notification
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pwd  = os.getenv("SMTP_PASSWORD", "")
    if smtp_user and smtp_pwd:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(
                f"Nouveau lead Voxa\n\n"
                f"Nom    : {name or '—'}\n"
                f"Email  : {email}\n"
                f"Marque : {brand} ({vert})\n"
                f"Score  : {score}/100\n"
                f"Date   : {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC\n",
                "plain", "utf-8"
            )
            msg["Subject"] = f"🎯 Lead Voxa — {brand} ({score}/100)"
            msg["From"]    = smtp_user
            msg["To"]      = "luc@sharper-media.com"
            with smtplib.SMTP(os.getenv("SMTP_HOST","smtp.gmail.com"),
                              int(os.getenv("SMTP_PORT","587"))) as s:
                s.starttls()
                s.login(smtp_user, smtp_pwd)
                s.sendmail(smtp_user, ["luc@sharper-media.com"], msg.as_string())
        except Exception:
            pass

    # Confirmation HTML
    body = f"""
    <div style="text-align:center;padding:60px 20px;max-width:480px;margin:0 auto">
      <div style="font-size:48px;margin-bottom:16px">✅</div>
      <div style="font-size:24px;font-weight:800;color:{N};margin-bottom:8px">Demande reçue !</div>
      <div style="font-size:14px;color:{T2};margin-bottom:24px;line-height:1.6">
        Votre audit gratuit de <strong>{brand}</strong> est en cours de préparation.
        Luc vous contacte sous 24h à <strong>{email}</strong>.
      </div>
      <div class="card" style="text-align:left;padding:16px 20px;margin-bottom:24px">
        <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:{T3};margin-bottom:10px">
          CE QUE VOUS RECEVREZ
        </div>
        {"".join(f'<div style="font-size:13px;color:{T2};margin-bottom:6px">✓ {item}</div>' for item in [
            f"GEO Score {brand} sur 4 LLMs — données réelles",
            "Benchmark vs vos concurrents directs",
            "3 recommandations actionnables prioritaires",
            "Rapport PDF complet (25 pages)",
        ])}
      </div>
      <a href="/demo" style="font-size:13px;color:{C1};font-weight:600">← Relancer une analyse</a>
    </div>"""
    return pg("Demande envoyée", body)


@server.route("/demo", methods=["GET", "POST"])
def demo():
    brand = request.form.get("brand", "").strip() if request.method == "POST" else ""
    vert  = request.form.get("vertical", "sport")
    mkt   = request.form.get("market", "fr")
    vote_html = score_html = lead_html = ""

    if brand:
        from voxa_engine import competitive_vote
        vote = competitive_vote(brand, vert, mkt)
        if vote.get("competitors"):
            chips = "".join(
                f'<span style="padding:4px 10px;background:{BG};border:1px solid {BD};'
                f'border-radius:20px;font-size:12px;color:{T2};margin:3px">{cx}</span>'
                for cx in vote["competitors"])
            vote_html = f"""<div class="card" style="margin-bottom:16px">
              <div class="lbl" style="margin-bottom:10px">CONCURRENTS DÉTECTÉS DANS L'IA · {brand.upper()}</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">{chips}</div>
              <div style="font-size:11px;color:{T3}">
                Marques les plus souvent citées avec <strong>{brand}</strong> par les LLMs.
                Voxa les tracke toutes automatiquement, chaque nuit.
              </div></div>"""

        score_html = _demo_geo_score(brand, vert, mkt)

        # Lead capture affiché après les résultats
        score_val = ""
        try:
            import re as _re
            m = _re.search(r'font-size:32px[^>]+>(\d+)', score_html)
            if m: score_val = m.group(1)
        except Exception:
            pass

        lead_html = f"""<div class="card" style="background:{N};padding:24px">
          <div style="font-weight:800;font-size:18px;color:{W};margin-bottom:4px">
            Recevoir l'audit complet de {brand} ?
          </div>
          <div style="color:rgba(255,255,255,.6);font-size:13px;margin-bottom:16px">
            Rapport PDF · 4 LLMs · {len(vote.get('competitors',[]))} concurrents trackés · Recommandations actionnables
          </div>
          <form method="POST" action="/contact" style="display:flex;flex-direction:column;gap:10px">
            <input type="hidden" name="brand"    value="{brand}">
            <input type="hidden" name="vertical" value="{vert}">
            <input type="hidden" name="score"    value="{score_val}">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
              <input name="name"  class="fi" placeholder="Prénom Nom"
                     style="margin-bottom:0;background:rgba(255,255,255,.1);
                            border-color:rgba(255,255,255,.2);color:{W}">
              <input name="email" type="email" class="fi" placeholder="vous@example.com" required
                     style="margin-bottom:0;background:rgba(255,255,255,.1);
                            border-color:rgba(255,255,255,.2);color:{W}">
            </div>
            <button type="submit" class="btn bg2"
                    style="width:100%;justify-content:center;font-size:14px;padding:12px">
              Recevoir mon audit gratuit →
            </button>
          </form>
          <div style="font-size:11px;color:rgba(255,255,255,.35);margin-top:10px;text-align:center">
            Réponse sous 24h · Sans engagement · Vos données vous appartiennent
          </div>
        </div>"""

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
      <div class="h1" style="font-size:26px;margin-bottom:6px">
        Votre marque dans ChatGPT et Perplexity
      </div>
      <div style="font-size:13px;color:{T2};margin-bottom:12px">
        Concurrents détectés + GEO Score — en 30 secondes.
      </div>
      <div style="display:inline-flex;gap:20px;font-size:12px;color:{T3}">
        <span>✓ Prompt library verticale sport/bet</span>
        <span>✓ Données propriétaires du client</span>
        <span>✓ Historique indépendant de votre agence</span>
      </div>
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

    {vote_html}{score_html}{lead_html}

    <div class="card" style="text-align:center;background:{N};padding:24px">
      <div style="font-weight:800;font-size:17px;color:{W};margin-bottom:4px">
        Tracker votre marque chaque semaine ?
      </div>
      <div style="color:rgba(255,255,255,.6);font-size:12px;margin-bottom:16px">
        Prompt library verticale · Données propriétaires · Historique indépendant de votre agence
      </div>
      <a href="/contact-form" class="btn bg2" style="width:auto;padding:10px 22px">
        Demander un audit gratuit →
      </a>
      <div style="font-size:11px;color:rgba(255,255,255,.3);margin-top:10px">
        Réponse sous 24h · Sans engagement
      </div>
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
        return f'<div class="ae inf">Mode démo — <a href="/register" style="color:{C1};font-weight:600">Créez un compte</a> pour les résultats live.</div>'
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
        f'<a href="/register" style="color:{C1};font-weight:600">Tracking complet 4 LLMs →</a></div></div>'
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

@server.route("/report/<slug>")
def download_report(slug):
    """Génère et télécharge le rapport PDF — accessible sans login."""
    from report_generator import generate_report, CLIENTS
    if slug not in CLIENTS:
        return jsonify({"error": f"Client inconnu : {slug}"}), 404
    try:
        pdf_path = generate_report(slug)
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"error": "Erreur génération PDF"}), 500
        return send_file(pdf_path, as_attachment=True,
                        download_name=os.path.basename(pdf_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route("/demo/<slug>")
def demo_client(slug):
    """Page pitch publique — sans login. URL à envoyer aux prospects."""
    cfg = vdb.CLIENTS_CONFIG.get(slug)
    if not cfg:
        return jsonify({"error": f"Client inconnu : {slug}"}), 404

    brand    = cfg["primary"]
    vertical = cfg["vertical"]

    # Data live depuis DB
    score_g  = vdb.get_score(slug)
    markets  = vdb.get_score_by_market(slug)
    comps    = vdb.get_competitors(slug, top=8)
    nss      = vdb.get_nss(slug)
    history  = vdb.get_history(slug, n_weeks=8)

    # Couleur score
    def sc_hex(s):
        if s is None: return T3
        return NG if s >= 70 else (C1 if s >= 45 else RED)

    # KPI hero
    score_val  = score_g["score"] or 0
    score_col  = sc_hex(score_val)
    score_lbl  = "Excellent" if score_val >= 70 else ("Moyen" if score_val >= 45 else "Faible")
    nss_col    = NG if nss >= 0 else RED

    lang_flags = {"fr":"🇫🇷","en":"🇬🇧","pt":"🇵🇹","pl":"🇵🇱","fr-ci":"🇨🇮"}

    # Marché cards
    mkt_cards = "".join(f"""
      <div style="background:{BG3};border:1px solid {BD};border-radius:10px;
                  padding:14px 16px;text-align:center;flex:1;min-width:80px">
        <div style="font-size:18px;margin-bottom:4px">{lang_flags.get(m['language'],'🌐')}</div>
        <div style="font-size:24px;font-weight:800;color:{sc_hex(m['score'])}">{m['score']}</div>
        <div style="font-size:10px;color:{T3};font-weight:700;letter-spacing:1px">/100</div>
        <div style="font-size:10px;color:{T3};margin-top:2px">{m['language'].upper()}</div>
      </div>
    """ for m in markets)

    # Concurrent bars (anonymisés sauf la marque primaire)
    def comp_bar(name, score, is_primary):
        col   = C1 if is_primary else T3
        label = name if is_primary else f"Concurrent {name[0]}."
        pct   = int(score)
        return f"""
      <div style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px">
          <span style="font-size:12px;font-weight:{'800' if is_primary else '500'};
                       color:{col}">{label}</span>
          <span style="font-size:12px;font-weight:700;color:{sc_hex(score)}">{score}/100</span>
        </div>
        <div style="height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden">
          <div style="height:100%;width:{pct}%;background:{'linear-gradient(90deg,'+C1+','+C2+')' if is_primary else 'rgba(90,122,138,0.4)'};
                      border-radius:3px;transition:width 0.8s"></div>
        </div>
      </div>"""

    comp_bars = "".join(comp_bar(c["name"], c["score"], c["is_primary"]) for c in comps)

    # Évolution
    hist_points = ""
    if len(history) > 1:
        max_s = max(h["score"] for h in history) or 100
        w = 100 / max(len(history) - 1, 1)
        pts = " ".join(f"{i*w:.1f},{100 - h['score']}" for i, h in enumerate(history))
        hist_points = f"""
        <svg viewBox="0 0 100 100" preserveAspectRatio="none"
             style="width:100%;height:80px;overflow:visible">
          <defs>
            <linearGradient id="hg" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="{C1}" stop-opacity="0.8"/>
              <stop offset="100%" stop-color="{C2}" stop-opacity="0.8"/>
            </linearGradient>
            <linearGradient id="hgf" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="{C1}" stop-opacity="0.15"/>
              <stop offset="100%" stop-color="{C1}" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <polyline points="{pts}" fill="none" stroke="url(#hg)"
                    stroke-width="2" vector-effect="non-scaling-stroke"/>
        </svg>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:{T3}">
          <span>{history[0]['date']}</span><span>{history[-1]['date']}</span>
        </div>"""

    body = f"""
    <!-- HERO -->
    <div style="text-align:center;padding:40px 24px 32px;
                background:linear-gradient(180deg,rgba(0,229,255,0.04) 0%,transparent 100%);
                border-bottom:1px solid {BD}">
      <div style="font-size:10px;font-weight:700;letter-spacing:3px;
                  color:{T3};margin-bottom:12px">GEO INTELLIGENCE · RAPPORT CLIENT</div>
      <div style="font-size:36px;font-weight:800;color:{W};margin-bottom:4px">{brand}</div>
      <div style="font-size:13px;color:{T3};margin-bottom:28px">
        Visibilité IA mesurée sur {score_g['n_prompts']} prompts · {score_g['run_date']}
      </div>

      <!-- KPI principal -->
      <div style="display:inline-flex;align-items:baseline;gap:6px;
                  padding:20px 40px;background:{BG3};border:1px solid {BD};
                  border-radius:16px;box-shadow:0 0 40px rgba(0,229,255,0.08)">
        <span style="font-size:72px;font-weight:900;line-height:1;
                     color:{score_col};font-family:Inter,sans-serif">{score_val}</span>
        <div>
          <div style="font-size:18px;color:{T3};font-weight:600">/100</div>
          <div style="font-size:12px;font-weight:700;color:{score_col};
                      margin-top:4px">{score_lbl}</div>
        </div>
        <div style="margin-left:24px;text-align:left;border-left:1px solid {BD};padding-left:24px">
          <div style="font-size:22px;font-weight:800;color:{nss_col}">{nss:+d}%</div>
          <div style="font-size:10px;color:{T3};font-weight:700;letter-spacing:1px">NET SENTIMENT</div>
        </div>
      </div>
    </div>

    <!-- MARCHÉS -->
    <div style="padding:28px 24px">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;
                  color:{T3};margin-bottom:14px">SCORE PAR MARCHÉ</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">{mkt_cards}</div>
    </div>

    <!-- BENCHMARK + ÉVOLUTION -->
    <div style="padding:0 24px 28px;display:grid;grid-template-columns:1fr 1fr;gap:16px">

      <!-- Benchmark -->
      <div style="background:{BG3};border:1px solid {BD};border-radius:12px;padding:20px">
        <div style="font-size:10px;font-weight:700;letter-spacing:2px;
                    color:{T3};margin-bottom:16px">BENCHMARK CONCURRENTS</div>
        {comp_bars}
        <div style="font-size:10px;color:{T3};margin-top:8px;font-style:italic">
          Les concurrents sont anonymisés dans cette vue publique.
        </div>
      </div>

      <!-- Évolution -->
      <div style="background:{BG3};border:1px solid {BD};border-radius:12px;padding:20px">
        <div style="font-size:10px;font-weight:700;letter-spacing:2px;
                    color:{T3};margin-bottom:16px">ÉVOLUTION GEO SCORE</div>
        {"" if not hist_points else hist_points}
        {"<div style='color:"+T3+";font-size:12px'>Historique insuffisant — premier run récent.</div>" if not hist_points else ""}
      </div>
    </div>

    <!-- MOAT + CTA -->
    <div style="margin:0 24px 32px;background:{N};border:1px solid rgba(0,229,255,0.15);
                border-radius:12px;padding:28px;text-align:center;
                box-shadow:0 0 40px rgba(0,229,255,0.06)">
      <div style="font-size:18px;font-weight:800;color:{W};margin-bottom:8px">
        Voir le dashboard complet ?
      </div>
      <div style="font-size:13px;color:{T3};margin-bottom:6px">
        4 LLMs · {len(markets)} marchés · alertes automatiques · recommandations actionnables
      </div>
      <div style="display:flex;gap:16px;justify-content:center;
                  font-size:11px;color:{T3};margin-bottom:20px">
        <span>✓ Prompt library verticale {vertical}</span>
        <span>✓ Données propriétaires</span>
        <span>✓ Historique indépendant de votre agence</span>
      </div>
      <a href="/contact-form" style="display:inline-block;padding:12px 28px;
         background:linear-gradient(135deg,{C1},{C2});color:{BG};
         font-weight:800;font-size:14px;border-radius:8px;text-decoration:none">
        Demander un accès complet →
      </a>
      <div style="font-size:11px;color:{T3};margin-top:10px">
        Réponse sous 24h · Sans engagement
      </div>
    </div>

    <!-- FOOTER -->
    <div style="padding:16px 24px;border-top:1px solid {BD};
                display:flex;justify-content:space-between;font-size:11px;color:{T3}">
      <span>Voxa GEO Intelligence · <a href="mailto:luc@sharper-media.com"
            style="color:{C1}">luc@sharper-media.com</a></span>
      <span>Données au {score_g['run_date']} · Confidentiel</span>
    </div>"""

    return pg_wide(f"Voxa · {brand} · GEO Score", body)


@server.route("/admin/new-client", methods=["GET", "POST"])
@login_required
def admin_new_client():
    """Onboarding web — crée une config JSON + lance le premier run automatiquement."""
    if not current_user.is_admin:
        return redirect("/settings")

    msg = ""
    if request.method == "POST":
        slug         = re.sub(r'[^a-z0-9_-]', '', request.form.get("slug","").lower().strip())
        client_name  = request.form.get("client_name","").strip()
        primary      = request.form.get("primary_brand","").strip()
        vertical     = request.form.get("vertical","sport")
        markets_raw  = request.form.get("markets","fr").strip()
        comps_raw    = request.form.get("competitors","").strip()

        if not all([slug, client_name, primary]):
            msg = "Slug, nom client et marque primaire sont requis."
        else:
            markets = [m.strip() for m in markets_raw.split(",") if m.strip()]
            cfg = {
                "slug":          slug,
                "client_name":   client_name,
                "primary_brand": primary,
                "vertical":      vertical,
                "markets":       markets,
                "competitors":   {},
            }
            # Parser les concurrents (format: fr:Winamax,Bet365|en:Unibet)
            if comps_raw:
                for part in comps_raw.split("|"):
                    if ":" in part:
                        lang, comps_str = part.split(":", 1)
                        cfg["competitors"][lang.strip()] = [
                            c.strip() for c in comps_str.split(",") if c.strip()
                        ]
                    else:
                        for m in markets:
                            cfg["competitors"][m] = [
                                c.strip() for c in comps_raw.split(",") if c.strip()
                            ]
                        break

            # Sauvegarder la config
            import pathlib
            config_dir = pathlib.Path(BASE_DIR) / "configs"
            config_dir.mkdir(exist_ok=True)
            config_path = config_dir / f"{slug}.json"
            with open(config_path, "w") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            # Lancer un premier run démo en arrière-plan
            import threading
            def first_run():
                try:
                    import tracker_generic as tg
                    tg.run_tracker(cfg, demo_mode=True)
                    print(f"  ✓ Premier run démo terminé pour {client_name}")
                except Exception as e:
                    print(f"  ✗ Erreur premier run : {e}")
            threading.Thread(target=first_run, daemon=True).start()

            msg = f"ok:{slug}"

    # Lister les configs existantes
    import pathlib, json as _json
    config_dir = pathlib.Path(BASE_DIR) / "configs"
    config_dir.mkdir(exist_ok=True)
    existing = []
    for p in sorted(config_dir.glob("*.json")):
        try:
            c = _json.load(open(p))
            existing.append({"slug": c.get("slug",""), "name": c.get("client_name",""),
                             "vertical": c.get("vertical",""), "markets": c.get("markets",[])})
        except Exception:
            pass

    existing_rows = "".join(f"""
    <tr style="border-bottom:1px solid {BD}">
      <td style="padding:10px 14px;font-weight:700;color:{C1}">{e['slug']}</td>
      <td style="padding:10px 14px;color:{W}">{e['name']}</td>
      <td style="padding:10px 14px;color:{T2}">{e['vertical']}</td>
      <td style="padding:10px 14px;color:{T3}">{', '.join(e['markets'])}</td>
      <td style="padding:10px 14px">
        <a href="/demo/{e['slug']}" style="color:{C1};font-size:12px">Pitch →</a>
      </td>
    </tr>""" for e in existing)

    success_block = ""
    if msg.startswith("ok:"):
        new_slug = msg[3:]
        success_block = f"""<div class="ae ok" style="margin-bottom:20px">
          ✓ Client créé — premier run démo en cours.
          <a href="/demo/{new_slug}" style="color:{NG};font-weight:700;margin-left:8px">
            Voir la page pitch →
          </a>
        </div>"""
    elif msg:
        success_block = f'<div class="ae err">{msg}</div>'

    body = f"""
    <div style="margin-bottom:28px">
      <div class="lbl" style="margin-bottom:6px">ADMIN</div>
      <div class="h1">Ajouter un client</div>
      <div style="font-size:13px;color:{T3};margin-top:4px">
        Crée la config, génère la prompt library, lance le premier run.
      </div>
    </div>

    {success_block}

    <div class="card" style="margin-bottom:24px">
      <form method="POST" style="display:flex;flex-direction:column;gap:14px">
        <div class="g2">
          <div>
            <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                          margin-bottom:5px;letter-spacing:1px">SLUG (identifiant)</label>
            <input name="slug" class="fi" style="margin-bottom:0"
                   placeholder="reims, monaco, rcsa..." required>
            <div style="font-size:10px;color:{T3};margin-top:4px">
              Minuscules, sans espaces. Ex: stade-reims
            </div>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                          margin-bottom:5px;letter-spacing:1px">NOM CLIENT</label>
            <input name="client_name" class="fi" style="margin-bottom:0"
                   placeholder="Stade de Reims" required>
          </div>
        </div>
        <div class="g2">
          <div>
            <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                          margin-bottom:5px;letter-spacing:1px">MARQUE PRIMAIRE</label>
            <input name="primary_brand" class="fi" style="margin-bottom:0"
                   placeholder="Stade de Reims" required>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                          margin-bottom:5px;letter-spacing:1px">VERTICALE</label>
            <select name="vertical" class="fs" style="margin-bottom:0">
              <option value="sport">⚽ Sport</option>
              <option value="bet">🎰 Betting</option>
              <option value="politics">🗳 Politics</option>
            </select>
          </div>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                        margin-bottom:5px;letter-spacing:1px">MARCHÉS</label>
          <input name="markets" class="fi" style="margin-bottom:0"
                 value="fr" placeholder="fr, en, pt...">
          <div style="font-size:10px;color:{T3};margin-top:4px">
            Séparés par des virgules. Codes : fr, en, pt, pl, fr-ci
          </div>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:{T3};display:block;
                        margin-bottom:5px;letter-spacing:1px">CONCURRENTS</label>
          <input name="competitors" class="fi" style="margin-bottom:0"
                 placeholder="RC Lens, Metz, Troyes ou fr:Winamax,Bet365|pt:Betway">
          <div style="font-size:10px;color:{T3};margin-top:4px">
            Simple : liste séparée par virgules (même pour tous les marchés)<br>
            Avancé : fr:Winamax,Bet365|pt:Betway,Placard
          </div>
        </div>
        <button type="submit" class="btn bg2" style="margin-top:4px">
          Créer le client et lancer le premier run →
        </button>
      </form>
    </div>

    <div style="margin-bottom:12px">
      <div class="lbl">CLIENTS CONFIGURÉS ({len(existing)})</div>
    </div>
    <div class="card">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="border-bottom:2px solid {BD}">
            {"".join(f'<th style="padding:8px 14px;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:{T3};text-align:left">{h}</th>' for h in ["Slug","Client","Vertical","Marchés","Pitch"])}
          </tr>
        </thead>
        <tbody>{existing_rows}</tbody>
      </table>
    </div>"""

    return pg_wide("Admin · Nouveau client", body)


@server.route("/optimize/<slug>")
def download_optimize(slug):
    """Génère et télécharge le package JSON-LD/FAQ — sans login."""
    from geo_optimizer import save_and_export
    if slug not in vdb.CLIENTS_CONFIG:
        return jsonify({"error": f"Client inconnu : {slug}"}), 404
    try:
        threshold = request.args.get("threshold", 60, type=int)
        path = save_and_export(slug, threshold)
        if not path or not os.path.exists(path):
            return jsonify({"error": "Erreur génération"}), 500
        return send_file(path, as_attachment=True,
                        download_name=os.path.basename(path),
                        mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
              <a href="/psg/" style="font-size:12px;font-weight:600;color:{W};
                   background:{BG3};border:1px solid {BD};padding:4px 10px;border-radius:6px">PSG →</a>
              <a href="/betclic/" style="font-size:12px;font-weight:600;color:{W};
                   background:{BG3};border:1px solid {BD};padding:4px 10px;border-radius:6px">Betclic →</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Rapports & Optimisation -->
    <div class="card" style="margin-bottom:18px">
      <div style="padding:20px 24px">
        <div class="lbl" style="margin-bottom:16px">RAPPORTS & OPTIMISATION GEO</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          {"".join(f'''
          <div style="background:{BG};border:1px solid {BD};border-radius:10px;padding:16px">
            <div style="font-weight:700;font-size:14px;color:{W};margin-bottom:4px">{cfg["name"]}</div>
            <div style="font-size:11px;color:{T3};margin-bottom:12px">{cfg["vertical"].title()} · {", ".join(cfg["markets"][:2]).upper()}</div>
            <div style="display:flex;flex-direction:column;gap:8px">
              <a href="/report/{slug}" style="display:block;text-align:center;padding:7px 12px;
                   background:{BG3};border:1px solid {BD};border-radius:8px;
                   font-size:12px;font-weight:600;color:{T2};text-decoration:none">
                📋 Rapport PDF
              </a>
              <a href="/optimize/{slug}" style="display:block;text-align:center;padding:7px 12px;
                   background:linear-gradient(135deg,{C1}15,{C2}15);
                   border:1px solid {C1}40;border-radius:8px;
                   font-size:12px;font-weight:600;color:{C1};text-decoration:none">
                ⚡ Package JSON-LD/FAQ
              </a>
            </div>
          </div>
          ''' for slug, cfg in vdb.CLIENTS_CONFIG.items())}
        </div>
        <div style="font-size:11px;color:{T3};margin-top:12px">
          Le package JSON-LD/FAQ contient les schémas Schema.org prêts à coller sur votre site + suggestions d'articles.
          Relancez un tracker 4 semaines après pour mesurer l'impact.
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
                  style="border:none;background:{C1};color:white;padding:5px 12px;
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