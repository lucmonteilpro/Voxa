"""
Voxa — Site Scanner v1.0
=========================
Audit de crawlabilité IA d'un site web.
Vérifie si les crawlers IA (GPTBot, PerplexityBot, ClaudeBot)
peuvent accéder au site et si le balisage est optimisé.

Usage :
    python3 site_scanner.py --url https://betclic.fr
    python3 site_scanner.py --url https://betclic.fr --pages /paris-sportifs/football/ligue-1
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from urllib.parse import urljoin


AI_CRAWLERS = {
    "GPTBot":          "OpenAI (ChatGPT training + search)",
    "ChatGPT-User":    "ChatGPT search en temps réel",
    "OAI-SearchBot":   "OpenAI SearchGPT",
    "PerplexityBot":   "Perplexity AI",
    "ClaudeBot":       "Anthropic (Claude)",
    "Claude-Web":      "Claude search",
    "Googlebot":       "Google (AI Overviews + Search)",
    "Bingbot":         "Microsoft (Copilot)",
    "Meta-ExternalAgent": "Meta AI",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VoxaScanner/1.0)"}


def fetch(url: str, timeout: int = 10) -> tuple:
    """Fetch une URL. Retourne (status_code, content, error)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        return e.code, "", str(e)
    except Exception as e:
        return 0, "", str(e)


def check_robots(base_url: str) -> dict:
    """Vérifie robots.txt pour les crawlers IA."""
    url = urljoin(base_url, "/robots.txt")
    status, content, error = fetch(url)

    result = {
        "url": url,
        "status": status,
        "crawlers": {},
        "issues": [],
    }

    if status != 200:
        result["issues"].append(f"robots.txt inaccessible (HTTP {status})")
        return result

    lines = content.lower().split("\n")
    current_agents = []

    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agents = [agent]
        elif line.startswith("disallow:") and current_agents:
            path = line.split(":", 1)[1].strip()
            if path == "/" or path == "/*":
                for agent in current_agents:
                    for crawler, desc in AI_CRAWLERS.items():
                        if agent == "*" or agent == crawler.lower():
                            result["crawlers"][crawler] = {
                                "blocked": True,
                                "rule": line,
                                "description": desc,
                            }

    # Marquer les non-bloqués
    for crawler, desc in AI_CRAWLERS.items():
        if crawler not in result["crawlers"]:
            result["crawlers"][crawler] = {
                "blocked": False,
                "description": desc,
            }

    blocked = [c for c, v in result["crawlers"].items() if v["blocked"]]
    if blocked:
        result["issues"].append(f"Crawlers IA bloqués : {', '.join(blocked)}")
    else:
        result["issues"].append("✓ Aucun crawler IA bloqué")

    return result


def check_llms_txt(base_url: str) -> dict:
    """Vérifie si llms.txt existe."""
    url = urljoin(base_url, "/llms.txt")
    status, content, _ = fetch(url)
    exists = status == 200 and len(content.strip()) > 10
    return {
        "url": url,
        "exists": exists,
        "size": len(content) if exists else 0,
        "issue": "✓ llms.txt présent" if exists else "✗ Pas de llms.txt — les LLMs n'ont pas de guide pour crawler votre site",
    }


def check_sitemap(base_url: str) -> dict:
    """Vérifie le sitemap."""
    url = urljoin(base_url, "/sitemap.xml")
    status, content, _ = fetch(url)
    exists = status == 200

    n_urls = 0
    if exists:
        n_urls = content.count("<loc>")

    return {
        "url": url,
        "exists": exists,
        "n_urls": n_urls,
        "issue": f"✓ Sitemap trouvé ({n_urls} URLs)" if exists else "✗ Pas de sitemap.xml",
    }


def check_page(base_url: str, path: str = "/") -> dict:
    """Analyse une page pour le balisage IA."""
    url = urljoin(base_url, path)
    status, content, error = fetch(url)

    result = {
        "url": url,
        "status": status,
        "checks": {},
        "issues": [],
    }

    if status != 200:
        result["issues"].append(f"Page inaccessible (HTTP {status})")
        return result

    # JSON-LD
    jsonld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        content, re.DOTALL | re.IGNORECASE)

    schemas_found = []
    for block in jsonld_blocks:
        try:
            data = json.loads(block)
            schema_type = data.get("@type", "unknown")
            if isinstance(schema_type, list):
                schema_type = ", ".join(schema_type)
            schemas_found.append(schema_type)
        except json.JSONDecodeError:
            schemas_found.append("(JSON invalide)")

    result["checks"]["jsonld"] = {
        "count": len(jsonld_blocks),
        "types": schemas_found,
    }

    has_faq = "FAQPage" in str(schemas_found)
    has_org = "Organization" in str(schemas_found)

    if not jsonld_blocks:
        result["issues"].append("✗ Aucun JSON-LD trouvé — les LLMs n'ont pas de données structurées")
    else:
        result["issues"].append(f"✓ {len(jsonld_blocks)} bloc(s) JSON-LD : {', '.join(schemas_found)}")

    if not has_faq:
        result["issues"].append("✗ Pas de FAQPage Schema — c'est le format le plus impactant pour les citations IA")
    else:
        result["issues"].append("✓ FAQPage Schema présent")

    if not has_org:
        result["issues"].append("◎ Pas de Organization Schema — recommandé pour l'autorité de marque")

    # dateModified
    has_date_modified = "dateModified" in content or "datemodified" in content.lower()
    result["checks"]["dateModified"] = has_date_modified
    if not has_date_modified:
        result["issues"].append("✗ Pas de dateModified — Perplexity pénalise les contenus sans date récente")
    else:
        result["issues"].append("✓ dateModified présent")

    # Meta description
    meta_desc = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
                          content, re.IGNORECASE)
    result["checks"]["meta_description"] = bool(meta_desc)
    if meta_desc:
        desc_len = len(meta_desc.group(1))
        result["issues"].append(f"✓ Meta description ({desc_len} chars)")
    else:
        result["issues"].append("✗ Pas de meta description")

    # Canonical
    has_canonical = bool(re.search(r'<link[^>]*rel=["\']canonical["\']', content, re.IGNORECASE))
    result["checks"]["canonical"] = has_canonical

    # Temps de chargement (basique)
    import time
    t0 = time.time()
    fetch(url)
    load_time = round(time.time() - t0, 2)
    result["checks"]["load_time_s"] = load_time
    if load_time > 3:
        result["issues"].append(f"⚠ Temps de chargement élevé ({load_time}s) — les crawlers IA ont des timeouts courts")

    return result


def scan(base_url: str, pages: list = None) -> dict:
    """Scan complet d'un site."""
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    base_url = base_url.rstrip("/")

    print(f"\n{'=' * 60}")
    print(f"  VOXA — Site Scanner v1.0")
    print(f"  URL : {base_url}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 60}")

    # 1. robots.txt
    print(f"\n  ── ROBOTS.TXT ──")
    robots = check_robots(base_url)
    for crawler, info in robots["crawlers"].items():
        status = "🔴 BLOQUÉ" if info["blocked"] else "🟢 OK"
        print(f"    {status}  {crawler:20s}  ({info['description']})")
    for issue in robots["issues"]:
        print(f"    {issue}")

    # 2. llms.txt
    print(f"\n  ── LLMS.TXT ──")
    llms = check_llms_txt(base_url)
    print(f"    {llms['issue']}")

    # 3. Sitemap
    print(f"\n  ── SITEMAP ──")
    sitemap = check_sitemap(base_url)
    print(f"    {sitemap['issue']}")

    # 4. Pages
    pages_to_check = ["/"] + (pages or [])
    pages_results = []
    for page in pages_to_check:
        print(f"\n  ── PAGE : {page} ──")
        result = check_page(base_url, page)
        pages_results.append(result)
        for issue in result["issues"]:
            print(f"    {issue}")

    # Score global
    total_checks = 0
    passed_checks = 0

    # robots : pas de crawler bloqué
    blocked_ai = [c for c, v in robots["crawlers"].items()
                  if v["blocked"] and c in ["GPTBot", "ChatGPT-User", "PerplexityBot", "ClaudeBot"]]
    total_checks += 1
    if not blocked_ai:
        passed_checks += 1

    # llms.txt
    total_checks += 1
    if llms["exists"]:
        passed_checks += 1

    # sitemap
    total_checks += 1
    if sitemap["exists"]:
        passed_checks += 1

    # pages
    for pr in pages_results:
        total_checks += 3  # jsonld, faq, dateModified
        if pr["checks"].get("jsonld", {}).get("count", 0) > 0:
            passed_checks += 1
        if "FAQPage" in str(pr["checks"].get("jsonld", {}).get("types", [])):
            passed_checks += 1
        if pr["checks"].get("dateModified"):
            passed_checks += 1

    crawlability_score = round(passed_checks / total_checks * 100) if total_checks > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"  SCORE CRAWLABILITÉ IA : {crawlability_score}/100")
    print(f"  ({passed_checks}/{total_checks} vérifications passées)")

    if crawlability_score >= 70:
        print(f"  ✓ Bonne base technique — des optimisations JSON-LD restent possibles")
    elif crawlability_score >= 40:
        print(f"  ◎ Base correcte mais lacunes importantes sur le balisage")
    else:
        print(f"  ✗ Problèmes critiques de crawlabilité IA")

    print(f"{'=' * 60}\n")

    return {
        "base_url": base_url,
        "crawlability_score": crawlability_score,
        "robots": robots,
        "llms_txt": llms,
        "sitemap": sitemap,
        "pages": pages_results,
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voxa Site Scanner")
    parser.add_argument("--url", required=True, help="URL du site à scanner")
    parser.add_argument("--pages", nargs="*", default=[], help="Pages à analyser")
    args = parser.parse_args()

    scan(args.url, args.pages)