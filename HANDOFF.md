# pjub — Handoff / status document

**What this is:** a small toolkit to watch Chilean **Poder Judicial** property
auctions ("Remates") from the public Oficina Judicial Virtual (OJV) and pull the
underlying court case file ("Ebook" / expediente PDF) for a given auction. Guest
("Invitado") access, no login. Base URL: `https://oficinajudicialvirtual.pjud.cl`.

> ⚠️ **Owner note:** I'm **iffy on the Playwright approach** (see "Automation
> status"). It doesn't work headless in the current environment. Treat the
> browser-driven method as the source of truth for now; Playwright is an
> unfinished experiment, not a dependency.

---

## Status at a glance

| Piece | Status | How it was done |
|---|---|---|
| **Step 1 — Remates listing → CSV** (all pages) | ✅ Working | In a real browser (JS console / browser automation) |
| **Step 2 — download case "Ebook" PDF + link it in CSV** | ✅ Working for the example row | Real browser (reCAPTCHA needs it) |
| **Chrome-free automation** (`pjud_playwright.py`) | 🚧 **Blocked / experimental** | Headless Chromium is rejected by the WAF |

**Delivered artifacts:**
- `remates_2026-08-23.csv` — 121 auctions (Civil, C.A. de Concepción, Libro/Tipo
  C, 23/08/2026→23/09/2026), 61 `Agendado` / 60 `Reprogramado`. Has an `Ebook`
  column.
- `docs/pjud_C-81-2026_Laja_TESORERIA-OYARCE_ebook.pdf` — the expediente for
  `C-81-2026` @ *Juzgado de Letras y Gar. de Laja* (TESORERÍA PROVINCIAL DE LOS
  ÁNGELES/OYARCE), 9 pages, ~441 KB. Linked from that row via
  `=HYPERLINK("docs/…","Ebook C-81-2026 (Laja)")` (relative path, clickable in
  Excel, survives moving the folder).

---

## The two walls (read this first)

Everything hard about this project comes from two protections on the site:

1. **F5 BIG-IP ASM WAF.** Plain scripted HTTP (`requests`, `curl`) is rejected
   with *"La URL solicitada ha sido rechazada"* even with a valid guest session.
   The `TS*` cookies are only validated by executing the page's JS challenge.
   → You need a **real browser JS runtime**. (Confirmed: `requests` fails; see
   `scrape_remates.py live`.)
2. **Invisible reCAPTCHA v3** on the case-detail / ebook path. A fresh score
   token is minted per click by `grecaptcha` in the page (site key `6Lel…`,
   actions like `validate_captcha_detcau_civil`). Not a solvable
   challenge — but you can't generate the token without a browser.

**Net:** the whole flow currently must run **inside a real, non-headless
browser**. That's the crux of the Playwright problem below.

---

## How it actually works (endpoints)

### Step 1 — listing
- `POST /remates/consultarRemates.php` → HTML `<table>` fragment (~20 rows/page).
- Form fields: `pagina, competencia, corte, tribunal, tipo, rol, era, desde, hasta`
  (`iddoc` is an unused empty hidden field).
- **Pagination is JWT-driven.** `pagina` is NOT a page number — it's a signed JWT
  copied from the previous page's *Siguiente* link
  (`onclick="consultarRemates('<JWT>')"`). Page 1 = empty `pagina`.
- Filter codes: competencia 1=Civil 8=Laboral 10=Penal 3=Cobranza 4=Familia;
  corte 46 = C.A. de Concepción (0 = all cortes); tipo letters C/V/E/A/F/I (0=all).

**Working method:** open the site → **Remates → Ver Remates**, set filters, click
Buscar, then paste `browser_scrape.js` into the DevTools console. It walks the
JWT chain and downloads the CSV.

### Step 2 — case file / "Ebook"
Auctions map to court cases you open in **Consulta Unificada** (menu item; there
is no `BusquedaUnificada.php` — that 404s).

- **Search (Búsqueda por RIT)** fields (ids): `competencia` (Civil=3),
  `conCorte` (46), `conTribunal`, `conTipoBus` (**2 = Expediente de 1ª
  Instancia**), `conTipoCausa` (Libro/Tipo, e.g. `C`), `conRolCausa` (Rol),
  `conEraCausa` (Año). **Rol AND Año are required** or you get "no results".
  Setting `conCorte` triggers a tribunal reload that CLEARS Rol/Año — set Corte
  first, then Rol/Año, then Buscar. Corte=Todos returns the RIT from every court;
  filter by Tribunal to pick the right row.
- Row magnifier → `detalleCausaCivil('<JWT>')` →
  `POST /ADIR/civil/modal_causaCivil.php` (data `{dtaCausa, token(recaptcha), …}`)
  → detail modal HTML into `#modalDetalleCivil`.
- Modal exposes **Texto Demanda, Anexos, Certificado de Envío, Ebook**, plus a
  per-folio **Historia** table.
- **Ebook download:** a `<form method=get target=_blank>` with one hidden
  `dtaEbook` (~360-char JWT), action
  `ADIR_871/civil/documentos/newebookcivil.php` →
  `GET .../newebookcivil.php?dtaEbook=<JWT>` → `application/pdf`.
  ⚠️ The `ADIR_871` prefix looks versioned/rotating — **read it from the live
  form each time; don't hardcode.**

**Working method:** open the cause detail in the browser, then in the console
fetch the ebook form's action+`dtaEbook` as a blob and download it; save under
`docs/`; then `python link_ebook.py --causa <RIT> --file docs/<pdf>`.

---

## Automation status — why I'm iffy on Playwright

Goal was a Chrome-free, unattended, schedulable script (`pjud_playwright.py`).
Current reality in this Windows environment:

- Playwright **Firefox** engine won't launch — *"side-by-side configuration is
  incorrect"* (missing Visual C++ runtime).
- Playwright full **Chromium (headed)** won't launch — `spawn UNKNOWN` (same
  class of Windows SxS/spawn issue). Only the **chromium-headless-shell** runs.
- The headless-shell **loads the site but the F5 WAF rejects the
  `consultarRemates.php` POST** ("rechazada"). Headless is detectable / doesn't
  clear the ASM challenge the way a real browser does.

So `pjud_playwright.py listing` currently **fails at the WAF**. It's committed as
a work-in-progress, not a working tool.

**Options for whoever picks this up (roughly in order):**
1. Fix the browser install so a **headed** (real) Chromium/Firefox runs, then
   drive it with Playwright headed (or `xvfb`/virtual display on Linux). A real,
   headed browser is what clears both walls.
2. Try an **anti-detection** setup: `playwright-stealth` / `undetected-chromedriver`,
   realistic UA + `--disable-blink-features=AutomationControlled`, real window.
   reCAPTCHA v3 may still score headless low.
3. Try **TLS-impersonation** (`curl_cffi`) for the **listing only** — it *might*
   slip past the F5 WAF with no browser. Won't help the ebook (reCAPTCHA).
4. Accept a **semi-manual** flow: keep the browser-console scripts
   (`browser_scrape.js` for listing; a small snippet for the ebook) — this is
   what produced everything here and it's reliable.

My recommendation: don't invest more in headless Playwright until a headed
browser is confirmed launchable on the target machine. The browser-console
method already works.

---

## File inventory

| File | Purpose | Status |
|---|---|---|
| `browser_scrape.js` | Paste in DevTools console on the Remates page → walks JWT pagination, downloads the listing CSV. | ✅ Working |
| `scrape_remates.py` | `web_fetch` Tier-1 probe (honestly reports the WAF block) + HTML-fragment→CSV parser. | ✅ (probe + parser) |
| `link_ebook.py` | Adds a clickable `Ebook` HYPERLINK column to the CSV for a given Causa. | ✅ Working |
| `pjud_playwright.py` | Headless-browser scraper attempt (listing; ebook not built). | 🚧 Blocked by WAF |
| `remates_2026-08-23.csv` | Dataset: 121 rows + `Ebook` column. | ✅ |
| `docs/…ebook.pdf` | Example downloaded expediente. | ✅ |
| `CLAUDE.md` | Working notes / reverse-engineering details. | — |
| `README.md` | User-facing overview + usage. | — |

## Environment notes
- Windows 11, Python 3.10, Playwright 1.62 (only `chromium-headless-shell`
  actually launches here).
- CSVs are UTF-8 **with BOM** so Excel renders Spanish accents.
- `remates_*.csv` filter shown above; change filters via `browser_scrape.js`
  (edit the on-page filters before running) or `pjud_playwright.py` args.

## Suggested next steps / plans
1. Decide automation path per the "Automation status" options above (my vote:
   confirm a headed browser first, or stay with the console scripts).
2. Extend step 2 to **batch** ebooks for many rows (browser-driven; ~a few
   seconds each because of reCAPTCHA).
3. Optionally also grab the modal's other docs (Texto Demanda, Anexos,
   Certificado) and richer fields (proc. type, etapa, litigantes) — useful to
   turn the docket list into a real "house watching" sheet.
4. Consider whether the case PDFs (personal legal data) should live in the repo
   or only locally — **this repo is private for that reason.**
