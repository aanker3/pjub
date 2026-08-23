# pjub — Chilean house / property-auction watcher

Scrapes the **Poder Judicial de Chile** public property-auction listing
("Remates") from the Oficina Judicial Virtual into a local CSV.

- Source: <https://oficinajudicialvirtual.pjud.cl> → **Remates → Ver Remates** (guest / "Invitado", no login).
- Output columns: `Tribunal, Competencia, Causa, Fecha/Hora, Estado Remate` — the
  exact on-screen table, **all pages**, UTF-8 (with BOM, so Excel shows accents).

## Current dataset

[`remates_2026-08-23.csv`](remates_2026-08-23.csv) — **121 auctions**, filtered to
Competencia **Civil**, Corte **C.A. de Concepción**, Tipo **C**, dates
**23/08/2026 → 23/09/2026** (61 `Agendado`, 60 `Reprogramado`).

## How the site works (reverse-engineered 2026-08-23)

- One `POST /remates/consultarRemates.php` returns an HTML `<table>` fragment (~20 rows/page).
- Fields: `pagina, competencia, corte, tribunal, tipo, rol, era, desde, hasta`
  (`iddoc` is an unused, empty hidden field).
- **Pagination is server-side and token-driven.** `pagina` is **not** a page number —
  it's a signed JWT copied from the previous page's *Siguiente* link
  (`onclick="consultarRemates('<JWT>')"`). Page 1 = empty `pagina`; follow the
  *Siguiente* JWT chain to walk every page. A plain integer returns an empty table.
- Filter codes: `competencia` 1=Civil, 8=Laboral, 10=Penal, 3=Cobranza, 4=Familia;
  `corte` 46 = C.A. de Concepción (0 = all cortes); `tipo` letters C/V/E/A/F/I (0 = all).

## ⚠️ The WAF: why this needs a browser

The site is fronted by an **F5 BIG-IP ASM** web-application firewall. Scripted
HTTP (plain `requests`, `curl`, etc.) is rejected with *"La URL solicitada ha
sido rechazada"* even with a valid guest session — the ASM challenge is only
cleared by a real browser executing JS. In [job-fit-finder](../.claude/skills/job-fit-finder)
terms this endpoint is a permanent **needs_browser (Tier 3)** case, so the
end-to-end capture runs in the browser.

## Usage

### 1. Capture (browser — the path that works)

1. Open the site, go to **Remates → Ver Remates**, set filters, click **Buscar**.
2. Open the DevTools console (F12) and paste all of [`browser_scrape.js`](browser_scrape.js).
3. It follows the JWT pagination chain and downloads `pjud_remates_<date>.csv`.

### 2. Tooling ([`scrape_remates.py`](scrape_remates.py))

Reuses the job-finder's shared fetch core (`_shared/web_fetch.py` — the same
browser-like `requests.Session` + challenge detection).

```bash
python scrape_remates.py live                       # probe endpoint; reports needs_browser (WAF)
python scrape_remates.py parse page*.html -o out.csv # convert saved HTML fragment(s) -> CSV
```

`live` reuses `web_fetch` and honestly reports the WAF block. `parse` runs the
real HTML-table parser over browser-captured fragments and writes the CSV.

## Files

| File | Purpose |
|------|---------|
| `browser_scrape.js` | In-page extractor: JWT pagination + CSV download (the working capture). |
| `scrape_remates.py` | `web_fetch` Tier-1 probe + HTML-fragment→CSV parser. |
| `remates_2026-08-23.csv` | Latest captured dataset (121 rows). |
