"""
Voxa — Crawler Gemini (UI mode, patchright)
============================================
Crawler gemini.google.com en mode UI via Chromium natif Patchright.

Stack technique :
- patchright avec Chromium natif (pas Chrome)
- Session persistante : crawlers/sessions/gemini_patchright/
- Google Search : toujours actif (pas de mode Adaptatif conditionnel)

Sélecteurs Gemini 2026 (validés via diagnostic DOM 2026-05-14) :
- Input box         : .ql-editor / [role="textbox"]
- Envoi             : button[aria-label*="Envoyer"] (FR)
- Mode switcher     : button[aria-label*="sélecteur de mode"]
- Streaming en cours: processing-state (web component)
- Streaming terminé : button[aria-label*="Copier"] apparaît
- Réponse texte     : model-response / message-content / [class*="markdown"]
- Sources           : .location-clickable (web components, pas des <a href>)
- Search indicator  : span:has-text("Google Search") dans processing-state

Note architecture : Gemini utilise des Web Components Angular (model-response,
response-container, processing-state, message-content) au lieu de <div>.

Usage standalone :
    python3 -m crawlers.gemini "Mon prompt"

Usage programmatique :
    from crawlers.gemini import GeminiCrawler
    with GeminiCrawler() as c:
        result = c.query("Quels sont les meilleurs sites de paris ?", language="fr")
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Optional

from .base import LLMCrawler, CrawlerResult, CrawlerSource


# ─────────────────────────────────────────────
# Sélecteurs DOM Gemini (validés 2026-05-14)
# ─────────────────────────────────────────────
SEL_INPUT = '.ql-editor'
SEL_SEND_FR = 'button[aria-label*="Envoyer"]'
SEL_SEND_EN = 'button[aria-label*="Send"]'
SEL_MODE_SWITCHER_FR = 'button[aria-label*="sélecteur de mode"]'
SEL_MODE_SWITCHER_EN = 'button[aria-label*="mode selector"]'
SEL_RESPONSE = 'model-response'
SEL_RESPONSE_MARKDOWN = '[class*="markdown"]'
SEL_RESPONSE_CONTENT = 'message-content'
SEL_PROCESSING_STATE = 'processing-state'
SEL_COPY_BUTTON_FR = 'button[aria-label*="Copier"]'
SEL_COPY_BUTTON_EN = 'button[aria-label*="Copy"]'
SEL_SOURCES = '.location-clickable'
SEL_SIGN_IN = 'a:has-text("Connexion"), a:has-text("Sign in"), button:has-text("Connexion"), button:has-text("Sign in")'

# Mode menu (ouvert via le mode switcher)
SEL_MODE_MENU_ITEM = 'button[role="menuitem"]'

# ─────────────────────────────────────────────
# Configuration : mode à forcer
# ─────────────────────────────────────────────
# Pro censure les paris sportifs (zone vide, confirmé 16/05/2026).
# Rapide répond mais avec des réponses courtes sans citer les bookmakers.
# On force Rapide pour garantir une réponse (le mode persiste entre sessions).
DEFAULT_MODE_TO_FORCE = "Rapide"
FALLBACK_MODEL_LABEL = "gemini-fallback"

# ─────────────────────────────────────────────
# Timing
# ─────────────────────────────────────────────
WAIT_AFTER_LOAD = 4000
WAIT_AFTER_TYPE = 800
WAIT_FOR_RESPONSE_END_S = 120
LOGIN_GRACE_SECONDS = 300

# Domain regex for fallback source extraction
DOMAIN_RE = re.compile(r'([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}')


class GeminiCrawler(LLMCrawler):
    name = "gemini"
    base_url = "https://gemini.google.com"

    # ─────────────────────────────────────────────
    # Override : Chromium natif via patchright
    # ─────────────────────────────────────────────
    def _get_sync_playwright(self):
        from patchright.sync_api import sync_playwright
        return sync_playwright

    def _get_launch_kwargs(self) -> dict:
        return {
            "user_data_dir": str(self.session_dir),
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 900},
        }

    # ─────────────────────────────────────────────
    # Login flow
    # ─────────────────────────────────────────────
    def _ensure_logged_in(self) -> None:
        page = self._page
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(WAIT_AFTER_LOAD)

        if self._is_logged_in():
            print(f"[{self.name}] ✓ Loggué via session persistée")
            return

        if self.headless:
            raise RuntimeError(
                f"[{self.name}] Pas loggué en mode headless. "
                "Lance d'abord en mode headed pour le login manuel."
            )

        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║  ÉTAPE LOGIN GEMINI                                          ║")
        print("║                                                              ║")
        print("║  → Fenêtre Chromium ouverte sur gemini.google.com            ║")
        print("║  → Connecte-toi avec ton compte Google (Gemini Advanced)     ║")
        print("║  → 2FA si nécessaire                                         ║")
        print("║                                                              ║")
        print("║  Le script reprend automatiquement dès détection du login.   ║")
        print(f"║  Timeout : {LOGIN_GRACE_SECONDS} secondes"
              f"{' ' * (47 - len(str(LOGIN_GRACE_SECONDS)))}║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        deadline = time.time() + LOGIN_GRACE_SECONDS
        while time.time() < deadline:
            time.sleep(2)
            if self._is_logged_in():
                print(f"[{self.name}] ✓ Login détecté")
                page.wait_for_timeout(3000)
                return
            remaining = int(deadline - time.time())
            if remaining % 30 < 2:
                print(f"[{self.name}]   ... {remaining}s restantes")

        raise RuntimeError(
            f"[{self.name}] Login non effectué dans {LOGIN_GRACE_SECONDS}s"
        )

    def _is_logged_in(self) -> bool:
        page = self._page
        try:
            # Négatif : bouton "Connexion" visible = pas loggué
            if page.locator(SEL_SIGN_IN).count() > 0:
                return False
        except Exception:
            pass
        try:
            # Positif : mode switcher (Gemini Advanced uniquement)
            for sel in [SEL_MODE_SWITCHER_FR, SEL_MODE_SWITCHER_EN]:
                if page.locator(sel).count() > 0:
                    return True
        except Exception:
            pass
        return False

    # ─────────────────────────────────────────────
    # Query flow
    # ─────────────────────────────────────────────
    def _do_query(self, prompt: str, language: Optional[str] = None) -> CrawlerResult:
        page = self._page

        # 1) Navigate vers la home (nouvelle conversation)
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(WAIT_AFTER_LOAD)

        # 2) Forcer le mode Pro (ou celui configuré)
        self._last_mode_selection_ok = False
        if self.mode_to_force:
            self._last_mode_selection_ok = self._select_mode(self.mode_to_force)

        # 3) Lire le modèle actif (après sélection)
        model_label = self._read_mode_label()

        # 3) Tape le prompt
        try:
            input_el = page.locator(SEL_INPUT).first
            input_el.wait_for(state="visible", timeout=10_000)
            input_el.click()
            page.wait_for_timeout(300)
            page.keyboard.type(prompt)
            page.wait_for_timeout(WAIT_AFTER_TYPE)
        except Exception as e:
            return CrawlerResult(
                prompt=prompt,
                response_text="",
                error=f"Erreur saisie prompt : {e}",
                screenshot_path=self._save_screenshot("error_type"),
            )

        # 4) Envoi via bouton Send
        try:
            sent = False
            for sel in [SEL_SEND_FR, SEL_SEND_EN]:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=3000)
                    sent = True
                    break
            if not sent:
                page.keyboard.press("Enter")
        except Exception as e:
            return CrawlerResult(
                prompt=prompt,
                response_text="",
                error=f"Erreur envoi : {e}",
                screenshot_path=self._save_screenshot("error_send"),
            )

        # 5) Attente fin streaming
        self._wait_for_response_complete()

        # 6) Extraction texte
        response_text = self._extract_response_text()

        # 7) Extraction sources (cascade 3 niveaux)
        sources, src_stats = self._extract_sources()

        # 8) Détection modèle (honnête : fallback si sélection a raté)
        if self.mode_to_force and not self._last_mode_selection_ok:
            model_used = f"{FALLBACK_MODEL_LABEL}-{self._normalize_model(model_label).replace('gemini-', '')}"
        else:
            model_used = self._normalize_model(model_label)

        # 9) Screenshot
        screenshot_path = self._save_screenshot("response")

        return CrawlerResult(
            prompt=prompt,
            response_text=response_text,
            sources=sources,
            model_used=model_used,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            metadata={
                "search_triggered": True,
                "auto_mode": "always_search",
                "mode_label": model_label,
                "sources_with_url": src_stats["with_url"],
                "sources_textonly": src_stats["textonly"],
            },
        )

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────
    def _read_mode_label(self) -> str:
        """Lit le label du mode switcher (ex: 'Rapide', 'Pro')."""
        page = self._page
        for sel in [SEL_MODE_SWITCHER_FR, SEL_MODE_SWITCHER_EN]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    text = btn.inner_text(timeout=3000).strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _select_mode(self, mode_name: str) -> bool:
        """Force la sélection d'un mode Gemini (ex: 'Pro', 'Rapide').

        Retourne True si succès, False si échec gracieux.
        """
        page = self._page

        # Vérifier si déjà sur le bon mode
        current = self._read_mode_label()
        if current.lower() == mode_name.lower():
            print(f"[{self.name}] ✓ Mode '{mode_name}' déjà actif")
            return True

        print(f"[{self.name}] → Mode actuel '{current}', "
              f"sélection de '{mode_name}'...")

        # Ouvrir le menu mode
        try:
            for sel in [SEL_MODE_SWITCHER_FR, SEL_MODE_SWITCHER_EN]:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    break
            page.wait_for_timeout(800)
        except Exception as e:
            print(f"[{self.name}] ⚠ Échec ouverture menu mode : {e}")
            return False

        # Cliquer sur l'option souhaitée
        try:
            # Les options sont des button[role="menuitem"] avec classe bard-mode-li
            # Le texte contient le nom du mode suivi d'une description
            items = page.locator(SEL_MODE_MENU_ITEM)
            found = False
            for i in range(items.count()):
                item = items.nth(i)
                text = item.inner_text(timeout=2000).strip()
                if text.lower().startswith(mode_name.lower()):
                    item.click(timeout=2000)
                    found = True
                    break

            if not found:
                print(f"[{self.name}] ⚠ Option '{mode_name}' introuvable "
                      f"dans le menu")
                page.keyboard.press("Escape")
                return False

            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[{self.name}] ⚠ Échec sélection '{mode_name}' : {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

        # Vérifier la sélection
        new_label = self._read_mode_label()
        if new_label.lower() == mode_name.lower():
            print(f"[{self.name}] ✓ Mode '{mode_name}' sélectionné")
            return True
        else:
            print(f"[{self.name}] ⚠ Sélection non confirmée "
                  f"(label actuel: '{new_label}')")
            return False

    def _wait_for_response_complete(self) -> None:
        """Attend la fin du streaming Gemini.

        Signal principal : apparition de button[aria-label*="Copier"/"Copy"].
        """
        page = self._page
        copy_selectors = [SEL_COPY_BUTTON_FR, SEL_COPY_BUTTON_EN]

        def copy_visible() -> bool:
            for sel in copy_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        def has_response() -> bool:
            try:
                el = page.locator(SEL_RESPONSE)
                if el.count() > 0:
                    text = el.first.inner_text(timeout=2000)
                    return len(text.strip()) > 100
            except Exception:
                pass
            return False

        # Phase 1 : attendre début de streaming (max 15s)
        deadline_start = time.time() + 15
        started = False
        while time.time() < deadline_start:
            try:
                if page.locator(SEL_PROCESSING_STATE).count() > 0:
                    started = True
                    break
            except Exception:
                pass
            if has_response():
                started = True
                break
            time.sleep(0.3)

        if not started:
            page.wait_for_timeout(5000)
            return

        # Phase 2 : attendre fin de streaming
        deadline_end = time.time() + WAIT_FOR_RESPONSE_END_S
        while time.time() < deadline_end:
            if copy_visible():
                page.wait_for_timeout(2000)
                return
            time.sleep(0.5)

        print(f"[{self.name}] ⚠ Timeout {WAIT_FOR_RESPONSE_END_S}s "
              f"sur fin de génération")

    def _extract_response_text(self) -> str:
        """Extrait le texte de la réponse depuis les web components Gemini."""
        page = self._page
        try:
            text = page.evaluate("""
                () => {
                    // Helper : nettoyer le header Gemini ("Google Search\\nGemini a dit")
                    function clean(raw) {
                        let t = raw.trim();
                        // Retirer le header "Google Search" + "Gemini a dit"
                        t = t.replace(/^Google Search\\s*/i, '');
                        t = t.replace(/^Gemini a dit\\s*/i, '');
                        t = t.replace(/^Gemini said\\s*/i, '');
                        return t.trim();
                    }

                    // Stratégie 1 : message-content (web component)
                    const mc = document.querySelector('message-content');
                    if (mc) {
                        const t = clean(mc.innerText);
                        if (t.length > 10) return t;
                    }

                    // Stratégie 2 : model-response
                    const mr = document.querySelector('model-response');
                    if (mr) {
                        const t = clean(mr.innerText);
                        if (t.length > 10) return t;
                    }

                    // Stratégie 3 : markdown class
                    const md = document.querySelector('[class*="markdown"]');
                    if (md) {
                        const t = clean(md.innerText);
                        if (t.length > 10) return t;
                    }

                    return '';
                }
            """)
            return text or ""
        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur extraction texte : {e}")
            return ""

    def _extract_sources(self) -> tuple[list[CrawlerSource], dict]:
        """Extraction des sources en cascade 3 niveaux.

        Niveau 1 : attributs DOM sur .location-clickable (href, data-url, etc.)
        Niveau 2 : shadow DOM des web components
        Niveau 3 : fallback parsing textContent pour extraire domaines

        Retourne (sources, stats) où stats = {with_url, textonly}.
        """
        page = self._page
        sources: list[CrawlerSource] = []
        stats = {"with_url": 0, "textonly": 0}

        try:
            raw_sources = page.evaluate("""
                () => {
                    const results = [];
                    const els = document.querySelectorAll('.location-clickable');

                    for (const el of els) {
                        const text = (el.innerText || '').trim();

                        // Filtrer les .location-clickable de géoloc (sidebar)
                        // qui ne sont pas des sources de contenu
                        const geoNoise = ['mettre à jour', 'update', 'position',
                                          "d'après vos adresses", 'from your addresses'];
                        const isGeo = geoNoise.some(
                            n => text.toLowerCase().includes(n)
                        );
                        // Aussi filtrer les textes très courts (< 5 chars)
                        // qui sont des labels UI, pas des sources
                        if (isGeo || text.length < 5) continue;

                        const entry = {
                            text: text.slice(0, 200),
                            url: null,
                            title: null,
                        };

                        // Niveau 1 : attributs DOM directs
                        for (const attr of ['href', 'data-url', 'data-href',
                                            'ng-href', 'data-source-url']) {
                            const val = el.getAttribute(attr);
                            if (val && val.startsWith('http')) {
                                entry.url = val;
                                break;
                            }
                        }

                        // Niveau 1b : aria-label peut contenir l'URL
                        if (!entry.url) {
                            const al = el.getAttribute('aria-label') || '';
                            if (al.startsWith('http')) entry.url = al;
                        }

                        // Niveau 1c : chercher un <a> enfant
                        if (!entry.url) {
                            const a = el.querySelector('a[href^="http"]');
                            if (a) entry.url = a.href;
                        }

                        // Niveau 1d : remonter au parent pour trouver un <a>
                        if (!entry.url) {
                            let parent = el.parentElement;
                            for (let i = 0; i < 3 && parent; i++) {
                                if (parent.tagName === 'A' && parent.href) {
                                    entry.url = parent.href;
                                    break;
                                }
                                const a = parent.querySelector('a[href^="http"]');
                                if (a) { entry.url = a.href; break; }
                                parent = parent.parentElement;
                            }
                        }

                        // Niveau 2 : shadow DOM
                        if (!entry.url && el.shadowRoot) {
                            const a = el.shadowRoot.querySelector('a[href^="http"]');
                            if (a) entry.url = a.href;
                        }

                        // Titre depuis le texte
                        entry.title = entry.text || null;

                        // Filtrer liens Google internes
                        if (entry.url &&
                            (entry.url.includes('accounts.google') ||
                             entry.url.includes('support.google') ||
                             entry.url.includes('policies.google'))) {
                            continue;
                        }

                        results.push(entry);
                    }

                    // Fallback global : liens <a> dans model-response
                    // (au cas où .location-clickable n'a rien donné)
                    if (results.length === 0) {
                        const mr = document.querySelector('model-response');
                        if (mr) {
                            const links = mr.querySelectorAll('a[href^="http"]');
                            for (const a of links) {
                                if (a.href.includes('google.com') &&
                                    !a.href.includes('google.com/search'))
                                    continue;
                                results.push({
                                    url: a.href,
                                    text: (a.innerText || '').trim().slice(0, 200),
                                    title: (a.innerText || '').trim().slice(0, 200),
                                });
                            }
                        }
                    }

                    return results;
                }
            """)
        except Exception as e:
            print(f"[{self.name}] ⚠ Erreur extraction sources : {e}")
            return sources, stats

        seen = set()
        for raw in raw_sources:
            url = raw.get("url")
            text = raw.get("text", "")
            title = raw.get("title")

            # Niveau 3 fallback : parse domain from text
            domain = None
            if url:
                stats["with_url"] += 1
                dedup_key = url
            else:
                stats["textonly"] += 1
                # Essayer d'extraire un domaine du texte
                match = DOMAIN_RE.search(text.lower())
                if match:
                    domain = match.group(0)
                dedup_key = domain or text

            if not dedup_key or dedup_key in seen:
                continue
            seen.add(dedup_key)

            sources.append(CrawlerSource(
                url=url,
                title=title or text or None,
                domain=domain,
                position=len(sources) + 1,
            ))

        return sources, stats

    @staticmethod
    def _normalize_model(mode_label: str) -> str:
        """'Rapide' → 'gemini-rapid', 'Pro' → 'gemini-pro', etc."""
        if not mode_label:
            return "gemini-unknown"
        slug = mode_label.lower().strip()
        slug = slug.replace(" ", "-").replace(".", "-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        if not slug.startswith("gemini"):
            slug = f"gemini-{slug}"
        return slug

    def _save_screenshot(self, suffix: str = "") -> Optional[Path]:
        try:
            path = self.screenshot_path_for(suffix)
            self._page.screenshot(path=str(path), full_page=True)
            return path
        except Exception as e:
            print(f"[{self.name}] ⚠ Screenshot KO: {e}")
            return None


# ─────────────────────────────────────────────
# Override __init__ pour session_dir dédiée
# ─────────────────────────────────────────────
_original_init = GeminiCrawler.__init__


def _patched_init(self, headless=False, session_dir=None,
                  screenshot_dir=None, timeout_ms=60_000, slow_mo_ms=50,
                  mode_to_force=DEFAULT_MODE_TO_FORCE):
    if session_dir is None:
        session_dir = (
            Path(__file__).parent.resolve() / "sessions" / "gemini_patchright"
        )
    _original_init(
        self,
        headless=headless,
        session_dir=session_dir,
        screenshot_dir=screenshot_dir,
        timeout_ms=timeout_ms,
        slow_mo_ms=slow_mo_ms,
    )
    self.mode_to_force = mode_to_force
    self._last_mode_selection_ok = False


GeminiCrawler.__init__ = _patched_init


# ─────────────────────────────────────────────
# CLI standalone
# ─────────────────────────────────────────────
def _main():
    if len(sys.argv) < 2:
        print('Usage: python3 -m crawlers.gemini "prompt" [--headless]')
        sys.exit(1)

    prompt = sys.argv[1]
    headless = "--headless" in sys.argv

    language = None
    if any(c in prompt.lower() for c in
           ["é", "è", "ê", "à", "ç", "quel", "comment"]):
        language = "fr"

    print(f"[POC] Crawler Gemini, headless={headless}")
    print(f"[POC] Prompt: {prompt}")
    print(f"[POC] Language: {language or 'auto'}\n")

    with GeminiCrawler(headless=headless) as crawler:
        result = crawler.query(prompt, language=language)

    print("\n" + "=" * 70)
    print(f"SUCCESS    : {result.is_success}")
    print(f"Duration   : {result.crawl_duration_ms} ms")
    print(f"Model      : {result.model_used}")
    print(f"Metadata   : {result.metadata}")
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
        url_display = s.url[:60] if s.url else "(text-only)"
        print(f"  [{s.position:2}] {s.domain or '?':35s} {url_display}")
        if s.title:
            print(f"       → {s.title[:80]}")


if __name__ == "__main__":
    _main()
