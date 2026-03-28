"""
Voxa Engine v1.0
================
1. competitive_vote  — détecte les concurrents IA d'une marque
2. AlertEngine       — détecte chutes de score + surpassement concurrent
3. RecoEngine        — génère recommandations Sport/Bet (Politics = mesure seule)

Usage :
    python3 voxa_engine.py --vote --brand PSG --vertical sport
    python3 voxa_engine.py --alerts
    python3 voxa_engine.py --recos
    python3 voxa_engine.py --all   # scheduler cron
"""

import os
import re
import argparse
import smtplib
from datetime import datetime, date
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).parent.resolve()

import voxa_db as vdb

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_H = "claude-haiku-4-5-20251001"


# ── 1. COMPETITIVE INTELLIGENCE VOTE ────────────────────────

VOTE_PROMPTS = {
    "sport": {
        "fr": "Quels clubs de football ou organisations sportives cites-tu le plus souvent avec {brand} ? Liste uniquement les noms, séparés par des virgules.",
        "en": "What sports clubs or organizations do you most often mention alongside {brand}? Names only, comma-separated.",
        "pt": "Quais clubes são mais frequentemente mencionados com {brand}? Apenas nomes, separados por vírgulas.",
    },
    "bet": {
        "fr": "Quels sites de paris sportifs cites-tu le plus souvent avec {brand} ? Noms uniquement, séparés par des virgules.",
        "en": "What sports betting sites do you most often mention alongside {brand}? Names only, comma-separated.",
        "pt": "Quais sites de apostas mencionas mais com {brand}? Apenas nomes, separados por vírgulas.",
    },
    "politics": {
        "fr": "Quels partis ou candidats cites-tu le plus souvent avec {brand} ? Noms uniquement, séparés par des virgules.",
        "en": "What political parties or candidates do you most often mention alongside {brand}? Names only, comma-separated.",
    },
}

_MOCK_COMPETITORS = {
    "sport":    ["Real Madrid","Manchester City","Bayern Munich","PSG","Barcelona","OL"],
    "bet":      ["Winamax","Bet365","FDJ","PMU","Unibet","1xBet"],
    "politics": ["La France Insoumise","Les Républicains","Parti Socialiste","Rassemblement National"],
}


def competitive_vote(brand: str, vertical: str = "sport", market: str = "fr") -> dict:
    """
    Envoie 1 prompt à Claude → retourne les concurrents détectés.
    Coût : ~0.001$. Endpoint public sur /api/v1/vote.
    """
    if not ANTHROPIC_KEY:
        mocks = [c for c in _MOCK_COMPETITORS.get(vertical, []) if brand.lower() not in c.lower()]
        return {"brand": brand, "vertical": vertical, "market": market,
                "competitors": mocks[:6], "llm": "mock", "cost_usd": 0.0}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        lang = market.split("-")[0] if "-" in market else market
        tpls = VOTE_PROMPTS.get(vertical, VOTE_PROMPTS["sport"])
        tpl  = tpls.get(lang, tpls.get("fr", ""))
        text = tpl.format(brand=brand)

        resp = client.messages.create(
            model=MODEL_H, max_tokens=200,
            messages=[{"role":"user","content":text}])
        raw = resp.content[0].text.strip()
        competitors = [
            c.strip().strip("•-–").strip()
            for c in re.split(r"[,\n;]", raw)
            if c.strip() and len(c.strip()) > 1 and brand.lower() not in c.lower()
        ][:10]
        return {
            "brand": brand, "vertical": vertical, "market": market,
            "competitors": competitors, "raw": raw, "llm": "claude-haiku",
            "cost_usd": round((resp.usage.input_tokens*0.0000008 +
                               resp.usage.output_tokens*0.000004), 5),
        }
    except Exception as e:
        return {"brand": brand, "competitors": [], "error": str(e)}


# ── 2. ALERT ENGINE ──────────────────────────────────────────

class AlertEngine:
    def __init__(self):
        pass

    def check_all(self) -> dict:
        results = {}
        for slug in vdb.CLIENTS_CONFIG:
            results[slug] = self.check(slug)
        return results

    def check(self, slug: str) -> list:
        alerts = []
        alerts += self._check_score_drop(slug)
        alerts += self._check_competitor_surge(slug)
        return alerts

    def _check_score_drop(self, slug: str) -> list:
        hist = vdb.get_history(slug, n_weeks=2)
        if len(hist) < 2:
            return []
        latest = hist[-1]["score"]; prev = hist[-2]["score"]
        drop = prev - latest
        if drop >= 15:
            cfg = vdb.CLIENTS_CONFIG[slug]
            created = vdb.create_alert(
                slug, "drop", "critical",
                f"Chute GEO Score — {cfg['name']}",
                f"Score passé de {prev} à {latest} (-{drop} pts) entre "
                f"{hist[-2]['date']} et {hist[-1]['date']}."
            )
            if created:
                _send_alert_email(slug, f"Chute GEO Score — {cfg['name']}",
                    f"Score passé de {prev} à {latest} (-{drop} pts).")
                return [{"type":"drop","severity":"critical","slug":slug}]
        return []

    def _check_competitor_surge(self, slug: str) -> list:
        comps = vdb.get_competitors(slug)
        primary = next((c for c in comps if c["is_primary"]), None)
        if not primary:
            return []
        primary_score = primary["score"]
        alerts = []
        for c in comps:
            if not c["is_primary"] and c["score"] > primary_score + 5:
                cfg = vdb.CLIENTS_CONFIG[slug]
                created = vdb.create_alert(
                    slug, "competitor", "warning",
                    f"{c['name']} vous dépasse",
                    f"{c['name']} score {c['score']}/100 vs votre {primary_score}/100."
                )
                if created:
                    alerts.append({"type":"competitor","severity":"warning","slug":slug})
        return alerts


def _send_alert_email(slug: str, title: str, body: str):
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pwd  = os.getenv("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pwd:
        print(f"  [ALERT no SMTP] {title}")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚠ Voxa Alert · {title}"
        msg["From"]    = smtp_user
        msg["To"]      = smtp_user
        msg.attach(MIMEText(f"<b>{title}</b><br>{body}", "html", "utf-8"))
        with smtplib.SMTP(os.getenv("SMTP_HOST","smtp.gmail.com"),
                          int(os.getenv("SMTP_PORT","587"))) as s:
            s.starttls(); s.login(smtp_user, smtp_pwd)
            s.sendmail(smtp_user, [smtp_user], msg.as_string())
    except Exception as e:
        print(f"  [ALERT email failed] {e}")


# ── 3. RECO ENGINE ───────────────────────────────────────────

RECO_TEMPLATES = {
    "discovery": {
        "title": "Enrichir votre page principale pour les LLMs",
        "body":  "Ajoutez un paragraphe structuré (200-300 mots) résumant votre marque, vos valeurs et vos distinctions clés. Les LLMs s'appuient sur les pages principales pour répondre aux requêtes de découverte. Format : définition + chiffres clés + positionnement concurrentiel.",
        "impact": 12.0, "category": "content",
    },
    "comparison": {
        "title": "Créer une page de comparaison dédiée",
        "body":  "Les prompts comparatifs sont ceux où vous perdez le plus de points. Créez une page /vs-[concurrent] qui compare objectivement votre offre. Les LLMs citent massivement les pages de comparaison bien structurées.",
        "impact": 18.0, "category": "content",
    },
    "transactional": {
        "title": "Schema Product/Event sur vos pages de conversion",
        "body":  "Ajoutez le balisage Schema adapté à votre verticale (SportsEvent/Offer pour le sport, Organization/hasOfferCatalog pour le betting). Ce balisage est lu en priorité par les LLMs pour les requêtes d'achat.",
        "impact": 20.0, "category": "schema",
    },
    "reputation": {
        "title": "Générer des sources tierces citables",
        "body":  "Les LLMs construisent leurs réponses réputation depuis les sources web disponibles. Ciblez 2-3 articles/mois dans des médias reconnus (L'Équipe, SportsPro, iGaming Business) avec votre marque en titre.",
        "impact": 22.0, "category": "pr",
    },
    "brand": {
        "title": "Page dédiée crédibilité et agréments",
        "body":  "Créez une page /agréments ou /à-propos listant vos licences (ANJ, SRIJ, etc.) avec numéros et dates. Les LLMs citent en priorité les informations officielles pour les requêtes de confiance.",
        "impact": 25.0, "category": "content",
    },
    "odds": {
        "title": "Page cotes et comparatif tarifaire",
        "body":  "Créez une page de présentation de vos cotes sur les compétitions majeures (Ligue 1, Champions League, CAN). Format structuré avec Schema priceRange. Les LLMs citent les pages qui répondent directement à 'meilleures cotes'.",
        "impact": 18.0, "category": "schema",
    },
}
RECO_DEFAULT = {
    "title": "Optimiser le contenu pour les requêtes IA",
    "body":  "Vérifiez que la réponse à ce type de prompt existe clairement sur votre site (FAQ, article, page dédiée). Les LLMs ne citent que ce qu'ils trouvent.",
    "impact": 10.0, "category": "content",
}


class RecoEngine:

    THRESHOLD = 60  # prompts avec score < 60 → candidats reco

    def generate_all(self) -> dict:
        results = {}
        for slug in vdb.CLIENTS_CONFIG:
            if vdb.CLIENTS_CONFIG[slug]["vertical"] == "politics":
                print(f"  [{slug}] Politics — mesure seule, pas d'optimisation")
                continue
            results[slug] = self.generate(slug)
        return results

    def generate(self, slug: str) -> list:
        cfg = vdb.CLIENTS_CONFIG.get(slug)
        if not cfg or cfg["vertical"] == "politics":
            return []

        weak = vdb.get_weak_prompts(slug, threshold=self.THRESHOLD)
        created = []
        for p in weak:
            tpl = RECO_TEMPLATES.get(p["category"], RECO_DEFAULT)
            # Enrichir avec Claude si disponible
            body = _enrich_reco(cfg["name"], p["text"], p["category"], tpl["body"])
            priority = "high" if p["score"] < 30 else "medium"
            rid = vdb.create_recommendation(
                slug=slug,
                title=tpl["title"],
                body=body,
                category=tpl["category"],
                priority=priority,
                impact_score=tpl["impact"],
                prompt_text=p["text"],
            )
            created.append({"id": rid, "title": tpl["title"],
                            "score": p["score"], "priority": priority})
        return created


def _enrich_reco(brand: str, prompt_text: str, category: str, base_body: str) -> str:
    """Enrichit la reco générique avec du contexte spécifique (optionnel)."""
    if not ANTHROPIC_KEY:
        return base_body
    try:
        import anthropic
        api = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = api.messages.create(
            model=MODEL_H, max_tokens=300,
            system="Expert GEO. Donne une recommandation courte (150 mots max), très concrète, adaptée à la marque. Texte simple, pas de markdown.",
            messages=[{"role":"user","content":
                f"Marque: {brand}\nPrompt sous-performant: '{prompt_text}'\n"
                f"Catégorie: {category}\nBase: {base_body}\n\n"
                "Adapte avec des exemples spécifiques à cette marque."}])
        return resp.content[0].text.strip()
    except Exception:
        return base_body


# ── RUNNER PRINCIPAL (cron) ──────────────────────────────────

def run_all():
    print(f"\n{'='*55}")
    print(f"  VOXA ENGINE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    ae = AlertEngine()
    re = RecoEngine()

    for slug, cfg in vdb.CLIENTS_CONFIG.items():
        print(f"\n  [{cfg['vertical'].upper()}] {cfg['name']}")

        alerts = ae.check(slug)
        print(f"    🔔 {len(alerts)} alerte(s)")
        for a in alerts:
            print(f"       {a['severity']} — {a['type']}")

        if cfg["vertical"] != "politics":
            recos = re.generate(slug)
            print(f"    💡 {len(recos)} recommandation(s)")
        else:
            print(f"    ℹ Politics : mesure seule")

    print(f"\n{'='*55}\n")


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Voxa Engine")
    p.add_argument("--vote",    action="store_true")
    p.add_argument("--alerts",  action="store_true")
    p.add_argument("--recos",   action="store_true")
    p.add_argument("--all",     action="store_true")
    p.add_argument("--brand",   default="PSG")
    p.add_argument("--vertical",default="sport")
    p.add_argument("--market",  default="fr")
    p.add_argument("--slug",    default="psg")
    args = p.parse_args()

    if args.vote:
        res = competitive_vote(args.brand, args.vertical, args.market)
        print(f"\n  Competitive vote — {args.brand}")
        for i, c in enumerate(res.get("competitors", []), 1):
            print(f"    {i}. {c}")
        print(f"  Cost: ${res.get('cost_usd',0)}")

    elif args.alerts:
        ae = AlertEngine()
        alerts = ae.check(args.slug)
        print(f"\n  Alertes [{args.slug}]: {len(alerts)}")
        for a in alerts: print(f"    {a}")

    elif args.recos:
        re = RecoEngine()
        recos = re.generate(args.slug)
        print(f"\n  Recommandations [{args.slug}]: {len(recos)}")
        for r in recos: print(f"    [{r['priority']}] {r['title']}")

    elif args.all:
        run_all()

    else:
        p.print_help()