/**
 * Minimal SVG charting — no external library, so the CRM works on an
 * intranet server with no internet access.
 */
import { isRTL, moneyShort } from './i18n.js';

const NS = 'http://www.w3.org/2000/svg';

export const PALETTE = ['#1a56a7', '#2670c9', '#3d8bdd', '#7fb2e8', '#c9761a', '#14683f', '#a32020', '#6b7280'];

const svgEl = (tag, attrs = {}, text) => {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * Horizontal bar chart — reads naturally in both RTL and LTR because
 * the label column simply swaps sides.
 */
export function barChart({ data, height = 26, format = moneyShort, colour }) {
  const rows = (data || []).filter((row) => row.value !== undefined);
  if (!rows.length) return emptyChart();

  const max = Math.max(...rows.map((row) => Math.abs(Number(row.value) || 0)), 1);
  const wrap = document.createElement('div');

  rows.forEach((row, index) => {
    const pct = (Math.abs(Number(row.value) || 0) / max) * 100;
    const bar = document.createElement('div');
    bar.className = 'funnel-row';
    bar.innerHTML = `
      <div class="label" title="${escapeAttr(row.label)}">${escapeHtml(row.label)}</div>
      <div class="track"><div class="fill" style="width:${pct.toFixed(1)}%;background:${colour || PALETTE[index % PALETTE.length]}"></div></div>
      <div class="pct">${escapeHtml(format(row.value))}</div>`;
    bar.style.setProperty('--h', `${height}px`);
    wrap.append(bar);
  });
  return wrap;
}

/** Conversion funnel with drop-off percentages. */
export function funnelChart(stages) {
  const rows = stages.filter((stage) => stage.value !== undefined);
  if (!rows.length || !rows[0].value) return emptyChart();

  const top = Math.max(Number(rows[0].value) || 1, 1);
  const wrap = document.createElement('div');

  rows.forEach((stage, index) => {
    const value = Number(stage.value) || 0;
    const pct = (value / top) * 100;
    const row = document.createElement('div');
    row.className = 'funnel-row';
    row.innerHTML = `
      <div class="label">${escapeHtml(stage.label)}</div>
      <div class="track">
        <div class="fill" style="width:${Math.max(pct, 3).toFixed(1)}%;background:${PALETTE[Math.min(index, PALETTE.length - 1)]}">
          ${value}
        </div>
      </div>
      <div class="pct">${pct.toFixed(0)}%</div>`;
    wrap.append(row);
  });
  return wrap;
}

/**
 * Grouped column chart for monthly trends.
 * series: [{ name, colour, points: [{ x, y }] }]
 */
export function columnChart({ series, height = 220, format = moneyShort }) {
  const labels = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort();
  if (!labels.length) return emptyChart();

  const width = Math.max(labels.length * 64 + 60, 420);
  const padding = { top: 16, right: 14, bottom: 30, left: 52 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  const max = Math.max(
    ...series.flatMap((s) => s.points.map((p) => Number(p.y) || 0)),
    1,
  );
  const niceMax = niceCeiling(max);

  const svg = svgEl('svg', {
    class: 'chart', viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'xMidYMid meet', height,
  });

  // horizontal grid + y-axis labels
  for (let step = 0; step <= 4; step += 1) {
    const value = (niceMax / 4) * step;
    const y = padding.top + plotH - (plotH / 4) * step;
    svg.append(svgEl('line', {
      class: 'grid-line', x1: padding.left, x2: width - padding.right, y1: y, y2: y,
    }));
    svg.append(svgEl('text', {
      x: padding.left - 6, y: y + 3, 'text-anchor': 'end', 'font-size': 10,
    }, format(value)));
  }

  const groupW = plotW / labels.length;
  const barW = Math.min((groupW - 8) / series.length, 22);

  labels.forEach((label, index) => {
    const groupX = padding.left + index * groupW;
    series.forEach((line, lineIndex) => {
      const point = line.points.find((p) => p.x === label);
      const value = Number(point?.y) || 0;
      const barH = (value / niceMax) * plotH;
      const x = groupX + (groupW - barW * series.length) / 2 + lineIndex * barW;
      const rect = svgEl('rect', {
        class: 'bar', x, y: padding.top + plotH - barH,
        width: Math.max(barW - 2, 2), height: Math.max(barH, 0),
        fill: line.colour || PALETTE[lineIndex % PALETTE.length], rx: 2,
      });
      rect.append(svgEl('title', {}, `${line.name} · ${label}: ${format(value)}`));
      svg.append(rect);
    });

    svg.append(svgEl('text', {
      x: groupX + groupW / 2, y: height - 10,
      'text-anchor': 'middle', 'font-size': 9.5,
    }, String(label).slice(2)));
  });

  svg.append(svgEl('line', {
    class: 'axis-line',
    x1: padding.left, x2: width - padding.right,
    y1: padding.top + plotH, y2: padding.top + plotH,
  }));

  const wrap = document.createElement('div');
  wrap.style.overflowX = 'auto';
  wrap.style.direction = 'ltr'; // charts always read left-to-right on the time axis
  wrap.append(svg);

  const legend = document.createElement('div');
  legend.className = 'chart-legend';
  legend.style.direction = isRTL() ? 'rtl' : 'ltr';
  legend.innerHTML = series.map((line, index) =>
    `<span class="key"><span class="swatch" style="background:${line.colour || PALETTE[index % PALETTE.length]}"></span>${escapeHtml(line.name)}</span>`).join('');
  wrap.append(legend);
  return wrap;
}

/** Donut chart for share-of-total breakdowns. */
export function donutChart({ data, size = 170, format = (v) => v }) {
  const rows = (data || []).filter((row) => Number(row.value) > 0);
  if (!rows.length) return emptyChart();

  const total = rows.reduce((sum, row) => sum + Number(row.value), 0);
  const radius = size / 2;
  const thickness = size * 0.22;
  const svg = svgEl('svg', { class: 'chart', viewBox: `0 0 ${size} ${size}`, width: size, height: size });

  let angle = -Math.PI / 2;
  rows.forEach((row, index) => {
    const slice = (Number(row.value) / total) * Math.PI * 2;
    const path = svgEl('path', {
      d: arcPath(radius, radius, radius - thickness, radius - 2, angle, angle + slice),
      fill: PALETTE[index % PALETTE.length],
    });
    path.append(svgEl('title', {}, `${row.label}: ${format(row.value)} (${((row.value / total) * 100).toFixed(0)}%)`));
    svg.append(path);
    angle += slice;
  });

  svg.append(svgEl('text', {
    x: radius, y: radius - 2, 'text-anchor': 'middle', 'font-size': 15, 'font-weight': 700, fill: 'currentColor',
  }, format(total)));

  const wrap = document.createElement('div');
  wrap.style.display = 'flex';
  wrap.style.alignItems = 'center';
  wrap.style.gap = '1rem';
  wrap.style.flexWrap = 'wrap';
  wrap.append(svg);

  const legend = document.createElement('div');
  legend.className = 'chart-legend';
  legend.style.flexDirection = 'column';
  legend.style.gap = '.3rem';
  legend.innerHTML = rows.map((row, index) =>
    `<span class="key"><span class="swatch" style="background:${PALETTE[index % PALETTE.length]}"></span>${escapeHtml(row.label)} — <b>${escapeHtml(format(row.value))}</b></span>`).join('');
  wrap.append(legend);
  return wrap;
}

function arcPath(cx, cy, innerR, outerR, start, end) {
  const large = end - start > Math.PI ? 1 : 0;
  const p = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x1, y1] = p(outerR, start);
  const [x2, y2] = p(outerR, end);
  const [x3, y3] = p(innerR, end);
  const [x4, y4] = p(innerR, start);
  return `M ${x1} ${y1} A ${outerR} ${outerR} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerR} ${innerR} 0 ${large} 0 ${x4} ${y4} Z`;
}

/** Rounds an axis maximum up to a readable 1/2/5 × 10ⁿ step. */
function niceCeiling(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalised = value / magnitude;
  const step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return step * magnitude;
}

function emptyChart() {
  const node = document.createElement('div');
  node.className = 'empty';
  node.style.padding = '1.6rem';
  node.textContent = '—';
  return node;
}

const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escapeAttr = (value) => escapeHtml(value).replace(/"/g, '&quot;');
