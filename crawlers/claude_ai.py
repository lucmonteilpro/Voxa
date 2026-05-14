"""
Voxa — Crawler Claude.ai (UI mode, patchright)
===============================================
Crawler Claude.ai en mode UI via Chromium natif Patchright.

Stack technique :
- patchright (anti-détection) avec Chromium natif (pas Chrome, pour
  éviter le conflit single-instance avec Chrome principal ouvert)
- Session persistante : cookies sauvegardés dans
  crawlers/sessions/claude_ai_patchright/
- Modèle forcé : Sonnet 4.6 (Adaptatif = web search automatique)

Sélecteurs Claude.ai 2026 (validés via diagnostic DOM 2026-05-13) :
- Input box        : [data-testid="chat-input"] (contenteditable, ProseMirror)
- Envoi            : Enter (pas de bouton Send dédié)
- Sélecteur modèle : [data-testid="model-selector-dropdown"]
                     aria-label="Modèle : Sonnet 4.6 Adaptatif"
- Web Search       : automatique en mode "Adaptatif" (pas de toggle)
- Stop streaming   : button[aria-label*="Arrêter"] (FR) / "Stop" (EN)
- Réponse texte    : div[class*="progressive-markdown"]
- Sources          : accordéon button[aria-expanded] dans la réponse,
                     contient les URLs dans un div.overflow-hidden

Login :
- Au 1er run, laisse 300s pour login Google OAuth / email manuel
- Cookies persistés → connexion automatique aux runs suivants

Usage standalone :
    python3 -m crawlers.claude_ai "Mon prompt"
    python3 -m crawlers.claude_ai "Mon prompt" --headless

Usage programmatique :
    from crawlers.claude_ai import ClaudeAICrawler
    with ClaudeAICrawler() as c:
        result = c.query("Quels sont les meilleurs sites de paris ?", language="fr")
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from .base import LLMCrawler, CrawlerResult, CrawlerSource


# ─────────────────────────────────────────────
# Sélecteurs DOM claude.ai (validés 2026-05-13)
# ─────────────────────────────────────────────
SEL_CHAT_INPUT = '[data-testid="chat-input"]'
SEL_MODEL_DROPDOWN = '[data-testid="model-selector-dropdown"]'
SEL_STOP_BUTTON_FR = 'button[aria-label*="Arrêter"]'
SEL_STOP_BUTTON_EN = 'button[aria-label*="Stop"]'
SEL_RESPONSE_CONTAINER = 'div[class*="font-claude-response"]'
SEL_RESPONSE_MARKDOWN = 'div[class*="progressive-markdown"]'
SEL_ACCORDION_BUTTON = 'button[aria-expanded]'
SEL_USER_MENU = '[data-testid="user-menu-button"]'

# ─────────────────────────────────────────────
# Configuration modèle
# ─────────────────────────────────────────────
DEFAULT_MODEL_TO_FORCE = "Sonnet 4.6"
FALLBACK_MODEL_LABEL = "claude-fallback"

# ─────────────────────────────────────────────
# Timing
# ─────────────────────────────────────────────
WAIT_AFTER_LOAD = 3000
WAIT_AFTER_TYPE = 800
WAIT_FOR_RESPONSE_END_S = 120
WAIT_AFTER_ACCORDION_CLICK = 2000
LOGIN_GRACE_SECONDS = 300


class ClaudeAICrawler(LLMCrawler):
    name = "claude-ai"
    base_url = "https://claude.ai"

    # ─────────────────────────────────────────────
    # Override : Chromium natif via patchright
    # ─────────────────────────────────────────────
    def _get_sync_playwright(self):
        """Utilise patchright au lieu de playwright standard."""
        from patchright.sync_api import sync_playwright
        return sync_playwright

    def _get_launch_kwargs(self) -> dict:
        """Chromium natif (pas channel='chrome') pour éviter le conflit
        single-instance avec Chrome principal ouvert."""
        return {
            "user_data_dir": str(self.session_dir),
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 900},
        }

    # ─────────────────────────────────────────────
    # Login flow
    # ─────────────────────────────────────────────
    def _ensure_logged_in(self) -> None:
        """Vérifie le login. Si pas loggué, attend login manuel."""
        page = self._page
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(WAIT_AFTER_LOAD)

        if self._has_chat_input():
            print(f"[{self.name}] ✓ Loggué via session persistée")
            return

        if self.headless:
            raise RuntimeError(
                f"[{self.name}] Pas loggué en mode headless. "
                "Lance d'abord en mode headed pour le login manuel."
            )

        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║  ÉTAPE LOGIN — Voxa attend ta connexion à claude.ai          ║")
        print("║                                                              ║")
        print("║  → Fenêtre Chromium ouverte sur claude.ai                    ║")
        print("║  → Connecte-toi (Google OAuth ou email/password)             ║")
        print("║  → Le script reprend automatiquement dès qu'il détecte       ║")
        print("║    que tu es dans l'interface principale                     ║")
        print("║                                                              ║")
        print(f"║  Timeout : {LOGIN_GRACE_SECONDS} secondes"
              f"{' ' * (47 - len(str(LOGIN_GRACE_SECONDS)))}║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        deadline = time.time() + LOGIN_GRACE_SECONDS
        while time.time() < deadline:
            time.sleep(2)
            if self._has_chat_input():
                print(f"[{self.name}] ✓ Login détecté")
                page.wait_for_timeout(2000)
                return
            remaining = int(deadline - time.time())
            if remaining % 30 < 2:
                print(f"[{self.name}]   ... {remaining}s restantes")

        raise RuntimeError(
            f"[{self.name}] Login non effectué dans {LOGIN_GRACE_SECONDS}s"
        )

    def _has_chat_input(self) -> bool:
        try:
            return self._page.locator(SEL_CHAT_INPUT).count() > 0
        except Exception:
            return False

    # ─────────────────────────────────────────────
    # Query flow
    # ─────────────────────────────────────────────
    def _do_query(self, prompt: str, language: Optional[str] = None) -> CrawlerResult:
        page = self._page

        # 1) Navigate vers /new pour une conversation fraîche
        page.goto(f"{self.base_url}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(WAIT_AFTER_LOAD)

        # 2) Vérifie/sélectionne le modèle
        self._last_model_selection_ok = False
        if self.model_to_force:
            self._last_model_selection_ok = self._verify_or_select_model(
                self.model_to_force
            )

        # 3) Tape le prompt
        try:
            input_el = page.locator(SEL_CHAT_INPUT).first
            input_el.wait_for(state="visible", timeout=10_000)
            input_el.click()
            page.wait_for_timeout(300)
            page.keyboard.type(prompt)
            page.wait_for_timeout(WAIT_AFTER_TYPE)
            page.keyboard.press("Enter")
        except Exception as e:
            return CrawlerResult(
                prompt=prompt,
                response_text="",
                error=f"Erreur envoi prompt : {e}",
                screenshot_path=self._save_screenshot("error_send"),
            )

        # 4) Attente fin streaming
        self._wait_for_response_complete()

        # 5) Détection search status (avant extraction texte/sources)
        search_triggered, search_status_text = self._detect_search_status()

        # 6) Extraction du texte de la réponse
        response_text = self._extract_response_text()

        # 7) Extraction des sources depuis l'accordéon
        sources = self._extract_sources_from_accordion() if search_triggered else []

        # 8) Détection du modèle utilisé
        model_used = self._detect_model_used()

        # 9) Screenshot
        screenshot_path = self._save_screenshot("response")

        return CrawlerResult(
            prompt=prompt,
            response_text=response_text,
            sources=sources,
            model_used=model_used,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            metadata={
                "search_triggered": search_triggered,
                "search_status_text": search_status_text,
            },
        )

    # ─────────────────────────────────────────────
    # Sélection de modèle
    # ─────────────────────────────────────────────
    def _verify_or_select_model(self, model_name: str) -> bool:
        """Vérifie que le modèle actif contient model_name.
        Si non, tente de le sélectionner via le menu dropdown.
        Retourne True si le modèle est actif, False sinon."""
        page = self._page

        try:
            dropdown = page.locator(SEL_MODEL_DROPDOWN).first
            if dropdown.count() == 0:
                print(f"[{self.name}] ⚠ Model dropdown introuvable")
                return False

            aria_label = dropdown.get_attribute("aria-label") or ""
            # aria-label format : "Modèle : Sonnet 4.6 Adaptatif"
            if model_name.lower() in aria_label.lower():
                print(f"[{self.name}] ✓ Modèle '{model_name}' déjà actif")
                return True

            # Modèle pas actif, on tente de le sélectionner
            print(f"[{self.name}] → Modèle actuel : {aria_label}, "
                  f"sélection de '{model_name}'...")
            dropdown.click(timeout=3000)
            page.wait_for_timeout(500)

            # Attente du menu
            try:
                page.wait_for_selector(
                    'div[role="menu"], [role="listbox"]',
                    state="visible", timeout=3000,
                )
            except Exception:
                print(f"[{self.name}] ⚠ Menu modèle ne s'est pas ouvert")
                page.keyboard.press("Escape")
                return False

            # Clic sur l'item du modèle voulu
            item_found = False
            for sel in [
                f'[role="menuitemradio"]:has-text("{model_name}")',
                f'[role="option"]:has-text("{model_name}")',
                f'button:has-text("{model_name}")',
            ]:
                try:
                    item = page.locator(sel).first
                    if item.count() > 0:
                        item.click(timeout=2000)
                        item_found = True
                        break
                except Exception:
                    continue

            if not item_found:
                print(f"[{self.name}] ⚠ Item '{model_name}' introuvable")
                page.keyboard.press("Escape")
                return False

            page.wait_for_timeout(500)

            # Vérification
            aria_label_after = dropdown.get_attribute("aria-label") or ""
            if model_name.lower() in aria_label_after.lower():
                print(f"[{self.name}] ✓ Modèle '{model_name}' sélectionné")
                return True
            else:
                print(f"[{self.name}] ⚠ Sélection non confirmée "
                      f"({aria_label_after})")
                return False

        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur vérification modèle : {e}")
            return False

    # ─────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────
    def _detect_search_status(self) -> tuple[bool, str]:
        """Détecte si Claude a déclenché un web search.

        L'indicateur est le texte d'état au-dessus de la réponse dans
        le conteneur font-claude-response. Patterns observés :
        - Search: "Rassemblé...", "Synthétisé..."
        - No search: "Identifié...", "Préparé..."

        Retourne (search_triggered, status_text).
        """
        page = self._page
        try:
            status_text = page.evaluate("""
                () => {
                    // Le texte d'état est dans un button[aria-expanded]
                    // à l'intérieur de font-claude-response
                    const btn = document.querySelector(
                        'div[class*="font-claude-response"] button[aria-expanded]'
                    );
                    if (btn) {
                        const span = btn.querySelector('span.truncate');
                        if (span) return span.innerText.trim();
                        return btn.innerText.trim().split('\\n')[0];
                    }
                    return '';
                }
            """)
        except Exception:
            return (False, "")

        if not status_text:
            return (False, "")

        # Heuristique : les verbes indiquant un web search
        search_verbs = ["rassemblé", "synthétisé", "recherché", "consulté",
                        "gathered", "searched", "synthesized", "fetched"]
        triggered = any(v in status_text.lower() for v in search_verbs)
        return (triggered, status_text)

    def _wait_for_response_complete(self) -> None:
        """Attend la fin du streaming Claude.

        Stratégie multi-signal :
        - Signal 1 : bouton stop (aria-label "Arrêter"/"Stop") disparaît
        - Signal 2 : réponse substantielle (>100 chars) ET pas de stop
        - Signal 3 : timeout safety
        """
        page = self._page
        stop_selectors = [SEL_STOP_BUTTON_FR, SEL_STOP_BUTTON_EN]

        def stop_visible() -> bool:
            for sel in stop_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        def has_response_text() -> bool:
            """Vérifie si du texte de réponse substantiel est apparu."""
            try:
                container = page.locator(SEL_RESPONSE_CONTAINER)
                if container.count() > 0:
                    txt = container.last.inner_text(timeout=2000)
                    return len(txt.strip()) > 100
            except Exception:
                pass
            return False

        # Phase 1 : attendre que le streaming démarre (max 15s)
        deadline_start = time.time() + 15
        streaming_started = False
        while time.time() < deadline_start:
            if stop_visible():
                streaming_started = True
                break
            # Parfois le stop apparaît et disparaît très vite
            if has_response_text():
                streaming_started = True
                break
            time.sleep(0.3)

        if not streaming_started:
            page.wait_for_timeout(5000)
            return

        # Phase 2 : attendre la fin du streaming
        deadline_end = time.time() + WAIT_FOR_RESPONSE_END_S
        while time.time() < deadline_end:
            if not stop_visible():
                # Vérifie qu'on a bien du texte avant de conclure
                page.wait_for_timeout(2000)  # stabilisation DOM
                if has_response_text():
                    return
                # Pas de texte, on attend encore un peu
                page.wait_for_timeout(3000)
                return
            time.sleep(0.5)

        print(f"[{self.name}] ⚠ Timeout {WAIT_FOR_RESPONSE_END_S}s "
              f"sur fin de génération")

    def _extract_response_text(self) -> str:
        """Extrait le texte de la réponse via JS (plus fiable que les locators
        pour les classes Tailwind longues de claude.ai)."""
        page = self._page

        try:
            text = page.evaluate("""
                () => {
                    // Stratégie 1 : progressive-markdown (réponse sans accordéon)
                    const pms = document.querySelectorAll(
                        'div[class*="progressive-markdown"]'
                    );
                    if (pms.length > 0) {
                        const last = pms[pms.length - 1];
                        const txt = last.innerText.trim();
                        if (txt.length > 30) return txt;
                    }

                    // Stratégie 2 : font-claude-response (conteneur complet)
                    const frs = document.querySelectorAll(
                        'div[class*="font-claude-response"]'
                    );
                    if (frs.length > 0) {
                        const last = frs[frs.length - 1];
                        return last.innerText.trim();
                    }

                    // Stratégie 3 : standard-markdown
                    const sms = document.querySelectorAll(
                        'div[class*="standard-markdown"]'
                    );
                    if (sms.length > 0) {
                        const last = sms[sms.length - 1];
                        const txt = last.innerText.trim();
                        if (txt.length > 30) return txt;
                    }

                    return '';
                }
            """)
            return text or ""
        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur extraction texte : {e}")
            return ""

    def _extract_sources_from_accordion(self) -> list[CrawlerSource]:
        """Ouvre l'accordéon 'Rassemblé les informations...' et extrait les URLs.

        L'accordéon est un <button aria-expanded="false"> dans le conteneur
        de la réponse. Son contenu (les liens sources) est dans un div
        .overflow-hidden adjacent.
        """
        page = self._page
        sources: list[CrawlerSource] = []

        # 1) Trouver et ouvrir l'accordéon
        try:
            # Cherche le bouton accordéon dans le conteneur de réponse
            accordion_sel = (
                'div[class*="font-claude-response"] '
                'button[aria-expanded]'
            )
            accordion = page.locator(accordion_sel).first
            if accordion.count() == 0:
                print(f"[{self.name}] ℹ Pas d'accordéon "
                      f"(Claude n'a pas fait de web search)")
                return sources

            # Ouvrir si fermé
            expanded = accordion.get_attribute("aria-expanded")
            if expanded != "true":
                accordion.click(timeout=3000)
                page.wait_for_timeout(WAIT_AFTER_ACCORDION_CLICK)
        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur accordéon : {e}")
            return sources

        # 2) Extraire les liens via JS — plus robuste pour naviguer le DOM
        try:
            links_data = page.evaluate("""
                () => {
                    // Cherche tous les boutons accordéon dans la réponse
                    const btns = document.querySelectorAll(
                        'div[class*="font-claude-response"] button[aria-expanded]'
                    );
                    if (btns.length === 0) return [];

                    // Prend le dernier (au cas où il y en a plusieurs)
                    const btn = btns[btns.length - 1];

                    // Stratégie multi-niveaux pour trouver le conteneur des liens
                    // L'accordéon a un parent qui contient un .overflow-hidden
                    let searchRoot = btn.parentElement;
                    for (let i = 0; i < 5 && searchRoot; i++) {
                        const overflow = searchRoot.querySelector(
                            '.overflow-hidden'
                        );
                        if (overflow) {
                            const links = overflow.querySelectorAll(
                                'a[href^="http"]'
                            );
                            if (links.length > 0) {
                                return Array.from(links).map(a => ({
                                    url: a.href,
                                    title: (a.innerText ||
                                            a.getAttribute('title') || '')
                                           .trim().slice(0, 200),
                                })).filter(l =>
                                    !l.url.includes('claude.ai') &&
                                    !l.url.includes('anthropic.com')
                                );
                            }
                        }
                        searchRoot = searchRoot.parentElement;
                    }

                    // Fallback : tous les liens dans le conteneur de réponse
                    // (hors liens claude.ai/anthropic)
                    const container = document.querySelector(
                        'div[class*="font-claude-response"]'
                    );
                    if (!container) return [];
                    const allLinks = container.querySelectorAll(
                        'a[href^="http"]'
                    );
                    return Array.from(allLinks).map(a => ({
                        url: a.href,
                        title: (a.innerText || '').trim().slice(0, 200),
                    })).filter(l =>
                        !l.url.includes('claude.ai') &&
                        !l.url.includes('anthropic.com')
                    );
                }
            """)
        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur extraction sources : {e}")
            return sources

        # 3) Construire la liste CrawlerSource (dédup par URL)
        seen = set()
        for link in links_data:
            url = link.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(CrawlerSource(
                url=url,
                title=link.get("title") or None,
                position=len(sources) + 1,
            ))

        return sources

    def _detect_model_used(self) -> Optional[str]:
        """Retourne le modèle effectivement utilisé, normalisé pour la DB.

        Ex: "Modèle : Sonnet 4.6 Adaptatif" → "claude-sonnet-4-6-adaptive"
        """
        if self.model_to_force:
            if getattr(self, "_last_model_selection_ok", False):
                try:
                    dropdown = self._page.locator(SEL_MODEL_DROPDOWN).first
                    aria_label = dropdown.get_attribute("aria-label") or ""
                    return self._normalize_model_label(aria_label)
                except Exception:
                    return "claude-sonnet-4-6"
            else:
                return FALLBACK_MODEL_LABEL

        # Pas de modèle forcé : lire ce qui est actif
        try:
            dropdown = self._page.locator(SEL_MODEL_DROPDOWN).first
            aria_label = dropdown.get_attribute("aria-label") or ""
            return self._normalize_model_label(aria_label)
        except Exception:
            return "claude-unknown"

    @staticmethod
    def _normalize_model_label(aria_label: str) -> str:
        """'Modèle : Sonnet 4.6 Adaptatif' → 'claude-sonnet-4-6-adaptive'"""
        model_part = (
            aria_label.split(":")[-1].strip()
            if ":" in aria_label
            else aria_label
        )
        slug = model_part.lower().strip()
        slug = slug.replace("adaptatif", "adaptive")
        slug = slug.replace(" ", "-")
        slug = slug.replace(".", "-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        if not slug.startswith("claude"):
            slug = f"claude-{slug}"
        return slug

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
# Override __init__ pour model_to_force + session_dir
# ─────────────────────────────────────────────
_original_init = ClaudeAICrawler.__init__


def _patched_init(self, headless=False, session_dir=None,
                  screenshot_dir=None, timeout_ms=60_000, slow_mo_ms=50,
                  model_to_force=DEFAULT_MODEL_TO_FORCE):
    """Init enrichi pour sélection de modèle + session Chromium dédiée."""
    if session_dir is None:
        session_dir = (
            Path(__file__).parent.resolve() / "sessions" / "claude_ai_patchright"
        )
    _original_init(
        self,
        headless=headless,
        session_dir=session_dir,
        screenshot_dir=screenshot_dir,
        timeout_ms=timeout_ms,
        slow_mo_ms=slow_mo_ms,
    )
    self.model_to_force = model_to_force
    self._last_model_selection_ok = False


ClaudeAICrawler.__init__ = _patched_init


# ─────────────────────────────────────────────
# CLI standalone
# ─────────────────────────────────────────────
def _main():
    """Test rapide depuis la ligne de commande.

    Usage :
        python3 -m crawlers.claude_ai "Mon prompt ici"
        python3 -m crawlers.claude_ai "Mon prompt ici" --headless
    """
    if len(sys.argv) < 2:
        print('Usage: python3 -m crawlers.claude_ai "prompt" [--headless]')
        sys.exit(1)

    prompt = sys.argv[1]
    headless = "--headless" in sys.argv

    language = None
    if any(c in prompt.lower() for c in
           ["é", "è", "ê", "à", "ç", "quel", "comment"]):
        language = "fr"

    print(f"[POC] Crawler Claude.ai, headless={headless}")
    print(f"[POC] Prompt: {prompt}")
    print(f"[POC] Language: {language or 'auto'}\n")

    with ClaudeAICrawler(headless=headless) as crawler:
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
