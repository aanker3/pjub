/* pjub — Poder Judicial "remates" (property auction) scraper, browser edition.
 *
 * WHY THE BROWSER: the site sits behind an F5 BIG-IP ASM WAF that rejects
 * scripted HTTP ("La URL solicitada ha sido rechazada"). A real browser tab has
 * already cleared the challenge, so we scrape from inside the page.
 *
 * HOW TO USE
 *   1. Go to https://oficinajudicialvirtual.pjud.cl  ->  Remates -> Ver Remates.
 *   2. Set your filters (Competencia / Corte / Tipo / Desde / Hasta) and click Buscar.
 *   3. Open DevTools console (F12) on that tab and paste this whole file, Enter.
 *   4. It walks every page via the JWT `pagina` chain and downloads one CSV.
 *
 * Pagination note: `pagina` is a signed JWT taken from the previous page's
 * "Siguiente" link (onclick="consultarRemates('<JWT>')"), NOT a page number.
 */
(async () => {
  const g = id => document.getElementById(id).value;
  const filters = {};
  for (const k of ['competencia', 'corte', 'tribunal', 'tipo', 'rol', 'era', 'desde', 'hasta'])
    filters[k] = g(k);

  async function fetchPage(paginaTok) {
    const params = new URLSearchParams();
    params.append('pagina', paginaTok || '');
    for (const k in filters) params.append(k, filters[k]);
    const txt = await fetch('/remates/consultarRemates.php', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: params.toString(),
    }).then(r => r.text());
    const doc = new DOMParser().parseFromString(txt, 'text/html');
    const rows = [...doc.querySelectorAll('tbody tr')]
      .map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.replace(/\s+/g, ' ').trim()))
      .filter(r => r.length >= 6);            // real data rows have 6 cells (icon + 5)
    let sig = null;
    for (const a of doc.querySelectorAll('a')) {
      if (/Siguiente/i.test(a.textContent)) {
        const m = (a.getAttribute('onclick') || '').match(/consultarRemates\('([^']+)'\)/);
        if (m) sig = m[1];
      }
    }
    return { rows, sig };
  }

  const all = [], seen = new Set();
  let tok = '', pages = 0;
  for (let i = 0; i < 50; i++) {              // hard cap = safety
    const { rows, sig } = await fetchPage(tok);
    pages++;
    let added = 0;
    for (const r of rows) {
      const cells = r.slice(1, 6);            // drop leading magnifier cell -> 5 cols
      const key = cells.join('|');
      if (!seen.has(key)) { seen.add(key); all.push(cells); added++; }
    }
    if (!sig || added === 0) break;           // no next page, or nothing new
    tok = sig;
  }

  const q = s => { s = s == null ? '' : String(s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const header = ['Tribunal', 'Competencia', 'Causa', 'Fecha/Hora', 'Estado Remate'];
  const csv = '﻿' + [header.join(',')].concat(all.map(r => r.map(q).join(','))).join('\r\n');

  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url; a.download = `pjud_remates_${stamp}.csv`;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  console.log(`pjub: ${pages} pages, ${all.length} rows -> ${a.download}`);
})();
