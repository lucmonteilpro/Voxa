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

Sélecteurs Perplexity 2026 (validés via diagnostic en mode anonyme) :
- Input box        : div[contenteditable="true"][role="textbox"]
- Stop streaming   : button[aria-label*="Arrêter"] (FR) / aria-label*="Stop" (EN)
- Sources          : bouton "Liens" → liste des <a href> externes
- Réponse texte    : div[class*="prose"] dans main

Sélection de modèle (Phase 2E - Sonar 2 forcé) :
- Bouton modèle (état générique)  : button[aria-label="Modèle"]   (FR)
                                   ou button[aria-label="Model"]   (EN)
- Bouton modèle (post-sélection)  : button[aria-label="<nom du modèle>"]
                                   (ex: aria-label="Sonar 2")
- Conteneur menu ouvert            : div[role="menu"]
- Item d'un modèle dans le menu    : [role="menuitemradio"]:has-text("Sonar 2")
                                   (le menu contient ~7 menuitemradio, un par modèle)

Login :
- Au 1er run, te laisse 90s pour login Google/Apple/Email manuel
- Cookies persistés → connexion automatique aux runs suivants
- Mode anonyme limité à ~3-5 prompts puis Perplexity force le signup

Usage standalone :
    python3 -m crawlers.perplexity "Mon prompt"
    python3 -m crawlers.perplexity "Mon prompt" --headless
    python3 -m crawlers.perplexity "Mon prompt" --model "Sonar 2"

Usage programmatique :
    from crawlers.perplexity import PerplexityCrawler
    with PerplexityCrawler() as c:                            # Sonar 2 par défaut
        result = c.query("Quels sont les meilleurs sites de paris ?", language="fr")

    with PerplexityCrawler(model_to_force=None) as c:         # Mode "Meilleur"
        result = c.query("...", language="fr")
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

# Sélection de modèle (Phase 2E) — sélecteurs validés via diagnostic
# Le menu utilise ARIA pattern "menu" (pas "dialog") avec items "menuitemradio"
SEL_MODEL_MENU_OPEN = 'div[role="menu"]'  # le conteneur du menu ouvert

# Aria-labels génériques du bouton modèle (état "pas encore choisi" ou réinitialisé).
# Le crawler en mode anonyme voit "Modèle" (FR) ou "Model" (EN).
# Une fois un modèle sélectionné, l'aria-label devient le nom du modèle (cf. ci-dessous).
GENERIC_MODEL_BUTTON_LABELS = ("Modèle", "Model")

# Noms de modèles connus (état post-sélection : aria-label = nom du modèle).
# Liste utilisée pour reconnaître le bouton modèle même après une sélection.
KNOWN_MODEL_NAMES = (
    "Meilleur", "Best",  # le mode auto en FR/EN
    "Sonar 2", "Sonar Pro", "Sonar",
    "GPT-5.4", "GPT-5.5", "GPT-5", "GPT-4",
    "Claude Sonnet 4.6", "Claude Opus 4.7", "Claude",
    "Gemini 3.1 Pro", "Gemini",
    "Grok",
)


# ─────────────────────────────────────────────
# Configuration : modèle à forcer par défaut
# ─────────────────────────────────────────────
# Décision Phase 2E : on force Sonar 2 pour stabiliser la mesure.
# Justification dans VOXA_PLAN.md → Note 1 stratégique persistante.
# Pour repasser en mode "Meilleur" (variance maximum), instancier avec
# model_to_force=None.
DEFAULT_MODEL_TO_FORCE = "Sonar 2"

# Label DB en cas d'échec de sélection : on stocke un label distinct pour
# tracer en DB que ce run n'utilise pas vraiment Sonar 2 (donc à exclure
# des analyses Sonar 2). C'est plus honnête que de mentir avec
# "perplexity-sonar-2" alors que la sélection a raté.
FALLBACK_MODEL_LABEL = "perplexity-fallback"


class PerplexityCrawler(LLMCrawler):
    name = "perplexity"
    base_url = "https://www.perplexity.ai"

    # Délais (en ms / secondes selon contexte)
    WAIT_AFTER_TYPE = 800
    WAIT_AFTER_LOAD = 2000             # laisse le JS se monter
    WAIT_FOR_RESPONSE_END_S = 90       # max attendu pour fin génération
    WAIT_AFTER_LINKS_CLICK = 2000      # laisse l'onglet Liens charger
    LOGIN_GRACE_SECONDS = 90
    WAIT_AFTER_MODEL_CLICK = 500       # laisse le menu s'ouvrir / se fermer
    MODEL_MENU_TIMEOUT_MS = 3000       # timeout d'apparition du menu

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

        # 1b) Force le modèle (Sonar 2 par défaut) si demandé.
        # Échec gracieux : on continue avec le modèle actif si la sélection rate.
        # On garde trace du résultat pour que _detect_model_used soit honnête.
        self._last_model_selection_ok = False
        if self.model_to_force:
            self._last_model_selection_ok = self._select_model(self.model_to_force)

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
    # Sélection de modèle (Phase 2E)
    # ─────────────────────────────────────────────
    def _select_model(self, model_name: str) -> bool:
        """Force la sélection d'un modèle spécifique sur Perplexity.

        Stratégie en 5 étapes :
          1. Vérifier si le modèle est déjà sélectionné (aria-label du bouton
             égal au nom du modèle) → si oui, sauter (idempotent)
          2. Trouver le bouton modèle (deux variantes possibles : aria-label
             générique "Modèle"/"Model" OU aria-label = nom d'un modèle déjà choisi)
          3. Cliquer dessus pour ouvrir le menu (div[role="menu"])
          4. Cliquer sur l'item du modèle voulu ([role="menuitemradio"])
          5. Vérifier que la sélection est confirmée

        Retourne True si succès, False si échec gracieux.
        En cas d'échec, le crawl continue avec le modèle actuellement
        sélectionné, et _detect_model_used renverra "perplexity-fallback"
        pour traçabilité honnête en DB.

        Note : Perplexity persiste le choix de modèle dans les cookies/
        localStorage. Une fois Sonar 2 sélectionné dans la session, il reste
        sélectionné aux runs suivants → étape 1 économise du temps.
        """
        page = self._page

        # ── Étape 1 : déjà sélectionné ?
        try:
            already = page.locator(
                f'button[aria-label="{model_name}"][aria-haspopup="menu"]'
            ).count()
            if already > 0:
                # Le bouton modèle porte déjà le nom voulu = OK
                return True
        except Exception:
            pass  # on continue avec la sélection complète

        # ── Étape 2 : trouver le bouton modèle
        model_button = self._find_model_button()
        if model_button is None:
            print(f"[{self.name}] ⚠ Bouton modèle introuvable, "
                  f"crawl avec modèle par défaut")
            return False

        # ── Étape 3 : cliquer sur le bouton pour ouvrir le menu
        try:
            model_button.click(timeout=3000)
            page.wait_for_timeout(self.WAIT_AFTER_MODEL_CLICK)
        except Exception as e:
            print(f"[{self.name}] ⚠ Échec clic sur bouton modèle : {e}")
            return False

        # ── Étape 3b : attendre l'apparition du menu
        try:
            page.wait_for_selector(
                SEL_MODEL_MENU_OPEN,
                state="visible",
                timeout=self.MODEL_MENU_TIMEOUT_MS,
            )
        except Exception:
            print(f"[{self.name}] ⚠ Menu modèle ne s'est pas ouvert")
            return False

        # ── Étape 4 : cliquer sur l'item correspondant au modèle voulu
        # Le menu contient des [role="menuitemradio"], un par modèle.
        # Sélecteur : on cible l'item qui contient le texte exact du nom.
        try:
            item_selector = (
                f'div[role="menu"] [role="menuitemradio"]:has-text("{model_name}")'
            )
            item = page.locator(item_selector).first
            item.wait_for(state="visible", timeout=2000)

            # Vérifier que l'item n'est pas désactivé (locked Pro/Max)
            try:
                aria_disabled = item.get_attribute("aria-disabled") or "false"
                if aria_disabled.lower() == "true":
                    print(f"[{self.name}] ⚠ Modèle '{model_name}' désactivé "
                          f"(probablement locked Pro/Max non disponible). "
                          f"Sélection ignorée.")
                    page.keyboard.press("Escape")
                    return False
            except Exception:
                pass  # si on ne peut pas lire aria-disabled, on tente le clic

            item.click(timeout=2000)
            page.wait_for_timeout(self.WAIT_AFTER_MODEL_CLICK)
        except Exception as e:
            print(f"[{self.name}] ⚠ Échec clic sur item '{model_name}' : {e}")
            # Tente de fermer le menu pour ne pas bloquer la suite
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

        # ── Étape 5 : vérifier que la sélection est confirmée
        # Le bouton modèle devrait maintenant porter aria-label="<model_name>"
        try:
            verified = page.locator(
                f'button[aria-label="{model_name}"][aria-haspopup="menu"]'
            ).count() > 0
        except Exception:
            verified = False

        if verified:
            print(f"[{self.name}] ✓ Modèle '{model_name}' sélectionné")
            return True
        else:
            print(f"[{self.name}] ⚠ Sélection '{model_name}' non confirmée "
                  f"(le bouton n'a pas pris l'aria-label attendu)")
            return False

    def _find_model_button(self):
        """Trouve le bouton qui ouvre le menu de sélection de modèle.

        Plusieurs button[aria-haspopup="menu"] peuvent exister sur la page
        (actions du fil, planifiées, fichiers, etc.). Le bouton modèle se
        distingue par son aria-label, qui peut prendre 2 formes :

        1) Cas le plus fréquent (état initial / mode anonyme) :
           aria-label="Modèle" (FR) ou aria-label="Model" (EN)
           → label générique car aucun modèle spécifique n'est explicitement choisi

        2) État post-sélection (un modèle a déjà été choisi) :
           aria-label="Sonar 2", "Meilleur", "GPT-5.4", etc.
           → le label devient le nom du modèle actif

        Retourne un Locator (le bouton) ou None si introuvable.
        """
        page = self._page

        # Tentative 1 : labels génériques ("Modèle" / "Model")
        for generic in GENERIC_MODEL_BUTTON_LABELS:
            try:
                btn = page.locator(
                    f'button[aria-label="{generic}"][aria-haspopup="menu"]'
                ).first
                if btn.count() > 0:
                    return btn
            except Exception:
                continue

        # Tentative 2 : labels = nom d'un modèle connu
        for known in KNOWN_MODEL_NAMES:
            try:
                btn = page.locator(
                    f'button[aria-label="{known}"][aria-haspopup="menu"]'
                ).first
                if btn.count() > 0:
                    return btn
            except Exception:
                continue

        # Aucun match
        return None

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

        Filtrage des liens internes Perplexity :
        On filtre tous les domaines Perplexity (perplexity.ai, perplexity.com,
        etc.) via a.hostname.includes('perplexity'). Sans ça, des liens comme
        perplexity.com/hub/legal/privacy-policy passaient dans les sources.
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

        # 2) Extraire tous les <a href> externes maintenant visibles.
        # Filtre élargi : a.hostname.includes('perplexity') exclut tous les
        # subdomaines Perplexity (perplexity.ai, perplexity.com, etc.).
        # Avant : a.href.includes('perplexity.ai') laissait passer perplexity.com.
        try:
            links_data = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href^="http"]');
                    const externals = [];
                    for (const a of links) {
                        // Filtre tous les domaines Perplexity (.ai, .com, etc.)
                        if (a.hostname && a.hostname.includes('perplexity')) continue;
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
        """Retourne le modèle effectivement utilisé pour la requête.

        Logique :
        - Si self.model_to_force est défini ET la sélection a réussi :
          retourne "perplexity-<model_to_force>" en kebab-case.
          Ex : "perplexity-sonar-2"
        - Si self.model_to_force est défini MAIS la sélection a échoué :
          retourne FALLBACK_MODEL_LABEL = "perplexity-fallback".
          Ce label permet de distinguer en DB les vrais runs Sonar 2 des
          runs où la sélection a raté (et qui sont donc en mode "Meilleur"
          ou autre).
        - Si self.model_to_force est None (mode "Meilleur" volontaire) :
          retourne "perplexity-default" comme avant.
        """
        if self.model_to_force:
            if getattr(self, "_last_model_selection_ok", False):
                slug = self.model_to_force.lower().replace(' ', '-')
                return f"perplexity-{slug}"
            else:
                # Sélection ratée : on ne ment pas en DB
                return FALLBACK_MODEL_LABEL
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
# Override session_dir + ajout model_to_force
# ─────────────────────────────────────────────
# On override __init__ pour deux raisons :
#  1) session_dir doit pointer vers le dossier patchright dédié (différent
#     de la session Playwright standard de la classe parente)
#  2) ajout du paramètre model_to_force (Phase 2E - décision Sonar 2)
_original_init = PerplexityCrawler.__init__


def _patched_init(self, headless=False, session_dir=None,
                   screenshot_dir=None, timeout_ms=60_000, slow_mo_ms=50,
                   model_to_force=DEFAULT_MODEL_TO_FORCE):
    """Init enrichi pour patchright + sélection de modèle.

    Args:
        headless: mode navigateur sans tête.
        session_dir: dossier de la session persistée. Si None, force le
            dossier patchright dédié.
        screenshot_dir: dossier des screenshots (passé tel quel au parent).
        timeout_ms: timeout global Playwright.
        slow_mo_ms: ralentissement Playwright (debug).
        model_to_force: nom du modèle à forcer (ex: "Sonar 2", "Claude Sonnet 4.6").
            Passer None pour rester en mode "Meilleur" (variance maximum).
            Par défaut : "Sonar 2" (cf. VOXA_PLAN.md → Note 1 stratégique).
    """
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
    # Ajout des attributs de sélection de modèle après l'init parent
    self.model_to_force = model_to_force
    self._last_model_selection_ok = False  # mis à jour à chaque _do_query


PerplexityCrawler.__init__ = _patched_init


# ─────────────────────────────────────────────
# CLI standalone (pour test rapide)
# ─────────────────────────────────────────────
def _main():
    """Test rapide depuis la ligne de commande.

    Usage :
        python3 -m crawlers.perplexity "Mon prompt ici"
        python3 -m crawlers.perplexity "Mon prompt ici" --headless
        python3 -m crawlers.perplexity "Mon prompt ici" --model "Sonar 2"
        python3 -m crawlers.perplexity "Mon prompt ici" --no-force-model
    """
    if len(sys.argv) < 2:
        print('Usage: python3 -m crawlers.perplexity "prompt" '
              '[--headless] [--model "Nom du modèle"] [--no-force-model]')
        sys.exit(1)

    prompt = sys.argv[1]
    headless = "--headless" in sys.argv

    # Détermine le modèle à forcer
    model_to_force = DEFAULT_MODEL_TO_FORCE
    if "--no-force-model" in sys.argv:
        model_to_force = None
    elif "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model_to_force = sys.argv[idx + 1]

    language = None
    # Détection naïve de la langue depuis le prompt (pour les sélecteurs)
    if any(c in prompt.lower() for c in ["é", "è", "ê", "à", "ç", "quel", "comment"]):
        language = "fr"

    print(f"[POC] Crawler Perplexity, headless={headless}")
    print(f"[POC] Prompt: {prompt}")
    print(f"[POC] Language: {language or 'auto'}")
    print(f"[POC] Model to force: {model_to_force or '(mode Meilleur)'}\n")

    with PerplexityCrawler(headless=headless, model_to_force=model_to_force) as crawler:
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