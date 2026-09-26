/**
 * A tiny drawing model shared by the DXF writer and the SVG preview.
 *
 * A Canvas is a list of entities on named layers plus a registry of blocks
 * (which are canvases themselves). Sheets are composed as blocks, so every
 * sheet can be inserted, exploded or attached as an Xref inside AutoCAD.
 */

/** ACI colour index and linetype per standard layer. */
export const STANDARD_LAYERS = {
  0: { color: 7, ltype: 'CONTINUOUS' },
  FRAME: { color: 7, ltype: 'CONTINUOUS', lw: 50 },
  TITLE: { color: 7, ltype: 'CONTINUOUS', lw: 25 },
  TEXT: { color: 7, ltype: 'CONTINUOUS' },
  'TEXT-TITLE': { color: 2, ltype: 'CONTINUOUS' },
  NOTES: { color: 7, ltype: 'CONTINUOUS' },
  GRID: { color: 8, ltype: 'CENTER' },
  'GRID-BUBBLE': { color: 8, ltype: 'CONTINUOUS' },
  OUTLINE: { color: 4, ltype: 'CONTINUOUS', lw: 35 },
  COLUMN: { color: 5, ltype: 'CONTINUOUS', lw: 35 },
  'COLUMN-HATCH': { color: 8, ltype: 'CONTINUOUS' },
  OPENING: { color: 6, ltype: 'CONTINUOUS' },
  'OPENING-HATCH': { color: 6, ltype: 'CONTINUOUS' },
  VOID: { color: 30, ltype: 'DASHED' },
  'VOID-HATCH': { color: 30, ltype: 'CONTINUOUS' },
  'PT-ZONE': { color: 4, ltype: 'DASHDOT' },
  'PT-TENDON': { color: 3, ltype: 'CONTINUOUS' },
  'PT-HATCH': { color: 4, ltype: 'CONTINUOUS' },
  'REBAR-BOT': { color: 1, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-TOP': { color: 5, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-U': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-TRIM': { color: 2, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-EXTENT': { color: 1, ltype: 'CONTINUOUS' },
  'REBAR-TEXT': { color: 7, ltype: 'CONTINUOUS' },
  'REBAR-MESH': { color: 4, ltype: 'CONTINUOUS' },
  'REBAR-PUNCH': { color: 6, ltype: 'CONTINUOUS', lw: 35 },
  'REBAR-RED': { color: 1, ltype: 'CONTINUOUS' },
  'REBAR': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-B1': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-B2': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-T1': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  'REBAR-T2': { color: 6, ltype: 'CONTINUOUS', lw: 50 },
  STAIR: { color: 8, ltype: 'CONTINUOUS' },
  BEAM: { color: 3, ltype: 'CONTINUOUS', lw: 25 },
  SUNKEN: { color: 4, ltype: 'CONTINUOUS' },
  'SUNKEN-HATCH': { color: 8, ltype: 'CONTINUOUS' },
  CALLOUT: { color: 3, ltype: 'CONTINUOUS' },
  DIM: { color: 8, ltype: 'CONTINUOUS' },
  DETAIL: { color: 7, ltype: 'CONTINUOUS' },
  'DETAIL-HATCH': { color: 8, ltype: 'CONTINUOUS' },
  SCHEDULE: { color: 7, ltype: 'CONTINUOUS' },
  'SCHEDULE-TEXT': { color: 7, ltype: 'CONTINUOUS' },
  HATCH: { color: 8, ltype: 'CONTINUOUS' },
  CABLE: { color: 3, ltype: 'CONTINUOUS', lw: 50 },
  'CABLE-TEXT': { color: 3, ltype: 'CONTINUOUS' },
  XREF: { color: 7, ltype: 'CONTINUOUS' },
};

export const LINETYPES = {
  CONTINUOUS: { desc: 'Solid line', pattern: [] },
  DASHED: { desc: 'Dashed __ __ __', pattern: [12.7, -6.35] },
  HIDDEN: { desc: 'Hidden __ __ __', pattern: [6.35, -3.175] },
  CENTER: { desc: 'Center ____ _ ____ _', pattern: [31.75, -6.35, 6.35, -6.35] },
  DASHDOT: { desc: 'Dash dot __ . __ . __', pattern: [12.7, -6.35, 0, -6.35] },
  PHANTOM: { desc: 'Phantom ____ _ _ ____', pattern: [31.75, -6.35, 6.35, -6.35, 6.35, -6.35] },
};

export class Canvas {
  constructor(name = '*Model_Space', root = null) {
    this.name = name;
    this.entities = [];
    this.root = root || this;
    if (!root) {
      this.blocks = new Map();
      this.layers = new Map(Object.entries(STANDARD_LAYERS).map(([k, v]) => [k, { ...v }]));
      this.textStyle = { name: 'STANDARD', font: 'arial.ttf' };
      this.textStyles = new Map([['STANDARD', { font: 'arial.ttf' }]]);
    }
  }

  /** Register a text style (DXF STYLE table entry) usable as `style` on text entities. */
  textStyleDef(name, def) { this.root.textStyles.set(name, def); return name; }

  /**
   * Apply a layer standard: rename every layer (in the table, in entities and
   * in blocks) and take colour / linetype / lineweight from the standard.
   * `map` is { internalName: { name, color?, ltype?, lw? } }.
   */
  applyLayerStandard(map) {
    const root = this.root;
    const rename = (canvas) => { for (const e of canvas.entities) if (map[e.layer]) e.layer = map[e.layer].name; };
    rename(root);
    for (const blk of root.blocks.values()) rename(blk);
    const next = new Map();
    for (const [name, def] of root.layers) {
      const m = map[name];
      if (!m) { next.set(name, def); continue; }
      const merged = { ...def, ...(m.color != null ? { color: m.color } : {}), ...(m.ltype ? { ltype: m.ltype } : {}), ...(m.lw != null ? { lw: m.lw } : {}) };
      next.set(m.name, next.has(m.name) ? { ...next.get(m.name), ...merged } : merged);
    }
    root.layers = next;
    return this;
  }

  layer(name, def) {
    if (def) this.root.layers.set(name, { color: 7, ltype: 'CONTINUOUS', ...def });
    else if (!this.root.layers.has(name)) this.root.layers.set(name, { color: 7, ltype: 'CONTINUOUS' });
    return name;
  }

  /** Create (or fetch) a block definition. */
  block(name) {
    const root = this.root;
    if (!root.blocks.has(name)) root.blocks.set(name, new Canvas(name, root));
    return root.blocks.get(name);
  }

  add(e) {
    if (!e.layer) e.layer = '0';
    this.layer(e.layer);
    this.entities.push(e);
    return e;
  }

  line(x1, y1, x2, y2, o = {}) { return this.add({ t: 'line', x1, y1, x2, y2, ...o }); }
  pline(pts, o = {}) { return this.add({ t: 'pline', pts: pts.map((p) => ({ x: p.x, y: p.y, bulge: p.bulge || 0 })), closed: !!o.closed, ...o }); }
  rect(x, y, w, h, o = {}) { return this.pline([{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }], { ...o, closed: true }); }
  circle(cx, cy, r, o = {}) { return this.add({ t: 'circle', cx, cy, r, ...o }); }
  arc(cx, cy, r, a1, a2, o = {}) { return this.add({ t: 'arc', cx, cy, r, a1, a2, ...o }); }
  /** Single-line text. align: L|C|R, valign: B|M|T, h: height, rot: degrees. */
  text(x, y, str, o = {}) { return this.add({ t: 'text', x, y, str: String(str), h: o.h || 2.5, rot: o.rot || 0, align: o.align || 'L', valign: o.valign || 'B', ...o }); }
  /** Multi-line text, attached top-left, wrapped at width. */
  mtext(x, y, str, o = {}) { return this.add({ t: 'mtext', x, y, str: String(str), h: o.h || 2.5, width: o.width || 0, attach: o.attach || 1, ...o }); }
  /** Hatch a list of polygons (outer + islands). pattern: SOLID | ANSI31 | ANSI37 | DOTS. */
  hatch(polys, o = {}) { return this.add({ t: 'hatch', polys: polys.map((p) => p.map((q) => ({ x: q.x, y: q.y }))), pattern: o.pattern || 'ANSI31', scale: o.scale || 1, angle: o.angle || 0, ...o }); }
  solid(pts, o = {}) { return this.add({ t: 'solid', pts: pts.map((p) => ({ x: p.x, y: p.y })), ...o }); }
  insert(name, x, y, o = {}) { return this.add({ t: 'insert', name, x, y, sx: o.sx || 1, sy: o.sy || o.sx || 1, rot: o.rot || 0, ...o }); }

  /** Arrow head as a filled triangle pointing from (fx,fy) towards (tx,ty). */
  arrow(fx, fy, tx, ty, size, o = {}) {
    const a = Math.atan2(ty - fy, tx - fx);
    const s = size;
    const p1 = { x: tx, y: ty };
    const p2 = { x: tx - s * Math.cos(a - 0.3), y: ty - s * Math.sin(a - 0.3) };
    const p3 = { x: tx - s * Math.cos(a + 0.3), y: ty - s * Math.sin(a + 0.3) };
    return this.solid([p1, p2, p3, p3], o);
  }

  /** Leader: polyline from text point through vertices to the target, arrow at the target. */
  leader(pts, o = {}) {
    for (let i = 0; i + 1 < pts.length; i++) this.line(pts[i].x, pts[i].y, pts[i + 1].x, pts[i + 1].y, o);
    const n = pts.length;
    if (n >= 2) this.arrow(pts[n - 2].x, pts[n - 2].y, pts[n - 1].x, pts[n - 1].y, o.arrowSize || 2.5, o);
  }

  /**
   * A dimension drawn as lines and text (no DIMENSION entity, so it stays
   * editable as plain geometry). p1 → p2 measured, offset perpendicular.
   */
  dim(p1, p2, offset, o = {}) {
    const dx = p2.x - p1.x, dy = p2.y - p1.y;
    const L = Math.hypot(dx, dy);
    if (L < 1e-6) return;
    const nx = -dy / L, ny = dx / L;
    const a = { x: p1.x + nx * offset, y: p1.y + ny * offset };
    const b = { x: p2.x + nx * offset, y: p2.y + ny * offset };
    const ext = o.ext || 2;
    const tick = o.tick || 1.5;
    const layer = o.layer || 'DIM';
    this.line(p1.x, p1.y, a.x + nx * ext, a.y + ny * ext, { layer });
    this.line(p2.x, p2.y, b.x + nx * ext, b.y + ny * ext, { layer });
    this.line(a.x, a.y, b.x, b.y, { layer });
    for (const p of [a, b]) {
      const ux = (dx / L), uy = (dy / L);
      this.line(p.x - (ux + nx) * tick * 0.7, p.y - (uy + ny) * tick * 0.7, p.x + (ux + nx) * tick * 0.7, p.y + (uy + ny) * tick * 0.7, { layer });
    }
    let rot = (Math.atan2(dy, dx) * 180) / Math.PI;
    if (rot > 90 || rot <= -90) rot += 180;
    const mid = { x: (a.x + b.x) / 2 + nx * (o.h || 2.5) * 0.4, y: (a.y + b.y) / 2 + ny * (o.h || 2.5) * 0.4 };
    this.text(mid.x, mid.y, o.text ?? String(Math.round(L)), { layer, h: o.h || 2.5, rot, align: 'C', valign: 'B' });
  }

  bbox() {
    let b = null;
    const push = (x, y) => {
      if (!b) b = { minX: x, minY: y, maxX: x, maxY: y };
      else { b.minX = Math.min(b.minX, x); b.minY = Math.min(b.minY, y); b.maxX = Math.max(b.maxX, x); b.maxY = Math.max(b.maxY, y); }
    };
    for (const e of this.entities) {
      switch (e.t) {
        case 'line': push(e.x1, e.y1); push(e.x2, e.y2); break;
        case 'pline': e.pts.forEach((p) => push(p.x, p.y)); break;
        case 'solid': e.pts.forEach((p) => push(p.x, p.y)); break;
        case 'hatch': e.polys.forEach((poly) => poly.forEach((p) => push(p.x, p.y))); break;
        case 'circle': case 'arc': push(e.cx - e.r, e.cy - e.r); push(e.cx + e.r, e.cy + e.r); break;
        case 'text': push(e.x, e.y); push(e.x + e.h * 0.8 * e.str.length, e.y + e.h); break;
        case 'mtext': push(e.x, e.y); break;
        case 'insert': {
          const blk = this.root.blocks.get(e.name);
          const bb = blk && blk.bbox();
          if (bb) { push(e.x + bb.minX * e.sx, e.y + bb.minY * e.sy); push(e.x + bb.maxX * e.sx, e.y + bb.maxY * e.sy); }
          break;
        }
        default: break;
      }
    }
    if (b) { b.w = b.maxX - b.minX; b.h = b.maxY - b.minY; b.cx = (b.minX + b.maxX) / 2; b.cy = (b.minY + b.maxY) / 2; }
    return b;
  }
}
