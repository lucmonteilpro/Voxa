"""
Voxa — Diagnostic ciblé : sources + bouton stop
================================================
Lance un crawl complet, attend une réponse, puis fait un dump détaillé
du DOM pour identifier :
1. Le bon sélecteur du bouton "Stop generating" (pour détecter la fin)
2. Le bon sélecteur des sources citées

Le script :
- Type un prompt
- Attend 30 secondes (réponse a le temps d'arriver)
- Dump tous les éléments DOM intéressants
- Te laisse 60 secondes pour inspecter manuellement avec devtools
- Sauvegarde HTML complet pour analyse offline

Usage :
    python3 -m crawlers.diagnose_response_dom
"""

import json
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

SESSION_DIR = Path(__file__).parent / "sessions" / "perplexity_patchright"
OUTPUT_DIR = Path(__file__).parent / "screenshots"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPT = "Quels sont les meilleurs sites de paris sportifs en France ?"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1) Navigation + envoi prompt
        print("[1] Navigation vers Perplexity...")
        page.goto("https://www.perplexity.ai", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        print("[2] Envoi du prompt...")
        input_box = page.locator('div[contenteditable="true"][role="textbox"]').first
        input_box.click()
        page.wait_for_timeout(300)
        page.keyboard.type(PROMPT)
        page.wait_for_timeout(800)
        page.keyboard.press("Enter")

        # 2) Pendant la génération : capture les boutons visibles
        print("[3] Capture des boutons pendant le streaming (3s après submit)...")
        page.wait_for_timeout(3000)

        streaming_buttons = page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                return Array.from(btns).slice(0, 30).map(b => ({
                    aria_label: b.getAttribute('aria-label'),
                    text: (b.innerText || '').trim().slice(0, 60),
                    classes: b.className.slice(0, 100),
                    visible: b.offsetParent !== null,
                    has_svg: b.querySelector('svg') !== null,
                }));
            }
        """)

        print("\n── Boutons pendant le streaming (potentiel bouton STOP) ──")
        for i, b in enumerate(streaming_buttons):
            if b['visible'] and (b['aria_label'] or b['text']):
                print(f"  [{i:2}] aria={b['aria_label']!r:40s} text={b['text']!r:30s} svg={b['has_svg']}")

        # 3) Attente longue pour réponse complète
        print("\n[4] Attente 35s pour avoir la réponse complète...")
        page.wait_for_timeout(35000)
        page.screenshot(path=str(OUTPUT_DIR / "diag_response_done.png"), full_page=True)

        # 4) Dump structuré du DOM
        print("\n[5] Dump DOM ciblé...")

        # 4a) Tous les <a href> dans la zone de réponse
        all_links = page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).slice(0, 60).map(a => ({
                    href: a.href,
                    text: (a.innerText || '').trim().slice(0, 80),
                    classes: a.className.slice(0, 80),
                    aria_label: a.getAttribute('aria-label'),
                    rel: a.getAttribute('rel'),
                    has_image: a.querySelector('img') !== null,
                }));
            }
        """)

        # Filtre les liens externes (probables sources)
        external_links = [a for a in all_links
                         if a['href'].startswith('http')
                         and 'perplexity.ai' not in a['href']]

        print(f"\n── Tous les <a href> externes ({len(external_links)}) ──")
        for i, a in enumerate(external_links[:30]):
            domain = a['href'].split('/')[2] if '/' in a['href'] else '?'
            print(f"  [{i:2}] {domain:35s} classes={a['classes'][:40]!r}")
            if a['text']:
                print(f"       text: {a['text'][:80]!r}")

        # 4b) Éléments avec data-testid (Perplexity les utilise souvent)
        testid_elements = page.evaluate("""
            () => {
                const els = document.querySelectorAll('[data-testid]');
                return Array.from(els).slice(0, 40).map(e => ({
                    tag: e.tagName,
                    testid: e.getAttribute('data-testid'),
                    text: (e.innerText || '').trim().slice(0, 60),
                }));
            }
        """)

        print(f"\n── Éléments avec data-testid ({len(testid_elements)}) ──")
        for el in testid_elements:
            if el['testid']:
                print(f"  {el['tag']:10s} testid={el['testid']!r:35s} text={el['text']!r}")

        # 4c) Classes contenant "source", "citation", "ref"
        custom_classes = page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                const matches = [];
                for (const el of all) {
                    const cls = el.className || '';
                    if (typeof cls !== 'string') continue;
                    if (/source|citation|reference|ref-/i.test(cls)) {
                        matches.push({
                            tag: el.tagName,
                            classes: cls.slice(0, 100),
                            text: (el.innerText || '').trim().slice(0, 60),
                        });
                    }
                    if (matches.length > 30) break;
                }
                return matches;
            }
        """)

        print(f"\n── Éléments avec classes 'source/citation/ref' ({len(custom_classes)}) ──")
        for el in custom_classes[:20]:
            print(f"  {el['tag']:10s} classes={el['classes'][:60]!r}")
            if el['text']:
                print(f"       text: {el['text'][:60]!r}")

        # 4d) Images dans la réponse (logos sources Perplexity)
        images_with_alt = page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('main img, article img');
                return Array.from(imgs).slice(0, 20).map(img => ({
                    alt: img.alt,
                    src_domain: (img.src || '').split('/')[2],
                    parent_tag: img.parentElement ? img.parentElement.tagName : '?',
                    parent_href: img.closest('a') ? img.closest('a').href : null,
                }));
            }
        """)

        print(f"\n── Images dans la réponse ({len(images_with_alt)}) ──")
        for img in images_with_alt[:15]:
            if img['parent_href']:
                domain = img['parent_href'].split('/')[2] if '/' in img['parent_href'] else '?'
                print(f"  alt={img['alt']!r:30s} parent_link={domain}")

        # 5) Sauvegarde tout
        ts = time.strftime("%Y%m%d_%H%M%S")
        dump_path = OUTPUT_DIR / f"diag_dom_{ts}.json"
        dump = {
            "streaming_buttons": streaming_buttons,
            "external_links": external_links,
            "testid_elements": testid_elements,
            "custom_classes": custom_classes,
            "images_with_alt": images_with_alt,
        }
        dump_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")

        html_path = OUTPUT_DIR / f"diag_dom_{ts}.html"
        html_path.write_text(page.content(), encoding="utf-8")

        print(f"\n✓ Dump JSON   : {dump_path}")
        print(f"✓ HTML complet: {html_path}")

        print("\n" + "=" * 70)
        print("PAUSE 60s — inspecte manuellement avec devtools si besoin")
        print("Cmd+Option+I → trouve une source citée → note le HTML qui l'entoure")
        print("=" * 70)

        for remaining in range(60, 0, -15):
            time.sleep(15)
            print(f"  ... {remaining - 15}s restantes")

        ctx.close()
        print("\n✓ Diagnostic terminé.")


if __name__ == "__main__":
    main()