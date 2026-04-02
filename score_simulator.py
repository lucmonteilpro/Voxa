"""
Voxa — Score Simulator v1.0
=============================
Pré-teste du contenu GEO sur les LLMs AVANT publication.
Deux méthodes combinées :
  1. Directe  → itération rapide (le LLM évalue le contenu)
  2. Réaliste → validation finale (le LLM répond au prompt avec le contenu injecté)

Usage :
    from score_simulator import simulate, simulate_and_iterate

    # Test simple
    result = simulate("Quel site de paris est le plus fiable ?",
                      "<faq>Betclic est agréé ANJ...</faq>",
                      brand="Betclic")

    # Test avec itération automatique (jusqu'à score cible)
    result = simulate_and_iterate(
        prompt="Quel site de paris est le plus fiable ?",
        brand="Betclic",
        vertical="bet",
        target_score=70,
        max_iterations=5)
"""

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("voxa.simulator")

BASE_DIR = Path(__file__).parent.resolve()

ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")

MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_GPT   = "gpt-4o-mini"


# ─────────────────────────────────────────────
# SCORING (même logique que le tracker)
# ─────────────────────────────────────────────

POS_WORDS = {
    "bet":      ["fiable", "sécurisé", "agréé", "recommandé", "meilleur", "leader",
                 "reconnu", "sérieux", "réputé", "certifié", "légal", "officiel",
                 "reliable", "secure", "licensed", "recommended", "best", "leading"],
    "sport":    ["meilleur", "recommandé", "excellent", "top", "incontournable",
                 "référence", "populaire", "champion", "best", "leading", "top-tier"],
    "politics": ["influent", "reconnu", "populaire", "crédible", "incontournable",
                 "leader", "important", "influential", "credible"],
}

NEG_WORDS = {
    "bet":      ["illégal", "frauduleux", "risqué", "éviter", "interdit", "arnaque",
                 "illegal", "fraudulent", "risky", "avoid", "banned", "scam"],
    "sport":    ["relégué", "mauvais", "décevant", "faible", "problème",
                 "relegated", "poor", "disappointing", "weak"],
    "politics": ["controversé", "scandale", "condamné", "extrémiste", "marginal",
                 "controversial", "scandal", "convicted", "extremist"],
}


def _score_response(response: str, brand: str, vertical: str = "bet") -> dict:
    """Score une réponse LLM avec la même formule que le tracker.
    Retourne un dict avec mentioned, position, sentiment, geo_score.
    """
    resp_lower = response.lower()
    brand_lower = brand.lower()

    # Présence (40 pts)
    occ = resp_lower.count(brand_lower)
    mentioned = occ > 0

    # Position (30 pts) — dans le premier tiers
    first_idx = resp_lower.find(brand_lower)
    early = mentioned and first_idx <= len(resp_lower) // 3

    # Sentiment (20 pts) — fenêtre 150 chars autour, SEULEMENT si mentionné
    pos_w = POS_WORDS.get(vertical, POS_WORDS["bet"])
    neg_w = NEG_WORDS.get(vertical, NEG_WORDS["bet"])
    sentiment = "neutral"
    if mentioned:
        start = max(0, first_idx - 100)
        end = first_idx + len(brand_lower) + 100
        ctx = resp_lower[start:end]
        sent_p = any(w in ctx for w in pos_w)
        sent_n = any(w in ctx for w in neg_w)
        if sent_p and not sent_n:
            sentiment = "positive"
        elif sent_n:
            sentiment = "negative"

    # Fréquence (10 pts)
    frequent = occ >= 2

    geo_score = max(0, min(100,
        (40 if mentioned else 0) +
        (30 if early else 0) +
        (20 if sentiment == "positive" else (-10 if sentiment == "negative" else 0)) +
        (10 if frequent else 0)
    ))

    return {
        "mentioned": mentioned,
        "mention_count": occ,
        "position": "early" if early else ("late" if mentioned else None),
        "sentiment": sentiment,
        "geo_score": geo_score,
    }


# ─────────────────────────────────────────────
# MÉTHODE DIRECTE — le LLM évalue le contenu
# ─────────────────────────────────────────────

DIRECT_SYSTEM = """Tu es un expert en évaluation de contenu web pour les moteurs de réponse IA.
Tu reçois un contenu web et un prompt utilisateur.
Tu dois évaluer si un moteur IA (ChatGPT, Perplexity, Claude) citerait ce contenu
pour répondre au prompt.

Réponds UNIQUEMENT en JSON valide :
{
  "score": <0-100>,
  "would_cite": <true/false>,
  "reason": "<1 phrase>",
  "improvements": ["<suggestion 1>", "<suggestion 2>"]
}"""

DIRECT_USER = """Contenu web proposé :
---
{content}
---

Prompt utilisateur : "{prompt}"

Marque à évaluer : {brand}

Évalue : ce contenu permettrait-il à {brand} d'être cité positivement dans la réponse d'un LLM à ce prompt ?"""


def simulate_direct(prompt: str, content: str, brand: str,
                    llm: str = "claude") -> dict:
    """Méthode directe : le LLM évalue si le contenu serait cité.
    Rapide (~0.5s), utile pour itérer sur des variantes.
    """
    user_msg = DIRECT_USER.format(content=content, prompt=prompt, brand=brand)

    try:
        raw = call_llm(DIRECT_SYSTEM, user_msg, llm=llm, max_tokens=300)
        # Parser le JSON
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
        result["method"] = "direct"
        result["llm"] = llm
        return result
    except Exception as e:
        log.warning(f"simulate_direct error: {e}")
        return {"score": 0, "would_cite": False, "reason": str(e),
                "improvements": [], "method": "direct", "llm": llm}


# ─────────────────────────────────────────────
# MÉTHODE RÉALISTE — le LLM répond au prompt
# ─────────────────────────────────────────────

REALISTIC_SYSTEM = """Tu es un assistant IA qui répond aux questions des utilisateurs.
Tu as accès aux sources web suivantes pour construire ta réponse :

--- SOURCE WEB ---
{content}
--- FIN SOURCE ---

Utilise cette source si elle est pertinente pour répondre à la question.
Réponds de façon factuelle et concise. Cite les marques et sites pertinents."""


def simulate_realistic(prompt: str, content: str, brand: str,
                       vertical: str = "bet", llm: str = "claude") -> dict:
    """Méthode réaliste : le LLM répond au prompt avec le contenu injecté.
    Score calculé avec la même formule que le tracker → comparable au score réel.
    """
    system = REALISTIC_SYSTEM.format(content=content)

    try:
        response = call_llm(system, prompt, llm=llm, max_tokens=400)
        scores = _score_response(response, brand, vertical)
        scores["method"] = "realistic"
        scores["llm"] = llm
        scores["response_preview"] = response[:300]
        return scores
    except Exception as e:
        log.warning(f"simulate_realistic error: {e}")
        return {"geo_score": 0, "mentioned": False, "method": "realistic",
                "llm": llm, "error": str(e)}


# ─────────────────────────────────────────────
# SIMULATION COMBINÉE (direct + réaliste)
# ─────────────────────────────────────────────

def simulate(prompt: str, content: str, brand: str,
             vertical: str = "bet", llms: list = None) -> dict:
    """Simulation combinée : directe pour le feedback + réaliste pour le score fiable.

    Retourne :
        score_direct     : évaluation du LLM (0-100)
        score_realistic  : score GEO calculé avec la formule tracker (0-100)
        improvements     : suggestions d'amélioration (du mode direct)
        details          : résultats détaillés par LLM
    """
    llms = llms or ["claude"]
    results = {"details": [], "improvements": set()}

    direct_scores = []
    realistic_scores = []

    for llm in llms:
        # Direct (rapide, itération)
        d = simulate_direct(prompt, content, brand, llm=llm)
        direct_scores.append(d.get("score", 0))
        for imp in d.get("improvements", []):
            results["improvements"].add(imp)
        results["details"].append(d)

        # Réaliste (score comparable au tracker)
        r = simulate_realistic(prompt, content, brand, vertical=vertical, llm=llm)
        realistic_scores.append(r.get("geo_score", 0))
        results["details"].append(r)

    results["score_direct"] = round(sum(direct_scores) / len(direct_scores)) if direct_scores else 0
    results["score_realistic"] = round(sum(realistic_scores) / len(realistic_scores)) if realistic_scores else 0
    results["score_predicted"] = results["score_realistic"]  # le score qu'on montre au client
    results["improvements"] = list(results["improvements"])
    results["prompt"] = prompt
    results["brand"] = brand
    results["n_llms"] = len(llms)
    results["timestamp"] = datetime.utcnow().isoformat()

    return results


# ─────────────────────────────────────────────
# ITÉRATION AUTOMATIQUE (self-eval loop)
# ─────────────────────────────────────────────

IMPROVE_SYSTEM = """Tu es un expert GEO (Generative Engine Optimization).
Tu reçois un contenu web qui a obtenu un score insuffisant pour être cité par les LLMs.

Tu dois réécrire ce contenu pour maximiser les chances qu'un LLM cite la marque {brand}
quand un utilisateur pose la question : "{prompt}"

Règles :
- Mentionne {brand} dans les 2 premières phrases
- Ton factuel, pas marketing
- Inclure des chiffres ou preuves concrètes
- Longueur : 150-300 mots
- Ne produis QUE le contenu amélioré, pas de commentaire"""


def simulate_and_iterate(prompt: str, brand: str, vertical: str = "bet",
                         initial_content: str = None,
                         target_score: int = 70,
                         max_iterations: int = 5,
                         llms: list = None) -> dict:
    """Boucle d'itération : génère/améliore du contenu jusqu'au score cible.

    1. Génère ou prend le contenu initial
    2. Simule (direct + réaliste)
    3. Si score < cible → demande au LLM d'améliorer
    4. Re-simule → jusqu'à score ≥ cible ou max itérations

    Retourne le meilleur contenu trouvé + historique des itérations.
    """
    llms = llms or ["claude"]

    # Contenu initial (généré si non fourni)
    if not initial_content:
        initial_content = _generate_initial_content(prompt, brand, vertical)

    iterations = []
    best_content = initial_content
    best_score = 0
    current_content = initial_content

    for i in range(max_iterations):
        # Simuler
        sim = simulate(prompt, current_content, brand, vertical, llms)
        score = sim["score_predicted"]

        iterations.append({
            "iteration": i + 1,
            "score_predicted": score,
            "score_direct": sim["score_direct"],
            "content_preview": current_content[:200],
            "improvements": sim["improvements"],
        })

        log.info(f"  Iteration {i+1}/{max_iterations}: score={score} (cible={target_score})")

        # Garder le meilleur
        if score > best_score:
            best_score = score
            best_content = current_content

        # Score atteint ?
        if score >= target_score:
            log.info(f"  ✓ Score cible atteint en {i+1} itérations")
            break

        # Améliorer pour la prochaine itération
        if i < max_iterations - 1:
            improve_prompt = IMPROVE_SYSTEM.format(brand=brand, prompt=prompt)
            feedback = "\n".join(f"- {imp}" for imp in sim["improvements"]) or "Score trop bas"

            improved = call_llm(
                improve_prompt,
                f"Contenu actuel (score {score}/100) :\n---\n{current_content}\n---\n\n"
                f"Feedback :\n{feedback}\n\nRéécris pour viser {target_score}/100.",
                llm="claude", max_tokens=500
            )
            if improved and len(improved.strip()) > 50:
                current_content = improved.strip()

    return {
        "prompt": prompt,
        "brand": brand,
        "vertical": vertical,
        "target_score": target_score,
        "best_score": best_score,
        "best_content": best_content,
        "n_iterations": len(iterations),
        "target_reached": best_score >= target_score,
        "iterations": iterations,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _generate_initial_content(prompt: str, brand: str, vertical: str) -> str:
    """Génère un contenu FAQ initial pour un prompt donné."""
    system = (
        f"Tu es un expert en contenu web optimisé pour les moteurs IA. "
        f"Écris un paragraphe FAQ de 150-200 mots qui répond à la question posée "
        f"en mentionnant {brand} de façon factuelle dans les 2 premières phrases. "
        f"Ton professionnel. Pas de markdown. Texte brut uniquement."
    )
    try:
        return call_llm(system, prompt, llm="claude", max_tokens=400)
    except Exception:
        return f"{brand} est une référence dans son secteur. Pour répondre à la question '{prompt}', {brand} se distingue par son expertise et sa fiabilité reconnue."


# ─────────────────────────────────────────────
# LLM CALLERS
# ─────────────────────────────────────────────

def call_llm(system: str, user: str, llm: str = "claude",
              max_tokens: int = 400) -> str:
    """Appelle un LLM et retourne le texte de la réponse."""
    if llm == "claude":
        return _call_claude(system, user, max_tokens)
    elif llm == "gpt":
        return _call_gpt(system, user, max_tokens)
    else:
        return _call_claude(system, user, max_tokens)


def _call_claude(system: str, user: str, max_tokens: int = 400) -> str:
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY manquante")
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model=MODEL_HAIKU, max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return resp.content[0].text


def _call_gpt(system: str, user: str, max_tokens: int = 400) -> str:
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY manquante")
    import openai
    client = openai.OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model=MODEL_GPT, max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return resp.choices[0].message.content


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Voxa Score Simulator")
    parser.add_argument("--prompt", required=True, help="Prompt à simuler")
    parser.add_argument("--brand", required=True, help="Marque à traquer")
    parser.add_argument("--vertical", default="bet", choices=["sport", "bet", "politics"])
    parser.add_argument("--content", default=None, help="Contenu à tester (sinon auto-généré)")
    parser.add_argument("--iterate", action="store_true", help="Mode itération automatique")
    parser.add_argument("--target", type=int, default=70, help="Score cible (défaut: 70)")
    parser.add_argument("--max-iter", type=int, default=5, help="Max itérations (défaut: 5)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"\n{'='*60}")
    print(f"  VOXA — Score Simulator v1.0")
    print(f"  Prompt : {args.prompt[:60]}...")
    print(f"  Marque : {args.brand}")
    print(f"  Mode   : {'Itération (target={args.target})' if args.iterate else 'Simple'}")
    print(f"{'='*60}\n")

    if args.iterate:
        result = simulate_and_iterate(
            prompt=args.prompt, brand=args.brand, vertical=args.vertical,
            initial_content=args.content,
            target_score=args.target, max_iterations=args.max_iter)

        print(f"\n  Résultat :")
        print(f"  Score final  : {result['best_score']}/100 (cible: {args.target})")
        print(f"  Itérations   : {result['n_iterations']}")
        print(f"  Cible atteinte : {'✓' if result['target_reached'] else '✗'}")
        print(f"\n  Contenu optimisé :")
        print(f"  {result['best_content'][:500]}")
        for it in result["iterations"]:
            print(f"\n  --- Itération {it['iteration']} (score: {it['score_predicted']}) ---")
            for imp in it.get("improvements", []):
                print(f"    → {imp}")
    else:
        content = args.content or _generate_initial_content(args.prompt, args.brand, args.vertical)
        result = simulate(args.prompt, content, args.brand, args.vertical)

        print(f"  Score direct    : {result['score_direct']}/100")
        print(f"  Score réaliste  : {result['score_realistic']}/100")
        print(f"  Score prédit    : {result['score_predicted']}/100")
        if result["improvements"]:
            print(f"\n  Améliorations suggérées :")
            for imp in result["improvements"]:
                print(f"    → {imp}")

    print(f"\n{'='*60}\n")