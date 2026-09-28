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

const MODES = ['design', 'shop'];
const BANDS = ['all', 'user', 'none'];
const filters = { q: '' };

export async function render({ params, navigate }) {
  const [projectId, sub, runId] = params;
  if (projectId && sub === 'run' && runId) return runPage(projectId, runId, navigate);
  if (projectId) return projectPage(projectId, navigate);
  return listPage(navigate);
}

// ------------------------------------------------------------------ helpers
const modeLabel = (mode) => t(mode === 'shop' ? 'dw_mode_shop' : 'dw_mode_design');
const bandsLabel = (bands) => t(`dw_bands_${bands || 'all'}`);
const statusBadge = (status) => el('span', {
  class: `badge ${status === 'done' ? 'green' : status === 'failed' ? 'red' : 'amber'}`,
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

// ----------------------------------------------------------- generate form
function openGenerateForm(project, levels, settings, preselected, navigate) {
  const fileInput = el('input', { type: 'file', name: 'file', accept: '.cpt,.dxf', required: true });
  const status = el('div.small.muted.mt-1');
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    field({
      name: 'level_id', label: t('dw_level'), type: 'select', value: preselected?.id || levels[0]?.id,
      options: levels.map((l) => ({ value: l.id, label: levelLabel(l) })),
    }),
    el('div.grid.grid-2', {}, [
      field({
        name: 'mode', label: t('dw_mode'), type: 'select', value: project.default_mode || settings.default_mode || 'design',
        options: MODES.map((m) => ({ value: m, label: modeLabel(m) })),
      }),
      field({
        name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: project.ram_bands || settings.ram_bands || 'all',
        options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })),
      }),
    ]),
    field({ name: 'revision', label: t('dw_revision'), value: '', dir: 'ltr', hint: t('dw_revision_hint') }),
    el('div.field', {}, [el('label', { text: t('dw_file') }), fileInput]),
    el('div.tiny.muted', { text: `${t('dw_numbering')}: ${exampleNo(settings, project, preselected || levels[0])}`, dir: 'ltr' }),
    status,
  ]);

  const { close } = openModal({
    title: `${t('dw_generate')} — ${project.code}`,
    body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', {
        type: 'button',
        onclick: async (event) => {
          const button = event.currentTarget;
          const data = readForm(form);
          const file = fileInput.files?.[0];
          if (!file) { fileInput.focus(); return; }
          button.disabled = true;
          status.textContent = t('dw_generating');
          try {
            const { run } = await api.generateDrawings(data.level_id, file, {
              mode: data.mode, ram_bands: data.ram_bands, revision: data.revision || undefined,
            });
            toast(t('dw_generated'), 'success');
            close();
            navigate(`drawings/${project.id}/run/${run.id}`);
          } catch (error) {
            toastError(error);
            status.textContent = error.localised || error.message;
            button.disabled = false;
          }
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
          item(t('dw_numbering'), exampleNo(settings, project, levels[0]), 'ltr'),
        ]),
        project.notes ? el('div.small.muted.mt-1', { text: project.notes }) : null,
      ]),
    ]));

    // levels
    const levelsCard = el('div.card', {}, [
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
            {
              label: t('actions'),
              render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
                can('drawings.create') ? el('button.btn.btn-sm', { type: 'button', title: t('dw_generate'), onclick: () => openGenerateForm(project, levels, settings, row, navigate) }, [icon('play', 14), t('dw_generate_for')]) : null,
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
    ]);
    body.append(levelsCard);

    // runs
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_runs') })]),
      el('div.card-body.flush', {}, [runsTable(runs, project, navigate, load)]),
    ]));
  }

  await load();
  return page;
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
      { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
      { label: t('dw_by'), render: (row) => pick(row, 'created_by_name') || '—' },
      {
        label: t('actions'),
        render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
          row.status === 'done' ? el('a.btn.btn-sm', { href: api.drawingRunZipUrl(row.id), title: t('dw_download_zip') }, [icon('download', 14), 'ZIP']) : null,
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

  page.append(pageHeader(`${project.code} · ${levelLabel(level)} · REV ${run.revision}`, [
    el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate(`drawings/${project.id}`) }, [icon('back', 16), t('back')]),
    run.status === 'done' ? el('a.btn', { href: api.drawingRunZipUrl(run.id) }, [icon('download', 16), t('dw_download_zip')]) : null,
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
    kpi(t('dw_duration'), run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'),
    kpi(t('dw_source'), run.source_name || run.source_file || '—'),
  ]));

  if (run.status === 'failed') {
    page.append(el('div.alert.danger', { text: run.error || t('error') }));
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
