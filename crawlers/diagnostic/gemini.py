"""
Voxa — Diagnostic DOM gemini.google.com
========================================
Script de découverte des sélecteurs DOM de Gemini.
Lance Chromium avec un profil persistant, navigue sur gemini.google.com,
et dumpe les éléments clés de l'interface.

Usage :
    python3 -m crawlers.diagnostic.gemini
    python3 -m crawlers.diagnostic.gemini --query "test prompt"
"""

import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright


SESSION_DIR = Path(__file__).parent.parent / "sessions" / "gemini_patchright"
URL = "https://gemini.google.com"
LOGIN_WAIT_S = 300


def dump_selectors(page, label: str, selectors: list[tuple[str, str]]):
    """Teste une liste de sélecteurs et affiche ceux qui matchent."""
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    for name, sel in selectors:
        try:
            count = page.locator(sel).count()
            if count > 0:
                el = page.locator(sel).first
                tag = el.evaluate("e => e.tagName") if count > 0 else "?"
                text = (el.inner_text(timeout=2000) or "")[:80].replace("\n", " ")
                attrs = el.evaluate("""e => {
                    const a = {};
                    for (const attr of e.attributes) a[attr.name] = attr.value;
                    return a;
                }""")
                print(f"  ✓ {name}")
                print(f"    selector : {sel}")
                print(f"    count    : {count}")
                print(f"    tag      : {tag}")
                print(f"    text     : {text[:60]}")
                for k in ("role", "aria-label", "data-testid", "contenteditable",
                          "class", "type", "placeholder", "jsname", "jsaction"):
                    if k in attrs:
                        val = attrs[k][:80] if len(attrs.get(k, "")) > 80 else attrs.get(k, "")
                        print(f"    {k} : {val}")
            else:
                print(f"  ✗ {name} — pas trouvé ({sel})")
        except Exception as e:
            print(f"  ⚠ {name} — erreur : {e}")


def dump_html_snippet(page, selector: str, label: str, max_len: int = 2000):
    """Dumpe le HTML interne d'un élément."""
    try:
        el = page.locator(selector).first
        if el.count() > 0:
            html = el.evaluate("e => e.outerHTML")
            print(f"\n{'─' * 60}")
            print(f"  HTML : {label}")
            print(f"{'─' * 60}")
            print(html[:max_len])
            if len(html) > max_len:
                print(f"  ... (tronqué, {len(html)} chars total)")
    except Exception as e:
        print(f"  ⚠ HTML dump {label} : {e}")


def main():
    do_query = "--query" in sys.argv
    query_text = ""
    if do_query:
        idx = sys.argv.index("--query")
        query_text = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Quel est le meilleur site de paris sportifs en France en 2025 ?"

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 60}")
    print(f"  Diagnostic DOM gemini.google.com")
    print(f"  Session : {SESSION_DIR}")
    print(f"  Query   : {'oui → ' + query_text[:50] if do_query else 'non (lecture DOM seule)'}")
    print(f"{'═' * 60}\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        ctx.set_default_timeout(60_000)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Navigation
        print("→ Navigation vers gemini.google.com...")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # Vérification login
        print("→ Vérification login...")
        logged_in = False

        # Détection robuste : on vérifie l'ABSENCE du bouton "Connexion"
        # ET la présence d'un indicateur post-login (avatar, historique).
        # NOTE: le contenteditable existe aussi en mode anonyme → pas fiable.
        def _is_logged_in() -> bool:
            """True si l'utilisateur est authentifié sur Gemini."""
            try:
                # Signal négatif : bouton "Connexion" / "Sign in" visible = PAS loggué
                sign_in_selectors = [
                    'a:has-text("Connexion")',
                    'a:has-text("Sign in")',
                    'button:has-text("Connexion")',
                    'button:has-text("Sign in")',
                ]
                for sel in sign_in_selectors:
                    if page.locator(sel).count() > 0:
                        return False
            except Exception:
                pass

            try:
                # Signaux positifs : éléments qui n'existent QUE post-login
                logged_in_selectors = [
                    # Mode switcher (Gemini Advanced) — le plus fiable
                    'button[aria-label*="sélecteur de mode"]',
                    'button[aria-label*="mode selector"]',
                    # Menu principal (loggué)
                    'button[aria-label*="Menu principal"]',
                ]
                for sel in logged_in_selectors:
                    if page.locator(sel).count() > 0:
                        return True
            except Exception:
                pass
            return False

        logged_in = _is_logged_in()
        if logged_in:
            print("  ✓ Loggué (bouton Connexion absent + indicateurs post-login)")

        if not logged_in:
            print()
            print("╔══════════════════════════════════════════════════════════════╗")
            print("║  ÉTAPE LOGIN GEMINI                                          ║")
            print("║                                                              ║")
            print("║  → Fenêtre Chromium ouverte sur gemini.google.com            ║")
            print("║  → Connecte-toi avec ton compte Google (Gemini Advanced)     ║")
            print("║  → 2FA si nécessaire                                         ║")
            print("║  → Vérifie que tu arrives bien sur l'interface principale    ║")
            print("║                                                              ║")
            print("║  Le script reprend automatiquement dès détection du login.   ║")
            print(f"║  Timeout : {LOGIN_WAIT_S} secondes"
                  f"{' ' * (47 - len(str(LOGIN_WAIT_S)))}║")
            print("╚══════════════════════════════════════════════════════════════╝")
            print()

            deadline = time.time() + LOGIN_WAIT_S
            while time.time() < deadline:
                time.sleep(2)
                if _is_logged_in():
                    logged_in = True
                    print("  ✓ Login détecté")
                    page.wait_for_timeout(3000)
                    break
                remaining = int(deadline - time.time())
                if remaining % 15 < 2:
                    print(f"  ... {remaining}s restantes")

            if not logged_in:
                print("  ✗ Timeout login, dump DOM quand même")

        # ════════════════════════════════════════════
        # PHASE 1 : Sélecteurs candidats
        # ════════════════════════════════════════════
        # ── Phase 1 : count-only (pas d'evaluate, Gemini Angular bloque)
        print("\n" + "═" * 60)
        print("  PHASE 1 : Sélecteurs candidats (count-only)")
        print("═" * 60)

        quick_checks = [
            # Input
            ("INPUT .ql-editor", ".ql-editor"),
            ("INPUT [role=textbox]", '[role="textbox"]'),
            ("INPUT contenteditable", 'div[contenteditable="true"]'),
            # Send
            ("SEND Envoyer", 'button[aria-label*="Envoyer"]'),
            ("SEND Send", 'button[aria-label*="Send"]'),
            # Mode
            ("MODE bard-mode-menu", '[data-testid="bard-mode-menu-button"]'),
            ("MODE sélecteur", 'button[aria-label*="sélecteur de mode"]'),
            # Sources (pre-query)
            ("SOURCE class", '[class*="source"]'),
            # Response (pre-query)
            ("RESPONSE model-response", "model-response"),
            ("RESPONSE response-container", "response-container"),
        ]
        for name, sel in quick_checks:
            try:
                c = page.locator(sel).count()
                mark = "✓" if c > 0 else "✗"
                print(f"  {mark} {name} ({sel}) — count={c}")
            except Exception as e:
                print(f"  ⚠ {name} — {e}")

        # ════════════════════════════════════════════
        # PHASE 3 : Envoi prompt de test
        # ════════════════════════════════════════════
        if do_query and logged_in:
            print("\n" + "═" * 60)
            print(f"  PHASE 3 : Envoi prompt de test")
            print(f"  → {query_text[:70]}")
            print("═" * 60)

            # Trouver l'input
            input_sel = None
            for sel in ['div[contenteditable="true"]', '.ql-editor',
                        '[role="textbox"]', 'textarea']:
                try:
                    if page.locator(sel).count() > 0:
                        input_sel = sel
                        break
                except Exception:
                    pass

            if not input_sel:
                print("  ✗ Input introuvable, abort Phase 3")
            else:
                print(f"  → Input : {input_sel}")
                el = page.locator(input_sel).first
                el.click()
                page.wait_for_timeout(500)
                page.keyboard.type(query_text)
                page.wait_for_timeout(1000)

                # Chercher le bouton send
                send_clicked = False
                for sel in ['button[aria-label*="Send"]', 'button[aria-label*="Envoyer"]',
                            'button[aria-label*="send"]', 'button[aria-label*="submit"]',
                            'button[type="submit"]']:
                    try:
                        btn = page.locator(sel).first
                        if btn.count() > 0 and btn.is_visible():
                            btn.click(timeout=3000)
                            send_clicked = True
                            print(f"  → Envoyé via bouton : {sel}")
                            break
                    except Exception:
                        continue

                if not send_clicked:
                    print("  → Pas de bouton Send trouvé, envoi via Enter")
                    page.keyboard.press("Enter")

                # 3b) DOM pendant streaming (t+4s)
                time.sleep(4)
                print("\n" + "─" * 60)
                print("  PHASE 3b : DOM pendant streaming (t+4s)")
                print("─" * 60)

                # Indicateurs streaming ciblés (pas de querySelectorAll('*'))
                dump_selectors(page, "Streaming indicators", [
                    ("model-response tag", "model-response"),
                    ("response-container", "response-container"),
                    ("processing-state", "processing-state"),
                    ("google-search label", 'span:has-text("Google Search")'),
                    ("thinking", '[class*="thinking"], [class*="loading"]'),
                ])

                # Stop button
                for sn, sl in [
                    ("stop", 'button[aria-label*="Stop"]'),
                    ("arrêter", 'button[aria-label*="Arrêter"]'),
                    ("stop testid", '[data-testid*="stop"]'),
                ]:
                    try:
                        c = page.locator(sl).count()
                        if c > 0:
                            print(f"  ✓ {sn} trouvé ({sl}) count={c}")
                    except Exception:
                        pass

                # Screenshot streaming
                ss_dir = Path(__file__).parent.parent / "screenshots"
                ss_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(ss_dir / "gemini_streaming.png"), full_page=True)
                print(f"  📸 {ss_dir / 'gemini_streaming.png'}")

                # 3c) Attente fin streaming (max 90s)
                print("\n  → Attente fin streaming (max 90s)...")
                deadline = time.time() + 90
                while time.time() < deadline:
                    time.sleep(2)
                    # Signal fin : bouton copy/retry apparaît, ou stop disparaît + texte long
                    for sel in ['button[aria-label*="Copy"]', 'button[aria-label*="Copier"]',
                                'button[aria-label*="copy"]',
                                'button[aria-label*="Retry"]', 'button[aria-label*="Réessayer"]',
                                'button[aria-label*="Share"]', 'button[aria-label*="Partager"]',
                                '[data-testid*="copy"]']:
                        try:
                            if page.locator(sel).count() > 0:
                                print(f"  ✓ Fin détectée via : {sel}")
                                deadline = 0
                                break
                        except Exception:
                            pass
                    remaining = int(deadline - time.time()) if deadline > 0 else 0
                    if remaining > 0 and remaining % 10 < 2:
                        print(f"  ... {remaining}s")

                page.wait_for_timeout(3000)

                # ════════════════════════════════════════════
                # PHASE 3d : DOM post-réponse complet
                # ════════════════════════════════════════════
                print("\n" + "═" * 60)
                print("  PHASE 3d : DOM post-réponse")
                print("═" * 60)

                # Sélecteurs réponse + sources (count-only, pas d'evaluate)
                post_checks = [
                    ("RESP model-response", "model-response"),
                    ("RESP response-container", "response-container"),
                    ("RESP markdown", '[class*="markdown"]'),
                    ("RESP message-content", "message-content"),
                    ("SRC source class", '[class*="source"]'),
                    ("SRC citation class", '[class*="citation"]'),
                    ("SRC footnote", '[class*="footnote"]'),
                    ("SRC sup a", "sup a"),
                    ("SRC chip", '[class*="chip"]'),
                    ("SRC fact-check", '[class*="fact-check"]'),
                    ("SRC location-clickable", '.location-clickable'),
                ]
                print()
                for name, sel in post_checks:
                    try:
                        c = page.locator(sel).count()
                        mark = "✓" if c > 0 else "✗"
                        print(f"  {mark} {name} — count={c}")
                    except Exception:
                        print(f"  ⚠ {name}")

                # Liens externes
                try:
                    links = page.evaluate("""
                        () => {
                            const links = document.querySelectorAll('a[href^="http"]');
                            return Array.from(links).map(a => ({
                                href: a.href,
                                text: a.innerText.trim().slice(0, 100),
                                className: (a.className || '').toString().slice(0, 50),
                                parentTag: a.parentElement?.tagName,
                                parentClass: (a.parentElement?.className || '').toString().slice(0, 40),
                            })).filter(l =>
                                !l.href.includes('google.com') ||
                                l.href.includes('google.com/search')
                            ).filter(l =>
                                !l.href.includes('accounts.google') &&
                                !l.href.includes('support.google') &&
                                !l.href.includes('policies.google')
                            );
                        }
                    """)
                    print(f"\n{'─' * 60}")
                    print(f"  LIENS EXTERNES ({len(links)})")
                    print(f"{'─' * 60}")
                    for l in links[:25]:
                        print(f"  {l['href'][:70]}")
                        print(f"    text: {l['text'][:50]}")
                        print(f"    parent: {l.get('parentTag')}.{l.get('parentClass', '')[:30]}")
                except Exception as e:
                    print(f"  ⚠ Dump liens : {e}")

                # Texte réponse
                try:
                    resp = page.evaluate("""
                        () => {
                            for (const sel of ['[class*="markdown"]',
                                               '[class*="model-response"]',
                                               '[class*="response-container"]',
                                               'message-content']) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText.length > 50)
                                    return { sel, text: el.innerText.trim().slice(0, 2000),
                                             len: el.innerText.length };
                            }
                            return null;
                        }
                    """)
                    if resp:
                        print(f"\n{'─' * 60}")
                        print(f"  TEXTE RÉPONSE ({resp['len']} chars via {resp['sel']})")
                        print(f"{'─' * 60}")
                        print(f"  {resp['text'][:1500]}")
                    else:
                        print("\n  ⚠ Aucune réponse textuelle trouvée")
                except Exception as e:
                    print(f"  ⚠ {e}")

                # Screenshot final
                page.screenshot(path=str(ss_dir / "gemini_response.png"), full_page=True)
                print(f"\n  📸 {ss_dir / 'gemini_response.png'}")

        # ════════════════════════════════════════════
        # Fin
        # ════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("  Diagnostic terminé.")
        print("  Fenêtre Chromium reste ouverte pour inspection.")
        print("  → Ctrl+C pour fermer.")
        print("═" * 60 + "\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n→ Fermeture...")

        ctx.close()


if __name__ == "__main__":
    main()
