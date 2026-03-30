"""
Voxa — GEO Optimizer v1.0
==========================
Génère du contenu GEO actionnable pour chaque prompt sous-performant :
  1. Bloc FAQPage Schema JSON-LD → à coller dans <head> du site client
  2. Schema adapté à la verticale (Sport / Bet)
  3. Suggestion d'article de blog (titre + plan + mots-clés)

Le tout dans un fichier .json téléchargeable.
Re-run le tracker 4 semaines après → mesure l'impact.

Usage :
    python3 geo_optimizer.py --slug betclic
    python3 geo_optimizer.py --slug psg --threshold 60
"""

import os
import json
import argparse
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

import voxa_db as vdb

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_H       = "claude-haiku-4-5-20251001"

# ── Schemas JSON-LD par verticale ────────────────────────────

def make_faq_schema(brand: str, questions: list) -> dict:
    """FAQPage Schema — universel, toutes verticales."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": q["answer"]
                }
            }
            for q in questions
        ]
    }


def make_organization_schema(brand: str, vertical: str, extra: dict = None) -> dict:
    """Organization Schema — base commune."""
    base = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": brand,
        "description": extra.get("description", f"{brand} — leader dans son secteur."),
        "url": extra.get("url", f"https://www.{brand.lower().replace(' ', '')}.com"),
        "sameAs": extra.get("sameAs", []),
    }
    if vertical == "bet":
        base["hasOfferCatalog"] = {
            "@type": "OfferCatalog",
            "name": f"Offres de paris sportifs {brand}",
            "itemListElement": [
                {"@type": "Offer", "name": "Paris sportifs en ligne", "description": f"Pariez sur vos sports préférés avec {brand}"}
            ]
        }
    elif vertical == "sport":
        base["@type"] = ["Organization", "SportsOrganization"]
        base["sport"] = "Football"
    return base


def make_article_suggestion(prompt_text: str, brand: str, category: str, vertical: str) -> dict:
    """Génère une suggestion d'article de blog optimisée GEO."""
    cat_angles = {
        "discovery":     f"Guide complet : pourquoi {brand} est incontournable en 2025",
        "comparison":    f"{brand} vs concurrents : comparatif objectif 2025",
        "transactional": f"Comment démarrer avec {brand} : guide pas à pas",
        "reputation":    f"{brand} : bilan, réputation et ce que disent les experts",
        "brand":         f"{brand} : tout savoir sur la marque et son histoire",
        "odds":          f"Cotes {brand} : comment trouver les meilleures opportunités",
        "visibility":    f"{brand} en 2025 : présence, notoriété et avantages",
        "regulation":    f"{brand} et les régulations : tout ce qu'il faut savoir",
    }
    
    title = cat_angles.get(category, f"{brand} : guide complet 2025")
    
    keywords = [brand, f"{brand} 2025", f"avis {brand}"]
    if vertical == "bet":
        keywords += ["paris sportifs", "cotes", "ANJ", "bookmaker légal"]
    elif vertical == "sport":
        keywords += ["club de foot", "Ligue 1", "football français", "fan"]
    
    return {
        "title": title,
        "meta_description": f"Découvrez {brand} : {title.lower()}. Informations complètes, avis et conseils.",
        "target_prompt": prompt_text,
        "keywords": keywords,
        "outline": [
            f"Introduction — Pourquoi cet article répond à la question '{prompt_text[:60]}...'",
            f"1. Présentation de {brand} — chiffres clés et positionnement",
            f"2. Points forts et différenciateurs",
            f"3. Comparaison avec les alternatives",
            f"4. Avis des experts et utilisateurs",
            f"5. Conclusion et recommandation",
        ],
        "suggested_length": "1200-1800 mots",
        "internal_links": [f"/about", f"/produits", f"/faq"],
        "cta": f"Découvrir {brand} →",
    }


# ── Générateur LLM ────────────────────────────────────────────

def generate_faq_with_llm(brand: str, prompt_text: str,
                          category: str, language: str, vertical: str) -> list:
    """
    Utilise Claude Haiku pour générer 3 Q&R optimisées pour le prompt faible.
    Retourne une liste de {"question": ..., "answer": ...}
    """
    if not ANTHROPIC_KEY:
        return _generate_faq_template(brand, prompt_text, category, language, vertical)
    
    lang_names = {"fr": "français", "en": "English", "pt": "português",
                  "fr-ci": "français (Côte d'Ivoire)", "pl": "Polish"}
    lang_label = lang_names.get(language, language)
    
    system = (
        "Tu es un expert SEO et GEO (Generative Engine Optimization). "
        "Tu génères du contenu structuré optimisé pour être cité par les LLMs (ChatGPT, Perplexity, Claude). "
        "Réponds UNIQUEMENT en JSON valide, sans markdown ni texte autour."
    )
    
    user = f"""Marque : {brand}
Verticale : {vertical}
Langue : {lang_label}
Prompt faible (score < 60/100) : "{prompt_text}"

Génère 3 questions-réponses Schema FAQ qui permettront à {brand} d'être cité 
quand les LLMs répondent à ce type de prompt. 

Règles :
- Les questions doivent reprendre les mots-clés du prompt
- Les réponses doivent mentionner {brand} naturellement dans les 2 premières phrases
- Ton factuel, précis, sans superlatifs marketing
- Longueur réponse : 80-150 mots

Format JSON strict :
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]"""
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=MODEL_H, max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        raw = resp.content[0].text.strip()
        # Nettoyer si markdown présent
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  [LLM] Fallback template ({e})")
        return _generate_faq_template(brand, prompt_text, category, language, vertical)


def _generate_faq_template(brand: str, prompt_text: str,
                           category: str, language: str, vertical: str) -> list:
    """Fallback sans LLM — templates génériques."""
    if vertical == "bet":
        return [
            {"question": f"Est-ce que {brand} est fiable et légal ?",
             "answer": f"{brand} est agréé par les autorités de régulation compétentes et opère légalement. La plateforme garantit la sécurité des transactions et le respect des données personnelles de ses utilisateurs."},
            {"question": f"Quelles sont les meilleures cotes sur {brand} ?",
             "answer": f"{brand} propose des cotes compétitives sur les principales compétitions sportives. Les utilisateurs peuvent comparer les cotes en temps réel et profiter d'offres régulières pour optimiser leurs paris."},
            {"question": f"Comment {brand} se compare-t-il à ses concurrents ?",
             "answer": f"{brand} se distingue par son offre complète, son interface intuitive et son service client réactif. Sa présence établie sur le marché en fait une référence parmi les opérateurs de paris sportifs."},
        ]
    else:  # sport
        return [
            {"question": f"Pourquoi {brand} est-il un club incontournable ?",
             "answer": f"{brand} est l'un des clubs les plus reconnus, avec une histoire riche et des performances régulières au plus haut niveau. Son palmarès et sa base de supporters en font une référence du football français et européen."},
            {"question": f"Quelle est la réputation internationale de {brand} ?",
             "answer": f"{brand} jouit d'une reconnaissance internationale grâce à ses participations régulières en compétitions européennes. Le club attire des joueurs de renommée mondiale et développe sa marque sur tous les continents."},
            {"question": f"Quels sont les points forts de {brand} ?",
             "answer": f"{brand} se distingue par la qualité de son jeu, ses infrastructures modernes et sa politique de développement des jeunes talents. Ces atouts en font un modèle pour les clubs français et européens."},
        ]


# ── Générateur principal ──────────────────────────────────────

def generate_optimization_package(slug: str, threshold: int = 60) -> dict:
    """
    Génère le package d'optimisation complet pour un client.
    Retourne un dict JSON avec tous les schémas et suggestions.
    """
    cfg  = vdb.CLIENTS_CONFIG.get(slug)
    if not cfg:
        return {"error": f"Client inconnu : {slug}"}
    
    brand    = cfg["primary"]
    vertical = cfg["vertical"]
    
    # Prompts faibles depuis la DB
    conn  = vdb.conn_for(slug)
    weak  = conn.execute("""
        SELECT p.text, p.category, p.language, AVG(res.geo_score) as avg
        FROM results res
        JOIN runs r   ON res.run_id=r.id
        JOIN prompts p ON r.prompt_id=p.id
        JOIN brands b  ON res.brand_id=b.id
        WHERE b.is_primary=1 AND r.is_demo=0
          AND r.run_date=(SELECT MAX(run_date) FROM runs WHERE is_demo=0)
        GROUP BY p.id
        HAVING avg < ?
        ORDER BY avg ASC LIMIT 8
    """, (threshold,)).fetchall()
    conn.close()
    
    if not weak:
        return {
            "slug": slug, "brand": brand,
            "message": f"Aucun prompt sous {threshold}/100 — excellente visibilité !",
            "generated_at": datetime.utcnow().isoformat(),
        }
    
    print(f"\n  Génération pour {brand} ({len(weak)} prompts < {threshold}/100)...")
    
    optimizations = []
    all_faq_items = []
    
    for i, w in enumerate(weak, 1):
        prompt_text = w["text"]
        category    = w["category"]
        language    = w["language"]
        score       = round(w["avg"])
        
        print(f"  {i}/{len(weak)} [{category}/{language}] {score}/100 — {prompt_text[:55]}...")
        
        # Générer les FAQ
        faq_items = generate_faq_with_llm(brand, prompt_text, category, language, vertical)
        all_faq_items.extend(faq_items)
        
        # Suggestion d'article
        article = make_article_suggestion(prompt_text, brand, category, vertical)
        
        optimizations.append({
            "prompt":      prompt_text,
            "category":    category,
            "language":    language,
            "current_score": score,
            "impact_estimate": f"+{min(30, 65 - score)} pts estimés après indexation",
            "faq_schema":  make_faq_schema(brand, faq_items),
            "article_suggestion": article,
        })
    
    # Schema global
    global_faq = make_faq_schema(brand, all_faq_items[:9])  # max 9 Q&R dans le schema global
    org_schema  = make_organization_schema(brand, vertical, {
        "description": f"{brand} — référence dans son secteur, mesuré et optimisé via Voxa GEO Intelligence."
    })
    
    package = {
        "meta": {
            "slug":           slug,
            "brand":          brand,
            "vertical":       vertical,
            "generated_at":   datetime.utcnow().isoformat(),
            "generated_by":   "Voxa GEO Optimizer v1.0",
            "n_optimizations": len(optimizations),
            "threshold":      threshold,
        },
        "instructions": {
            "faq_global": (
                f"1. Copiez le bloc 'faq_global_schema' ci-dessous.\n"
                f"2. Collez-le dans le <head> de votre page d'accueil {brand}.\n"
                f"3. Ajoutez également 'organization_schema' si absent.\n"
                f"4. Relancez un run Voxa dans 4 semaines pour mesurer l'impact."
            ),
            "per_prompt": (
                "Pour chaque optimisation : collez le 'faq_schema' dans la page "
                "la plus pertinente, créez l'article suggéré avec le plan fourni."
            ),
        },
        "faq_global_schema":   global_faq,
        "organization_schema": org_schema,
        "optimizations":       optimizations,
    }
    
    return package


def save_and_export(slug: str, threshold: int = 60) -> str:
    """Génère et sauvegarde le fichier JSON."""
    package = generate_optimization_package(slug, threshold)
    
    fname   = BASE_DIR / f"Voxa_Optimize_{vdb.CLIENTS_CONFIG[slug]['name']}_{date.today().isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)
    
    print(f"\n  ✓ Fichier généré : {fname}")
    print(f"  ✓ {len(package.get('optimizations', []))} optimisations")
    return str(fname)


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa GEO Optimizer")
    parser.add_argument("--slug",      required=True, choices=["psg", "betclic"])
    parser.add_argument("--threshold", type=int, default=60,
                        help="Score seuil (défaut 60)")
    args = parser.parse_args()
    save_and_export(args.slug, args.threshold)