"""
Voxa — Crawler Perplexity (UI mode, patchright)
================================================
Implémentation production-ready du crawler Perplexity en mode UI.

Stack technique :
- patchright (fork de Playwright) pour bypass Cloudflare bot detection
- channel="chrome" : utilise Google Chrome installé localement (signature plus
  authentique que Chromium bundled)
- Session persistante : cookies sauvegardés entre runs dans
  crawlers/sessions/perplexity_patchright/

Sélecteurs Perplexity 2026 (validés via diagnostic) :
- Input box        : div[contenteditable="true"][role="textbox"]
- Stop streaming   : button[aria-label*="Arrêter"] (FR) / aria-label*="Stop" (EN)
- Sources          : bouton "Liens" → liste des <a href> externes
- Réponse texte    : div[class*="prose"] dans main

Login :
- Au 1er run, te laisse 90s pour login Google/Apple/Email manuel
- Cookies persistés → connexion automatique aux runs suivants
- Mode anonyme limité à ~3-5 prompts puis Perplexity force le signup

Usage standalone :
    python3 -m crawlers.perplexity "Mon prompt"
    python3 -m crawlers.perplexity "Mon prompt" --headless

Usage programmatique :
    from crawlers.perplexity import PerplexityCrawler
    with PerplexityCrawler() as c:
        result = c.query("Quels sont les meilleurs sites de paris ?", language="fr")
        print(result.response_text)
        print(f"{len(result.sources)} sources")
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from .base import LLMCrawler, CrawlerResult, CrawlerSource


# ─────────────────────────────────────────────
# Sélecteurs DOM (centralisés pour maintenance facile)
# ─────────────────────────────────────────────
SEL_INPUT_BOX = 'div[contenteditable="true"][role="textbox"]'
SEL_RESPONSE_PROSE = 'div[class*="prose"]'

# Bouton stop : multi-lingue
SEL_STOP_BUTTON_FR = 'button[aria-label*="Arrêter"]'
SEL_STOP_BUTTON_EN = 'button[aria-label*="Stop"]'

# Onglet "Liens" : multi-lingue
SEL_LINKS_TAB_FR = 'button:has-text("Liens")'
SEL_LINKS_TAB_EN = 'button:has-text("Sources")'

# Détection signup wall (Perplexity force login après mode anonyme épuisé)
SEL_SIGNUP_WALL = (
    'text=Inscrivez-vous, '
    'text=Sign up below, '
    'button:has-text("Continuer avec Google")'
)

# Détection user logué : présence d'un avatar/menu
SEL_USER_LOGGED_IN = (
    '[data-testid="user-avatar"], '
    'button[aria-label*="profile"], '
    'button[aria-label*="account"], '
    'button[aria-label*="compte"]'
)


class PerplexityCrawler(LLMCrawler):
    name = "perplexity"
    base_url = "https://www.perplexity.ai"

    # Délais (en ms / secondes selon contexte)
    WAIT_AFTER_TYPE = 800
    WAIT_AFTER_LOAD = 2000             # laisse le JS se monter
    WAIT_FOR_RESPONSE_END_S = 90       # max attendu pour fin génération
    WAIT_AFTER_LINKS_CLICK = 2000      # laisse l'onglet Liens charger
    LOGIN_GRACE_SECONDS = 90

    # ─────────────────────────────────────────────
    # Override : utiliser patchright + Chrome stable
    # ─────────────────────────────────────────────
    def _get_sync_playwright(self):
        """Utilise patchright (anti-Cloudflare) au lieu de playwright standard."""
        from patchright.sync_api import sync_playwright
        return sync_playwright

    def _get_launch_kwargs(self) -> dict:
        """Override pour utiliser channel='chrome' (Google Chrome stable installé)."""
        return {
            "user_data_dir": str(self.session_dir),
            "headless": self.headless,
            "channel": "chrome",  # IMPORTANT pour patchright vs Cloudflare
            "viewport": {"width": 1280, "height": 900},
        }

    # ─────────────────────────────────────────────
    # Login flow
    # ─────────────────────────────────────────────
    def _ensure_logged_in(self) -> None:
        """Vérifie le login. Si signup wall et mode headed, attend login manuel."""
        page = self._page
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(self.WAIT_AFTER_LOAD)

        # Cas 1 : déjà loggué
        if self._is_user_logged_in():
            print(f"[{self.name}] ✓ Loggué via session persistée")
            return

        # Cas 2 : pas de signup wall, accès UI possible (mode anonyme)
        if not self._is_signup_wall() and self._has_input_box():
            print(f"[{self.name}] ✓ Mode anonyme (input accessible)")
            return

        # Cas 3 : signup wall en mode headless → impossible de continuer
        if self.headless:
            raise RuntimeError(
                f"[{self.name}] Signup wall en mode headless. "
                "Lance d'abord en mode headed pour faire le login manuel."
            )

        # Cas 4 : signup wall en mode headed → attends login manuel
        print(f"[{self.name}] ⚠ Signup wall détectée, login manuel requis")
        print(f"[{self.name}] → Connecte-toi dans la fenêtre Chromium "
              f"(Google/Apple/Email)")
        print(f"[{self.name}] → Tu as {self.LOGIN_GRACE_SECONDS}s. "
              f"Le script reprend automatiquement.\n")

        deadline = time.time() + self.LOGIN_GRACE_SECONDS
        while time.time() < deadline:
            time.sleep(5)
            remaining = int(deadline - time.time())
            if self._is_user_logged_in():
                print(f"[{self.name}] ✓ Connexion détectée")
                page.wait_for_timeout(self.WAIT_AFTER_LOAD)
                return
            if not self._is_signup_wall() and self._has_input_box():
                print(f"[{self.name}] ✓ Accès UI rétabli")
                return
            print(f"[{self.name}]   ... {remaining}s restantes")

        # Si on arrive ici, login non effectué dans le délai imparti
        raise RuntimeError(
            f"[{self.name}] Login non effectué dans le délai de "
            f"{self.LOGIN_GRACE_SECONDS}s"
        )

    def _is_user_logged_in(self) -> bool:
        try:
            return self._page.locator(SEL_USER_LOGGED_IN).count() > 0
        except Exception:
            return False

    def _is_signup_wall(self) -> bool:
        try:
            return self._page.locator(SEL_SIGNUP_WALL).count() > 0
        except Exception:
            return False

    def _has_input_box(self) -> bool:
        try:
            return self._page.locator(SEL_INPUT_BOX).count() > 0
        except Exception:
            return False

    # ─────────────────────────────────────────────
    # Query flow
    # ─────────────────────────────────────────────
    def _do_query(self, prompt: str, language: Optional[str] = None) -> CrawlerResult:
        page = self._page

        # 1) Navigate vers la home pour partir d'un état propre
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(self.WAIT_AFTER_LOAD)

        # 2) Type le prompt
        try:
            input_box = page.locator(SEL_INPUT_BOX).first
            input_box.wait_for(state="visible", timeout=10_000)
            input_box.click()
            page.wait_for_timeout(300)
            page.keyboard.type(prompt)
            page.wait_for_timeout(self.WAIT_AFTER_TYPE)
            page.keyboard.press("Enter")
        except Exception as e:
            return CrawlerResult(
                prompt=prompt,
                response_text="",
                error=f"Erreur envoi prompt : {e}",
                screenshot_path=self._save_screenshot("error_send"),
            )

        # 3) Attendre la fin de la génération
        self._wait_for_response_complete(language)

        # 4) Extraire la réponse
        response_text = self._extract_response_text()

        # 5) Extraire les sources via l'onglet "Liens"
        sources = self._extract_sources_via_links_tab(language)

        # 6) Screenshot pour audit
        screenshot_path = self._save_screenshot("response")

        # 7) Détecter le modèle utilisé (best effort)
        model_used = self._detect_model_used()

        return CrawlerResult(
            prompt=prompt,
            response_text=response_text,
            sources=sources,
            model_used=model_used,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        )

    # ─────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────
    def _wait_for_response_complete(self, language: Optional[str] = None) -> None:
        """Attend la disparition du bouton 'Arrêter la réponse' (= fin streaming).

        Stratégie en 2 phases :
        - Phase 1 (max 10s) : attendre que le bouton stop apparaisse
          (= streaming démarré)
        - Phase 2 (max WAIT_FOR_RESPONSE_END_S) : attendre qu'il disparaisse
          (= streaming fini)
        """
        page = self._page

        # On accepte FR + EN par défaut (Perplexity est localisé selon l'user)
        stop_selectors = [SEL_STOP_BUTTON_FR, SEL_STOP_BUTTON_EN]

        def stop_visible() -> bool:
            for sel in stop_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        # Phase 1 : attendre l'apparition du bouton stop
        deadline_start = time.time() + 10
        streaming_started = False
        while time.time() < deadline_start:
            if stop_visible():
                streaming_started = True
                break
            time.sleep(0.3)

        if not streaming_started:
            # Le bouton n'est jamais apparu : peut-être réponse instantanée
            # ou erreur. On attend juste un peu et on continue.
            page.wait_for_timeout(2000)
            return

        # Phase 2 : attendre la disparition du bouton stop
        deadline_end = time.time() + self.WAIT_FOR_RESPONSE_END_S
        while time.time() < deadline_end:
            if not stop_visible():
                page.wait_for_timeout(1500)  # stabilisation DOM
                return
            time.sleep(0.5)

        print(f"[{self.name}] ⚠ Timeout {self.WAIT_FOR_RESPONSE_END_S}s sur "
              f"fin de génération")

    def _extract_response_text(self) -> str:
        """Extrait le texte de la réponse depuis le conteneur prose."""
        page = self._page
        try:
            prose = page.locator(SEL_RESPONSE_PROSE).first
            if prose.count() > 0:
                txt = prose.inner_text(timeout=5000).strip()
                if txt and len(txt) > 50:
                    return txt
        except Exception:
            pass
        # Fallback sur main article
        try:
            article = page.locator('main article').first
            if article.count() > 0:
                return article.inner_text(timeout=5000).strip()
        except Exception:
            pass
        return ""

    def _extract_sources_via_links_tab(
        self, language: Optional[str] = None
    ) -> list[CrawlerSource]:
        """Clique sur l'onglet 'Liens' et extrait les sources avec URLs réelles.

        Perplexity 2026 ne met plus les sources dans le texte de la réponse
        (juste des badges "domaine+N"). Les vraies URLs sont dans l'onglet
        séparé "Liens" / "Sources".
        """
        page = self._page
        sources: list[CrawlerSource] = []

        # 1) Trouver et cliquer sur le bouton "Liens" (FR ou EN)
        clicked = False
        for sel in [SEL_LINKS_TAB_FR, SEL_LINKS_TAB_EN]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            # Pas d'onglet Liens trouvé : peut-être réponse sans sources
            return sources

        page.wait_for_timeout(self.WAIT_AFTER_LINKS_CLICK)

        # 2) Extraire tous les <a href> externes maintenant visibles
        try:
            links_data = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href^="http"]');
                    const externals = [];
                    for (const a of links) {
                        if (a.href.includes('perplexity.ai')) continue;
                        externals.push({
                            url: a.href,
                            text: (a.innerText || '').trim().slice(0, 200),
                            title: a.getAttribute('title'),
                        });
                    }
                    return externals;
                }
            """)
        except Exception:
            return sources

        # 3) Construire les CrawlerSource (dédup par URL)
        seen = set()
        for link in links_data:
            url = link.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(CrawlerSource(
                url=url,
                title=(link.get("title") or link.get("text") or "")[:200] or None,
                position=len(sources) + 1,
            ))

        return sources

    def _detect_model_used(self) -> Optional[str]:
        """Tente de détecter quel modèle Perplexity a utilisé."""
        page = self._page
        try:
            # Le bouton "Modèle" affiche parfois le nom à côté
            for label in ["Sonar", "GPT-5", "GPT-4", "Claude", "Grok", "Gemini"]:
                if page.locator(f'text="{label}"').count() > 0:
                    return f"perplexity-{label.lower().replace(' ', '-')}"
        except Exception:
            pass
        return "perplexity-default"

    def _save_screenshot(self, suffix: str = "") -> Optional[Path]:
        """Sauvegarde un screenshot pleine page. Best effort."""
        try:
            path = self.screenshot_path_for(suffix)
            self._page.screenshot(path=str(path), full_page=True)
            return path
        except Exception as e:
            print(f"[{self.name}] ⚠ Screenshot KO: {e}")
            return None


# ─────────────────────────────────────────────
# Override session_dir pour utiliser le dossier patchright dédié
# ─────────────────────────────────────────────
# On override __init__ pour que la session par défaut soit la session
# patchright (différente de la session Playwright standard)
_original_init = PerplexityCrawler.__init__


def _patched_init(self, headless=False, session_dir=None,
                   screenshot_dir=None, timeout_ms=60_000, slow_mo_ms=50):
    if session_dir is None:
        # Force le session_dir spécifique patchright
        session_dir = (
            Path(__file__).parent.resolve() / "sessions" / "perplexity_patchright"
        )
    _original_init(
        self,
        headless=headless,
        session_dir=session_dir,
        screenshot_dir=screenshot_dir,
        timeout_ms=timeout_ms,
        slow_mo_ms=slow_mo_ms,
    )


PerplexityCrawler.__init__ = _patched_init


# ─────────────────────────────────────────────
# CLI standalone (pour test rapide)
# ─────────────────────────────────────────────
def _main():
    """Test rapide depuis la ligne de commande.

    Usage :
        python3 -m crawlers.perplexity "Mon prompt ici"
        python3 -m crawlers.perplexity "Mon prompt ici" --headless
    """
    if len(sys.argv) < 2:
        print('Usage: python3 -m crawlers.perplexity "prompt" [--headless]')
        sys.exit(1)

    prompt = sys.argv[1]
    headless = "--headless" in sys.argv
    language = None
    # Détection naïve de la langue depuis le prompt (pour les sélecteurs)
    if any(c in prompt.lower() for c in ["é", "è", "ê", "à", "ç", "quel", "comment"]):
        language = "fr"

    print(f"[POC] Crawler Perplexity, headless={headless}")
    print(f"[POC] Prompt: {prompt}")
    print(f"[POC] Language: {language or 'auto'}\n")

    with PerplexityCrawler(headless=headless) as crawler:
        result = crawler.query(prompt, language=language)

    print("\n" + "=" * 70)
    print(f"SUCCESS    : {result.is_success}")
    print(f"Duration   : {result.crawl_duration_ms} ms")
    print(f"Model      : {result.model_used}")
    print(f"Screenshot : {result.screenshot_path}")
    if result.error:
        print(f"Error      : {result.error}")
    print("=" * 70)
    print(f"\nRESPONSE ({len(result.response_text)} chars):")
    preview = result.response_text[:1500]
    print(preview + ("..." if len(result.response_text) > 1500 else ""))
    print("\n" + "=" * 70)
    print(f"SOURCES ({len(result.sources)}):")
    for s in result.sources:
        print(f"  [{s.position:2}] {s.domain or '?':35s} {s.url[:60]}")
        if s.title:
            print(f"       → {s.title[:80]}")


if __name__ == "__main__":
    _main()