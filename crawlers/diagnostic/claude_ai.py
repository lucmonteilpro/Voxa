"""
Voxa — Diagnostic DOM claude.ai
================================
Script de découverte des sélecteurs DOM de claude.ai.
Lance Chrome avec un profil persistant, navigue sur claude.ai,
et dumpe les éléments clés de l'interface.

Usage :
    python3 -m crawlers.diagnose_claude_ai_dom
    python3 -m crawlers.diagnose_claude_ai_dom --query "test prompt"
"""

import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright


SESSION_DIR = Path(__file__).parent.parent / "sessions" / "claude_ai_patchright"
URL = "https://claude.ai"
LOGIN_WAIT_S = 300  # 5 min — OAuth Google en chaîne peut être long


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
                # Show key attributes
                for k in ("role", "aria-label", "data-testid", "contenteditable",
                          "class", "type", "placeholder"):
                    if k in attrs:
                        val = attrs[k][:80] if len(attrs.get(k, "")) > 80 else attrs.get(k, "")
                        print(f"    {k} : {val}")
            else:
                print(f"  ✗ {name} — pas trouvé ({sel})")
        except Exception as e:
            print(f"  ⚠ {name} — erreur : {e}")


def dump_html_snippet(page, selector: str, label: str, max_len: int = 1500):
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
        query_text = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Quels sont les meilleurs sites de paris sportifs en France ?"

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 60}")
    print(f"  Diagnostic DOM claude.ai")
    print(f"  Session : {SESSION_DIR}")
    print(f"  Query   : {'oui → ' + query_text[:50] if do_query else 'non (lecture DOM seule)'}")
    print(f"{'═' * 60}\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            # Chromium natif Patchright (pas channel="chrome") pour éviter
            # le conflit single-instance avec Chrome principal ouvert.
            viewport={"width": 1280, "height": 900},
        )
        ctx.set_default_timeout(60_000)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Navigation
        print("→ Navigation vers claude.ai...")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Vérification login
        print("→ Vérification login...")
        # Essayer de détecter si on est loggué
        logged_in = False
        login_indicators = [
            ('avatar/menu', '[data-testid="user-menu"], button[aria-label*="Account"], button[aria-label*="Compte"]'),
            ('input box', '[contenteditable="true"], textarea[placeholder], div[role="textbox"]'),
            ('new chat btn', 'button:has-text("New chat"), button:has-text("Nouvelle conversation"), a[href="/new"]'),
        ]
        for name, sel in login_indicators:
            try:
                if page.locator(sel).count() > 0:
                    print(f"  ✓ Indicateur login trouvé : {name}")
                    logged_in = True
                    break
            except Exception:
                pass

        if not logged_in:
            print()
            print("╔══════════════════════════════════════════════════════════════╗")
            print("║  ÉTAPE LOGIN — Voxa attend ta connexion à claude.ai          ║")
            print("║                                                              ║")
            print("║  → Fenêtre Chrome ouverte sur claude.ai                      ║")
            print("║  → Connecte-toi (Google OAuth ou email/password)             ║")
            print("║  → Le script reprend automatiquement dès qu'il détecte       ║")
            print("║    que tu es dans l'interface principale                     ║")
            print("║                                                              ║")
            print(f"║  Timeout : {LOGIN_WAIT_S} secondes{' ' * (47 - len(str(LOGIN_WAIT_S)))}║")
            print("╚══════════════════════════════════════════════════════════════╝")
            print()

            # Sélecteurs qui n'existent QUE post-login (interface principale)
            # NOTE: 'nav' existe aussi sur la page publique → ne pas l'utiliser
            post_login_selectors = [
                ('contenteditable', 'div[contenteditable="true"]'),
                ('ProseMirror', '.ProseMirror'),
                ('textarea', 'textarea'),
                ('textbox role', '[role="textbox"]'),
                ('fieldset input', 'fieldset div[contenteditable]'),
                ('new chat link', 'a[href="/new"]'),
                ('chat history', '[class*="conversation"], [class*="Conversation"], [class*="chat-list"]'),
                ('user avatar pro', 'button[data-testid="user-menu"], img[alt*="avatar"], [class*="avatar"]'),
            ]

            deadline = time.time() + LOGIN_WAIT_S
            while time.time() < deadline:
                time.sleep(2)
                for name, sel in post_login_selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            print(f"  ✓ Login détecté via : {name} ({sel})")
                            logged_in = True
                            break
                    except Exception:
                        pass
                if logged_in:
                    page.wait_for_timeout(2000)
                    break
                remaining = int(deadline - time.time())
                if remaining % 10 < 2:  # affiche toutes les ~10s
                    print(f"  ... {remaining}s restantes")

            if not logged_in:
                print("  ✗ Timeout login, dump DOM quand même")

        # Navigation vers /new pour s'assurer d'avoir le composer chargé
        print("\n→ Navigation vers claude.ai/new (composer)...")
        page.goto(f"{URL}/new", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)  # laisser React/Next.js charger

        # ════════════════════════════════════════════
        # PHASE 1 : Dump des sélecteurs candidats
        # ════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("  PHASE 1 : Sélecteurs candidats")
        print("═" * 60)

        # 1) Zone d'input
        dump_selectors(page, "INPUT (zone de saisie)", [
            ("contenteditable div", 'div[contenteditable="true"]'),
            ("contenteditable textbox", 'div[contenteditable="true"][role="textbox"]'),
            ("textarea", "textarea"),
            ("prosemirror", ".ProseMirror"),
            ("data-testid input", '[data-testid*="input"], [data-testid*="composer"]'),
            ("placeholder attr", '[placeholder*="message"], [placeholder*="Message"], [placeholder*="Claude"]'),
            ("fieldset input", 'fieldset div[contenteditable="true"]'),
        ])

        # 2) Bouton Send
        dump_selectors(page, "SEND (bouton envoi)", [
            ("aria-label send", 'button[aria-label*="Send"], button[aria-label*="Envoyer"]'),
            ("data-testid send", '[data-testid*="send"]'),
            ("submit button", 'button[type="submit"]'),
            ("svg arrow up", 'button:has(svg) >> nth=-1'),  # souvent le dernier bouton avec icône
        ])

        # 3) Sélection modèle
        dump_selectors(page, "MODEL SELECTOR (choix du modèle)", [
            ("data-testid model", '[data-testid*="model"]'),
            ("aria-label model", 'button[aria-label*="model"], button[aria-label*="Model"], button[aria-label*="Modèle"]'),
            ("button with model name", 'button:has-text("Sonnet"), button:has-text("Opus"), button:has-text("Haiku")'),
            ("select/dropdown model", 'select, [role="listbox"], [role="combobox"]'),
            ("popover trigger", '[data-testid*="selector"], [data-testid*="picker"]'),
            ("menu button", 'button[aria-haspopup="menu"], button[aria-haspopup="listbox"]'),
        ])

        # 4) Toggle Web Search
        dump_selectors(page, "WEB SEARCH (toggle)", [
            ("data-testid search", '[data-testid*="search"], [data-testid*="web"]'),
            ("aria-label search", 'button[aria-label*="search"], button[aria-label*="Search"], button[aria-label*="web"]'),
            ("switch role", '[role="switch"]'),
            ("checkbox search", 'input[type="checkbox"]'),
            ("toggle button text", 'button:has-text("Search"), button:has-text("Recherche"), button:has-text("Web")'),
        ])

        # 5) Zone de réponse / streaming
        dump_selectors(page, "RESPONSE (zone de réponse)", [
            ("data-testid response", '[data-testid*="response"], [data-testid*="message"]'),
            ("prose class", 'div[class*="prose"]'),
            ("markdown class", 'div[class*="markdown"], div[class*="Markdown"]'),
            ("assistant message", '[data-testid*="assistant"], [class*="assistant"]'),
            ("article", "article"),
            ("role article", '[role="article"]'),
        ])

        # 6) Indicateur streaming
        dump_selectors(page, "STREAMING INDICATOR", [
            ("stop button", 'button[aria-label*="Stop"], button[aria-label*="Arrêter"]'),
            ("data-testid stop", '[data-testid*="stop"]'),
            ("loading/spinner", '[class*="loading"], [class*="spinner"], [class*="animate"]'),
            ("cursor blink", '[class*="cursor"], [class*="caret"]'),
        ])

        # 7) Sources / Citations
        dump_selectors(page, "SOURCES / CITATIONS", [
            ("footnote", '[class*="footnote"], [class*="citation"], [class*="source"]'),
            ("data-testid source", '[data-testid*="source"], [data-testid*="citation"]'),
            ("sup links", "sup a, a sup"),
            ("reference section", '[class*="reference"], [class*="Reference"]'),
        ])

        # ════════════════════════════════════════════
        # PHASE 1b : Dump exhaustif data-testid + aria + roles
        # ════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("  PHASE 1b : Tous les data-testid sur la page")
        print("═" * 60)
        try:
            testids = page.evaluate("""
                () => Array.from(document.querySelectorAll('[data-testid]'))
                    .map(el => ({
                        testid: el.getAttribute('data-testid'),
                        tag: el.tagName,
                        text: (el.innerText || '').trim().slice(0, 60).replace(/\\n/g, ' '),
                        role: el.getAttribute('role'),
                        type: el.getAttribute('type'),
                    }))
            """)
            for t in testids:
                role_s = f" role={t['role']}" if t.get('role') else ""
                type_s = f" type={t['type']}" if t.get('type') else ""
                print(f"  [{t['tag']:10s}] data-testid=\"{t['testid']}\"{role_s}{type_s}")
                if t['text']:
                    print(f"             text: {t['text'][:60]}")
        except Exception as e:
            print(f"  ⚠ Erreur : {e}")

        print("\n" + "═" * 60)
        print("  PHASE 1c : Tous les aria-label buttons")
        print("═" * 60)
        try:
            aria_btns = page.evaluate("""
                () => Array.from(document.querySelectorAll('button[aria-label]'))
                    .map(el => ({
                        label: el.getAttribute('aria-label'),
                        text: (el.innerText || '').trim().slice(0, 60).replace(/\\n/g, ' '),
                        haspopup: el.getAttribute('aria-haspopup'),
                        testid: el.getAttribute('data-testid'),
                    }))
            """)
            for b in aria_btns:
                popup_s = f" haspopup={b['haspopup']}" if b.get('haspopup') else ""
                tid_s = f" data-testid={b['testid']}" if b.get('testid') else ""
                print(f"  aria-label=\"{b['label']}\"{popup_s}{tid_s}")
                if b['text'] and b['text'] != b['label']:
                    print(f"    text: {b['text'][:50]}")
        except Exception as e:
            print(f"  ⚠ Erreur : {e}")

        print("\n" + "═" * 60)
        print("  PHASE 1d : contenteditable + textarea + input[type=text]")
        print("═" * 60)
        try:
            inputs = page.evaluate("""
                () => {
                    const els = [
                        ...document.querySelectorAll('[contenteditable]'),
                        ...document.querySelectorAll('textarea'),
                        ...document.querySelectorAll('input[type="text"]'),
                    ];
                    return els.map(el => ({
                        tag: el.tagName,
                        ce: el.getAttribute('contenteditable'),
                        role: el.getAttribute('role'),
                        testid: el.getAttribute('data-testid'),
                        placeholder: el.getAttribute('placeholder'),
                        className: (el.className || '').slice(0, 80),
                        parentTag: el.parentElement?.tagName,
                        parentClass: (el.parentElement?.className || '').slice(0, 50),
                    }));
                }
            """)
            for inp in inputs:
                ce_s = f" contenteditable={inp['ce']}" if inp.get('ce') else ""
                role_s = f" role={inp['role']}" if inp.get('role') else ""
                tid_s = f" data-testid={inp['testid']}" if inp.get('testid') else ""
                ph_s = f" placeholder=\"{inp['placeholder']}\"" if inp.get('placeholder') else ""
                print(f"  [{inp['tag']}]{ce_s}{role_s}{tid_s}{ph_s}")
                print(f"    class: {inp.get('className', '')[:60]}")
                print(f"    parent: {inp.get('parentTag')}.{inp.get('parentClass', '')[:40]}")
        except Exception as e:
            print(f"  ⚠ Erreur : {e}")

        # ════════════════════════════════════════════
        # PHASE 2 : Dump HTML brut des zones clés
        # ════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("  PHASE 2 : HTML brut des zones clés")
        print("═" * 60)

        # Dump la zone d'input
        for sel in ['div[contenteditable="true"]', '.ProseMirror', 'fieldset']:
            dump_html_snippet(page, sel, f"Input ({sel})", 800)

        # Dump la toolbar / barre d'actions (contient souvent model picker + send)
        for sel in ['fieldset', 'form', '[class*="composer"], [class*="Composer"]']:
            dump_html_snippet(page, sel, f"Toolbar ({sel})", 2000)

        # ════════════════════════════════════════════
        # PHASE 3 : Envoi prompt de test + capture streaming + sources
        # ════════════════════════════════════════════
        if do_query and logged_in:
            print("\n" + "═" * 60)
            print(f"  PHASE 3 : Envoi prompt de test")
            print(f"  → {query_text[:70]}")
            print("═" * 60)

            # 3a) Clic + type + Enter via le sélecteur validé
            input_el = page.locator('[data-testid="chat-input"]')
            if input_el.count() == 0:
                print("  ✗ [data-testid='chat-input'] introuvable, abort Phase 3")
            else:
                input_el.first.click()
                page.wait_for_timeout(500)
                page.keyboard.type(query_text)
                page.wait_for_timeout(800)
                print("  → Texte tapé, envoi via Enter...")
                page.keyboard.press("Enter")

                # 3b) Dump DOM PENDANT le streaming (2s après envoi)
                time.sleep(3)
                print("\n" + "─" * 60)
                print("  PHASE 3b : DOM pendant streaming (t+3s)")
                print("─" * 60)

                # Chercher tout indicateur visuel de streaming/search
                try:
                    indicators = page.evaluate("""
                        () => {
                            // Cherche textes indicateurs de recherche web
                            const searchTerms = ['search', 'recherche', 'looking', 'browsing',
                                                 'source', 'web', 'fetching'];
                            const allEls = document.querySelectorAll('*');
                            const found = [];
                            for (const el of allEls) {
                                const text = (el.innerText || '').toLowerCase().trim();
                                if (text.length > 3 && text.length < 100) {
                                    for (const term of searchTerms) {
                                        if (text.includes(term)) {
                                            found.push({
                                                tag: el.tagName,
                                                text: el.innerText.trim().slice(0, 80),
                                                class: (el.className || '').toString().slice(0, 60),
                                                testid: el.getAttribute('data-testid'),
                                                role: el.getAttribute('role'),
                                                visible: el.offsetParent !== null,
                                            });
                                            break;
                                        }
                                    }
                                }
                            }
                            return found.slice(0, 20);
                        }
                    """)
                    print(f"  Indicateurs search/streaming : {len(indicators)} trouvés")
                    for ind in indicators:
                        vis = " [VISIBLE]" if ind.get('visible') else " [hidden]"
                        tid = f" testid={ind['testid']}" if ind.get('testid') else ""
                        print(f"    [{ind['tag']}]{vis}{tid} — {ind['text'][:60]}")
                except Exception as e:
                    print(f"  ⚠ Erreur indicateurs : {e}")

                # Dump tous les nouveaux data-testid apparus
                try:
                    testids_streaming = page.evaluate("""
                        () => Array.from(document.querySelectorAll('[data-testid]'))
                            .map(el => ({
                                testid: el.getAttribute('data-testid'),
                                tag: el.tagName,
                                text: (el.innerText || '').trim().slice(0, 50).replace(/\\n/g, ' '),
                                visible: el.offsetParent !== null,
                            }))
                    """)
                    print(f"\n  data-testid pendant streaming ({len(testids_streaming)}) :")
                    for t in testids_streaming:
                        vis = "✓" if t.get('visible') else "·"
                        print(f"    {vis} [{t['tag']:8s}] {t['testid']}")
                        if t['text']:
                            print(f"      text: {t['text'][:50]}")
                except Exception as e:
                    print(f"  ⚠ Erreur data-testid : {e}")

                # Boutons stop/cancel
                for sel_name, sel in [
                    ("stop FR", 'button[aria-label*="Arrêter"]'),
                    ("stop EN", 'button[aria-label*="Stop"]'),
                    ("stop testid", '[data-testid*="stop"]'),
                    ("cancel", 'button[aria-label*="Cancel"], button[aria-label*="Annuler"]'),
                ]:
                    try:
                        c = page.locator(sel).count()
                        if c > 0:
                            print(f"  ✓ {sel_name} trouvé ({sel}) — count={c}")
                    except Exception:
                        pass

                # Screenshot pendant streaming
                ss_dir = Path(__file__).parent.parent / "screenshots"
                ss_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(ss_dir / "claude_ai_streaming.png"), full_page=True)
                print(f"  📸 Screenshot streaming : {ss_dir / 'claude_ai_streaming.png'}")

                # 3c) Attendre fin streaming (max 90s)
                print("\n  → Attente fin streaming (max 90s)...")
                deadline = time.time() + 90

                # Stratégie : poller la disparition du bouton stop OU l'apparition
                # d'un bouton "copy" / "retry" / "thumbs up" (= réponse terminée)
                while time.time() < deadline:
                    time.sleep(2)
                    # Check fin via boutons post-réponse
                    post_response_indicators = [
                        '[data-testid*="copy"]',
                        '[data-testid*="retry"]',
                        'button[aria-label*="Copier"]',
                        'button[aria-label*="Copy"]',
                        'button[aria-label*="Réessayer"]',
                        'button[aria-label*="Retry"]',
                    ]
                    finished = False
                    for sel in post_response_indicators:
                        try:
                            if page.locator(sel).count() > 0:
                                print(f"  ✓ Fin streaming détectée via : {sel}")
                                finished = True
                                break
                        except Exception:
                            pass
                    if finished:
                        break

                    # Check via disparition du bouton stop
                    stop_found = False
                    for sel in ['button[aria-label*="Stop"]', 'button[aria-label*="Arrêter"]',
                                '[data-testid*="stop"]']:
                        try:
                            if page.locator(sel).count() > 0:
                                stop_found = True
                                break
                        except Exception:
                            pass
                    # Si stop n'a jamais été trouvé et on a du texte de réponse → fini
                    if not stop_found:
                        try:
                            # Vérifie s'il y a du texte de réponse substantiel
                            resp_text = page.evaluate("""
                                () => {
                                    const msgs = document.querySelectorAll('[data-testid*="message"], [class*="message"]');
                                    let text = '';
                                    msgs.forEach(m => text += m.innerText);
                                    return text.length;
                                }
                            """)
                            if resp_text > 100:
                                print(f"  ✓ Streaming semble terminé (pas de stop, {resp_text} chars)")
                                break
                        except Exception:
                            pass

                    remaining = int(deadline - time.time())
                    if remaining % 10 < 2:
                        print(f"  ... {remaining}s restantes")

                page.wait_for_timeout(2000)

                # ════════════════════════════════════════════
                # PHASE 3d : Dump POST-RÉPONSE complet
                # ════════════════════════════════════════════
                print("\n" + "═" * 60)
                print("  PHASE 3d : DOM post-réponse")
                print("═" * 60)

                # Tous les data-testid après réponse
                try:
                    testids_post = page.evaluate("""
                        () => Array.from(document.querySelectorAll('[data-testid]'))
                            .map(el => ({
                                testid: el.getAttribute('data-testid'),
                                tag: el.tagName,
                                text: (el.innerText || '').trim().slice(0, 60).replace(/\\n/g, ' '),
                                role: el.getAttribute('role'),
                            }))
                    """)
                    print(f"\n  Tous les data-testid ({len(testids_post)}) :")
                    for t in testids_post:
                        role_s = f" role={t['role']}" if t.get('role') else ""
                        print(f"    [{t['tag']:8s}] {t['testid']}{role_s}")
                        if t['text']:
                            print(f"             → {t['text'][:60]}")
                except Exception as e:
                    print(f"  ⚠ Erreur : {e}")

                # aria-label des boutons post-réponse
                try:
                    aria_post = page.evaluate("""
                        () => Array.from(document.querySelectorAll('button[aria-label]'))
                            .map(el => ({
                                label: el.getAttribute('aria-label'),
                                testid: el.getAttribute('data-testid'),
                                haspopup: el.getAttribute('aria-haspopup'),
                            }))
                            .filter(b => !b.label.startsWith("Plus d'options pour"))
                    """)
                    print(f"\n  aria-label buttons (hors sidebar) : {len(aria_post)}")
                    for b in aria_post:
                        tid_s = f" testid={b['testid']}" if b.get('testid') else ""
                        print(f"    \"{b['label']}\"{tid_s}")
                except Exception as e:
                    print(f"  ⚠ Erreur : {e}")

                # Sélecteurs réponse
                dump_selectors(page, "RÉPONSE (post-query)", [
                    ("prose", 'div[class*="prose"]'),
                    ("markdown", 'div[class*="markdown"]'),
                    ("message-content testid", '[data-testid*="message"]'),
                    ("assistant testid", '[data-testid*="assistant"]'),
                    ("user testid", '[data-testid*="user"]'),
                    ("article", "article"),
                    ("chat-message", '[class*="chat-message"], [class*="ChatMessage"]'),
                ])

                # Sélecteurs sources
                dump_selectors(page, "SOURCES / CITATIONS (post-query)", [
                    ("footnote", '[class*="footnote"]'),
                    ("citation", '[class*="citation"]'),
                    ("source testid", '[data-testid*="source"]'),
                    ("citation testid", '[data-testid*="citation"]'),
                    ("reference testid", '[data-testid*="ref"]'),
                    ("sup a", "sup a"),
                    ("a with sup", "a:has(sup)"),
                    ("search-result", '[class*="search-result"], [data-testid*="search"]'),
                    ("web-source", '[class*="web-source"], [class*="WebSource"]'),
                    ("tooltip source", '[class*="tooltip"]'),
                ])

                # HTML de la réponse
                for sel in ['div[class*="prose"]', 'div[class*="markdown"]',
                            '[data-testid*="message"]']:
                    dump_html_snippet(page, sel, f"Response HTML ({sel})", 3000)

                # Liens externes (sources citées)
                try:
                    links = page.evaluate("""
                        () => {
                            const links = document.querySelectorAll('a[href^="http"]');
                            return Array.from(links).map(a => ({
                                href: a.href,
                                text: a.innerText.trim().slice(0, 100),
                                className: (a.className || '').toString().slice(0, 60),
                                parentTag: a.parentElement?.tagName,
                                parentClass: (a.parentElement?.className || '').toString().slice(0, 40),
                                inSup: !!a.closest('sup'),
                                testid: a.getAttribute('data-testid'),
                                ariaLabel: a.getAttribute('aria-label'),
                            })).filter(l => !l.href.includes('claude.ai') && !l.href.includes('anthropic.com'));
                        }
                    """)
                    print(f"\n{'─' * 60}")
                    print(f"  LIENS EXTERNES ({len(links)} trouvés)")
                    print(f"{'─' * 60}")
                    for l in links[:30]:
                        sup = " [SUP]" if l.get("inSup") else ""
                        tid = f" testid={l['testid']}" if l.get('testid') else ""
                        print(f"  {l['href'][:70]}{sup}{tid}")
                        print(f"    text: {l['text'][:50]}")
                        print(f"    parent: {l.get('parentTag')}.{l.get('parentClass', '')[:30]}")
                        print(f"    class: {l.get('className', '')[:50]}")
                except Exception as e:
                    print(f"  ⚠ Dump liens : {e}")

                # Texte complet de la réponse
                try:
                    resp_full = page.evaluate("""
                        () => {
                            // Tente plusieurs sélecteurs pour la réponse
                            for (const sel of ['[data-testid*="message"]', 'div[class*="prose"]',
                                               'div[class*="markdown"]', 'article']) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText.length > 50) {
                                    return {
                                        selector: sel,
                                        text: el.innerText.trim().slice(0, 2000),
                                        len: el.innerText.length,
                                    };
                                }
                            }
                            return null;
                        }
                    """)
                    if resp_full:
                        print(f"\n{'─' * 60}")
                        print(f"  TEXTE RÉPONSE ({resp_full['len']} chars via {resp_full['selector']})")
                        print(f"{'─' * 60}")
                        print(f"  {resp_full['text'][:1500]}")
                    else:
                        print("\n  ⚠ Aucune réponse textuelle trouvée")
                except Exception as e:
                    print(f"  ⚠ Erreur texte réponse : {e}")

                # Screenshot final
                page.screenshot(path=str(ss_dir / "claude_ai_response.png"), full_page=True)
                print(f"\n  📸 Screenshot réponse : {ss_dir / 'claude_ai_response.png'}")

        # ════════════════════════════════════════════
        # Fin : pause pour inspection manuelle
        # ════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("  Diagnostic terminé.")
        print("  La fenêtre Chrome reste ouverte pour inspection manuelle.")
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
