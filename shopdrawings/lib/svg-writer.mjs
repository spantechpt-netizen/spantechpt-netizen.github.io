/**
 * Renders a Canvas as an SVG so a sheet can be previewed in a browser (or in
 * this repository) without AutoCAD. Blocks are expanded inline.
 */
import { encodeText } from './dxf-writer.mjs';
void encodeText;

const ACI = { 1: '#ff2b2b', 2: '#e6c700', 3: '#22b14c', 4: '#1ec8d8', 5: '#3a6cff', 6: '#e13cd6', 7: '#1c1c1c', 8: '#8a8a8a', 9: '#c0c0c0', 30: '#ff8c1a', 40: '#ffbf00', 256: '#1c1c1c' };
const color = (i) => ACI[i] || '#1c1c1c';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const DASH = { DASHED: '12,6', HIDDEN: '6,3', CENTER: '30,6,6,6', DASHDOT: '12,6,1,6', PHANTOM: '30,6,6,6,6,6' };

export function toSvg(root, opts = {}) {
  const b = root.bbox();
  if (!b) return '<svg xmlns="http://www.w3.org/2000/svg"/>';
  const pad = opts.pad ?? Math.max(b.w, b.h) * 0.01;
  const minX = b.minX - pad, minY = b.minY - pad, W = b.w + 2 * pad, Hh = b.h + 2 * pad;
  const pxW = opts.width || 1600;
  const pxH = Math.round((pxW * Hh) / W);
  const unit = W / pxW; // drawing units per pixel
  const out = [];
  const layers = root.layers;
  const strokeFor = (e) => {
    const L = layers.get(e.layer) || { color: 7 };
    const c = e.color != null ? e.color : L.color;
    const lw = e.lw != null ? e.lw : (L.lw ?? 0);
    const dashType = e.ltype || L.ltype;
    const width = Math.max(unit * 0.9, (lw / 100) * (opts.lwScale || 1) * unit * 2.2);
    let s = `stroke="${color(c)}" stroke-width="${width.toFixed(3)}" fill="none" stroke-linecap="round" stroke-linejoin="round"`;
    if (DASH[dashType]) s += ` stroke-dasharray="${DASH[dashType].split(',').map((v) => (parseFloat(v) * unit * 2.5).toFixed(2)).join(',')}"`;
    return { s, c: color(c), width };
  };
  const Y = (y) => -y;
  const tx = (x, y, t) => {
    const r = ((t.rot || 0) * Math.PI) / 180;
    const px = x * (t.sx || 1), py = y * (t.sy || 1);
    return { x: (t.x || 0) + px * Math.cos(r) - py * Math.sin(r), y: (t.y || 0) + px * Math.sin(r) + py * Math.cos(r) };
  };
  let patternN = 0;
  const defs = [];

  const render = (canvas, t) => {
    for (const e of canvas.entities) {
      const st = strokeFor(e);
      switch (e.t) {
        case 'line': {
          const a = tx(e.x1, e.y1, t), c = tx(e.x2, e.y2, t);
          out.push(`<line x1="${a.x}" y1="${Y(a.y)}" x2="${c.x}" y2="${Y(c.y)}" ${st.s}/>`);
          break;
        }
        case 'pline': {
          const pts = e.pts.map((p) => tx(p.x, p.y, t));
          const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${Y(p.y)}`).join(' ') + (e.closed ? ' Z' : '');
          out.push(`<path d="${d}" ${st.s}/>`);
          break;
        }
        case 'circle': {
          const c = tx(e.cx, e.cy, t);
          out.push(`<circle cx="${c.x}" cy="${Y(c.y)}" r="${e.r * (t.sx || 1)}" ${st.s}/>`);
          break;
        }
        case 'arc': {
          const c = tx(e.cx, e.cy, t);
          const r = e.r * (t.sx || 1);
          const a1 = ((e.a1 + (t.rot || 0)) * Math.PI) / 180, a2 = ((e.a2 + (t.rot || 0)) * Math.PI) / 180;
          const p1 = { x: c.x + r * Math.cos(a1), y: c.y + r * Math.sin(a1) };
          const p2 = { x: c.x + r * Math.cos(a2), y: c.y + r * Math.sin(a2) };
          let sweep = e.a2 - e.a1; while (sweep < 0) sweep += 360;
          out.push(`<path d="M${p1.x} ${Y(p1.y)} A${r} ${r} 0 ${sweep > 180 ? 1 : 0} 0 ${p2.x} ${Y(p2.y)}" ${st.s}/>`);
          break;
        }
        case 'solid': {
          const pts = e.pts.map((p) => tx(p.x, p.y, t));
          out.push(`<polygon points="${pts.map((p) => `${p.x},${Y(p.y)}`).join(' ')}" fill="${st.c}" stroke="none"/>`);
          break;
        }
        case 'hatch': {
          const d = e.polys.map((poly) => poly.map((p, i) => { const q = tx(p.x, p.y, t); return `${i ? 'L' : 'M'}${q.x} ${Y(q.y)}`; }).join(' ') + ' Z').join(' ');
          let fill;
          if (e.pattern === 'SOLID') fill = st.c;
          else {
            const id = `hp${patternN++}`;
            const sp = 3.175 * (e.scale || 1) * (t.sx || 1);
            const angle = (e.pattern === 'DOTS' ? 0 : 45) + (e.angle || 0);
            const double = e.pattern === 'ANSI37';
            defs.push(`<pattern id="${id}" patternUnits="userSpaceOnUse" width="${sp}" height="${sp}" patternTransform="rotate(${-angle})"><line x1="0" y1="0" x2="0" y2="${sp}" stroke="${st.c}" stroke-width="${(unit * 0.9).toFixed(3)}"/>${double ? `<line x1="0" y1="0" x2="${sp}" y2="0" stroke="${st.c}" stroke-width="${(unit * 0.9).toFixed(3)}"/>` : ''}</pattern>`);
            fill = `url(#${id})`;
          }
          out.push(`<path d="${d}" fill="${fill}" fill-rule="evenodd" stroke="none" opacity="${e.pattern === 'SOLID' ? 1 : 0.9}"/>`);
          break;
        }
        case 'text': {
          const p = tx(e.x, e.y, t);
          const h = e.h * (t.sx || 1);
          const anchor = { L: 'start', C: 'middle', R: 'end' }[e.align] || 'start';
          const base = { B: 'auto', M: 'central', T: 'hanging' }[e.valign] || 'auto';
          const rot = -((e.rot || 0) + (t.rot || 0));
          const L = layers.get(e.layer) || { color: 7 };
          const c = color(e.color != null ? e.color : L.color);
          out.push(`<text x="${p.x}" y="${Y(p.y)}" font-size="${(h * 1.38).toFixed(3)}" font-family="Arial, Helvetica, sans-serif" text-anchor="${anchor}" dominant-baseline="${base}" fill="${c}" transform="rotate(${rot} ${p.x} ${Y(p.y)})"${e.bold ? ' font-weight="bold"' : ''}>${esc(e.str)}</text>`);
          break;
        }
        case 'mtext': {
          const p = tx(e.x, e.y, t);
          const h = e.h * (t.sx || 1);
          const L = layers.get(e.layer) || { color: 7 };
          const c = color(e.color != null ? e.color : L.color);
          const lines = wrap(e.str, e.width ? Math.floor(e.width / (h * 0.78)) : 0);
          const lh = h * 1.55 * (e.lineSpacing || 1);
          lines.forEach((ln, i) => {
            out.push(`<text x="${p.x}" y="${Y(p.y - h - i * lh)}" font-size="${(h * 1.38).toFixed(3)}" font-family="Arial, Helvetica, sans-serif" fill="${c}"${e.bold ? ' font-weight="bold"' : ''}>${esc(ln)}</text>`);
          });
          break;
        }
        case 'insert': {
          const blk = root.blocks.get(e.name);
          if (!blk) break;
          const o = tx(e.x, e.y, t);
          render(blk, { x: o.x, y: o.y, sx: (t.sx || 1) * (e.sx || 1), sy: (t.sy || 1) * (e.sy || e.sx || 1), rot: (t.rot || 0) + (e.rot || 0) });
          break;
        }
        default: break;
      }
    }
  };
  render(root, { x: 0, y: 0, sx: 1, sy: 1, rot: 0 });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${pxW}" height="${pxH}" viewBox="${minX} ${-(minY + Hh)} ${W} ${Hh}">` +
    `<defs>${defs.join('')}</defs><rect x="${minX}" y="${-(minY + Hh)}" width="${W}" height="${Hh}" fill="#ffffff"/>${out.join('\n')}</svg>`;
}

export function wrap(str, maxChars) {
  const paras = String(str).split(/\r?\n/);
  if (!maxChars || maxChars < 8) return paras;
  const lines = [];
  for (const p of paras) {
    const words = p.split(/\s+/);
    let cur = '';
    for (const w of words) {
      if ((cur + ' ' + w).trim().length > maxChars && cur) { lines.push(cur); cur = w; }
      else cur = (cur ? cur + ' ' : '') + w;
    }
    lines.push(cur);
  }
  return lines;
}
