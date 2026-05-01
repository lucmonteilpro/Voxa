"""
Voxa — LLMCrawler base class
=============================
Classe abstraite qui définit le contrat commun à tous les crawlers de LLMs
en mode UI (Perplexity, ChatGPT, Claude, Gemini, etc.).

Utilisation typique :

    from crawlers.perplexity import PerplexityCrawler

    with PerplexityCrawler(headless=False) as crawler:
        result = crawler.query("Quels sont les meilleurs sites de paris ?")
        print(result.response_text)
        for src in result.sources:
            print(f"  - {src['domain']}: {src['url']}")

Toute classe qui hérite de LLMCrawler doit implémenter au minimum :
  - _ensure_logged_in()
  - _do_query(prompt, language)

Le pattern context manager (__enter__ / __exit__) garantit que le navigateur
est toujours fermé proprement, même en cas d'erreur.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ─────────────────────────────────────────────
# Types de sortie
# ─────────────────────────────────────────────
@dataclass
class CrawlerSource:
    """Une source citée par le LLM dans sa réponse."""
    url: str
    title: Optional[str] = None
    domain: Optional[str] = None
    position: Optional[int] = None  # ordre d'apparition (1, 2, 3...)
    snippet: Optional[str] = None   # extrait textuel de la citation, si dispo

    def __post_init__(self):
        # Calcule automatiquement le domain depuis l'URL si pas fourni
        if self.url and not self.domain:
            try:
                parsed = urlparse(self.url)
                self.domain = parsed.netloc.replace("www.", "") if parsed.netloc else None
            except Exception:
                self.domain = None


@dataclass
class CrawlerResult:
    """Résultat d'une query envoyée au LLM via UI."""
    prompt: str
    response_text: str
    sources: list[CrawlerSource] = field(default_factory=list)
    model_used: Optional[str] = None       # ex: "perplexity-sonar", "gpt-4-turbo"
    crawler_name: str = ""                 # ex: "perplexity", "chatgpt"
    language: Optional[str] = None         # langue du prompt (fr, en, pt...)
    crawl_duration_ms: Optional[int] = None
    screenshot_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None            # si la query a échoué partiellement

    def to_dict(self) -> dict:
        """Sérialisation JSON-ready (utile pour debug / logs / export)."""
        d = asdict(self)
        d["sources"] = [asdict(s) for s in self.sources]
        return d

    @property
    def is_success(self) -> bool:
        return self.error is None and bool(self.response_text)


# ─────────────────────────────────────────────
# Classe abstraite LLMCrawler
# ─────────────────────────────────────────────
class LLMCrawler(ABC):
    """Contrat commun pour tous les crawlers de LLMs en mode UI.

    Sous-classes concrètes : PerplexityCrawler, ChatGPTCrawler, ClaudeCrawler...

    Args:
        headless: True pour mode invisible (prod), False pour mode visible (dev/POC)
        session_dir: répertoire pour stocker cookies/localStorage entre runs
        screenshot_dir: répertoire de sortie des screenshots
        timeout_ms: timeout par défaut pour les opérations Playwright (ms)
        slow_mo_ms: délai entre actions Playwright (ms) — utile en mode visible
    """

    # Chaque sous-classe DOIT redéfinir ces 2 attributs
    name: str = ""           # ex: "perplexity"
    base_url: str = ""       # ex: "https://www.perplexity.ai"

    def __init__(
        self,
        headless: bool = False,
        session_dir: Optional[Path] = None,
        screenshot_dir: Optional[Path] = None,
        timeout_ms: int = 60_000,
        slow_mo_ms: int = 50,
    ):
        if not self.name or not self.base_url:
            raise NotImplementedError(
                f"{type(self).__name__} doit définir 'name' et 'base_url'"
            )

        self.headless = headless
        self.timeout_ms = timeout_ms
        self.slow_mo_ms = slow_mo_ms

        # Répertoires : par défaut sous crawlers/<name>/
        base = Path(__file__).parent.resolve()
        self.session_dir = session_dir or (base / "sessions" / self.name)
        self.screenshot_dir = screenshot_dir or (base / "screenshots")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Initialisés dans __enter__ via Playwright
        self._playwright = None
        self._context = None
        self._page = None

    # ── Context manager : garantit la fermeture propre ─────
    def _get_sync_playwright(self):
        """Retourne le sync_playwright à utiliser.

        Les sous-classes peuvent override pour utiliser patchright
        (anti-Cloudflare) au lieu de playwright standard.

        Par défaut : playwright standard.
        """
        from playwright.sync_api import sync_playwright
        return sync_playwright

    def _get_launch_kwargs(self) -> dict:
        """Kwargs pour launch_persistent_context. Override dans sous-classes si besoin."""
        return {
            "user_data_dir": str(self.session_dir),
            "headless": self.headless,
            "slow_mo": self.slow_mo_ms,
            "viewport": {"width": 1280, "height": 800},
        }

    def __enter__(self):
        sync_playwright = self._get_sync_playwright()

        self._playwright = sync_playwright().start()
        # launch_persistent_context : navigateur avec session sauvegardée sur disque
        # → cookies, localStorage, history persistent entre runs
        self._context = self._playwright.chromium.launch_persistent_context(
            **self._get_launch_kwargs(),
        )
        self._context.set_default_timeout(self.timeout_ms)
        # On réutilise la première page si elle existe (cas d'un context persistant)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

        # Login check à l'ouverture
        self._ensure_logged_in()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._context:
                self._context.close()
        finally:
            if self._playwright:
                self._playwright.stop()
        return False  # ne supprime pas les exceptions

    # ── API publique principale ────────────────────────────
    def query(self, prompt: str, language: Optional[str] = None) -> CrawlerResult:
        """Envoie un prompt au LLM et retourne le résultat structuré."""
        if not self._page:
            raise RuntimeError(
                f"{self.name} crawler n'est pas démarré. "
                "Utilise le context manager : `with PerplexityCrawler() as c:`"
            )

        start = time.time()
        try:
            result = self._do_query(prompt, language=language)
            result.crawler_name = self.name
            result.language = language
            result.crawl_duration_ms = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return CrawlerResult(
                prompt=prompt,
                response_text="",
                crawler_name=self.name,
                language=language,
                crawl_duration_ms=int((time.time() - start) * 1000),
                error=f"{type(e).__name__}: {e}",
            )

    def screenshot_path_for(self, suffix: str = "") -> Path:
        """Génère un path unique pour un screenshot, sous screenshot_dir/."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        suffix_part = f"_{suffix}" if suffix else ""
        return self.screenshot_dir / f"{self.name}_{ts}{suffix_part}.png"

    # ── Méthodes à implémenter par les sous-classes ────────
    @abstractmethod
    def _ensure_logged_in(self) -> None:
        """Vérifie que l'utilisateur est loggué.

        Si non, met en pause pour permettre un login manuel (en mode headed)
        ou raise une RuntimeError (en mode headless).
        """
        ...

    @abstractmethod
    def _do_query(self, prompt: str, language: Optional[str] = None) -> CrawlerResult:
        """Implémentation spécifique de l'envoi du prompt et de l'extraction.

        Doit retourner un CrawlerResult avec au minimum :
          - prompt (le prompt envoyé)
          - response_text (la réponse du LLM)

        Et idéalement :
          - sources (liste de CrawlerSource)
          - model_used (nom du modèle utilisé)
          - screenshot_path
        """
        ...