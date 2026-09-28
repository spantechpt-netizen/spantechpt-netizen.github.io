/**
 * Reinforcement drawings from RAM Concept.
 *
 *   #/drawings                 registered projects
 *   #/drawings/:id             one project: its data, levels and generation runs
 *   #/drawings/:id/run/:runId  one run: the numbered sheets, previews, assumptions
 */
import { api } from '../api.js';
import { t, pick, formatDate, formatDateTime, getLang } from '../i18n.js';
import {
  el, clear, icon, dataTable, field, readForm, openModal, confirmDialog,
  toast, toastError, pageHeader,
} from '../ui.js';
import { can } from '../app.js';
import { editorPage } from './rebar-editor.js';

const MODES = ['design', 'shop'];
const BANDS = ['all', 'user', 'none'];
const FILE_CATEGORIES = ['design', 'ram', 'pt_design', 'pt_shop'];
const filters = { q: '' };
let projectTab = 'levels';

export async function render({ params, navigate }) {
  const [projectId, sub, runId, sub2] = params;
  if (projectId && sub === 'run' && runId && sub2 === 'edit') return editorPage(projectId, runId, navigate);
  if (projectId && sub === 'run' && runId) return runPage(projectId, runId, navigate);
  if (projectId) return projectPage(projectId, navigate);
  return listPage(navigate);
}

const fmtBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n || 0} B`);
const fill = (key, vars) => Object.entries(vars).reduce((text, [k, v]) => text.replace(`{${k}}`, v), t(key));

/** Top / bottom reinforcement weight of a run from its sheets (kg). */
function runWeights(run) {
  const w = { T: 0, B: 0 };
  for (const s of run.sheets || []) {
    if (!s.weight) continue;
    if (/TOP/i.test(s.title)) w.T += s.weight; else if (/BOTTOM/i.test(s.title)) w.B += s.weight;
  }
  return w;
}

/** The level a file name points at: its code or name inside the file name, else the first level. */
function guessLevel(fileName, levels) {
  const name = fileName.toUpperCase().replace(/[_\-.]+/g, ' ');
  const hit = levels.find((l) => new RegExp(`(^|\\s)${l.code.toUpperCase().replace(/[-]/g, ' ')}(\\s|$)`).test(name))
    || levels.find((l) => l.name && name.includes(l.name.toUpperCase()))
    || levels.find((l) => l.zone && name.includes(l.zone.toUpperCase()));
  return hit || levels[0];
}

// ------------------------------------------------------------------ helpers
const modeLabel = (mode) => t(mode === 'shop' ? 'dw_mode_shop' : 'dw_mode_design');
const bandsLabel = (bands) => t(`dw_bands_${bands || 'all'}`);
const MESHES = ['bottom', 'both'];
const meshLabel = (mesh) => t(`dw_mesh_${mesh || 'bottom'}`);
const BEAM_DESIGNS = ['ram', 'office', 'max'];
const beamDesignLabel = (v) => t(`dw_bd_${v || 'ram'}`);
const ROTATIONS = ['auto', '0', '90'];
const rotateLabel = (v) => t(`dw_rotate_${v == null || v === '' ? 'auto' : v}`);
const statusBadge = (status) => el('span', {
  class: `badge ${status === 'issued' ? 'green' : status === 'failed' || status === 'blocked' ? 'red' : status === 'superseded' ? 'grey' : status === 'running' ? 'amber' : 'blue'}`,
  text: t(`dw_status_${status || 'running'}`),
});
const levelLabel = (level) => [level.code, [level.name, level.zone].filter(Boolean).join(' - ')].filter(Boolean).join(' · ');
const exampleNo = (settings, project, level) =>
  `${project?.default_mode === 'shop' ? settings.shop_prefix : settings.design_prefix}-${project?.code || 'P26-001'}-${level?.code || 'B1'}-02`;

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function workflowCard() {
  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_workflow') })]),
    el('div.card-body', {}, [
      el('ol', { style: { margin: 0, paddingInlineStart: '1.2rem' } }, ['dw_step1', 'dw_step2', 'dw_step3', 'dw_step4'].map((key) => el('li', { text: t(key).replace(/^[\d١-٩]+[-.]\s*/, '') }))),
      el('div.mt-1', {}, [
        el('a', { href: 'help/ram-drawings-workflow.html', target: '_blank', rel: 'noopener', text: t('dw_open_workflow') }),
        el('a', { href: 'help/ram-file-workflow.html', target: '_blank', rel: 'noopener', text: t('dw_open_file_workflow') }),
      ]),
    ]),
  ]);
}

// --------------------------------------------------------------------- list
async function listPage(navigate) {
  const page = el('div');
  const listHost = el('div');

  const search = el('input', {
    type: 'search', placeholder: t('dw_search'), value: filters.q,
    oninput: debounce((event) => { filters.q = event.target.value; refresh(); }, 280),
  });

  page.append(el('div.toolbar', {}, [
    el('div.search-box', {}, [icon('search', 15), search]),
    el('div.spacer'),
    can('drawings.create') ? el('button.btn', {
      type: 'button', onclick: () => openProjectForm(null, (project) => navigate(`drawings/${project.id}`)),
    }, [icon('plus', 16), t('dw_new_project')]) : null,
  ]));
  page.append(el('div.alert.info', { text: t('dw_project_hint') }));
  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [listHost])]));
  page.append(workflowCard());

  async function refresh() {
    clear(listHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { projects } = await api.drawingProjects({ q: filters.q });
      clear(listHost).append(dataTable({
        rows: projects,
        empty: t('nothing_here'),
        onRowClick: (row) => navigate(`drawings/${row.id}`),
        columns: [
          {
            label: t('dw_project'),
            render: (row) => el('div', {}, [
              el('div.bold', { text: pick(row, 'name') }),
              el('div.tiny.muted', { text: row.code, dir: 'ltr' }),
            ]),
          },
          { label: t('dw_client'), render: (row) => row.client || '—' },
          { label: t('dw_consultant'), render: (row) => row.consultant || '—' },
          { label: t('dw_location'), render: (row) => row.location || '—' },
          { label: t('dw_levels'), className: 'num', render: (row) => row.level_count },
          { label: t('dw_runs'), className: 'num', render: (row) => row.run_count },
          { label: t('dw_last_run'), render: (row) => (row.last_run_at ? formatDate(row.last_run_at) : '—') },
          { label: t('owner'), render: (row) => pick(row, 'owner_name') || '—' },
        ],
      }));
    } catch (error) {
      clear(listHost).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }
  refresh();
  return page;
}

// ------------------------------------------------------------ project form
function openProjectForm(project, after) {
  const isNew = !project;
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'code', label: t('dw_code'), value: project?.code || '', dir: 'ltr', hint: isNew ? t('dw_code_hint') : '' }),
      field({ name: 'name', label: t('dw_name'), value: project?.name || '', dir: 'ltr', required: true }),
      field({ name: 'name_ar', label: t('dw_name_ar'), value: project?.name_ar || '', dir: 'rtl' }),
      field({ name: 'location', label: t('dw_location'), value: project?.location || '', dir: 'ltr' }),
      field({ name: 'client', label: t('dw_client'), value: project?.client || '', dir: 'ltr' }),
      field({ name: 'consultant', label: t('dw_consultant'), value: project?.consultant || '', dir: 'ltr' }),
      field({ name: 'contractor', label: t('dw_contractor'), value: project?.contractor || '', dir: 'ltr' }),
      field({
        name: 'country', label: t('country'), type: 'select', value: project?.country || '',
        options: [{ value: '', label: '—' }, ...['SA', 'EG', 'QA'].map((c) => ({ value: c, label: t(`country_${c}`) }))],
      }),
      field({ name: 'prepared', label: t('dw_prepared'), value: project?.prepared || '', dir: 'ltr', hint: t('dw_signatures_hint') }),
      field({ name: 'checked', label: t('dw_checked'), value: project?.checked || '', dir: 'ltr' }),
      field({ name: 'approved', label: t('dw_approved'), value: project?.approved || '', dir: 'ltr' }),
      field({
        name: 'default_mode', label: t('dw_default_mode'), type: 'select', value: project?.default_mode || 'design',
        options: MODES.map((m) => ({ value: m, label: modeLabel(m) })),
      }),
      field({
        name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: project?.ram_bands || 'all',
        options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })),
      }),
      field({
        name: 'mesh', label: t('dw_mesh'), type: 'select', value: project?.mesh || 'bottom', hint: t('dw_mesh_hint'),
        options: MESHES.map((m) => ({ value: m, label: meshLabel(m) })),
      }),
      field({
        name: 'rotate', label: t('dw_rotate'), type: 'select', value: project?.rotate || 'auto', hint: t('dw_rotate_hint'),
        options: ROTATIONS.map((m) => ({ value: m, label: rotateLabel(m) })),
      }),
      field({
        name: 'beam_design', label: t('dw_beam_design'), type: 'select', value: project?.beam_design || 'ram', hint: t('dw_bd_hint'),
        options: BEAM_DESIGNS.map((m) => ({ value: m, label: beamDesignLabel(m) })),
      }),
    ]),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: project?.notes || '', rows: 2 }),
    field({ name: 'spec', label: t('dw_spec'), type: 'textarea', value: project?.spec && Object.keys(project.spec).length ? JSON.stringify(project.spec, null, 2) : '', rows: 3, dir: 'ltr' }),
  ]);

  const { close } = openModal({
    title: isNew ? t('dw_new_project') : t('dw_edit_project'),
    size: 'wide',
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          const data = readForm(form);
          if (data.spec) {
            try { data.spec = JSON.parse(data.spec); } catch { toast(`${t('dw_spec')}: JSON`, 'error'); return; }
          } else data.spec = {};
          if (!data.code) delete data.code;
          event.currentTarget.disabled = true;
          try {
            const result = isNew ? await api.createDrawingProject(data) : await api.updateDrawingProject(project.id, data);
            toast(t('saved'), 'success');
            close();
            after?.(result.project);
          } catch (error) { toastError(error); event.currentTarget.disabled = false; }
        },
      }),
    ]),
  });
}

// -------------------------------------------------------------- level form
function openLevelForm(projectId, level, after) {
  const isNew = !level;
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'code', label: t('dw_level_code'), value: level?.code || '', dir: 'ltr', required: true, hint: t('dw_level_code_hint') }),
      field({ name: 'name', label: t('dw_level_name'), value: level?.name || '', dir: 'ltr', required: true }),
      field({ name: 'zone', label: t('dw_zone'), value: level?.zone || '', dir: 'ltr' }),
      field({ name: 'wall_thickness', label: t('dw_wall_thickness'), type: 'number', value: level?.wall_thickness ?? '', min: 100, max: 2000, step: 10, hint: t('dw_wall_thickness_hint') }),
      field({ name: 'sort_order', label: t('dw_sort_order'), type: 'number', value: level?.sort_order ?? '', min: 0, max: 999 }),
    ]),
    field({ name: 'ram_failed_columns', label: t('dw_ram_failed'), value: (level?.punching?.ram_failed || []).join(', '), dir: 'ltr', hint: t('dw_ram_failed_hint') }),
    field({ name: 'ram_failed_beams', label: t('dw_ram_failed_beams'), value: (level?.punching?.beams_ram_failed || []).join(', '), dir: 'ltr', hint: t('dw_ram_failed_beams_hint') }),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: level?.notes || '', rows: 2 }),
  ]);
  const { close } = openModal({
    title: isNew ? t('dw_new_level') : t('dw_edit_level'),
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          const data = readForm(form);
          if (data.sort_order === null) delete data.sort_order;
          event.currentTarget.disabled = true;
          try {
            if (isNew) await api.createDrawingLevel(projectId, data);
            else await api.updateDrawingLevel(level.id, data);
            toast(t('saved'), 'success');
            close();
            after?.();
          } catch (error) { toastError(error); event.currentTarget.disabled = false; }
        },
      }),
    ]),
  });
}

// ----------------------------------------------------------- reference plan
function openReferenceForm(level, after) {
  let ref = level.reference || null;
  const status = el('div.small');
  const found = el('div');
  const drawFound = () => {
    clear(found);
    if (!ref) { status.textContent = t('dw_reference_none'); return; }
    const sm = ref.summary || {};
    status.textContent = `${t('dw_reference_current')}: ${ref.name || ''}`;
    found.append(el('div.small.mt-1', {}, [
      el('div', { text: `${t('dw_reference_found')}: ${sm.columns ?? '?'} ${t('dw_reference_columns')} · ${sm.outlines ?? '?'} ${t('dw_reference_outlines')} · ${sm.units || ''}` }),
      el('div', { text: `${t('dw_reference_grid')}: ${(sm.grid_x || []).join(' ')} / ${(sm.grid_y || []).join(' ')}`, dir: 'ltr' }),
      sm.grid_from_drawing === false ? el('div.muted', { text: t('dw_reference_grid_derived') }) : null,
      sm.bbox ? el('div.tiny.muted', { text: `DXF extents: ${sm.bbox.minX}, ${sm.bbox.minY} → ${sm.bbox.maxX}, ${sm.bbox.maxY} mm`, dir: 'ltr' }) : null,
    ]));
  };
  drawFound();
  const input = el('input', { type: 'file', accept: '.dxf', style: { display: 'none' } });
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    try { const res = await api.uploadDrawingReference(level.id, file); ref = res.level.reference; drawFound(); toast(t('saved'), 'success'); } catch (error) { toastError(error); }
  });
  const use = ref?.use || { grid: true, columns: true, outline: true };
  const align = ref?.align || { mode: 'auto' };
  const pointFields = el('div.grid.grid-2', {}, [
    el('div', {}, [el('label.small', { text: t('dw_align_dxf') }), el('div.grid.grid-2', {}, [field({ name: 'dxf_x', label: t('dw_align_x'), type: 'number', value: align.dxf?.x ?? '', step: 1 }), field({ name: 'dxf_y', label: t('dw_align_y'), type: 'number', value: align.dxf?.y ?? '', step: 1 })])]),
    el('div', {}, [el('label.small', { text: t('dw_align_ram') }), el('div.grid.grid-2', {}, [field({ name: 'ram_x', label: t('dw_align_x'), type: 'number', value: align.ram?.x ?? '', step: 1 }), field({ name: 'ram_y', label: t('dw_align_y'), type: 'number', value: align.ram?.y ?? '', step: 1 })])]),
    field({ name: 'rot', label: t('dw_align_rot'), type: 'select', value: String(align.rot || 0), options: [0, 90, 180, 270].map((v) => ({ value: String(v), label: `${v}°` })) }),
  ]);
  const modeSel = field({ name: 'mode', label: t('dw_reference_align'), type: 'select', value: align.mode || 'auto', options: [{ value: 'auto', label: t('dw_align_auto') }, { value: 'point', label: t('dw_align_point') }] });
  const syncMode = () => { pointFields.style.display = modeSel.querySelector('select').value === 'point' ? '' : 'none'; };
  modeSel.querySelector('select').addEventListener('change', syncMode); syncMode();
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.alert.info', { text: t('dw_reference_hint') }),
    el('div.row.wrap', {}, [input, el('button.btn.btn-sm', { type: 'button', onclick: () => input.click() }, [icon('upload', 14), t('dw_reference_upload')]), status]),
    found,
    el('h4.mt-1', { text: t('dw_reference_use') }),
    el('div.grid.grid-3', {}, [
      field({ name: 'use_grid', label: t('dw_use_grid'), type: 'checkbox', value: use.grid !== false }),
      field({ name: 'use_columns', label: t('dw_use_columns'), type: 'checkbox', value: use.columns !== false }),
      field({ name: 'use_outline', label: t('dw_use_outline'), type: 'checkbox', value: use.outline !== false }),
    ]),
    modeSel,
    pointFields,
  ]);
  const { close } = openModal({
    title: `${t('dw_reference')} — ${levelLabel(level)}`,
    size: 'wide',
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      ref || level.reference ? el('button.btn-secondary.btn', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_delete_reference_confirm')))) return; try { await api.deleteDrawingReference(level.id); toast(t('deleted'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }, [icon('trash', 14), t('dw_reference_remove')]) : null,
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async () => {
          if (!ref) { input.click(); return; }
          const d = readForm(form);
          const payload = { use: { grid: d.use_grid, columns: d.use_columns, outline: d.use_outline }, align: d.mode === 'point' ? { mode: 'point', dxf: { x: d.dxf_x, y: d.dxf_y }, ram: { x: d.ram_x, y: d.ram_y }, rot: Number(d.rot) } : { mode: 'auto' } };
          try { await api.updateDrawingReference(level.id, payload); toast(t('dw_reference_saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); }
        },
      }),
    ]),
  });
}

// ----------------------------------------------------------- generate form
function openGenerateForm(project, levels, settings, preselected, navigate) {
  const fileInput = el('input', { type: 'file', name: 'files', accept: '.cpt,.dxf', multiple: true, required: true });
  const mapHost = el('div');
  const status = el('div.small.muted.mt-1');
  let picked = [];
  fileInput.addEventListener('change', () => {
    picked = [...(fileInput.files || [])].map((file) => ({ file, levelId: (picked.length === 0 && preselected && fileInput.files.length === 1 ? preselected : guessLevel(file.name, levels))?.id }));
    clear(mapHost);
    if (picked.length < 1) return;
    mapHost.append(el('div.tiny.muted', { text: t('dw_files_map_hint') }));
    mapHost.append(dataTable({
      rows: picked,
      columns: [
        { label: t('dw_file'), render: (row) => el('span', { text: row.file.name, dir: 'ltr' }) },
        { label: t('dw_file_size'), render: (row) => fmtBytes(row.file.size) },
        {
          label: t('dw_level'),
          render: (row) => el('select', { onchange: (e) => { row.levelId = Number(e.target.value); } }, levels.map((l) => { const o = el('option', { value: l.id, text: levelLabel(l) }); if (l.id === row.levelId) o.selected = true; return o; })),
        },
      ],
    }));
  });
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({
        name: 'mode', label: t('dw_mode'), type: 'select', value: project.default_mode || settings.default_mode || 'design',
        options: MODES.map((m) => ({ value: m, label: modeLabel(m) })),
      }),
      field({
        name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: project.ram_bands || settings.ram_bands || 'all',
        options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })),
      }),
      field({
        name: 'mesh', label: t('dw_mesh'), type: 'select', value: project.mesh || settings.mesh || 'bottom',
        options: MESHES.map((m) => ({ value: m, label: meshLabel(m) })),
      }),
      field({
        name: 'rotate', label: t('dw_rotate'), type: 'select', value: project.rotate || settings.rotate || 'auto',
        options: ROTATIONS.map((m) => ({ value: m, label: rotateLabel(m) })),
      }),
      field({
        name: 'beam_design', label: t('dw_beam_design'), type: 'select', value: project.beam_design || settings.beam_design || 'ram',
        options: BEAM_DESIGNS.map((m) => ({ value: m, label: beamDesignLabel(m) })),
      }),
    ]),
    field({ name: 'revision', label: t('dw_revision'), value: '', dir: 'ltr', hint: t('dw_revision_hint') }),
    field({ name: 'notes', label: t('dw_run_notes'), type: 'textarea', value: '', rows: 2, hint: t('dw_run_notes_hint') }),
    el('div.field', {}, [el('label', { text: t('dw_files_multi') }), fileInput]),
    mapHost,
    el('div.tiny.muted', { text: `${t('dw_numbering')}: ${exampleNo(settings, project, preselected || levels[0])}`, dir: 'ltr' }),
    status,
  ]);

  const { close } = openModal({
    title: `${t('dw_generate')} — ${project.code}`,
    size: 'wide',
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button',
        onclick: async (event) => {
          const button = event.currentTarget;
          const data = readForm(form);
          if (!picked.length) { fileInput.focus(); return; }
          button.disabled = true;
          const results = [];
          for (let i = 0; i < picked.length; i++) {
            const { file, levelId } = picked[i];
            status.textContent = fill('dw_batch_progress', { n: i + 1, total: picked.length }) + ` ${file.name}`;
            try {
              const { run } = await api.generateDrawings(levelId, file, { mode: data.mode, ram_bands: data.ram_bands, mesh: data.mesh, beam_design: data.beam_design, rotate: data.rotate, revision: data.revision || undefined, notes: data.notes || undefined });
              results.push({ ok: true, run, file });
            } catch (error) {
              results.push({ ok: false, error, file });
            }
          }
          const ok = results.filter((r) => r.ok);
          status.textContent = fill('dw_batch_done', { ok: ok.length, fail: results.length - ok.length });
          if (ok.length === results.length) toast(t('dw_generated'), 'success'); else toastError(results.find((r) => !r.ok).error);
          if (results.length === 1 && ok.length === 1) { close(); navigate(`drawings/${project.id}/run/${ok[0].run.id}`); return; }
          if (ok.length) { close(); navigate(`drawings/${project.id}`); return; }
          button.disabled = false;
        },
      }, [icon('play', 16), t('dw_generate')]),
    ]),
  });
}

// ------------------------------------------------------------------ project
async function projectPage(projectId, navigate) {
  const page = el('div');
  const body = el('div');
  page.append(body);

  async function load() {
    clear(body).append(el('div.loading-page', { text: t('loading') }));
    let data;
    try { data = await api.drawingProject(projectId); } catch (error) {
      clear(body).append(el('div.alert.danger', { text: error.localised || error.message }));
      return;
    }
    const { project, levels, runs, settings } = data;
    clear(body);

    body.append(pageHeader(`${project.code} · ${pick(project, 'name')}`, [
      el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate('drawings') }, [icon('back', 16), t('back')]),
      can('drawings.create') ? el('button.btn-secondary.btn', { type: 'button', onclick: () => openProjectForm(project, load) }, [icon('edit', 16), t('edit')]) : null,
      can('drawings.create') && levels.length ? el('button.btn', { type: 'button', onclick: () => openGenerateForm(project, levels, settings, null, navigate) }, [icon('play', 16), t('dw_generate')]) : null,
      can('drawings.delete') ? el('button.btn-danger.btn', {
        type: 'button',
        onclick: async () => {
          if (!(await confirmDialog(t('dw_delete_project_confirm')))) return;
          try { await api.deleteDrawingProject(project.id); toast(t('deleted'), 'success'); navigate('drawings'); } catch (error) { toastError(error); }
        },
      }, [icon('trash', 16), t('delete')]) : null,
    ]));

    const item = (label, value, dir) => el('div.detail-item', {}, [el('div.k', { text: label }), el('div.v', { text: value || '—', dir })]);
    body.append(el('div.card', {}, [
      el('div.card-body', {}, [
        el('div.detail-grid', {}, [
          item(t('dw_client'), project.client, 'ltr'),
          item(t('dw_consultant'), project.consultant, 'ltr'),
          item(t('dw_contractor'), project.contractor, 'ltr'),
          item(t('dw_location'), project.location, 'ltr'),
          item(t('dw_prepared'), project.prepared || settings.prepared, 'ltr'),
          item(t('dw_checked'), project.checked || settings.checked, 'ltr'),
          item(t('dw_approved'), project.approved || settings.approved, 'ltr'),
          item(t('dw_default_mode'), modeLabel(project.default_mode)),
          item(t('dw_ram_bands'), bandsLabel(project.ram_bands)),
          item(t('dw_mesh'), meshLabel(project.mesh)),
          item(t('dw_beam_design'), beamDesignLabel(project.beam_design)),
          item(t('dw_rotate'), rotateLabel(project.rotate)),
          item(t('dw_numbering'), exampleNo(settings, project, levels[0]), 'ltr'),
        ]),
        project.notes ? el('div.small.muted.mt-1', { text: project.notes }) : null,
      ]),
    ]));

    // tabs: levels & runs / project files / revision history
    const tabs = el('div.tabs');
    const panel = el('div');
    const TABS = [
      { key: 'levels', label: t('dw_tab_levels'), build: () => levelsPanel() },
      { key: 'files', label: t('dw_tab_files'), build: () => filesPanel() },
      { key: 'history', label: t('dw_tab_history'), build: () => historyPanel() },
      { key: 'submittals', label: t('dw_tab_submittals'), build: () => submittalsPanel(project, levels, runs, data.submittals || [], settings, load) },
      { key: 'quantities', label: t('dw_tab_quantities'), build: () => quantitiesPanel(project, settings) },
      { key: 'beam_types', label: t('dw_tab_beam_types'), build: () => beamTypesPanel(project, load) },
    ];
    const draw = () => {
      clear(tabs);
      for (const tab of TABS) tabs.append(el('button', { type: 'button', class: tab.key === projectTab ? 'active' : '', text: tab.label, onclick: () => { projectTab = tab.key; draw(); clear(panel).append(tab.build()); } }));
    };
    draw();
    panel.append((TABS.find((x) => x.key === projectTab) || TABS[0]).build());
    body.append(tabs, panel);

    function levelsPanel() {
      const host = el('div');
      host.append(el('div.card', {}, [
        el('div.card-header', {}, [
          el('h3', { text: t('dw_levels') }),
          el('div.spacer'),
          can('drawings.create') ? el('button.btn.btn-sm', { type: 'button', onclick: () => openLevelForm(project.id, null, load) }, [icon('plus', 14), t('dw_new_level')]) : null,
        ]),
        el('div.card-body.flush', {}, [
          levels.length ? dataTable({
            rows: levels,
            columns: [
              { label: t('dw_sort_order'), className: 'num', render: (row) => row.sort_order },
              { label: t('dw_level_code'), render: (row) => el('span.bold', { text: row.code, dir: 'ltr' }) },
              { label: t('dw_level_name'), render: (row) => el('span', { text: [row.name, row.zone].filter(Boolean).join(' - '), dir: 'ltr' }) },
              { label: t('dw_wall_thickness'), className: 'num', render: (row) => row.wall_thickness || '—' },
              { label: t('dw_runs'), className: 'num', render: (row) => row.run_count },
              { label: t('dw_last_rev'), render: (row) => (row.last_revision != null ? `REV ${row.last_revision}` : '—') },
              { label: t('dw_last_run'), render: (row) => (row.last_run_at ? formatDate(row.last_run_at) : '—') },
              { label: t('dw_edits_list'), className: 'num', render: (row) => (row.edits?.length ? el('span.badge.amber', { text: String(row.edits.length) }) : '—') },
              { label: t('dw_ram_failed'), render: (row) => (row.punching?.ram_failed?.length ? el('span.badge.red', { text: row.punching.ram_failed.join(', '), dir: 'ltr' }) : '—') },
              { label: t('dw_reference_short'), render: (row) => (row.reference ? el('span.badge.green', { text: `${row.reference.summary?.columns ?? '?'} ${t('dw_reference_columns')} · ${(row.reference.summary?.grid_x || []).join('')}/${(row.reference.summary?.grid_y || []).join('')}`, dir: 'ltr' }) : '—') },
              {
                label: t('actions'),
                render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
                  can('drawings.create') ? el('button.btn.btn-sm', { type: 'button', title: t('dw_generate'), onclick: () => openGenerateForm(project, levels, settings, row, navigate) }, [icon('play', 14), t('dw_generate_for')]) : null,
                  can('drawings.create') ? el('button.btn-secondary.btn.btn-sm', { type: 'button', title: t('dw_reference'), onclick: () => openReferenceForm(row, load) }, [icon('upload', 14), t('dw_reference_short')]) : null,
                  can('drawings.create') ? el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('edit'), onclick: () => openLevelForm(project.id, row, load) }, [icon('edit', 14)]) : null,
                  can('drawings.delete') ? el('button.btn-secondary.btn.btn-sm.btn-icon', {
                    type: 'button', title: t('delete'),
                    onclick: async () => {
                      if (!(await confirmDialog(t('dw_delete_level_confirm')))) return;
                      try { await api.deleteDrawingLevel(row.id); toast(t('deleted'), 'success'); load(); } catch (error) { toastError(error); }
                    },
                  }, [icon('trash', 14)]) : null,
                ]),
              },
            ],
          }) : el('div.empty', {}, [icon('layers', 40), el('div', { text: t('dw_no_levels') })]),
        ]),
      ]));
      host.append(el('div.card', {}, [
        el('div.card-header', {}, [el('h3', { text: t('dw_runs') })]),
        el('div.card-body.flush', {}, [runsTable(runs, project, navigate, load)]),
      ]));
      return host;
    }

    function filesPanel() {
      const host = el('div');
      host.append(el('div.alert.info', { text: t('dw_files_hint') }));
      for (const cat of FILE_CATEGORIES) {
        const mine = (data.files || []).filter((f) => f.category === cat);
        // the packages generated here belong to the PT sections
        const generated = cat === 'pt_design' || cat === 'pt_shop' ? runs.filter((r) => r.status !== 'failed' && r.status !== 'running' && (cat === 'pt_design' ? r.mode === 'design' : r.mode === 'shop')) : [];
        const rows = [
          ...generated.map((r) => ({ generated: true, id: `run-${r.id}`, run: r, name: `${r.prefix}-${r.level_code}_REV${r.revision}.zip`, bytes: null, revision: r.revision, note: r.notes || t('dw_generated_package'), created_at: r.created_at, uploaded_by_name: r.created_by_name, uploaded_by_name_ar: r.created_by_name_ar, level_code: r.level_code, status: r.status })),
          ...mine,
        ];
        host.append(el('div.card', {}, [
          el('div.card-header', {}, [
            el('h3', { text: t(`dw_files_${cat}`) }),
            el('span.badge.grey', { text: String(rows.length) }),
            el('div.spacer'),
            can('drawings.create') ? uploadButton(cat) : null,
          ]),
          el('div.card-body.flush', {}, [rows.length ? dataTable({
            rows,
            columns: [
              { label: t('dw_file_name'), render: (row) => el('div', {}, [el('div.bold', { text: row.name, dir: 'ltr' }), row.generated ? el('div.tiny.muted', { text: `${t('dw_run')} #${row.run.serial} · ${levelLabel({ code: row.run.level_code, name: row.run.level_name, zone: row.run.level_zone })}`, dir: 'ltr' }) : null]) },
              { label: t('dw_level'), render: (row) => row.level_code || '—' },
              { label: t('dw_file_rev'), render: (row) => row.revision || '—' },
              { label: t('status'), render: (row) => (row.generated ? statusBadge(row.status) : '—') },
              { label: t('dw_file_note'), render: (row) => row.note || '—' },
              { label: t('dw_file_size'), render: (row) => (row.bytes != null ? fmtBytes(row.bytes) : '—') },
              { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
              { label: t('dw_file_by'), render: (row) => pick(row, 'uploaded_by_name') || '—' },
              {
                label: t('actions'),
                render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
                  row.generated
                    ? el('a.btn.btn-sm', { href: api.drawingRunZipUrl(row.run.id), title: t('dw_download_zip') }, [icon('download', 14), 'ZIP'])
                    : el('a.btn.btn-sm', { href: api.drawingFileUrl(row.id), title: t('open') }, [icon('download', 14), t('open')]),
                  row.generated ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => navigate(`drawings/${project.id}/run/${row.run.id}`) }, [icon('chevron', 14), t('open')]) : null,
                  !row.generated && can('drawings.create') ? el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('edit'), onclick: () => openFileForm(row, load) }, [icon('edit', 14)]) : null,
                  !row.generated && can('drawings.delete') ? el('button.btn-secondary.btn.btn-sm.btn-icon', {
                    type: 'button', title: t('delete'),
                    onclick: async () => {
                      if (!(await confirmDialog(t('dw_delete_file_confirm')))) return;
                      try { await api.deleteDrawingFile(row.id); toast(t('deleted'), 'success'); load(); } catch (error) { toastError(error); }
                    },
                  }, [icon('trash', 14)]) : null,
                ]),
              },
            ],
          }) : el('div.empty', {}, [icon('empty', 32), el('div', { text: t('dw_no_files') })])]),
        ]));
      }
      return host;

      function uploadButton(cat) {
        const input = el('input', { type: 'file', multiple: true, style: { display: 'none' } });
        input.addEventListener('change', async () => {
          const files = [...(input.files || [])];
          if (!files.length) return;
          const levelId = levels.length === 1 ? levels[0].id : (levels.length ? null : null);
          for (const file of files) {
            try { await api.uploadDrawingFile(project.id, file, { category: cat, level_id: levelId || undefined }); } catch (error) { toastError(error); }
          }
          toast(t('saved'), 'success');
          load();
        });
        return el('span', {}, [input, el('button.btn.btn-sm', { type: 'button', onclick: () => input.click() }, [icon('upload', 14), t('dw_upload_file')])]);
      }
    }

    function openFileForm(file, after) {
      const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
        field({ name: 'category', label: t('dw_file_category'), type: 'select', value: file.category, options: FILE_CATEGORIES.map((c) => ({ value: c, label: t(`dw_files_${c}`) })) }),
        field({ name: 'level_id', label: t('dw_level'), type: 'select', value: file.level_id || '', options: [{ value: '', label: '—' }, ...levels.map((l) => ({ value: l.id, label: levelLabel(l) }))] }),
        field({ name: 'revision', label: t('dw_file_rev'), value: file.revision || '', dir: 'ltr' }),
        field({ name: 'note', label: t('dw_file_note'), type: 'textarea', value: file.note || '', rows: 2 }),
      ]);
      const { close } = openModal({
        title: file.name,
        body: form,
        footer: el('div.row', {}, [
          el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
          el('button.btn', { type: 'button', text: t('save'), onclick: async () => { try { const data = readForm(form); await api.updateDrawingFile(file.id, { ...data, level_id: data.level_id || null }); toast(t('saved'), 'success'); close(); after(); } catch (error) { toastError(error); } } }),
        ]),
      });
    }

    function historyPanel() {
      const host = el('div');
      host.append(el('div.alert.info', { text: t('dw_history_hint') }));
      for (const level of levels) {
        const mine = runs.filter((r) => r.level_id === level.id && r.status !== 'running').sort((a, b) => a.serial - b.serial);
        if (!mine.length) continue;
        let prev = null;
        const rows = mine.map((r) => {
          const w = runWeights(r);
          const row = { ...r, w, dT: prev ? w.T - prev.T : null, dB: prev ? w.B - prev.B : null };
          if (r.status !== 'failed') prev = w;
          return row;
        }).reverse();
        const delta = (v) => (v == null ? '—' : el('span', { class: v > 0 ? 'badge amber' : v < 0 ? 'badge green' : 'badge grey', text: `${v > 0 ? '+' : ''}${Math.round(v).toLocaleString('en-US')}` }));
        host.append(el('div.card', {}, [
          el('div.card-header', {}, [el('h3', { text: levelLabel(level), dir: 'ltr' })]),
          el('div.card-body.flush', {}, [dataTable({
            rows,
            onRowClick: (row) => navigate(`drawings/${project.id}/run/${row.id}`),
            columns: [
              { label: t('dw_serial'), className: 'num', render: (row) => `#${row.serial}` },
              { label: t('dw_mode'), render: (row) => modeLabel(row.mode) },
              { label: t('dw_revision'), render: (row) => `REV ${row.revision}` },
              { label: t('status'), render: (row) => statusBadge(row.status) },
              { label: t('dw_run_notes'), render: (row) => el('span', { text: row.notes || '—' }) },
              { label: t('dw_sheets'), className: 'num', render: (row) => row.sheet_count },
              { label: t('dw_weight_t'), className: 'num', render: (row) => el('span', {}, [String(Math.round(row.w.T).toLocaleString('en-US')), ' ', delta(row.dT)]) },
              { label: t('dw_weight_b'), className: 'num', render: (row) => el('span', {}, [String(Math.round(row.w.B).toLocaleString('en-US')), ' ', delta(row.dB)]) },
              { label: t('dw_edits_list'), className: 'num', render: (row) => (row.edits?.length ? row.edits.length : '—') },
              { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
              { label: t('dw_by'), render: (row) => pick(row, 'created_by_name') || '—' },
            ],
          })]),
        ]));
      }
      if (!host.querySelector('.card')) host.append(el('div.empty', {}, [icon('empty', 40), el('div', { text: t('dw_no_runs') })]));
      return host;
    }
  }

  await load();
  return page;
}

// ------------------------------------------------------------- submittals
const SUBMITTAL_STATUS = ['draft', 'submitted', 'approved', 'approved_as_noted', 'resubmit', 'rejected', 'withdrawn'];
const PURPOSES = ['approval', 'information', 'resubmission', 'as_built'];
const submittalBadge = (status) => el('span', {
  class: `badge ${status === 'approved' ? 'green' : status === 'approved_as_noted' || status === 'submitted' ? 'blue' : status === 'resubmit' || status === 'rejected' ? 'red' : status === 'withdrawn' ? 'grey' : 'amber'}`,
  text: t(`dw_sstatus_${status}`),
});

function submittalsPanel(project, levels, runs, submittals, settings, reload) {
  const host = el('div');
  host.append(el('div.alert.info', { text: t('dw_submittals_hint') }));
  const usable = runs.filter((r) => r.status !== 'failed' && r.status !== 'running');
  host.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('dw_tab_submittals') }),
      el('span.badge.grey', { text: String(submittals.length) }),
      el('div.spacer'),
      can('drawings.create') && usable.length ? el('button.btn.btn-sm', { type: 'button', onclick: () => openSubmittalForm(project, levels, usable, settings, reload) }, [icon('plus', 14), t('dw_new_submittal')]) : null,
    ]),
    el('div.card-body.flush', {}, [submittals.length ? dataTable({
      rows: submittals,
      columns: [
        { label: t('dw_submittal_no'), render: (row) => el('span.bold', { text: row.code, dir: 'ltr' }) },
        { label: t('dw_submittal_date'), render: (row) => row.date },
        { label: t('dw_submittal_subject'), render: (row) => el('span', { text: row.subject || '—', dir: 'ltr' }) },
        { label: t('dw_submittal_to'), render: (row) => el('span', { text: [row.to_name, row.attention].filter(Boolean).join(' · ') || '—', dir: 'ltr' }) },
        { label: t('dw_submittal_purpose'), render: (row) => t(`dw_purpose_${row.purpose}`) },
        { label: t('dw_submittal_items'), className: 'num', render: (row) => row.items.length },
        { label: t('status'), render: (row) => submittalBadge(row.status) },
        { label: t('dw_submittal_response'), render: (row) => el('span.small', { text: [row.response_date, row.response_notes].filter(Boolean).join(' — ') || '—' }) },
        { label: t('dw_by'), render: (row) => pick(row, 'created_by_name') || '—' },
        {
          label: t('actions'),
          render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
            el('a.btn.btn-sm', { href: api.drawingSubmittalFormUrl(row.id), target: '_blank', rel: 'noopener', title: t('dw_submittal_open_form') }, [icon('chevron', 14), t('print')]),
            can('drawings.create') ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => openSubmittalStatus(row, reload) }, [icon('edit', 14), t('dw_submittal_mark')]) : null,
            can('drawings.delete') ? el('button.btn-secondary.btn.btn-sm.btn-icon', {
              type: 'button', title: t('delete'),
              onclick: async () => {
                if (!(await confirmDialog(t('dw_delete_submittal_confirm')))) return;
                try { await api.deleteDrawingSubmittal(row.id); toast(t('deleted'), 'success'); reload(); } catch (error) { toastError(error); }
              },
            }, [icon('trash', 14)]) : null,
          ]),
        },
      ],
    }) : el('div.empty', {}, [icon('empty', 32), el('div', { text: t('dw_no_submittals') })])]),
  ]));
  // the drawings of each submittal, with what they supersede
  for (const sub of submittals) {
    host.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${sub.code} · ${sub.subject || ''}`, dir: 'ltr' }), el('div.spacer'), submittalBadge(sub.status)]),
      el('div.card-body.flush', {}, [dataTable({
        rows: sub.items,
        columns: [
          { label: t('dw_sheet_no'), render: (row) => el('span.bold', { text: row.no, dir: 'ltr' }) },
          { label: t('dw_sheet_title'), render: (row) => el('span', { text: row.title, dir: 'ltr' }) },
          { label: t('dw_level'), render: (row) => el('span', { text: row.level === 'ALL' ? 'ALL' : `${row.level} - ${row.level_name || ''}`, dir: 'ltr' }) },
          { label: t('dw_revision'), render: (row) => `REV ${row.rev}` },
          { label: t('dw_submittal_supersedes'), render: (row) => (row.prev_rev != null ? el('span', { text: `REV ${row.prev_rev} (${row.prev_submittal})`, dir: 'ltr' }) : '—') },
        ],
      })]),
    ]));
  }
  return host;
}

function openSubmittalForm(project, levels, runs, settings, after) {
  const levelOf = (r) => levelLabel({ code: r.level_code, name: r.level_name, zone: r.level_zone });
  const picked = new Map(); // run id -> Set of sheet numbers (null = all)
  const runsHost = el('div');
  const sheetsHost = el('div');
  const drawSheets = () => {
    clear(sheetsHost);
    for (const run of runs.filter((r) => picked.has(r.id))) {
      const chosen = picked.get(run.id);
      const sheets = run.sheets.filter((sh) => !(sh.level === 'ALL' && /COVER|INDEX/i.test(sh.title)));
      sheetsHost.append(el('div.card', {}, [
        el('div.card-header', {}, [el('h3', { text: `#${run.serial} · ${levelOf(run)} · REV ${run.revision}`, dir: 'ltr' }), el('div.spacer'), el('label.small', {}, [el('input', { type: 'checkbox', checked: chosen === null, onchange: (e) => { picked.set(run.id, e.target.checked ? null : new Set(sheets.map((x) => x.no))); drawSheets(); } }), ' ', t('dw_submittal_all_sheets')])]),
        el('div.card-body', {}, [el('div.grid.grid-2', {}, sheets.map((sh) => el('label.small', {}, [
          el('input', { type: 'checkbox', checked: chosen === null || chosen.has(sh.no), disabled: chosen === null, onchange: (e) => { if (e.target.checked) chosen.add(sh.no); else chosen.delete(sh.no); } }),
          ' ', el('span', { text: `${sh.no} — ${sh.title}`, dir: 'ltr' }),
        ])))]),
      ]));
    }
  };
  runsHost.append(dataTable({
    rows: runs,
    columns: [
      { label: '', render: (row) => el('input', { type: 'checkbox', onchange: (e) => { if (e.target.checked) picked.set(row.id, null); else picked.delete(row.id); drawSheets(); } }) },
      { label: t('dw_serial'), className: 'num', render: (row) => `#${row.serial}` },
      { label: t('dw_level'), render: (row) => el('span', { text: levelOf(row), dir: 'ltr' }) },
      { label: t('dw_mode'), render: (row) => modeLabel(row.mode) },
      { label: t('dw_revision'), render: (row) => `REV ${row.revision}` },
      { label: t('status'), render: (row) => statusBadge(row.status) },
      { label: t('dw_sheets'), className: 'num', render: (row) => row.sheet_count },
    ],
  }));
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'to_name', label: t('dw_submittal_to'), value: project.consultant || '', dir: 'ltr' }),
      field({ name: 'attention', label: t('dw_submittal_attention'), value: '', dir: 'ltr' }),
      field({ name: 'purpose', label: t('dw_submittal_purpose'), type: 'select', value: 'approval', options: PURPOSES.map((p) => ({ value: p, label: t(`dw_purpose_${p}`) })) }),
      field({ name: 'date', label: t('dw_submittal_date'), type: 'date', value: new Date().toISOString().slice(0, 10) }),
    ]),
    field({ name: 'subject', label: t('dw_submittal_subject'), value: '', dir: 'ltr', hint: t('optional') }),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: '', rows: 2 }),
    el('h4.mt-1', { text: t('dw_submittal_runs') }),
    runsHost,
    el('h4.mt-1', { text: t('dw_submittal_sheets') }),
    sheetsHost,
    el('div.tiny.muted', { text: `${t('dw_submittal_no')}: ${settings.submittal?.prefix || 'SPAN-SUB'}-${project.code}-001`, dir: 'ltr' }),
  ]);
  const { close } = openModal({
    title: t('dw_new_submittal'),
    size: 'wide',
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button', text: t('create'),
        onclick: async (event) => {
          if (!picked.size) { toast(t('dw_submittal_runs'), 'error'); return; }
          const data = readForm(form);
          const sheets = [...picked.values()].some((v) => v !== null) ? runs.filter((r) => picked.has(r.id)).flatMap((r) => (picked.get(r.id) === null ? r.sheets.map((x) => x.no) : [...picked.get(r.id)])) : undefined;
          event.currentTarget.disabled = true;
          try {
            const { submittal } = await api.createDrawingSubmittal(project.id, { ...data, subject: data.subject || undefined, run_ids: [...picked.keys()], sheets });
            toast(t('saved'), 'success');
            close();
            window.open(api.drawingSubmittalFormUrl(submittal.id), '_blank', 'noopener');
            after?.();
          } catch (error) { toastError(error); event.currentTarget.disabled = false; }
        },
      }),
    ]),
  });
}

function openSubmittalStatus(sub, after) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'status', label: t('status'), type: 'select', value: sub.status, options: SUBMITTAL_STATUS.map((v) => ({ value: v, label: t(`dw_sstatus_${v}`) })) }),
      field({ name: 'date', label: t('dw_submittal_date'), type: 'date', value: sub.date || '' }),
      field({ name: 'to_name', label: t('dw_submittal_to'), value: sub.to_name || '', dir: 'ltr' }),
      field({ name: 'attention', label: t('dw_submittal_attention'), value: sub.attention || '', dir: 'ltr' }),
      field({ name: 'response_date', label: t('dw_submittal_response_date'), type: 'date', value: sub.response_date || '' }),
      field({ name: 'response_by', label: t('dw_submittal_response_by'), value: sub.response_by || '', dir: 'ltr' }),
    ]),
    field({ name: 'subject', label: t('dw_submittal_subject'), value: sub.subject || '', dir: 'ltr' }),
    field({ name: 'response_notes', label: t('dw_submittal_response'), type: 'textarea', value: sub.response_notes || '', rows: 2 }),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: sub.notes || '', rows: 2 }),
  ]);
  const { close } = openModal({
    title: `${sub.code}`,
    size: 'wide',
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn-secondary.btn', { type: 'button', text: t('dw_submittal_reissue'), onclick: async () => { try { await api.updateDrawingSubmittal(sub.id, { ...readForm(form), reissue: true }); toast(t('saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }),
      el('button.btn', { type: 'button', text: t('save'), onclick: async () => { try { await api.updateDrawingSubmittal(sub.id, readForm(form)); toast(t('saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }),
    ]),
  });
}

// --------------------------------------------------------- quantities and cost
const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 }));
const csvOf = (rows) => rows.map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
function downloadText(name, text) {
  const a = el('a', { href: URL.createObjectURL(new Blob([`﻿${text}`], { type: 'text/csv;charset=utf-8' })), download: name });
  document.body.append(a); a.click(); a.remove();
}

// ----------------------------------------------------------- beam schedule
/** The project's unified beam schedule: the types on record, where each came from, calling up an earlier project's schedule. */
function beamTypesPanel(project, reload) {
  const host = el('div');
  const draw = (types) => {
    clear(host);
    const sourceOf = (t) => {
      const sname = t.source || {};
      if (sname.imported) return fill('dw_bt_source_import', { code: sname.project_code || sname.project_id || '?' });
      if (sname.run_id) return fill('dw_bt_source_run', { run: sname.run_id, level: sname.level || '', rev: sname.revision || '' });
      return '—';
    };
    host.append(el('div.card', {}, [
      el('div.card-header', {}, [
        el('h3', { text: `${t('dw_tab_beam_types')} (${types.length})` }), el('div.spacer'),
        can('drawings.create') ? el('button.btn.btn-sm', { type: 'button', onclick: () => openBeamTypesImport(project, (r) => draw(r.beam_types)) }, [icon('copy', 14), t('dw_bt_import')]) : null,
      ]),
      el('div.card-body', {}, [el('div.small.muted', { text: t('dw_bt_hint') })]),
      types.length ? el('div.card-body.flush', {}, [dataTable({
        rows: types,
        columns: [
          { label: t('dw_beam_type'), render: (r) => el('span.bold', { text: `${r.mark}`, dir: 'ltr' }) },
          { label: t('dw_beam_section'), render: (r) => el('span', { text: `${r.width} x ${r.depth}`, dir: 'ltr' }) },
          { label: t('dw_beam_top'), render: (r) => r.top?.text || '—' },
          { label: t('dw_beam_bottom'), render: (r) => r.bottom?.text || '—' },
          { label: t('dw_beam_stirrups'), render: (r) => (r.stirrups ? `T${r.stirrups.dia}-${r.stirrups.legs}L @ ${r.stirrups.spacing}` : '—') },
          { label: t('dw_bt_source'), render: (r) => el('span.small', { text: `${sourceOf(r)}${r.source?.by ? ` · ${r.source.by}` : ''}`, dir: 'ltr' }) },
          { label: t('date'), render: (r) => (r.created_at ? formatDate(r.created_at) : '—') },
          {
            label: t('actions'),
            render: (r) => (can('drawings.delete') ? el('button.btn-secondary.btn.btn-sm.btn-icon', {
              type: 'button', title: t('delete'),
              onclick: async () => {
                if (!(await confirmDialog(t('dw_bt_delete_confirm')))) return;
                try { const res = await api.deleteDrawingBeamType(project.id, r.mark); toast(t('deleted'), 'success'); draw(res.beam_types); } catch (error) { toastError(error); }
              },
            }, [icon('trash', 14)]) : null),
          },
        ],
      })]) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_bt_empty') })]),
    ]));
  };
  draw(project.beam_types || []);
  return host;
}

function openBeamTypesImport(project, after) {
  const select = el('select', { name: 'from_project_id' });
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.small.muted', { text: t('dw_bt_import_hint') }),
    el('div.field', {}, [el('label', { text: t('dw_bt_from') }), select]),
  ]);
  api.drawingProjects().then(({ projects }) => {
    for (const p of projects.filter((p) => p.id !== project.id && (p.beam_types || []).length)) select.append(el('option', { value: p.id, text: `${p.code} · ${p.name} (${p.beam_types.length})` }));
    if (!select.options.length) select.append(el('option', { value: '', text: '—' }));
  }).catch(toastError);
  const { close } = openModal({
    title: t('dw_bt_import'),
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button', text: t('dw_bt_import'),
        onclick: async (e) => {
          if (!select.value) return;
          e.currentTarget.disabled = true;
          try {
            const res = await api.importDrawingBeamTypes(project.id, { from_project_id: Number(select.value) });
            toast(fill('dw_bt_imported', { added: res.added, skipped: res.skipped }), 'success');
            close(); after?.(res);
          } catch (error) { toastError(error); e.currentTarget.disabled = false; }
        },
      }),
    ]),
  });
}

function quantitiesPanel(project, settings) {
  const host = el('div');
  host.append(el('div.alert.info', { text: t('dw_quantities_hint') }));
  const body = el('div.loading-page', { text: t('loading') });
  host.append(body);
  (async () => {
    let q, costData;
    try {
      q = await api.drawingProjectQuantities(project.id);
      costData = await api.drawingProjectCost(project.id);
    } catch (error) { clear(body).append(el('div.alert.danger', { text: error.localised || error.message })); return; }
    clear(body);
    body.classList.remove('loading-page');
    if (!q.levels.length) { body.append(el('div.empty', {}, [icon('empty', 40), el('div', { text: t('dw_no_quantities') })])); return; }
    const T = q.totals;
    const rowsAll = [...q.levels, { id: t('dw_qty_totals'), name: '', level_code: '', totals: true, steel: T.steel, concrete: T.concrete, cables: T.cables }];
    const cell = (v, d) => el('span', { text: num(v, d), dir: 'ltr' });
    const levelCell = (row) => el('div', {}, [el('div.bold', { text: row.totals ? row.id : `${row.level_code} · ${row.name}`, dir: 'ltr' }), row.totals ? null : el('div.tiny.muted', { text: `${t('dw_qty_source')}: #${row.run_serial} REV ${row.revision} · ${modeLabel(row.mode)}`, dir: 'ltr' })]);
    // steel
    const dias = T.steel.byDia.map((d) => d.dia);
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_steel') }), el('div.spacer'), el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => downloadText(`${project.code}_steel.csv`, csvOf([['LEVEL', 'TOP kg', 'BOTTOM kg', 'OTHER kg', 'MESH kg', 'TOTAL kg', 'kg/m2', ...dias.map((d) => `T${d} kg`)], ...rowsAll.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.steel.top_kg, r.steel.bottom_kg, r.steel.other_kg, r.steel.mesh_kg ?? 0, r.steel.kg, r.steel.kg_per_m2 ?? '', ...dias.map((d) => r.steel.byDia.find((x) => x.dia === d)?.kg ?? 0)])])) }, [icon('download', 14), t('dw_export_csv')])]),
      el('div.card-body.flush', {}, [dataTable({
        rows: rowsAll,
        columns: [
          { label: t('dw_level'), render: levelCell },
          { label: t('dw_qty_top'), className: 'num', render: (r) => cell(r.steel.top_kg, 0) },
          { label: t('dw_qty_bottom'), className: 'num', render: (r) => cell(r.steel.bottom_kg, 0) },
          { label: t('dw_qty_other'), className: 'num', render: (r) => cell(r.steel.other_kg, 0) },
          { label: t('dw_mesh_kg'), className: 'num', render: (r) => cell(r.steel.mesh_kg ?? 0, 0) },
          { label: t('dw_qty_kg'), className: 'num', render: (r) => el('span.bold', { text: num(r.steel.kg, 0), dir: 'ltr' }) },
          { label: t('dw_qty_kg_m2'), className: 'num', render: (r) => cell(r.steel.kg_per_m2, 2) },
          ...dias.map((d) => ({ label: `T${d}`, className: 'num', render: (r) => cell(r.steel.byDia.find((x) => x.dia === d)?.kg ?? 0, 0) })),
        ],
      })]),
    ]));
    // concrete
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_concrete') }), el('div.spacer'), el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => downloadText(`${project.code}_concrete.csv`, csvOf([['LEVEL', 'THK mm', 'GROSS m2', 'OPENINGS m2', 'NET m2', 'SLAB m3', 'DROPS m3', 'BEAMS m3', 'TOTAL m3', 'FORMWORK m2'], ...rowsAll.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.concrete.thickness ?? '', r.concrete.gross_area_m2, r.concrete.openings_m2, r.concrete.net_area_m2, r.concrete.slab_m3, r.concrete.drops_m3, r.concrete.beams_m3, r.concrete.total_m3, r.concrete.formwork_m2])])) }, [icon('download', 14), t('dw_export_csv')])]),
      el('div.card-body.flush', {}, [dataTable({
        rows: rowsAll,
        columns: [
          { label: t('dw_level'), render: levelCell },
          { label: t('dw_qty_thk'), className: 'num', render: (r) => (r.concrete.thickness ? cell(r.concrete.thickness, 0) : '—') },
          { label: t('dw_qty_gross'), className: 'num', render: (r) => cell(r.concrete.gross_area_m2) },
          { label: t('dw_qty_openings'), className: 'num', render: (r) => cell(r.concrete.openings_m2) },
          { label: t('dw_qty_net'), className: 'num', render: (r) => cell(r.concrete.net_area_m2) },
          { label: t('dw_qty_slab'), className: 'num', render: (r) => cell(r.concrete.slab_m3) },
          { label: t('dw_qty_drops'), className: 'num', render: (r) => cell(r.concrete.drops_m3) },
          { label: t('dw_qty_beams'), className: 'num', render: (r) => cell(r.concrete.beams_m3) },
          { label: t('dw_qty_total_m3'), className: 'num', render: (r) => el('span.bold', { text: num(r.concrete.total_m3), dir: 'ltr' }) },
          { label: t('dw_qty_formwork'), className: 'num', render: (r) => cell(r.concrete.formwork_m2) },
        ],
      })]),
    ]));
    // cables
    const pt = rowsAll.filter((r) => r.cables);
    if (pt.length) body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_cables') }), el('div.spacer'), el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => downloadText(`${project.code}_cables.csv`, csvOf([['LEVEL', 'TENDONS', 'STRANDS', 'TENDON m', 'STRAND m', 'CUTTING m', 'STRAND kg', 'kg/m2', 'LIVE', 'DEAD', 'DUCT 20x50 m', 'DUCT 20x70 m'], ...pt.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.cables.tendons, r.cables.strands, r.cables.tendon_m, r.cables.strand_m, r.cables.cutting_m, r.cables.kg, r.cables.kg_per_m2 ?? '', r.cables.live_ends, r.cables.dead_ends, r.cables.duct_small_m, r.cables.duct_large_m])])) }, [icon('download', 14), t('dw_export_csv')])]),
      el('div.card-body.flush', {}, [dataTable({
        rows: pt,
        columns: [
          { label: t('dw_level'), render: levelCell },
          { label: t('dw_qty_tendons'), className: 'num', render: (r) => cell(r.cables.tendons, 0) },
          { label: t('dw_qty_strands'), className: 'num', render: (r) => cell(r.cables.strands, 0) },
          { label: t('dw_qty_tendon_m'), className: 'num', render: (r) => cell(r.cables.tendon_m, 0) },
          { label: t('dw_qty_strand_m'), className: 'num', render: (r) => cell(r.cables.strand_m, 0) },
          { label: t('dw_qty_cutting_m'), className: 'num', render: (r) => cell(r.cables.cutting_m, 0) },
          { label: t('dw_qty_strand_kg'), className: 'num', render: (r) => el('span.bold', { text: num(r.cables.kg, 0), dir: 'ltr' }) },
          { label: t('dw_qty_kg_m2'), className: 'num', render: (r) => cell(r.cables.kg_per_m2, 2) },
          { label: t('dw_qty_live'), className: 'num', render: (r) => cell(r.cables.live_ends, 0) },
          { label: t('dw_qty_dead'), className: 'num', render: (r) => cell(r.cables.dead_ends, 0) },
          { label: t('dw_qty_duct_small'), className: 'num', render: (r) => cell(r.cables.duct_small_m, 0) },
          { label: t('dw_qty_duct_large'), className: 'num', render: (r) => cell(r.cables.duct_large_m, 0) },
        ],
      })]),
    ]));
    // cost study with a what-if on the rates
    const costHost = el('div');
    const RATE_KEYS = ['steel_per_ton', 'rebar_labour_per_ton', 'concrete_per_m3', 'formwork_per_m2', 'strand_per_kg', 'anchor_live', 'anchor_dead', 'duct_per_m', 'pt_labour_per_m2', 'markup_pct', 'vat_pct'];
    const ratesForm = el('form', { onsubmit: (e) => e.preventDefault() }, [el('div.grid.grid-4', {}, RATE_KEYS.map((k) => field({ name: k, label: t(`dw_rate_${k}`), type: 'number', value: costData.cost.rates[k], min: 0, step: 0.01 })))]);
    const drawCost = (c) => {
      clear(costHost);
      const cur = c.currency;
      const rowsCost = [...c.levels.map((l, i) => ({ ...l, level_code: q.levels[i]?.level_code || l.id })), { id: t('dw_qty_totals'), totals: true, ...c.totals }];
      const lineKeys = c.totals.lines.map((l) => l.key);
      costHost.append(dataTable({
        rows: rowsCost,
        columns: [
          { label: t('dw_level'), render: (r) => el('span.bold', { text: r.totals ? r.id : `${r.level_code} · ${r.name}`, dir: 'ltr' }) },
          ...lineKeys.map((k) => ({ label: t(`dw_cost_${k}`), className: 'num', render: (r) => cell(r.lines.find((l) => l.key === k)?.amount, 0) })),
          { label: t('dw_cost_direct'), className: 'num', render: (r) => cell(r.direct, 0) },
          { label: t('dw_cost_markup'), className: 'num', render: (r) => cell(r.markup, 0) },
          { label: t('dw_cost_vat'), className: 'num', render: (r) => cell(r.vat, 0) },
          { label: `${t('dw_cost_total')} (${cur})`, className: 'num', render: (r) => el('span.bold', { text: num(r.total, 0), dir: 'ltr' }) },
          { label: t('dw_cost_per_m2'), className: 'num', render: (r) => cell(r.per_m2, 0) },
        ],
      }));
      costHost.append(el('div.card-body', {}, [dataTable({
        rows: c.totals.lines,
        columns: [
          { label: t('dw_cost_item'), render: (l) => t(`dw_cost_${l.key}`) },
          { label: t('dw_cost_unit'), render: (l) => l.unit },
          { label: t('dw_cost_qty'), className: 'num', render: (l) => cell(l.qty, 2) },
          { label: `${t('dw_cost_rate')} (${cur})`, className: 'num', render: (l) => cell(l.rate, 2) },
          { label: `${t('dw_cost_amount')} (${cur})`, className: 'num', render: (l) => el('span.bold', { text: num(l.amount, 0), dir: 'ltr' }) },
        ],
      })]));
    };
    drawCost(costData.cost);
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_cost') }), el('div.spacer'),
        el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => downloadText(`${project.code}_cost.csv`, csvOf([['ITEM', 'UNIT', 'QTY', 'RATE', 'AMOUNT'], ...costData.cost.totals.lines.map((l) => [l.key, l.unit, l.qty, l.rate, l.amount]), ['DIRECT', '', '', '', costData.cost.totals.direct], ['MARKUP', '', '', '', costData.cost.totals.markup], ['VAT', '', '', '', costData.cost.totals.vat], ['TOTAL', '', '', '', costData.cost.totals.total]])) }, [icon('download', 14), t('dw_export_csv')]),
        el('button.btn.btn-sm', { type: 'button', onclick: async () => { try { const rates = readForm(ratesForm); costData = await api.drawingProjectCost(project.id, rates); drawCost(costData.cost); } catch (error) { toastError(error); } } }, [icon('play', 14), t('dw_cost_apply')])]),
      el('div.card-body', {}, [el('div.small.muted', { text: t('dw_cost_hint') }), ratesForm]),
      el('div.card-body.flush', {}, [costHost]),
    ]));
  })();
  return host;
}

function runsTable(runs, project, navigate, reload) {
  return dataTable({
    rows: runs,
    empty: t('dw_no_runs'),
    onRowClick: (row) => navigate(`drawings/${project.id}/run/${row.id}`),
    columns: [
      { label: t('dw_serial'), className: 'num', render: (row) => `#${row.serial}` },
      { label: t('dw_level'), render: (row) => el('span', { text: levelLabel({ code: row.level_code, name: row.level_name, zone: row.level_zone }), dir: 'ltr' }) },
      { label: t('dw_mode'), render: (row) => modeLabel(row.mode) },
      { label: t('dw_revision'), render: (row) => `REV ${row.revision}` },
      { label: t('dw_sheets'), className: 'num', render: (row) => row.sheet_count },
      { label: t('status'), render: (row) => statusBadge(row.status) },
      { label: t('dw_run_notes'), render: (row) => el('span.small', { text: row.notes || '—' }) },
      { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
      { label: t('dw_by'), render: (row) => pick(row, 'created_by_name') || '—' },
      {
        label: t('actions'),
        render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
          row.status !== 'failed' && row.status !== 'running' ? el('a.btn.btn-sm', { href: api.drawingRunZipUrl(row.id), title: t('dw_download_zip') }, [icon('download', 14), 'ZIP']) : null,
          can('drawings.delete') ? el('button.btn-secondary.btn.btn-sm.btn-icon', {
            type: 'button', title: t('delete'),
            onclick: async () => {
              if (!(await confirmDialog(t('dw_delete_run_confirm')))) return;
              try { await api.deleteDrawingRun(row.id); toast(t('deleted'), 'success'); reload(); } catch (error) { toastError(error); }
            },
          }, [icon('trash', 14)]) : null,
        ]),
      },
    ],
  });
}

// ----------------------------------------------------------- punching alert
/**
 * The punching check of a run: a strict red alert while columns block the run, the per-column estimate, and the
 * engineer's decision (thicken / passing in RAM / bypass at own responsibility, with an acknowledgement).
 */
function punchingCard(run, project, navigate) {
  const P = run.punching;
  const blocking = P.blocking || [];
  const warnings = (P.warnings || []).filter((id) => !blocking.includes(id));
  const columns = (P.levels || []).flatMap((lv) => (lv.columns || []).map((c) => ({ ...c, level: lv.level, overridden: (lv.overridden || []).includes(c.id) })));
  const shown = columns.filter((c) => c.status !== 'ok' || c.ram_failed || c.overridden || blocking.includes(c.id));
  const statusOf = (c) => {
    const parts = [];
    if (c.ram_failed) parts.push(t('dw_punch_in_ram'));
    parts.push(t(`dw_punch_${c.status}`));
    if (c.ssr) parts.push(t('dw_punch_ssr'));
    if (c.overridden) parts.push(t('dw_punch_mode_bypass'));
    return parts.join(' · ');
  };
  const decision = P.decision;
  const body = el('div.card-body', {}, [
    blocking.length ? el('div.alert.danger', {}, [el('strong', { text: fill('dw_punch_blocked', { n: blocking.length, cols: blocking.join(', ') }) })]) : null,
    warnings.length ? el('div.alert.warn', { text: fill('dw_punch_warn', { cols: warnings.join(', ') }) }) : null,
    decision ? el('div.small.mt-1', {}, [el('span.badge.blue', { text: fill('dw_punch_decided', { mode: t(`dw_punch_mode_${decision.mode}`), by: decision.by, date: decision.date }) }), decision.note ? el('span.muted', { text: ` ${decision.note}` }) : null]) : null,
    el('div.tiny.muted.mt-1', { text: t('dw_punch_hint') }),
    shown.length ? dataTable({
      rows: shown,
      columns: [
        { label: t('dw_punch_col'), render: (c) => el('span.bold', { text: `${c.id}`, dir: 'ltr' }) },
        { label: t('dw_level'), render: (c) => c.level },
        { label: t('dw_punch_loc'), render: (c) => t(`dw_punch_loc_${c.loc}`) },
        { label: t('dw_punch_trib'), className: 'num', render: (c) => `${c.trib_m2}` },
        { label: t('dw_punch_vu'), className: 'num', render: (c) => `${c.Vu_kn}` },
        { label: t('dw_punch_ratio'), className: 'num', render: (c) => el('span', { class: c.ratio > 1 ? 'text-danger bold' : '', text: `${c.ratio}` }) },
        { label: t('dw_punch_status'), render: (c) => el('span', { class: `badge ${blocking.includes(c.id) ? 'red' : c.status === 'ok' && !c.ram_failed ? 'green' : 'amber'}`, text: statusOf(c) }) },
      ],
    }) : null,
  ]);
  const act = async (mode, extra = {}) => {
    try {
      const res = await api.punchingDecision(run.id, { mode, ...extra });
      toast(mode === 'thicken' ? t('saved') : t('dw_punch_regenerated'), 'success');
      navigate(`drawings/${project.id}/run/${res.run.id}`);
    } catch (error) { toastError(error); }
  };
  const flagged = [...new Set([...blocking, ...warnings])];
  const decide = (mode) => {
    const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
      el('div.alert.warn', { text: t(mode === 'bypass' ? 'dw_punch_bypass_hint' : 'dw_punch_ram_ok_hint') }),
      field({ name: 'columns', label: t('dw_punch_columns'), value: flagged.join(', '), dir: 'ltr', hint: t('dw_punch_all_flagged') }),
      field({ name: 'note', label: t('dw_punch_note'), type: 'textarea', value: '', rows: 2 }),
      el('label.row', { style: { gap: '.5rem', alignItems: 'flex-start' } }, [el('input', { type: 'checkbox', name: 'acknowledge' }), el('span', { text: t('dw_punch_ack') })]),
    ]);
    const { close } = openModal({
      title: t(mode === 'bypass' ? 'dw_punch_bypass' : 'dw_punch_ram_ok'),
      body: form,
      footer: el('div.row', {}, [
        el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
        el('button.btn-danger.btn', {
          type: 'button', text: t(mode === 'bypass' ? 'dw_punch_bypass' : 'dw_punch_ram_ok'),
          onclick: async (e) => {
            const ack = form.querySelector('input[name=acknowledge]').checked;
            if (!ack) { toast(t('dw_punch_ack'), 'error'); return; }
            const data = readForm(form);
            e.currentTarget.disabled = true;
            close();
            await act(mode, { columns: data.columns && data.columns.trim() ? data.columns : 'all', note: data.note || undefined, acknowledge: true });
          },
        }),
      ]),
    });
  };
  const actions = can('drawings.create') && (blocking.length || warnings.length) && run.status !== 'superseded' ? el('div.row.wrap.mt-1', { style: { gap: '.5rem' } }, [
    el('button.btn-secondary.btn', { type: 'button', title: t('dw_punch_thicken_hint'), onclick: () => act('thicken') }, [icon('edit', 14), t('dw_punch_thicken')]),
    el('button.btn.btn-success', { type: 'button', title: t('dw_punch_ram_ok_hint'), onclick: () => decide('ram_ok') }, [icon('check', 14), t('dw_punch_ram_ok')]),
    el('button.btn-danger.btn', { type: 'button', title: t('dw_punch_bypass_hint'), onclick: () => decide('bypass') }, [icon('bell', 14), t('dw_punch_bypass')]),
    decision ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => act('clear') }, [t('dw_punch_clear')]) : null,
  ]) : null;
  if (actions) body.append(actions);
  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: blocking.length ? t('dw_punch_title') : t('dw_punch_status') }), el('div.spacer'), statusBadge(run.status)]),
    body,
  ]);
}

// ------------------------------------------------------------- beam check
/** The office beam design of a run: forces, bars (RAM / office / drawn), the deflection check, and the decision when a beam blocks. */
function beamCheckCard(run, project, navigate) {
  const B = run.beam_check;
  const blocking = B.blocking || [];
  const rows = (B.levels || []).flatMap((lv) => (lv.beams || []).map((b) => ({ ...b, level: lv.level })));
  const schedRows = (run.beams || []).flatMap((lv) => lv.beams || []);
  const sched = (id) => schedRows.find((r) => String(r.id).toUpperCase() === String(id).toUpperCase());
  const decision = B.decision;
  const reasonsOf = (b) => [...(b.ram_failed ? [t('dw_beam_in_ram')] : []), ...(b.reasons || []).map((r) => t(`dw_beam_reason_${r}`))].join(' · ');
  const body = el('div.card-body', {}, [
    blocking.length ? el('div.alert.danger', {}, [el('strong', { text: fill('dw_beam_blocked', { n: blocking.length, beams: blocking.join(', ') }) })]) : null,
    decision ? el('div.small.mt-1', {}, [el('span.badge.blue', { text: fill('dw_punch_decided', { mode: t(`dw_beam_mode_${decision.mode}`), by: decision.by, date: decision.date }) }), decision.note ? el('span.muted', { text: ` ${decision.note}` }) : null]) : null,
    el('div.tiny.muted.mt-1', { text: t('dw_bd_hint') }),
    (B.levels || []).some((lv) => (lv.assumed || []).length) ? el('div.tiny.muted', { text: (B.levels || []).flatMap((lv) => lv.assumed || []).join('; '), dir: 'ltr' }) : null,
    rows.length ? dataTable({
      rows,
      columns: [
        { label: t('dw_beam_list'), render: (b) => el('span.bold', { text: `${b.id} ${b.width}x${b.depth}`, dir: 'ltr' }) },
        { label: t('dw_beam_spans'), render: (b) => el('span', { text: b.spans.map((s) => (s.length / 1000).toFixed(1)).join(' + ') + (b.no_supports ? ' ?' : ''), dir: 'ltr', title: b.no_supports ? t('dw_beam_no_supports') : '' }) },
        { label: t('dw_beam_trib'), className: 'num', render: (b) => (b.trib_mm.total / 1000).toFixed(1) },
        { label: t('dw_beam_wu'), className: 'num', render: (b) => `${b.loads.wu}` },
        { label: t('dw_beam_mneg'), className: 'num', render: (b) => `${b.Mneg_max}` },
        { label: t('dw_beam_mpos'), className: 'num', render: (b) => `${b.Mpos_max}` },
        { label: t('dw_beam_vu'), className: 'num', render: (b) => `${b.Vu}` },
        { label: t('dw_beam_ram_bars'), render: (b) => { const r = sched(b.id); return el('span', { text: r?.ram ? `${r.ram.top?.text || '-'} / ${r.ram.bottom?.text || '-'} / ${r.ram.stirrups?.text || '-'}` : '—', dir: 'ltr' }); } },
        { label: t('dw_beam_office_bars'), render: (b) => el('span', { text: `${b.top?.text || '-'} / ${b.bottom?.text || '-'} / ${b.stirrups?.text || '-'}`, dir: 'ltr' }) },
        { label: t('dw_beam_chosen'), render: (b) => { const r = sched(b.id); return el('span.bold', { text: r ? `${r.mark || '??'}: ${r.top?.text || '-'} / ${r.bottom?.text || '-'} / ${r.stirrups?.text || '-'}` : '—', dir: 'ltr' }); } },
        { label: t('dw_beam_defl'), render: (b) => el('span', { class: b.deflection.ok ? '' : 'text-danger bold', text: b.deflection.table_ok ? t('dw_beam_defl_table') : fill('dw_beam_defl_ratio', { r: b.deflection.ratio }) }) },
        { label: t('dw_beam_status'), render: (b) => el('span', { class: `badge ${blocking.includes(b.id) ? 'red' : b.status === 'ok' ? 'green' : 'amber'}`, text: b.status === 'ok' && !b.ram_failed ? t('dw_beam_ok') : `${t('dw_beam_fail')}: ${reasonsOf(b)}` }) },
      ],
    }) : null,
  ]);
  const act = async (mode, extra = {}) => {
    try {
      const res = await api.beamDecision(run.id, { mode, ...extra });
      toast(mode === 'deepen' ? t('saved') : t('dw_punch_regenerated'), 'success');
      navigate(`drawings/${project.id}/run/${res.run.id}`);
    } catch (error) { toastError(error); }
  };
  const flagged = [...new Set((B.levels || []).flatMap((lv) => lv.failing || []))];
  const decide = (mode) => {
    const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
      el('div.alert.warn', { text: t(mode === 'bypass' ? 'dw_beam_bypass_hint' : 'dw_beam_ram_ok_hint') }),
      field({ name: 'beams', label: t('dw_beam_columns'), value: flagged.join(', '), dir: 'ltr', hint: t('dw_punch_all_flagged') }),
      field({ name: 'note', label: t('dw_punch_note'), type: 'textarea', value: '', rows: 2 }),
      el('label.row', { style: { gap: '.5rem', alignItems: 'flex-start' } }, [el('input', { type: 'checkbox', name: 'acknowledge' }), el('span', { text: t('dw_punch_ack') })]),
    ]);
    const { close } = openModal({
      title: t(mode === 'bypass' ? 'dw_beam_bypass' : 'dw_beam_ram_ok'),
      body: form,
      footer: el('div.row', {}, [
        el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
        el('button.btn-danger.btn', {
          type: 'button', text: t(mode === 'bypass' ? 'dw_beam_bypass' : 'dw_beam_ram_ok'),
          onclick: async (e) => {
            if (!form.querySelector('input[name=acknowledge]').checked) { toast(t('dw_punch_ack'), 'error'); return; }
            const data = readForm(form);
            e.currentTarget.disabled = true; close();
            await act(mode, { beams: data.beams && data.beams.trim() ? data.beams : 'all', note: data.note || undefined, acknowledge: true });
          },
        }),
      ]),
    });
  };
  const actions = can('drawings.create') && blocking.length && run.status !== 'superseded' ? el('div.row.wrap.mt-1', { style: { gap: '.5rem' } }, [
    el('button.btn-secondary.btn', { type: 'button', title: t('dw_beam_deepen_hint'), onclick: () => act('deepen') }, [icon('edit', 14), t('dw_beam_deepen')]),
    el('button.btn.btn-success', { type: 'button', title: t('dw_beam_ram_ok_hint'), onclick: () => decide('ram_ok') }, [icon('check', 14), t('dw_beam_ram_ok')]),
    el('button.btn-danger.btn', { type: 'button', title: t('dw_beam_bypass_hint'), onclick: () => decide('bypass') }, [icon('bell', 14), t('dw_beam_bypass')]),
    decision ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => act('clear') }, [t('dw_punch_clear')]) : null,
  ]) : null;
  if (actions) body.append(actions);
  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: blocking.length ? t('dw_beam_check_title') : t('dw_beam_check') }), el('div.spacer'), el('span.badge.grey', { text: beamDesignLabel(B.design) }), statusBadge(run.status)]),
    body,
  ]);
}

// ---------------------------------------------------------------------- run
async function runPage(projectId, runId, navigate) {
  const page = el('div');
  let data;
  try { data = await api.drawingRun(runId); } catch (error) {
    page.append(el('div.alert.danger', { text: error.localised || error.message }));
    return page;
  }
  const { run, project } = data;
  const level = { code: run.level_code, name: run.level_name, zone: run.level_zone };

  const produced = run.status !== 'failed' && run.status !== 'running';
  page.append(pageHeader(`${project.code} · ${levelLabel(level)} · REV ${run.revision}`, [
    el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate(`drawings/${project.id}`) }, [icon('back', 16), t('back')]),
    produced && can('drawings.create') && run.mode === 'design' ? el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate(`drawings/${project.id}/run/${run.id}/edit`) }, [icon('edit', 16), t('dw_edit_rebar')]) : null,
    produced && can('drawings.create') && run.status !== 'issued' && run.status !== 'blocked' ? el('button.btn-success.btn', {
      type: 'button',
      onclick: async () => {
        if (!(await confirmDialog(t('dw_issue_confirm'), { danger: false }))) return;
        try { await api.updateDrawingRun(run.id, { status: 'issued' }); toast(t('saved'), 'success'); navigate(`drawings/${project.id}/run/${run.id}`); } catch (error) { toastError(error); }
      },
    }, [icon('check', 16), t('dw_issue')]) : null,
    produced ? el('a.btn', { href: api.drawingRunZipUrl(run.id) }, [icon('download', 16), t('dw_download_zip')]) : null,
    produced && can('drawings.create') && run.quantities ? el('button.btn-secondary.btn', {
      type: 'button', title: t('dw_takeoff_hint'),
      onclick: () => {
        // the edited sheet (DXF) comes back: the bars are found by their tags and the take-off moves by the difference
        const input = el('input', { type: 'file', accept: '.dxf' });
        input.onchange = async () => {
          const file = input.files && input.files[0];
          if (!file) return;
          try {
            const res = await api.updateDrawingTakeoff(run.id, file);
            const d = res.takeoff;
            toast(fill('dw_takeoff_updated', { changed: d.changed, bars: d.bars, kg: (d.delta.kg >= 0 ? '+' : '') + d.delta.kg }), 'success');
            navigate(`drawings/${project.id}/run/${run.id}`);
          } catch (error) { toastError(error); }
        };
        input.click();
      },
    }, [icon('upload', 16), t('dw_takeoff_update')]) : null,
    can('drawings.delete') ? el('button.btn-danger.btn', {
      type: 'button',
      onclick: async () => {
        if (!(await confirmDialog(t('dw_delete_run_confirm')))) return;
        try { await api.deleteDrawingRun(run.id); toast(t('deleted'), 'success'); navigate(`drawings/${project.id}`); } catch (error) { toastError(error); }
      },
    }, [icon('trash', 16), t('delete')]) : null,
  ]));

  const kpi = (label, value, cls = '') => el(`div.kpi${cls ? `.${cls}` : ''}`, {}, [el('div.label', { text: label }), el('div.value', { text: value, dir: 'ltr' })]);
  page.append(el('div.kpi-grid', {}, [
    kpi(t('dw_serial'), `#${run.serial}`),
    kpi(t('dw_sheets'), String(run.sheet_count)),
    kpi(t('dw_mode'), modeLabel(run.mode)),
    kpi(t('dw_ram_bands'), bandsLabel(run.ram_bands)),
    kpi(t('dw_mesh'), meshLabel(run.mesh)),
    kpi(t('dw_beam_design'), beamDesignLabel(run.beam_design)),
    kpi(t('dw_rotate'), rotateLabel(run.rotate)),
    kpi(t('dw_designer'), run.created_by_name || '—'),
    kpi(t('dw_duration'), run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'),
    kpi(t('dw_source'), run.source_name || run.source_file || '—'),
  ]));

  if (run.status === 'failed') {
    page.append(el('div.alert.danger', { text: run.error || t('error') }));
  }
  if (run.punching) page.append(punchingCard(run, project, navigate));
  if (run.beam_check) page.append(beamCheckCard(run, project, navigate));
  // revision notes and status
  const notesBox = el('textarea', { rows: 2, placeholder: t('dw_run_notes_hint') });
  notesBox.value = run.notes || '';
  page.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_run_notes') }), el('div.spacer'), statusBadge(run.status)]),
    el('div.card-body', {}, [
      can('drawings.create') ? notesBox : el('div', { text: run.notes || '—' }),
      can('drawings.create') ? el('div.row.mt-1', {}, [
        el('button.btn.btn-sm', { type: 'button', text: t('dw_save_notes'), onclick: async () => { try { await api.updateDrawingRun(run.id, { notes: notesBox.value }); toast(t('saved'), 'success'); } catch (error) { toastError(error); } } }),
        run.edits?.length ? el('span.badge.amber', { text: `${run.edits.length} ${t('dw_edits_list')}` }) : null,
      ]) : null,
    ]),
  ]));

  // beam design through RAM: prepare the strips model, and the types read back on a calculated run
  if (produced && /\.cpt$/i.test(run.source_file || '')) {
    const bsHost = el('div');
    const drawStrips = (info) => {
      clear(bsHost);
      if (info) bsHost.append(el('div.row.wrap', { style: { gap: '.5rem', alignItems: 'center' } }, [
        el('span.badge.green', { text: fill('dw_beams_prepared', { beams: info.beams, spans: info.spans, splitters: info.splitters, removed: Object.values(info.removed || {}).reduce((a, b) => a + b, 0) }) }),
        el('a.btn.btn-sm', { href: api.beamStripsUrl(run.id) }, [icon('download', 14), t('dw_beams_download')]),
      ]));
    };
    drawStrips(run.beam_strips);
    const types = (run.beams || []).flatMap((lv) => (lv.types || []).map((tp) => ({ ...tp, level: lv.level })));
    const undesigned = (run.beams || []).flatMap((lv) => lv.undesigned || []);
    const addedMarks = (run.beams || []).flatMap((lv) => (lv.added || []).map((tp) => tp.mark));
    page.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_beams') }), el('div.spacer'), can('drawings.create') ? el('button.btn.btn-sm', { type: 'button', onclick: async (e) => { e.currentTarget.disabled = true; try { const { beam_strips } = await api.prepareBeamStrips(run.id); drawStrips(beam_strips); toast(t('saved'), 'success'); } catch (error) { toastError(error); } e.currentTarget.disabled = false; } }, [icon('play', 14), t('dw_beams_prepare')]) : null]),
      el('div.card-body', {}, [el('div.small.muted', { text: t('dw_beams_hint') }), bsHost, addedMarks.length ? el('div.mt-1', {}, [el('span.badge.amber', { text: fill('dw_bt_added_on_run', { marks: addedMarks.join(', ') }), dir: 'ltr' })]) : null]),
      types.length ? el('div.card-body.flush', {}, [dataTable({
        rows: types,
        columns: [
          { label: t('dw_beam_type'), render: (r) => el('span.row', { style: { gap: '.3rem', alignItems: 'center' } }, [el('span.bold', { text: `${r.mark}`, dir: 'ltr' }), el('span', { class: `badge ${r.isNew ? 'amber' : 'grey'}`, text: t(r.isNew ? 'dw_bt_new' : 'dw_bt_existing') })]) },
          { label: t('dw_level'), render: (r) => r.level },
          { label: t('dw_beam_section'), render: (r) => el('span', { text: `${r.width} x ${r.depth}`, dir: 'ltr' }) },
          { label: t('dw_beam_top'), render: (r) => r.top?.text || '—' },
          { label: t('dw_beam_bottom'), render: (r) => r.bottom?.text || '—' },
          { label: t('dw_beam_stirrups'), render: (r) => (r.stirrups ? `T${r.stirrups.dia}-${r.stirrups.legs}L @ ${r.stirrups.spacing}` : '—') },
          { label: t('dw_beam_count'), className: 'num', render: (r) => r.count },
          { label: t('dw_beam_list'), render: (r) => el('span.small', { text: r.beams.join(', '), dir: 'ltr' }) },
        ],
      })]) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_beams_none') })]),
      undesigned.length ? el('div.card-body', {}, [el('div.small', { text: `${t('dw_beams_undesigned')}: ${undesigned.join(', ')}`, dir: 'ltr' })]) : null,
    ]));
  }

  const previewHost = el('div');
  const showPreview = (sheet) => {
    clear(previewHost).append(el('div.card', {}, [
      el('div.card-header', {}, [
        el('h3', { text: `${sheet.no} — ${sheet.title}`, dir: 'ltr' }),
        el('div.spacer'),
        el('a.btn-secondary.btn.btn-sm', { href: api.drawingRunFileUrl(run.id, 'preview', `${sheet.file}.svg`), target: '_blank', rel: 'noopener' }, [icon('chevron', 14), t('open')]),
        el('a.btn.btn-sm', { href: api.drawingRunFileUrl(run.id, 'dxf', `${sheet.file}.dxf`, true) }, [icon('download', 14), t('dw_download_dxf')]),
      ]),
      el('div.card-body.tight', {}, [
        el('img', { src: api.drawingRunFileUrl(run.id, 'preview', `${sheet.file}.svg`), alt: sheet.no, style: { width: '100%', height: 'auto', display: 'block', background: '#fff' } }),
      ]),
    ]));
    previewHost.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  page.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_sheets') })]),
    el('div.card-body.flush', {}, [dataTable({
      rows: run.sheets,
      onRowClick: showPreview,
      columns: [
        { label: t('dw_sheet_no'), render: (row) => el('span.bold', { text: row.no, dir: 'ltr' }) },
        { label: t('dw_sheet_title'), render: (row) => el('span', { text: row.title, dir: 'ltr' }) },
        { label: t('dw_level'), render: (row) => el('span', { text: row.level === 'ALL' ? 'ALL' : `${row.level} - ${row.level_name || ''}`, dir: 'ltr' }) },
        { label: t('dw_scale'), render: (row) => (row.scale ? `1:${row.scale}` : 'NTS') },
        { label: t('dw_weight'), className: 'num', render: (row) => (row.weight ? row.weight.toLocaleString('en-US') : '—') },
        {
          label: t('actions'),
          render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
            el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => showPreview(row) }, [icon('search', 14), t('dw_preview')]),
            el('a.btn.btn-sm', { href: api.drawingRunFileUrl(run.id, 'dxf', `${row.file}.dxf`, true) }, [icon('download', 14), t('dw_download_dxf')]),
          ]),
        },
      ],
    })]),
  ]));
  page.append(previewHost);

  const list = (title, items) => (items && items.length ? el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: `${title} (${items.length})` })]),
    el('div.card-body', {}, [el('ul.small', { style: { margin: 0, paddingInlineStart: '1.2rem' }, dir: 'ltr' }, items.map((text) => el('li', { text })))]),
  ]) : null);
  page.append(list(t('dw_assumptions'), run.assumptions));
  page.append(list(t('dw_findings'), run.findings));

  if (run.report_md) {
    const pre = el('pre.small', { text: run.report_md, dir: 'ltr', style: { whiteSpace: 'pre-wrap', margin: 0, maxHeight: '420px', overflow: 'auto' } });
    page.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_report') })]),
      el('div.card-body', {}, [pre]),
    ]));
  }
  return page;
}
