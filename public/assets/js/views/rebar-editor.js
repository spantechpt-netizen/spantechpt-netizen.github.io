/**
 * Interactive reinforcement editor for one design run.
 *
 * The plan of the run (plan.json: outline, supports, every bar with a stable id) is drawn as SVG; the engineer
 * selects bars, deletes them, lengthens / shortens them, changes their call-out, or adds new bars. The edits are
 * kept on the level (they apply to every later generation of that level) and "regenerate" produces a new run
 * with them applied.
 */
import { api } from '../api.js';
import { t } from '../i18n.js';
import { el, clear, icon, field, confirmDialog, toast, toastError, pageHeader } from '../ui.js';

const NS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs = {}, children = []) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  for (const c of [].concat(children)) if (c) node.append(c);
  return node;
}
const dist = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);

export async function editorPage(projectId, runId, navigate) {
  const page = el('div');
  let data;
  try {
    const [runData, plan, projectData] = await Promise.all([api.drawingRun(runId), api.drawingRunPlan(runId), api.drawingProject(projectId)]);
    data = { ...runData, plan: Array.isArray(plan) ? plan : [], levels: projectData.levels };
  } catch (error) {
    page.append(el('div.alert.danger', { text: error.localised || error.message }));
    return page;
  }
  const { run, project } = data;
  const level = data.levels.find((l) => l.id === run.level_id) || { edits: [] };
  const parts = data.plan;
  if (!parts.length) { page.append(el('div.alert.danger', { text: 'plan.json' })); return page; }

  // ------------------------------------------------------------- state
  const state = {
    edits: (level.edits || []).map((e) => ({ ...e })),
    dirty: false,
    selected: new Set(),
    face: 'all',
    mode: 'select',
    part: 0,
    view: { k: 0.01, tx: 0, ty: 0 },
    addPts: [],
  };
  let addCounter = 0;

  // ------------------------------------------------------------- derived bars (plan + edits)
  function currentBars() {
    const part = parts[state.part];
    const byId = new Map(part.bars.map((b) => [b.id, { ...b, a: { ...b.a }, b: { ...b.b }, state: 'kept' }]));
    const added = [];
    state.edits.forEach((e, i) => {
      if (e.level && e.level !== part.id) return;
      if (e.op === 'add') { if (!e.level || e.level === part.id) added.push({ id: e._cid || (e._cid = `new-${++addCounter}`), kind: 'added', detail: null, face: e.face, a: e.a, b: e.b, l1: e.l1, l2: `L=${Math.round(dist(e.a, e.b) / 10) * 10}`, state: 'added', editIndex: i }); return; }
      const bar = byId.get(e.id);
      if (!bar) return;
      if (e.op === 'delete') bar.state = 'deleted';
      else if (e.op === 'length') {
        const L = dist(bar.a, bar.b) || 1;
        const u = { x: (bar.b.x - bar.a.x) / L, y: (bar.b.y - bar.a.y) / L };
        bar.a = { x: bar.a.x - u.x * (e.start || 0), y: bar.a.y - u.y * (e.start || 0) };
        bar.b = { x: bar.b.x + u.x * (e.end || 0), y: bar.b.y + u.y * (e.end || 0) };
        bar.l2 = `L=${Math.round(dist(bar.a, bar.b) / 10) * 10}`;
        if (bar.state !== 'deleted') bar.state = 'edited';
      } else if (e.op === 'spec') { bar.l1 = e.l1; if (bar.state !== 'deleted') bar.state = 'edited'; }
    });
    return [...byId.values(), ...added];
  }
  const visible = (bar) => state.face === 'all' || bar.face === state.face || (state.face === 'T' && bar.face === 'TB');

  // ------------------------------------------------------------- SVG
  const svgRoot = svg('svg', { xmlns: NS });
  const world = svg('g');
  svgRoot.append(world);
  const wrap = el('div.canvas-wrap', {}, [svgRoot]);
  const applyView = () => {
    const { k, tx, ty } = state.view;
    world.setAttribute('transform', `translate(${tx} ${ty}) scale(${k} ${-k})`);
    world.classList.toggle('nolabels', k < 0.03); // labels only once zoomed in enough to read them
    for (const txt of world.querySelectorAll('text')) { const s = 1 / k; txt.setAttribute('transform', `${txt.dataset.at} scale(${s} ${-s})`); }
  };
  const fit = () => {
    const part = parts[state.part];
    const b = part.bbox;
    const W = wrap.clientWidth || 800, H = wrap.clientHeight || 500;
    const k = Math.min((W - 40) / (b.w || 1), (H - 40) / (b.h || 1));
    state.view = { k, tx: W / 2 - b.cx * k, ty: H / 2 + b.cy * k };
    applyView();
  };
  const toWorld = (ev) => {
    const r = svgRoot.getBoundingClientRect();
    const { k, tx, ty } = state.view;
    return { x: (ev.clientX - r.left - tx) / k, y: -(ev.clientY - r.top - ty) / k };
  };

  function draw() {
    clear(world);
    const part = parts[state.part];
    const poly = (pts) => pts.map((p) => `${p.x},${p.y}`).join(' ');
    if (part.grid) {
      const b = part.bbox;
      for (const g of part.grid.x) world.append(svg('line', { class: 'grid', x1: g.x, y1: b.minY - 1500, x2: g.x, y2: b.maxY + 1500 }));
      for (const g of part.grid.y) world.append(svg('line', { class: 'grid', x1: b.minX - 1500, y1: g.y, x2: b.maxX + 1500, y2: g.y }));
    }
    world.append(svg('polygon', { class: 'outline', points: poly(part.outline) }));
    for (const z of part.thickZones || []) world.append(svg('polygon', { class: 'thick', points: poly(z.polygon) }));
    for (const w of part.walls || []) world.append(svg('polygon', { class: 'wall', points: poly(w.polygon) }));
    for (const bm of part.beams || []) world.append(svg('polygon', { class: 'beam', points: poly(bm.polygon) }));
    for (const o of part.openings || []) world.append(svg('polygon', { class: 'opening', points: poly(o.polygon) }));
    for (const c of part.columns || []) world.append(svg('rect', { class: 'column', x: c.cx - c.w / 2, y: c.cy - c.h / 2, width: c.w, height: c.h }));
    const bars = currentBars();
    for (const bar of bars) {
      if (!visible(bar)) continue;
      const cls = ['bar', bar.face, bar.state === 'deleted' ? 'deleted' : '', bar.state === 'edited' || bar.state === 'added' ? 'edited' : '', state.selected.has(bar.id) ? 'selected' : ''].filter(Boolean).join(' ');
      const g = svg('g', { 'data-id': bar.id });
      g.append(svg('line', { class: 'hit', x1: bar.a.x, y1: bar.a.y, x2: bar.b.x, y2: bar.b.y }));
      g.append(svg('line', { class: cls, x1: bar.a.x, y1: bar.a.y, x2: bar.b.x, y2: bar.b.y }));
      const m = { x: (bar.a.x + bar.b.x) / 2, y: (bar.a.y + bar.b.y) / 2 };
      const ang = (Math.atan2(bar.b.y - bar.a.y, bar.b.x - bar.a.x) * 180) / Math.PI;
      const rot = ang >= 89.5 || ang < -90.5 ? ang + 180 : ang; // vertical labels read top to bottom, as on the sheets
      const txt = svg('text', { class: 'lbl', 'font-size': 11, 'text-anchor': 'middle' }, `${bar.l1} ${bar.l2}`);
      txt.dataset.at = `translate(${m.x} ${m.y}) rotate(${rot})`;
      txt.setAttribute('dy', -4);
      g.append(txt);
      g.addEventListener('click', (ev) => { ev.stopPropagation(); if (state.mode !== 'select') return; onPick(bar, ev.shiftKey); });
      world.append(g);
    }
    if (state.addPts.length === 1) world.append(svg('circle', { cx: state.addPts[0].x, cy: state.addPts[0].y, r: 120, fill: '#1e6bff' }));
    applyView();
    renderSide();
  }

  function onPick(bar, multi) {
    if (!multi) state.selected.clear();
    if (state.selected.has(bar.id)) state.selected.delete(bar.id); else state.selected.add(bar.id);
    draw();
  }

  // pan / zoom / rubber band / add
  let drag = null;
  let rubber = null;
  svgRoot.addEventListener('pointerdown', (ev) => {
    if (ev.button === 1 || state.mode === 'pan' || ev.altKey) { drag = { x: ev.clientX, y: ev.clientY, tx: state.view.tx, ty: state.view.ty }; svgRoot.setPointerCapture(ev.pointerId); return; }
    if (state.mode === 'add') {
      const p = toWorld(ev);
      const snapped = state.addPts.length ? snap(state.addPts[0], p) : p;
      state.addPts.push({ x: Math.round(snapped.x), y: Math.round(snapped.y) });
      if (state.addPts.length === 2) {
        const [a, b] = state.addPts;
        state.addPts = [];
        if (dist(a, b) >= 200) {
          const face = state.face === 'B' ? 'B' : 'T';
          state.edits.push({ op: 'add', level: parts[state.part].id, face, a, b, l1: specInput.value || `T12-150 (${face})` });
          state.dirty = true;
        }
      }
      draw();
      return;
    }
    if (state.mode === 'select' && ev.target === svgRoot || ev.target === world || ev.target.classList?.contains('outline') || ev.target.classList?.contains('grid')) {
      const p = toWorld(ev);
      rubber = { a: p, b: p, node: svg('rect', { class: 'rubber' }) };
      world.append(rubber.node);
      svgRoot.setPointerCapture(ev.pointerId);
    }
  });
  svgRoot.addEventListener('pointermove', (ev) => {
    if (drag) { state.view.tx = drag.tx + (ev.clientX - drag.x); state.view.ty = drag.ty + (ev.clientY - drag.y); applyView(); return; }
    if (rubber) {
      rubber.b = toWorld(ev);
      const x = Math.min(rubber.a.x, rubber.b.x), y = Math.min(rubber.a.y, rubber.b.y);
      rubber.node.setAttribute('x', x); rubber.node.setAttribute('y', y);
      rubber.node.setAttribute('width', Math.abs(rubber.b.x - rubber.a.x)); rubber.node.setAttribute('height', Math.abs(rubber.b.y - rubber.a.y));
    }
  });
  const endDrag = (ev) => {
    if (drag) { drag = null; return; }
    if (rubber) {
      const { a, b } = rubber;
      rubber.node.remove();
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
      if (x1 - x0 > 200 && y1 - y0 > 200) {
        if (!ev.shiftKey) state.selected.clear();
        for (const bar of currentBars()) if (visible(bar) && bar.state !== 'deleted' && [bar.a, bar.b].every((p) => p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1)) state.selected.add(bar.id);
        draw();
      } else if (!ev.shiftKey && state.selected.size) { state.selected.clear(); draw(); }
      rubber = null;
    }
  };
  svgRoot.addEventListener('pointerup', endDrag);
  svgRoot.addEventListener('pointercancel', endDrag);
  svgRoot.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const r = svgRoot.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    const { k, tx, ty } = state.view;
    state.view = { k: k * f, tx: mx - (mx - tx) * f, ty: my - (my - ty) * f };
    applyView();
  }, { passive: false });
  const snap = (a, p) => (Math.abs(p.x - a.x) > Math.abs(p.y - a.y) * 4 ? { x: p.x, y: a.y } : Math.abs(p.y - a.y) > Math.abs(p.x - a.x) * 4 ? { x: a.x, y: p.y } : p);

  // ------------------------------------------------------------- side panel
  const side = el('div.side');
  const specInput = el('input', { type: 'text', placeholder: t('dw_new_spec'), dir: 'ltr' });
  const startInput = el('input.num', { type: 'number', value: 500, step: 50, style: { width: '90px' } });
  const endInput = el('input.num', { type: 'number', value: 500, step: 50, style: { width: '90px' } });

  function addLength(sign) {
    const ds = sign * (Number(startInput.value) || 0), de = sign * (Number(endInput.value) || 0);
    for (const id of state.selected) {
      if (id.startsWith('new-')) { const e = state.edits.find((x) => x._cid === id); if (e) { const L = dist(e.a, e.b) || 1; const u = { x: (e.b.x - e.a.x) / L, y: (e.b.y - e.a.y) / L }; e.a = { x: Math.round(e.a.x - u.x * ds), y: Math.round(e.a.y - u.y * ds) }; e.b = { x: Math.round(e.b.x + u.x * de), y: Math.round(e.b.y + u.y * de) }; } continue; }
      const existing = state.edits.find((e) => e.op === 'length' && e.id === id);
      if (existing) { existing.start = (existing.start || 0) + ds; existing.end = (existing.end || 0) + de; }
      else state.edits.push({ op: 'length', id, start: ds, end: de, level: parts[state.part].id });
    }
    state.dirty = true;
    draw();
  }
  function setSpec() {
    const l1 = specInput.value.trim();
    if (!l1) return;
    for (const id of state.selected) {
      if (id.startsWith('new-')) { const e = state.edits.find((x) => x._cid === id); if (e) e.l1 = l1; continue; }
      const existing = state.edits.find((e) => e.op === 'spec' && e.id === id);
      if (existing) existing.l1 = l1; else state.edits.push({ op: 'spec', id, l1, level: parts[state.part].id });
    }
    state.dirty = true;
    draw();
  }
  function deleteSelected() {
    for (const id of state.selected) {
      if (id.startsWith('new-')) { state.edits = state.edits.filter((e) => e._cid !== id); continue; }
      if (!state.edits.some((e) => e.op === 'delete' && e.id === id)) state.edits.push({ op: 'delete', id, level: parts[state.part].id });
    }
    state.selected.clear();
    state.dirty = true;
    draw();
  }
  function removeEdit(i) { state.edits.splice(i, 1); state.dirty = true; draw(); }
  const cleanEdits = () => state.edits.map(({ _cid, ...e }) => e);
  async function save() {
    try { await api.saveDrawingEdits(level.id, cleanEdits()); state.dirty = false; toast(t('dw_edits_saved'), 'success'); renderSide(); return true; } catch (error) { toastError(error); return false; }
  }
  async function regenerate() {
    if (!(await save())) return;
    const btn = side.querySelector('[data-regen]');
    if (btn) { btn.disabled = true; btn.textContent = t('dw_generating'); }
    try {
      const { run: fresh } = await api.regenerateDrawingRun(run.id, { notes: `${t('dw_edits_list')}: ${state.edits.length}` });
      toast(t('dw_regenerated'), 'success');
      navigate(`drawings/${project.id}/run/${fresh.id}`);
    } catch (error) { toastError(error); if (btn) { btn.disabled = false; btn.textContent = t('dw_regenerate'); } }
  }

  function renderSide() {
    clear(side);
    const modeBtn = (m, label, ic) => el('button', { type: 'button', class: state.mode === m ? 'active' : '', onclick: () => { state.mode = m; state.addPts = []; svgRoot.classList.toggle('pan', m === 'pan'); draw(); } }, [icon(ic, 14), ' ', label]);
    const faceBtn = (f, label) => el('button', { type: 'button', class: state.face === f ? 'active' : '', onclick: () => { state.face = f; state.selected.clear(); draw(); } }, label);
    side.append(el('div.card', {}, [el('div.card-body.tight', {}, [
      el('div.row.wrap', {}, [
        el('div.segmented', {}, [modeBtn('select', t('dw_select'), 'search'), modeBtn('pan', t('dw_pan'), 'menu'), modeBtn('add', t('dw_add_bar'), 'plus')]),
        el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: fit }, [t('dw_fit')]),
      ]),
      el('div.row.wrap.mt-1', {}, [
        el('div.segmented', {}, [faceBtn('all', t('all')), faceBtn('T', t('dw_show_top')), faceBtn('B', t('dw_show_bottom'))]),
        parts.length > 1 ? el('select', { onchange: (e) => { state.part = Number(e.target.value); state.selected.clear(); draw(); fit(); } }, parts.map((p, i) => { const o = el('option', { value: i, text: p.name }); if (i === state.part) o.selected = true; return o; })) : null,
      ]),
      state.mode === 'add' ? el('div.tiny.muted.mt-1', { text: t('dw_add_bar_hint') }) : null,
    ])]));
    side.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${state.selected.size} ${t('dw_selected')}` })]),
      el('div.card-body.tight', {}, [
        el('div.row.wrap', {}, [el('span.small', { text: t('dw_extend_start') }), startInput, el('span.small', { text: t('dw_extend_end') }), endInput]),
        el('div.row.wrap.mt-1', {}, [
          el('button.btn.btn-sm', { type: 'button', disabled: !state.selected.size, onclick: () => addLength(1) }, ['+ ', t('dw_apply_length')]),
          el('button.btn-secondary.btn.btn-sm', { type: 'button', disabled: !state.selected.size, onclick: () => addLength(-1) }, ['− ', t('dw_apply_length')]),
          el('button.btn-danger.btn.btn-sm', { type: 'button', disabled: !state.selected.size, onclick: deleteSelected }, [icon('trash', 14), t('dw_delete_bars')]),
        ]),
        el('div.row.wrap.mt-1', {}, [specInput, el('button.btn.btn-sm', { type: 'button', disabled: !state.selected.size, onclick: setSpec }, [t('dw_apply_length')])]),
      ]),
    ]));
    side.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${t('dw_edits_list')} (${state.edits.length})` }), el('div.spacer'), state.dirty ? el('span.badge.amber', { text: t('dw_edits_pending') }) : null]),
      el('div.card-body.tight', {}, [
        el('ul.edits', { style: { margin: 0, paddingInlineStart: '1rem' } }, state.edits.map((e, i) => el('li', {}, [
          el('span', { text: e.op === 'add' ? `ADD ${e.face} ${e.l1} (${Math.round(dist(e.a, e.b))})` : `${e.op.toUpperCase()} ${e.id}${e.op === 'length' ? ` ${e.start >= 0 ? '+' : ''}${e.start}/${e.end >= 0 ? '+' : ''}${e.end}` : e.op === 'spec' ? ` → ${e.l1}` : ''}` }),
          ' ',
          el('button.btn-ghost.btn.btn-sm', { type: 'button', onclick: () => removeEdit(i) }, [icon('x', 12)]),
        ]))),
        el('div.row.wrap.mt-1', {}, [
          el('button.btn', { type: 'button', onclick: save }, [icon('check', 14), t('dw_save_edits')]),
          el('button.btn-success.btn', { type: 'button', 'data-regen': '1', onclick: regenerate }, [icon('play', 14), t('dw_regenerate')]),
          state.edits.length ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: async () => { if (await confirmDialog(t('dw_clear_edits'))) { state.edits = []; state.dirty = true; draw(); } } }, [t('dw_clear_edits')]) : null,
        ]),
      ]),
    ]));
  }

  page.append(pageHeader(`${t('dw_editor')} — ${project.code} · REV ${run.revision}`, [
    el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate(`drawings/${project.id}/run/${run.id}`) }, [icon('back', 16), t('back')]),
  ]));
  page.append(el('div.alert.info', { text: t('dw_editor_hint') }));
  page.append(el('div.rebar-editor', {}, [wrap, side]));
  draw();
  setTimeout(fit, 30);
  return page;
}
