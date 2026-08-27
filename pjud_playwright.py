#!/usr/bin/env python3
"""Chrome-free pjud remates scraper + ebook downloader, via headless Playwright.

Why a browser engine at all: the site is behind an F5 BIG-IP ASM WAF (rejects
plain scripted HTTP) and the case-detail / ebook path is gated by invisible
reCAPTCHA v3. A real JS engine clears both. We use Playwright's **Firefox**
engine, headless, so it runs unattended (no visible Chrome, cron-able).

Everything runs INSIDE the browser process; only a small summary comes back to
Python -> cheap to run repeatedly.

Commands:
    python pjud_playwright.py listing [--corte 46 --competencia 1 --tipo C \
        --desde 23/08/2026 --hasta 23/09/2026 -o remates_<date>.csv]
    python pjud_playwright.py ebook  --causa C-81-2026 --tribunal-name Laja  # (step 2, added next)
"""

import argparse
import csv
import sys
from datetime import date

from playwright.sync_api import sync_playwright

BASE = "https://oficinajudicialvirtual.pjud.cl"
INDEX_URL = f"{BASE}/indexN.php"
COLUMNS = ["Tribunal", "Competencia", "Causa", "Fecha/Hora", "Estado Remate"]

# JS run inside the page: walk the JWT `pagina` chain, return deduped 5-col rows.
_LISTING_JS = r"""
async (filters) => {
  async function fetchPage(tok){
    const params = new URLSearchParams();
    params.append('pagina', tok || '');
    for (const k in filters) params.append(k, filters[k]);
    const txt = await fetch('/remates/consultarRemates.php', {
      method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
               'X-Requested-With':'XMLHttpRequest'},
      body: params.toString(),
    }).then(r => r.text());
    if (/rechazada/i.test(txt)) return {waf:true};
    const doc = new DOMParser().parseFromString(txt, 'text/html');
    const rows = [...doc.querySelectorAll('tbody tr')]
      .map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.replace(/\s+/g,' ').trim()))
      .filter(r => r.length >= 6);
    let sig = null;
    for (const a of doc.querySelectorAll('a')) {
      if (/Siguiente/i.test(a.textContent)) {
        const m = (a.getAttribute('onclick')||'').match(/consultarRemates\('([^']+)'\)/);
        if (m) sig = m[1];
      }
    }
    return {rows, sig};
  }
  const all = [], seen = new Set();
  let tok = '', pages = 0;
  for (let i = 0; i < 60; i++) {
    const res = await fetchPage(tok);
    if (res.waf) return {rows: all, pages, waf: true};
    pages++;
    let added = 0;
    for (const r of res.rows) {
      const c = r.slice(1, 6);                 // drop leading magnifier cell
      const key = c.join('|');
      if (!seen.has(key)) { seen.add(key); all.push(c); added++; }
    }
    if (!res.sig || added === 0) break;
    tok = res.sig;
  }
  return {rows: all, pages, waf: false};
}
"""


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _settle(page, timeout_s=35):
    """Wait for the F5 ASM JS challenge to run + redirect and the app to load."""
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        try:
            html = page.content().lower()
        except Exception:                      # still navigating (challenge redirect)
            page.wait_for_timeout(600)
            continue
        if "rechazada" in html:                # WAF interstitial -> give it time
            page.wait_for_timeout(1500)
            continue
        if "consulta unificada" in html or "remates" in html:
            return True
        page.wait_for_timeout(700)
    return False


def _new_page(pw, headless=True):
    # Chromium engine (Playwright's own, headless) -- NOT the user's Chrome.
    browser = pw.chromium.launch(headless=headless)
    ctx = browser.new_context(locale="es-CL", user_agent=UA,
                              viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    # Landing on indexN.php establishes the guest session and clears the F5 JS challenge.
    page.goto(INDEX_URL, wait_until="domcontentloaded", timeout=60000)
    _settle(page)
    return browser, ctx, page


def cmd_listing(a):
    filters = {"competencia": a.competencia, "corte": a.corte, "tribunal": a.tribunal,
               "tipo": a.tipo, "rol": a.rol, "era": a.era,
               "desde": a.desde, "hasta": a.hasta}
    with sync_playwright() as pw:
        browser, ctx, page = _new_page(pw, headless=not a.headed)
        try:
            result = page.evaluate(_LISTING_JS, filters)
        finally:
            browser.close()
    if result.get("waf"):
        sys.exit("F5 WAF rejected the request even in-browser — try --headed.")
    rows = result["rows"]
    out = a.out or f"remates_{date.today().isoformat()}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"listing: {result['pages']} pages, {len(rows)} rows -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headed", action="store_true", help="show the browser window (debug)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lv = sub.add_parser("listing", help="scrape the remates listing to CSV")
    lv.add_argument("--corte", default="46")
    lv.add_argument("--competencia", default="1")
    lv.add_argument("--tipo", default="C")
    lv.add_argument("--tribunal", default="0")
    lv.add_argument("--rol", default="")
    lv.add_argument("--era", default="")
    lv.add_argument("--desde", default="23/08/2026")
    lv.add_argument("--hasta", default="23/09/2026")
    lv.add_argument("-o", "--out", default="")
    lv.set_defaults(fn=cmd_listing)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
