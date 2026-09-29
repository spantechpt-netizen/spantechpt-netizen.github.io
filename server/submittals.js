/**
 * Submittal request forms (transmittals): one template for the whole office, filled from the project data and the
 * drawing runs picked for it. The numbers, titles and revisions on the form are the ones printed in the title
 * blocks, so the form and the drawings never disagree, and a revised drawing goes out under a new submittal that
 * names the revision it supersedes.
 */

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const PURPOSE_LABELS = { approval: 'FOR APPROVAL', information: 'FOR INFORMATION', resubmission: 'RE-SUBMISSION', as_built: 'AS BUILT' };
export const STATUS_LABELS = { draft: 'DRAFT', submitted: 'SUBMITTED', approved: 'APPROVED', approved_as_noted: 'APPROVED AS NOTED', resubmit: 'REVISE AND RESUBMIT', rejected: 'REJECTED', withdrawn: 'WITHDRAWN' };

/** `SPAN-SUB-P26-001-003` (+ `-R1` when the same submittal is re-issued). */
export const submittalCode = (prefix, projectCode, serial, revision = 0) => `${prefix}-${projectCode}-${String(serial).padStart(3, '0')}${revision ? `-R${revision}` : ''}`;

/**
 * The items of a submittal from the runs picked: every plan sheet of each run (the cover / index sheet is not a
 * drawing to approve), or only the sheet numbers listed in `only`. Each item names the earlier submittal and
 * revision of the same drawing number when there was one, so the form says what it supersedes.
 */
export function submittalItems(runs, { only = null, previous = [] } = {}) {
  const items = [];
  const seen = new Set();
  for (const run of runs) {
    for (const s of run.sheets || []) {
      if (s.level === 'ALL' && /COVER|INDEX/i.test(s.title)) continue;
      if (only && !only.includes(s.no)) continue;
      if (seen.has(s.no)) continue;
      seen.add(s.no);
      const item = { run_id: run.id, mode: run.mode, level: s.level, level_name: s.level_name || run.level_name || '', no: s.no, title: s.title, rev: run.revision, file: s.file, scale: s.scale || null };
      // the latest earlier submittal carrying this drawing number
      const prior = previous
        .flatMap((p) => (p.items || []).filter((it) => it.no === s.no).map((it) => ({ code: p.code, rev: it.rev, status: p.status, date: p.date })))
        .sort((a, b) => (a.date < b.date ? 1 : -1))[0];
      if (prior) { item.prev_rev = prior.rev; item.prev_submittal = prior.code; item.prev_status = prior.status; }
      items.push(item);
    }
  }
  return items;
}

/** The printable form (A4, prints from the browser): office header, project block, the drawing list, the response boxes. */
export function submittalHtml({ submittal, project, settings, items, user }) {
  const tpl = settings.submittal || {};
  const S = submittal;
  const purpose = PURPOSE_LABELS[S.purpose] || S.purpose;
  const status = STATUS_LABELS[S.status] || S.status;
  const rows = items.map((it, i) => `<tr>
      <td class="c">${i + 1}</td>
      <td class="mono">${esc(it.no)}</td>
      <td>${esc(it.title)}</td>
      <td class="mono">${esc(it.level === 'ALL' ? 'ALL' : `${it.level}${it.level_name ? ' - ' + it.level_name : ''}`)}</td>
      <td class="c mono">${esc(it.rev)}</td>
      <td class="c mono">${it.prev_rev != null ? `${esc(it.prev_rev)} <span class="tiny">(${esc(it.prev_submittal)})</span>` : '-'}</td>
      <td class="c">${it.scale ? `1:${esc(it.scale)}` : 'NTS'}</td>
      <td class="resp"></td>
    </tr>`).join('');
  const responses = (tpl.responses || []).map((r) => `<label><span class="box"></span> ${esc(r)}</label>`).join('');
  const signatures = (tpl.signatures || []).map((sg) => `<div class="sig"><div class="line"></div><div>${esc(sg)}</div><div class="tiny">NAME / SIGN / DATE</div></div>`).join('');
  const kinds = { shop: 'SHOP DRAWINGS', design: 'DESIGN DRAWINGS', mixed: 'DESIGN AND SHOP DRAWINGS' };
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${esc(S.code)} - ${esc(tpl.title || 'SUBMITTAL')}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @page { size: A4; margin: 12mm; }
  body { font: 11px/1.4 Arial, Helvetica, sans-serif; color: #111; margin: 0; padding: 12mm; max-width: 190mm; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0b3d6b; padding-bottom: 6px; }
  .head .co { font-size: 18px; font-weight: 700; color: #0b3d6b; letter-spacing: .5px; }
  .head .line { font-size: 10px; color: #555; }
  .head .no { text-align: right; }
  .head .no .code { font-family: Consolas, Menlo, monospace; font-size: 16px; font-weight: 700; }
  h1 { font-size: 15px; margin: 10px 0 2px; color: #0b3d6b; }
  h1 small { display: block; font-size: 11px; color: #555; font-weight: 400; }
  table.meta { width: 100%; border-collapse: collapse; margin: 8px 0; }
  table.meta td { border: 1px solid #999; padding: 4px 6px; vertical-align: top; }
  table.meta td.k { width: 18%; background: #eef3f8; font-weight: 700; }
  table.list { width: 100%; border-collapse: collapse; margin-top: 6px; }
  table.list th, table.list td { border: 1px solid #666; padding: 4px 5px; text-align: left; }
  table.list th { background: #0b3d6b; color: #fff; font-weight: 700; font-size: 10px; }
  .c { text-align: center !important; }
  .mono { font-family: Consolas, Menlo, monospace; }
  .tiny { font-size: 9px; color: #555; }
  .resp { width: 22mm; }
  .intro { margin: 8px 0; }
  .responses { display: flex; flex-wrap: wrap; gap: 10px 22px; margin: 10px 0; padding: 8px; border: 1px solid #666; }
  .responses label { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }
  .box { display: inline-block; width: 12px; height: 12px; border: 1.5px solid #111; }
  .sigs { display: flex; gap: 14px; margin-top: 14px; }
  .sig { flex: 1; text-align: center; font-weight: 700; }
  .sig .line { height: 34px; border-bottom: 1px solid #111; margin-bottom: 4px; }
  .foot { margin-top: 12px; font-size: 9px; color: #555; border-top: 1px solid #999; padding-top: 6px; }
  .status { display: inline-block; padding: 2px 8px; border: 1.5px solid #0b3d6b; border-radius: 3px; font-weight: 700; color: #0b3d6b; }
  .print { position: fixed; top: 8px; right: 8px; padding: 6px 12px; font: 12px Arial; }
  @media print { .print { display: none; } body { padding: 0; } }
</style></head>
<body>
<button class="print" onclick="window.print()">Print / PDF</button>
<div class="head">
  <div><div class="co">${esc(settings.company || '')}</div><div class="line">${esc(settings.company_line || '')}${tpl.contact ? ' · ' + esc(tpl.contact) : ''}</div></div>
  <div class="no"><div class="tiny">SUBMITTAL No.</div><div class="code">${esc(S.code)}</div><div class="tiny">DATE ${esc(S.date)}</div></div>
</div>
<h1>${esc(tpl.title || 'DRAWING SUBMITTAL')}<small>${esc(tpl.title_ar || '')}</small></h1>
<table class="meta">
  <tr><td class="k">PROJECT</td><td>${esc(project.name)}${project.name_ar ? ' · ' + esc(project.name_ar) : ''} <span class="mono">(${esc(project.code)})</span></td><td class="k">STATUS</td><td><span class="status">${esc(status)}</span></td></tr>
  <tr><td class="k">TO</td><td>${esc(S.to_name || project.consultant || '')}</td><td class="k">ATTENTION</td><td>${esc(S.attention || '')}</td></tr>
  <tr><td class="k">CLIENT</td><td>${esc(project.client || '')}</td><td class="k">CONTRACTOR</td><td>${esc(project.contractor || '')}</td></tr>
  <tr><td class="k">LOCATION</td><td>${esc(project.location || '')}</td><td class="k">PURPOSE</td><td>${esc(purpose)} · ${esc(kinds[S.kind] || S.kind)}</td></tr>
  <tr><td class="k">SUBJECT</td><td colspan="3">${esc(S.subject || '')}</td></tr>
</table>
<div class="intro">${esc(tpl.intro || '')}</div>
<table class="list">
  <thead><tr><th class="c">#</th><th>DRAWING No.</th><th>TITLE</th><th>LEVEL</th><th class="c">REV</th><th class="c">SUPERSEDES REV</th><th class="c">SCALE</th><th class="c">ACTION</th></tr></thead>
  <tbody>${rows || '<tr><td colspan="8" class="c">NO DRAWINGS</td></tr>'}</tbody>
</table>
<div class="tiny" style="margin-top:4px">${items.length} DRAWING(S). ACTION CODES: A = APPROVED · B = APPROVED AS NOTED · C = REVISE AND RESUBMIT · D = REJECTED.</div>
${S.notes ? `<div class="intro"><b>NOTES:</b> ${esc(S.notes)}</div>` : ''}
<div class="responses">${responses}</div>
${S.response_notes || S.response_date ? `<table class="meta"><tr><td class="k">RESPONSE</td><td>${esc(S.response_notes || '')}</td><td class="k">DATE / BY</td><td>${esc(S.response_date || '')} ${esc(S.response_by || '')}</td></tr></table>` : ''}
<div class="sigs">${signatures}<div class="sig"><div class="line"></div><div>RECEIVED BY (CONSULTANT)</div><div class="tiny">NAME / SIGN / DATE</div></div></div>
<div class="foot">${esc(tpl.footer || '')}${user ? ` · Prepared in ${esc(settings.company || '')} PT Suite by ${esc(user.name || '')}` : ''}</div>
</body></html>`;
}
