# pjub — project notes for Claude

Chilean **Poder Judicial** property-auction ("Remates") watcher + case-file
downloader. Data from the Oficina Judicial Virtual (OJV), guest / "Invitado"
access (no login). Base: `https://oficinajudicialvirtual.pjud.cl`.

## Golden rules
- **The site is behind an F5 BIG-IP ASM WAF.** Plain scripted HTTP (`requests`,
  `curl`) is rejected with *"La URL solicitada ha sido rechazada"* even with a
  valid guest session. Everything that hits pjud must run **inside a real
  browser tab** that has already cleared the JS challenge. This is the
  `needs_browser` (Tier 3) case from the job-fit-finder skill.
- Reuse the job-finder "parser" = `_shared/web_fetch.py` (shared session/fetch
  core) where HTTP is possible; parsing/CSV is stdlib.
- Output CSVs are UTF-8 **with BOM** so Excel renders the Spanish accents.

## Step 1 — Remates listing → CSV  ✅ done
- Endpoint: `POST /remates/consultarRemates.php` returns an HTML `<table>`
  fragment (~20 rows/page).
- Fields: `pagina, competencia, corte, tribunal, tipo, rol, era, desde, hasta`
  (`iddoc` = unused empty hidden field).
- **Pagination is JWT-driven**: `pagina` is NOT a page number — it's a signed
  JWT copied from the previous page's *Siguiente* link
  (`onclick="consultarRemates('<JWT>')"`). Page 1 = empty `pagina`.
- Codes: competencia 1=Civil 8=Laboral 10=Penal 3=Cobranza 4=Familia;
  corte 46 = C.A. de Concepción (0 = all); tipo C/V/E/A/F/I (0 = all).
- Output: `remates_2026-08-23.csv` — 121 rows (Civil, C.A. Concepción, tipo C,
  23/08→23/09/2026). Captured with `browser_scrape.js`.

## Step 2 — per-case "ebook" (expediente PDF) download  ✅ done (for C-81-2026)
For a remates row, open the underlying cause in **Consulta Unificada**, open its
detail modal (magnifier), download the **Ebook** (full expediente PDF), save it
under `docs/`, and add a clickable `Ebook` HYPERLINK column to the CSV.

### Consulta Unificada — Búsqueda por RIT
- Reach it: menu **Consulta Unificada** (JS-loaded fragment; there is no
  `BusquedaUnificada.php` — that 404s).
- Fields (ids): `competencia` (Civil=3), `conCorte` (46 = C.A. Concepción),
  `conTribunal`, `conTipoBus` (**2 = Expediente de 1ª Instancia**),
  `conTipoCausa` (Libro/Tipo, e.g. `C`), `conRolCausa` (Rol), `conEraCausa` (Año).
- **Rol AND Año are required** — leaving either blank returns "No se han
  encontrado resultados". Setting `conCorte` triggers an async tribunal reload
  that CLEARS Rol/Año, so set Corte first, then fill Rol/Año, then Buscar.
- Search + detail both fire an **invisible reCAPTCHA v3** (site key
  `6Lel...`, actions like `validate_captcha_detcau_civil`) handled by the page's
  own JS — trigger the real button/anchor, never a raw fetch. Not a solvable
  challenge, just a score token.
- Corte = Todos returns the same RIT from every court nationwide; filter results
  by Tribunal to pick the one you want.

### Endpoints (all browser-only; WAF + reCAPTCHA)
- Row magnifier → `detalleCausaCivil('<JWT dtaCausa>')`.
- Detail modal: `POST /ADIR/civil/modal_causaCivil.php`
  data `{dtaCausa:<JWT>, token:<recaptcha>, ...}` → HTML injected into
  `#modalDetalleCivil`.
- Modal exposes: **Texto Demanda, Anexos, Certificado de Envío, Ebook**, plus a
  per-folio **Historia** table (each doc is a `<form>` you submit).
- **Ebook download**: a `<form method=get target=_blank>` with a single hidden
  `dtaEbook` (~360-char JWT), action
  `ADIR_871/civil/documentos/newebookcivil.php` → `GET .../newebookcivil.php?dtaEbook=<JWT>`
  → `application/pdf`. ⚠️ the `ADIR_871` prefix looks versioned/rotating; read it
  from the live form each time, don't hardcode.

### Done for the example
- Target: `C-81-2026` @ *Juzgado de Letras y Gar. de Laja*, caratulado
  **TESORERÍA PROVINCIAL DE LOS ÁNGELES/OYARCE**, proc. *Tributario - Remate
  Bienes Raíces*, F.Ing 20/05/2026.
- Saved: `docs/pjud_C-81-2026_Laja_TESORERIA-OYARCE_ebook.pdf` (9 pp, 441 KB).
- CSV: `Ebook` column added; the C-81-2026 row now holds
  `=HYPERLINK("docs/...","Ebook C-81-2026 (Laja)")` (relative path → survives
  moving the folder; Excel evaluates it as a clickable link).
- Tool: `link_ebook.py --causa <RIT> --file docs/<pdf> [--label ...]`.

### To repeat for another row (manual browser steps for now)
1. Consulta Unificada → set Competencia/Corte, fill Libro/Tipo + Rol + Año → Buscar.
2. Find the right Tribunal row → click its magnifier.
3. In the modal, hover **Ebook**, submit that form (or fetch
   `newebookcivil.php?dtaEbook=<token>` in-page) → save the PDF to `docs/`.
4. `python link_ebook.py --causa <RIT> --file docs/<pdf>`.

## Files
| File | Purpose |
|------|---------|
| `browser_scrape.js` | In-page remates extractor (JWT pagination) → CSV download. |
| `scrape_remates.py` | `web_fetch` Tier-1 probe + HTML-fragment→CSV parser. |
| `remates_2026-08-23.csv` | Step-1 dataset (121 rows). |
| `docs/` | Downloaded case files ("ebooks"). |
