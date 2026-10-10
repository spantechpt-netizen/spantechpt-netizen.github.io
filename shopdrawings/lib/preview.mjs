/**
 * Turns a parsed drawing (from parseDxf or fromLibredwgJson) into a Canvas so
 * it can be previewed as SVG with the same renderer as the generated sheets.
 */
import { Canvas } from './canvas.mjs';

export function drawingToCanvas(model, { space = 'model', layers } = {}) {
  const c = new Canvas();
  if (model.layers) for (const [n, d] of model.layers) c.layer(n, { color: d.color, ltype: (d.ltype || 'CONTINUOUS').toUpperCase(), lw: d.lw && d.lw < 29 ? d.lw : undefined });
  const addTo = (target, e) => {
    if (layers && !layers.has(e.layer)) return;
    const o = { layer: e.layer };
    if (e.color != null && e.color !== 256 && e.color !== 0) o.color = e.color;
    switch (e.type) {
      case 'LINE': target.line(e.x, e.y, e.x2, e.y2, o); break;
      case 'LWPOLYLINE': if (e.pts?.length > 1) target.pline(e.pts, { ...o, closed: e.closed }); break;
      case 'CIRCLE': target.circle(e.x, e.y, e.r, o); break;
      case 'ARC': target.arc(e.x, e.y, e.r, e.a1, e.a2, o); break;
      case 'SOLID': if (e.pts?.length >= 3) target.solid(e.pts.length === 3 ? [...e.pts, e.pts[2]] : e.pts, o); break;
      case 'TEXT': {
        const align = { 0: 'L', 1: 'C', 2: 'R', 3: 'L', 4: 'C', 5: 'L' }[e.halign] || 'L';
        const valign = { 0: 'B', 1: 'B', 2: 'M', 3: 'T' }[e.valign] || 'B';
        target.text(e.x, e.y, e.text || '', { ...o, h: e.height || 2.5, rot: e.rotation || 0, align: e.halign === 4 || e.halign === 3 || e.halign === 5 ? 'C' : align, valign: e.halign === 4 || e.halign === 3 || e.halign === 5 ? 'M' : valign });
        break;
      }
      case 'MTEXT': {
        // attachment 1-3 top, 4-6 middle, 7-9 bottom; shift so the top-left pen matches
        const h = e.height || 2.5;
        const lines = (e.text || '').split('\n').length;
        let y = e.y;
        const att = e.attachment || 1;
        if (att >= 4 && att <= 6) y += (lines * h * 1.55) / 2;
        else if (att >= 7) y += lines * h * 1.55;
        let x = e.x;
        if (att % 3 === 2 && e.width) x -= e.width / 2;
        else if (att % 3 === 0 && e.width) x -= e.width;
        target.mtext(x, y, e.text || '', { ...o, h, width: e.width || 0, rot: e.rotation || 0 });
        break;
      }
      case 'HATCH': if (e.paths?.length) target.hatch(e.paths.filter((p) => p.length >= 3), { ...o, pattern: e.solid || e.pattern === 'SOLID' ? 'SOLID' : 'ANSI31', scale: 30 }); break;
      case 'INSERT': if (e.name && model.blocks.has(e.name)) { target.insert(e.name, e.x, e.y, { ...o, sx: e.sx ?? 1, sy: e.sy ?? e.sx ?? 1, rot: e.rotation || 0 }); for (const a of e.attribs || []) addTo(target, a); } break;
      default: break;
    }
  };
  for (const [name, blk] of model.blocks) {
    if (name === '*Model_Space' || name.startsWith('*Paper_Space')) continue;
    const b = c.block(name);
    const bx = blk.base?.x || 0, by = blk.base?.y || 0;
    for (const e of blk.entities) addTo(b, shift(e, -bx, -by));
  }
  const ents = space === 'paper' ? model.paperspace || [] : model.entities;
  for (const e of ents) addTo(c, e);
  return c;
}

function shift(e, dx, dy) {
  if (!dx && !dy) return e;
  const s = { ...e };
  if (e.x != null) { s.x = e.x + dx; s.y = e.y + dy; }
  if (e.x2 != null) { s.x2 = e.x2 + dx; s.y2 = e.y2 + dy; }
  if (e.pts) s.pts = e.pts.map((p) => ({ ...p, x: p.x + dx, y: p.y + dy }));
  if (e.paths) s.paths = e.paths.map((path) => path.map((p) => ({ ...p, x: p.x + dx, y: p.y + dy })));
  return s;
}
