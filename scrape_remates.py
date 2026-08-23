#!/usr/bin/env python3
"""Scrape the Chilean Poder Judicial property-auction ("remates") listing to CSV.

Data source: https://oficinajudicialvirtual.pjud.cl  (Oficina Judicial Virtual,
guest / "Invitado" access -- no login required).

HOW THE SITE WORKS (reverse-engineered 2026-08-23)
--------------------------------------------------
* The "Listado de Remates" table is filled by a POST to
  remates/consultarRemates.php which returns an HTML <table> fragment (~20 rows).
* Form fields sent: pagina, competencia, corte, tribunal, tipo, rol, era,
  desde, hasta.  (`iddoc` is an unused hidden field -- it is empty.)
* PAGINATION IS SERVER-SIDE and token-driven: `pagina` is NOT a page number,
  it is a signed JWT lifted from the previous page's "Siguiente" link
  (onclick="consultarRemates('<JWT>')"). Page 1 = empty `pagina`; follow the
  Siguiente JWT chain to walk every page. Passing a plain integer returns empty.
* Codes: competencia 1=Civil 8=Laboral 10=Penal 3=Cobranza 4=Familia;
  corte 46 = C.A. de Concepcion (0 = all); tipo letters C/V/E/A/F/I (0 = all).

THE WALL: an F5 BIG-IP ASM WAF fronts the site. Scripted HTTP (this module's
`web_fetch` session, curl, etc.) gets "La URL solicitada ha sido rechazada"
even with a valid guest session -- the ASM challenge is only cleared by a real
browser running JS. In job-fit-finder terms this endpoint is a permanent
**needs_browser (Tier 3)** case.

So this file does two things:
  1. `live`  -- try the Tier-1 web_fetch path (reusing the shared job-finder core)
                and honestly report the WAF block.
  2. `parse` -- turn browser-captured consultarRemates HTML fragment(s) into the
                CSV, using a real HTML-table parser.
For the end-to-end capture that actually works, run browser_scrape.js in the
page (see README.md); it follows the JWT chain and downloads the CSV directly.

Usage:
    python scrape_remates.py live                       # probe the WAF (expects needs_browser)
    python scrape_remates.py parse page*.html -o out.csv  # HTML fragments -> CSV
"""

import argparse
import csv
import glob
import re
import sys
from datetime import date
from html.parser import HTMLParser

# --- reuse the job-fit-finder / rent-finder fetch core ---------------------
SHARED = r"C:\Users\doubl\.claude\skills\_shared"
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)
from web_fetch import make_session, get  # noqa: E402  (shared tiered-fetch core)

BASE = "https://oficinajudicialvirtual.pjud.cl"
INDEX_URL = f"{BASE}/indexN.php"
VER_URL = f"{BASE}/verRemates.php"
CONSULTAR_URL = f"{BASE}/remates/consultarRemates.php"

COLUMNS = ["Tribunal", "Competencia", "Causa", "Fecha/Hora", "Estado Remate"]
WAF_MARKER = "url solicitada ha sido rechazada"  # F5 ASM rejection page


class _RowParser(HTMLParser):
    """Extract <tbody> rows from a consultarRemates.php fragment into cell lists."""

    def __init__(self):
        super().__init__()
        self.in_tbody = self.in_td = False
        self.rows, self._row, self._cell = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self._row = []
        elif tag == "td" and self._row is not None:
            self.in_td, self._cell = True, []

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "td" and self.in_td:
            self.in_td = False
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self.in_td:
            self._cell.append(data)


def parse_fragment(html):
    """A consultarRemates HTML fragment -> list of 5-col data rows (icon col dropped)."""
    p = _RowParser()
    p.feed(html)
    out = []
    for row in p.rows:
        cells = row[1:] if len(row) == 6 else row      # drop leading magnifier cell
        if len(cells) >= 5 and cells[0] and "Total de registros" not in cells[0]:
            out.append(cells[:5])
    return out


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM => Excel-friendly
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def cmd_live(a):
    """Tier-1 probe. Reuses web_fetch; expected to hit the F5 WAF -> needs_browser."""
    s = make_session()
    get(s, INDEX_URL)          # establish guest PHPSESSID
    get(s, VER_URL)
    payload = {"pagina": "", "competencia": a.competencia, "corte": a.corte,
               "tribunal": a.tribunal, "tipo": a.tipo, "rol": a.rol, "era": a.era,
               "desde": a.desde, "hasta": a.hasta, "iddoc": ""}
    r = s.post(CONSULTAR_URL, data=payload, timeout=30,
               headers={"X-Requested-With": "XMLHttpRequest",
                        "Referer": INDEX_URL,
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    body = r.text.lower()
    if WAF_MARKER in body or "<table" not in body:
        print("status: needs_browser  (F5 WAF rejected the scripted request)")
        print("  -> run browser_scrape.js in the page instead. See README.md.")
        return 2
    rows = parse_fragment(r.text)
    write_csv(rows, a.out or f"remates_{date.today().isoformat()}.csv")
    print("NOTE: only page 1 fetched; server paginates via a JWT `pagina` token.")
    return 0


def cmd_parse(a):
    files = []
    for pat in a.files:
        files.extend(sorted(glob.glob(pat)))
    if not files:
        sys.exit("No input HTML files matched.")
    rows, seen = [], set()
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for r in parse_fragment(f.read()):
                key = "|".join(r)
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    write_csv(rows, a.out or f"remates_{date.today().isoformat()}.csv")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lv = sub.add_parser("live", help="probe the endpoint via web_fetch (expects WAF)")
    lv.add_argument("--corte", default="46")
    lv.add_argument("--competencia", default="1")
    lv.add_argument("--tipo", default="C")
    lv.add_argument("--tribunal", default="0")
    lv.add_argument("--rol", default="")
    lv.add_argument("--era", default="")
    lv.add_argument("--desde", default="23/08/2026")
    lv.add_argument("--hasta", default="23/09/2026")
    lv.add_argument("-o", "--out", default="")
    lv.set_defaults(fn=cmd_live)

    ps = sub.add_parser("parse", help="convert saved consultarRemates HTML fragments to CSV")
    ps.add_argument("files", nargs="+", help="HTML file(s) / glob(s)")
    ps.add_argument("-o", "--out", default="")
    ps.set_defaults(fn=cmd_parse)

    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
