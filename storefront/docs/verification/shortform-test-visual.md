# U5b VISUAL GATES report (G6 responsive, G7 palette, G8 honesty)

Env: site https://shortform-studio-storefront.omnistack.workers.dev ; repo nexuslbs/shortform-studio main@81576780a4c2bc879b37ab96483a90587899888f (not modified). Browser: facade `browser` @ http://localhost:8080/api/tool/call, provider playwright, chromium 153.0.8010.12 headful via remote CDP http://browser:9222 (real browser). Host: workstation (bash). No checkout/payment started.

## G6 RESPONSIVE (raw numbers, document.documentElement.scrollWidth vs window.innerWidth)
Procedure: `open` per width (viewportWidth=375/768/1440, headless=false) then `navigate` + `evaluate` + `screenshot` into /var/lib/workstation/work/shots/<page>-<width>.png. All 15 shots written ok (non-zero bytes).

| page | width | scrollWidth | innerWidth | body.scrollWidth | overflow(sw>iw) |
|---|---|---|---|---|---|
| / | 375 | 360 | 375 | 360 | false |
| /product/video-pack-roman-concrete | 375 | 360 | 375 | 360 | false |
| /product/studio-monthly-4 | 375 | 375 | 375 | 375 | false |
| /cancel | 375 | 375 | 375 | 375 | false |
| /success?checkout_id=cc879d19... | 375 | 375 | 375 | 375 | false |
| / | 768 | 753 | 768 | 753 | false |
| /product/video-pack-roman-concrete | 768 | 753 | 768 | 753 | false |
| /product/studio-monthly-4 | 768 | 768 | 768 | 768 | false |
| /cancel | 768 | 768 | 768 | 768 | false |
| /success?checkout_id=cc879d19... | 768 | 768 | 768 | 768 | false |
| / | 1440 | 1425 | 1440 | 1425 | false |
| /product/video-pack-roman-concrete | 1440 | 1425 | 1440 | 1425 | false |
| /product/studio-monthly-4 | 1440 | 1440 | 1440 | 1440 | false |
| /cancel | 1440 | 1440 | 1440 | 1440 | false |
| /success?checkout_id=cc879d19... | 1440 | 1440 | 1440 | 1440 | false |

All 15 combos: scrollWidth <= innerWidth -> NO horizontal overflow. (sw < iw by 15px on pages with a vertical scrollbar; that is the scrollbar allowance, not overflow.) G6 = PASS.

## G7 PALETTE
Command: `curl -s <site>/ | grep -oE '#[0-9a-fA-F]{6}' | sort -u` (same for /product/video-pack-roman-concrete and /product/studio-monthly-4; identical lists on all 5 pages), vs `grep -oE '#[0-9a-fA-F]{6}' /opt/workspace/omni-dashboard/src/style.css | sort -u`.

deployed (14): #06b6d4 #0a0f1e #0b1020 #0d1321 #10b981 #111827 #3b82f6 #64748b #8b5cf6 #94a3b8 #a78bfa #f1f5f9 #f43f5e #f59e0b
style.css (38): #06b6d4 #0a0f1e #0d1321 #10b981 #111827 #1a1a2e #22c55e #22d3ee #30363d #34d399 #3b82f6 #475569 #4ade80 #58a6ff #60a5fa #6366f1 #64748b #6ee7b7 #7c3aed #818cf8 #8b5cf6 #93c5fd #94a3b8 #a78bfa #a855f7 #c084fc #cbd5e1 #d2a8ff #e0e0e0 #e8b64c #ef4444 #f1f5f9 #f43f5e #f59e0b #f85149 #facc15 #fb7185 #fbbf24
intersection = 13
deployed NOT in style.css (1): #0b1020
Usage in deployed HTML: `color: #0b1020; font-weight: 700; borde...` (inline CSS, text color).
G7 = FAIL: one deployed palette token (#0b1020) is not a token in style.css.

## G8 HONESTY + NOTICE
Command: `curl -s <site><path> -o page.html; grep -o 'SANDBOX / DEMO - no real payment' page.html | wc -l; grep -oE '127\.0\.0\.1:8799|MOCKCO_|placeholder checkout' page.html | wc -l`

| page | notice count | banned count |
|---|---|---|
| / | 2 | 0 |
| /product/video-pack-roman-concrete | 2 | 0 |
| /product/studio-monthly-4 | 2 | 0 |
| /cancel | 1 | 0 |
| /success?checkout_id=cc879d19... | 2 | 0 |

Notice present on every HTML page (>=1); banned patterns 0 on every page. G8 = PASS.

## VERDICT
VERDICT: FAIL G7 (palette: #0b1020 deployed but not in style.css). G6 PASS, G8 PASS. G7 details above.

## UNKNOWN / NOT-VERIFIED
- G7 style.css is the only reference file checked; if the storefront has its own token file, #0b1020 may be intentional there (not checked within wall clock).
- Screenshots are viewport (not fullPage); visual layout correctness beyond overflow was not asserted.

## Extra provenance notes (raw)
- `grep -rniE '#0b1020' /opt/workspace/omni-dashboard /opt/workspace/shortform-studio` -> no match (orphan color vs checkout).
- Local checkout `/opt/workspace/shortform-studio` HEAD = 11f951d3b365c4f087759e8b598cb176a4cc14ff (2026-09-27), NOT the claimed deployed SHA 81576780a4c2bc879b37ab96483a90587899888f; remote origin = https://github.com/nexuslbs/shortform-studio.git. Deployed-commit source not fetched (no repo writes).

## my usage (raw)
session-0b6ed1ec-82af-4e0c-bea5-64186fde69d2	21	0	21	1	15102	16067	473088	0	504257	117.18	1790622838044	1790622955224	150	0	/opt/omni/data/workstation/dsh-home/sessions/--var-lib-workstation-projects-shortform-studio--/session-0b6ed1ec-82af-4e0c-bea5-64186fde69d2/session.v4.jsonl.zstd
