"""
Voxa — Agent SEO
================
Audit technique du site cible pour l'optimisation GEO (Generative Engine Optimization).

S'appuie sur `site_scanner.py` existant pour :
- Vérifier la crawlabilité IA (robots.txt + 9 bots IA)
- Vérifier llms.txt et sitemap
- Analyser le balisage JSON-LD, meta, FAQPage, dateModified

Ajoute une couche métier Voxa :
- Auto-résolution de l'URL par slug client (betclic → https://www.betclic.fr/)
- Cross-référence avec les angles morts du Gap Analyzer (mode couplé)
- Recommandations actionnables priorisées

Usage CLI :
    # Audit technique pur (mode standalone)
    python3 -m agents.seo_agent --slug betclic

    # Audit + cross-ref avec angles morts du Gap Analyzer
    python3 -m agents.seo_agent --slug betclic --with-gap

    # Forcer une URL personnalisée
    python3 -m agents.seo_agent --slug betclic --url https://www.betclic.fr/aide/

    # Analyser des pages additionnelles
    python3 -m agents.seo_agent --slug betclic --pages /paris-sportifs /aide/paiement

    # Dry-run (n'écrit pas en agent_runs)
    python3 -m agents.seo_agent --slug betclic --dry-run

    # Sortie JSON (pour intégration future avec orchestrateur)
    python3 -m agents.seo_agent --slug betclic --json
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from typing import Optional

from .base import Agent

# Réutilise les fonctions du site_scanner existant
# IMPORTANT : `scan()` print en console, on l'appellera dans un redirect_stdout pour
# récupérer le résultat sans pollution console
import site_scanner


# ─────────────────────────────────────────────
# URLs par défaut par slug
# Permet l'auto-résolution : --slug betclic → https://www.betclic.fr/
# Si un slug est absent ici, l'agent demandera l'URL en CLI explicite.
# ─────────────────────────────────────────────
DEFAULT_URLS = {
    "betclic":      "https://www.betclic.fr/",
    "psg":          "https://www.psg.fr/",
    "winamax":      "https://www.winamax.fr/",
    "unibet":       "https://www.unibet.fr/",
    "ephilippe":    "https://horizons-le-parti.fr/",
    "saintetienne": "https://www.asse.fr/",
    "lehavre":      "https://www.hac-foot.com/",
}


# ─────────────────────────────────────────────
# Pages stratégiques par slug
# (en plus de la home, l'agent vérifie ces pages-là par défaut)
# ─────────────────────────────────────────────
DEFAULT_PAGES_BY_SLUG = {
    "betclic": [
        "/paris-sportifs/football/",
        "/aide/",
    ],
    # Pour les autres clients, juste la home pour l'instant
}


class SEOAgent(Agent):
    """Audit technique GEO d'un site cible.

    Output structuré :
    {
        "summary": {
            "slug": "betclic",
            "target_url": "https://www.betclic.fr/",
            "crawlability_score": 78,
            "n_pages_analyzed": 3,
            "n_critical_issues": 2,
            "n_with_jsonld": 2,
            "n_with_faq": 0,
            "with_gap_xref": True/False,
        },
        "robots_txt": {...},      # raw output de site_scanner.check_robots
        "llms_txt": {...},        # raw output de site_scanner.check_llms_txt
        "sitemap": {...},         # raw output de site_scanner.check_sitemap
        "pages": [...],           # raw output de site_scanner.check_page (1 par page)
        "recommendations": [
            {
                "priority": "haute",      # haute / moyenne / info
                "category": "jsonld" | "robots" | "faq" | "metadata" | "performance",
                "title": "Ajouter un schema FAQPage sur /aide/paiement",
                "body": "Détails actionnables...",
                "linked_blind_spot": null | "regulation" | "payment" | ...,
            }
        ],
    }
    """

    name = "seo_agent"

    def __init__(self,
                 slug: str,
                 target_url: Optional[str] = None,
                 extra_pages: Optional[list] = None,
                 with_gap_xref: bool = False,
                 **kwargs):
        super().__init__(slug=slug, **kwargs)
        # Résolution de l'URL cible
        if target_url:
            self.target_url = target_url
        else:
            self.target_url = DEFAULT_URLS.get(slug)
            if not self.target_url:
                raise ValueError(
                    f"Pas d'URL par défaut pour slug='{slug}'. "
                    f"Précise --url <URL> ou ajoute le slug dans DEFAULT_URLS."
                )
        # Pages additionnelles à analyser (au-delà de la home)
        if extra_pages is None:
            extra_pages = DEFAULT_PAGES_BY_SLUG.get(slug, [])
        self.extra_pages = extra_pages
        self.with_gap_xref = with_gap_xref

    def execute(self, input_data: dict) -> dict:
        """Lance l'audit + génère les recommandations."""

        # 1) Lancer site_scanner.scan() en silenc — on capture le print pour ne pas
        #    polluer la sortie console (l'output sera affiché par notre formatteur)
        scan_result = self._run_silent_scan()

        # 2) Si mode couplé : récupère les angles morts du dernier run Gap Analyzer
        gap_blind_spots = []
        if self.with_gap_xref:
            gap_blind_spots = self._load_gap_blind_spots()

        # 3) Générer les recommandations actionnables
        recommendations = self._build_recommendations(scan_result, gap_blind_spots)

        # 4) Construire le summary
        n_pages = len(scan_result.get("pages", []))
        n_with_jsonld = sum(
            1 for p in scan_result.get("pages", [])
            if p.get("checks", {}).get("jsonld", {}).get("count", 0) > 0
        )
        n_with_faq = sum(
            1 for p in scan_result.get("pages", [])
            if "FAQPage" in str(p.get("checks", {}).get("jsonld", {}).get("types", []))
        )
        n_critical = sum(1 for r in recommendations if r["priority"] == "haute")

        summary = {
            "slug": self.slug,
            "target_url": self.target_url,
            "crawlability_score": scan_result.get("crawlability_score", 0),
            "n_pages_analyzed": n_pages,
            "n_critical_issues": n_critical,
            "n_with_jsonld": n_with_jsonld,
            "n_with_faq": n_with_faq,
            "with_gap_xref": self.with_gap_xref,
            "n_gap_blind_spots_referenced": len(gap_blind_spots),
        }

        return {
            "summary": summary,
            "robots_txt": scan_result.get("robots", {}),
            "llms_txt": scan_result.get("llms_txt", {}),
            "sitemap": scan_result.get("sitemap", {}),
            "pages": scan_result.get("pages", []),
            "recommendations": recommendations,
        }

    # ─────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────
    def _run_silent_scan(self) -> dict:
        """Lance site_scanner.scan() en redirigeant ses prints vers /dev/null.

        Permet de récupérer le dict de résultat sans pollution console.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                result = site_scanner.scan(self.target_url, pages=self.extra_pages)
            except Exception as e:
                # En cas d'erreur réseau (timeout, DNS, etc.), on retourne un résultat partiel
                return {
                    "base_url": self.target_url,
                    "crawlability_score": 0,
                    "robots": {"error": str(e), "crawlers": {}, "issues": []},
                    "llms_txt": {"exists": False, "issue": f"Scan failed: {e}"},
                    "sitemap": {"exists": False, "issue": f"Scan failed: {e}"},
                    "pages": [],
                    "scan_error": str(e),
                }
        return result

    def _load_gap_blind_spots(self) -> list:
        """Charge les angles morts du dernier run Gap Analyzer pour ce slug.

        Utilise self.get_last_run() de la classe Agent.
        """
        last = self.get_last_run("gap_analyzer")
        if not last:
            return []
        output = last.get("output", {})
        return output.get("blind_spots", [])

    def _build_recommendations(self, scan: dict, blind_spots: list) -> list:
        """Génère les recos priorisées selon le scan + (optionnellement) les angles morts."""
        recos = []

        # ── Crawlabilité (robots.txt) ──
        robots = scan.get("robots", {})
        crawlers = robots.get("crawlers", {})
        critical_bots = ["GPTBot", "ChatGPT-User", "PerplexityBot", "ClaudeBot"]
        blocked_critical = [
            bot for bot in critical_bots
            if crawlers.get(bot, {}).get("blocked", False)
        ]
        if blocked_critical:
            recos.append({
                "priority": "haute",
                "category": "robots",
                "title": f"Bloquage critique : {len(blocked_critical)} bot(s) IA majeurs bloqués",
                "body": (
                    f"robots.txt bloque actuellement : {', '.join(blocked_critical)}. "
                    f"Ces bots alimentent ChatGPT, Perplexity, Claude. "
                    f"Sans accès, votre marque ne peut pas apparaître dans leurs réponses. "
                    f"Action : retirer les Disallow concernés ou ajouter explicitement "
                    f"des User-Agent: <bot> Allow: /"
                ),
                "linked_blind_spot": None,
            })

        # ── llms.txt ──
        llms = scan.get("llms_txt", {})
        if not llms.get("exists", False):
            recos.append({
                "priority": "moyenne",
                "category": "metadata",
                "title": "Ajouter un fichier /llms.txt",
                "body": (
                    "Le fichier /llms.txt à la racine du site indique aux LLMs quelles "
                    "pages prioriser. Standard émergent (similaire à robots.txt). "
                    "Action : créer un /llms.txt listant les pages stratégiques pour la "
                    "compréhension de votre marque par les IA."
                ),
                "linked_blind_spot": None,
            })

        # ── Sitemap ──
        sitemap = scan.get("sitemap", {})
        if not sitemap.get("exists", False):
            recos.append({
                "priority": "haute",
                "category": "metadata",
                "title": "Ajouter un sitemap.xml",
                "body": (
                    "Aucun sitemap.xml détecté. Les bots IA s'appuient massivement sur "
                    "ce fichier pour découvrir le contenu. "
                    "Action : générer /sitemap.xml et le déclarer dans robots.txt."
                ),
                "linked_blind_spot": None,
            })

        # ── Pages : JSON-LD, FAQPage, dateModified ──
        for page in scan.get("pages", []):
            page_url = page.get("url", "")
            checks = page.get("checks", {})

            # JSON-LD manquant
            jsonld = checks.get("jsonld", {})
            if jsonld.get("count", 0) == 0:
                recos.append({
                    "priority": "haute",
                    "category": "jsonld",
                    "title": f"Aucun JSON-LD sur {page_url}",
                    "body": (
                        "Les LLMs s'appuient massivement sur les données structurées "
                        "JSON-LD pour comprendre une page. "
                        f"Action : ajouter au minimum un schema Organization sur {page_url}, "
                        f"plus un FAQPage si la page contient des Q&R."
                    ),
                    "linked_blind_spot": None,
                })

            # FAQPage manquant (le plus impactant)
            has_faq = "FAQPage" in str(jsonld.get("types", []))
            if not has_faq:
                recos.append({
                    "priority": "moyenne",
                    "category": "faq",
                    "title": f"Pas de FAQPage Schema sur {page_url}",
                    "body": (
                        "Le schema FAQPage est le format **le plus cité par les LLMs**. "
                        "Si la page contient des Q/R (même informelles), les structurer "
                        f"en FAQPage augmente significativement les chances d'être cité. "
                        f"Action : ajouter un schema FAQPage avec 3-5 questions sur {page_url}."
                    ),
                    "linked_blind_spot": None,
                })

            # dateModified manquant
            if not checks.get("dateModified"):
                recos.append({
                    "priority": "moyenne",
                    "category": "metadata",
                    "title": f"Pas de dateModified sur {page_url}",
                    "body": (
                        "Perplexity et autres LLMs pénalisent les contenus sans date "
                        "de mise à jour visible. "
                        f"Action : ajouter une propriété dateModified au schema JSON-LD "
                        f"de {page_url}, mise à jour automatiquement à chaque modification."
                    ),
                    "linked_blind_spot": None,
                })

            # Meta description manquante
            if not checks.get("meta_description"):
                recos.append({
                    "priority": "moyenne",
                    "category": "metadata",
                    "title": f"Meta description manquante sur {page_url}",
                    "body": (
                        "Les bots IA utilisent souvent la meta description comme résumé "
                        f"de référence. Action : rédiger une meta description de 150-160 "
                        f"chars sur {page_url}, claire et orientée vers les questions "
                        f"des utilisateurs."
                    ),
                    "linked_blind_spot": None,
                })

            # Performance
            load_time = checks.get("load_time_s", 0)
            if load_time > 3:
                recos.append({
                    "priority": "moyenne",
                    "category": "performance",
                    "title": f"Temps de chargement élevé sur {page_url} ({load_time}s)",
                    "body": (
                        "Les crawlers IA ont des timeouts courts (souvent 5-10s). "
                        f"Une page qui charge en {load_time}s risque de ne pas être "
                        f"complètement crawlée. Action : optimiser les performances "
                        f"(compression images, lazy-loading, CDN)."
                    ),
                    "linked_blind_spot": None,
                })

        # ── Cross-référencement avec les angles morts du Gap Analyzer ──
        if blind_spots:
            for bs in blind_spots:
                category = bs.get("category", "")
                prompt = bs.get("prompt", "")
                # On suggère une page dédiée selon la catégorie
                page_suggestion = self._suggest_page_for_category(category)
                recos.append({
                    "priority": "haute",
                    "category": "gap_xref",
                    "title": (
                        f"Combler l'angle mort '{bs.get('category_label', category)}' "
                        f"identifié par le Gap Analyzer"
                    ),
                    "body": (
                        f"Le Gap Analyzer a identifié un score 0/100 sur le prompt : "
                        f"\"{prompt}\". "
                        f"Action concrète : créer une page dédiée (ex : {page_suggestion}) "
                        f"avec un schema FAQPage, traitant explicitement la question. "
                        f"Vérifier que les bots IA peuvent y accéder (robots.txt) et "
                        f"que dateModified est présent."
                    ),
                    "linked_blind_spot": category,
                })

        # Tri par priorité (haute → moyenne → info)
        priority_order = {"haute": 0, "moyenne": 1, "info": 2}
        recos.sort(key=lambda r: priority_order.get(r.get("priority", "info"), 99))

        return recos

    def _suggest_page_for_category(self, category: str) -> str:
        """Suggère une URL de page à créer selon la catégorie d'angle mort."""
        suggestions = {
            "regulation": "/securite-anj/ ou /pourquoi-nous-faire-confiance/",
            "payment":    "/aide/depot-retrait/ ou /moyens-de-paiement/",
            "visibility": "/comparatif-bookmakers/",
            "brand":      "/pourquoi-betclic/",
            "odds":       "/cotes-football/ ou /cotes-meilleures/",
        }
        return suggestions.get(category, "/[page-thématique-dédiée]/")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def _format_console_output(output: dict) -> None:
    """Affiche le rapport SEO en console de façon lisible."""
    s = output["summary"]

    print()
    print("═" * 70)
    print(f"  Voxa SEO Agent — {s['slug']} ({s['target_url']})")
    print("═" * 70)
    print(f"  Score crawlabilité IA : {s['crawlability_score']}/100")
    print(f"  Pages analysées       : {s['n_pages_analyzed']}")
    print(f"  Pages avec JSON-LD    : {s['n_with_jsonld']}/{s['n_pages_analyzed']}")
    print(f"  Pages avec FAQPage    : {s['n_with_faq']}/{s['n_pages_analyzed']}")
    print(f"  Issues critiques      : {s['n_critical_issues']}")
    if s.get("with_gap_xref"):
        print(f"  Cross-ref Gap         : {s['n_gap_blind_spots_referenced']} angle(s) mort(s) référencé(s)")
    print("═" * 70)

    # Crawlers IA
    robots = output.get("robots_txt", {})
    crawlers = robots.get("crawlers", {})
    if crawlers:
        print("\nACCÈS DES CRAWLERS IA")
        print("─" * 70)
        for bot_name, info in crawlers.items():
            status = "✗ BLOQUÉ" if info.get("blocked") else "✓ OK"
            print(f"  {status:10s} {bot_name:25s} ({info.get('description', '')})")

    # Recommandations
    recos = output.get("recommendations", [])
    if recos:
        print(f"\n\nRECOMMANDATIONS ({len(recos)} au total, triées par priorité)")
        print("─" * 70)
        for i, r in enumerate(recos, 1):
            priority_icon = {
                "haute":   "🔴",
                "moyenne": "🟡",
                "info":    "🟢"
            }.get(r["priority"], "•")
            print(f"\n[{i}] {priority_icon} {r['priority'].upper()} — {r['title']}")
            if r.get("linked_blind_spot"):
                print(f"    → Lié à l'angle mort : {r['linked_blind_spot']}")
            print(f"    {r['body']}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Voxa SEO Agent — audit technique GEO du site cible",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--slug", default="betclic",
                        help="Slug client (défaut : betclic)")
    parser.add_argument("--url",
                        help="URL du site (défaut : auto-résolu depuis le slug)")
    parser.add_argument("--pages", nargs="*",
                        help="Pages additionnelles à analyser (défaut : pages stratégiques par slug)")
    parser.add_argument("--with-gap", action="store_true",
                        help="Cross-référence avec le dernier run du Gap Analyzer")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas en agent_runs (debug)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON brut")
    args = parser.parse_args()

    try:
        agent = SEOAgent(
            slug=args.slug,
            target_url=args.url,
            extra_pages=args.pages,
            with_gap_xref=args.with_gap,
        )
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    # Exécution
    print(f"⏳ Audit en cours sur {agent.target_url} ...", file=sys.stderr)

    if args.dry_run:
        try:
            agent.validate_input({})
            output = agent.execute({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            output = agent.run({})
        except Exception as e:
            print(f"✗ Erreur : {e}", file=sys.stderr)
            sys.exit(1)

    # Output
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    _format_console_output(output)


if __name__ == "__main__":
    main()