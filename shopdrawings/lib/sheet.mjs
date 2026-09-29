/**
 * One drawing sheet composed as a block. The sheet frame, title band, notes
 * and schedule live in "paper millimetres" and are scaled up by the drawing
 * scale, while the slab plan is placed at true size (1 unit = 1 mm) — the
 * usual Middle-East convention of a frame scaled around model-space geometry,
 * so everything on the plan measures correctly in AutoCAD.
 *
 * The right-hand strip follows the layout of the reference drawings: key
 * plan, schedule, notes, coordination / contract references, revisions and
 * the title block with project, client, engineer, contractor and the
 * shop-drawing author.
 */
import { Canvas } from './canvas.mjs';
import { wrap } from './svg-writer.mjs';

export const SHEET_SIZES = { A1: { w: 841, h: 594 }, A0: { w: 1189, h: 841 }, A2: { w: 594, h: 420 } };
export const SCALES = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500];
export const DETAIL_SCALES = [5, 10, 12.5, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 250, 300];

/** Fixed layout of an A1 sheet in paper mm (origin bottom-left). */
/**
 * Frame options (`meta.frame`, paper mm): the right-hand strip width and the height of each of its boxes, the
 * bottom detail strip, and which boxes are drawn (`keyplan`, `refs`, `schedule`, `details`); a box switched off
 * gives its room to the notes. `size` picks A0 / A1 / A2.
 */
export const DEFAULT_FRAME = { size: 'A1', rightWidth: 185, bottomStrip: 125, titleH: 150, refsH: 52, keyH: 46, schedH: 140, keyplan: true, refs: true, schedule: true, details: false, margin: { left: 20, bottom: 10, right: 10, top: 10 } };

export function layoutFor(size = 'A1', frameOpts = {}) {
  const F = { ...DEFAULT_FRAME, ...frameOpts, margin: { ...DEFAULT_FRAME.margin, ...(frameOpts.margin || {}) } };
  const { w, h } = SHEET_SIZES[size] || SHEET_SIZES[F.size] || SHEET_SIZES.A1;
  const right = Math.max(120, Number(F.rightWidth) || 185);
  const x0 = F.margin.left, y0 = F.margin.bottom, x1 = w - F.margin.right, y1 = h - F.margin.top;
  const rx = x1 - right;
  const strip = F.details === false ? 0 : Math.max(0, Number(F.bottomStrip) || 125);
  const titleH = Math.max(60, Number(F.titleH) || 150), refsH = F.refs === false ? 0 : Math.max(0, Number(F.refsH) || 52), keyH = F.keyplan === false ? 0 : Math.max(0, Number(F.keyH) || 46), schedH = F.schedule === false ? 0 : Math.max(0, Number(F.schedH) || 140);
  const notesH = Math.max(40, y1 - y0 - titleH - refsH - keyH - schedH);
  const plan = { x: x0, y: y0 + strip, w: rx - x0, h: y1 - y0 - strip };
  return {
    w, h,
    frame: { x: x0, y: y0, w: x1 - x0, h: y1 - y0 },
    title: { x: rx, y: y0, w: right, h: titleH },
    refs: { x: rx, y: y0 + titleH, w: right, h: refsH },
    notes: { x: rx, y: y0 + titleH + refsH, w: right, h: notesH },
    schedule: { x: rx, y: y0 + titleH + refsH + notesH, w: right, h: schedH },
    keyplan: { x: rx, y: y1 - keyH, w: right, h: keyH },
    plan,
    halves: [{ x: plan.x, y: plan.y, w: plan.w / 2, h: plan.h }, { x: plan.x + plan.w / 2, y: plan.y, w: plan.w / 2, h: plan.h }],
    strip: { x: x0, y: y0, w: rx - x0, h: strip },
    details: [0, 1, 2].map((i) => ({ x: x0 + (i * (rx - x0)) / 3, y: y0, w: (rx - x0) / 3, h: strip })),
    opts: F,
  };
}

export function chooseScale(bboxMm, area, margin = 12) {
  const w = area.w - 2 * margin, h = area.h - 2 * margin - 14; // 14: room for the plan title
  for (const s of SCALES) if (bboxMm.w / s <= w && bboxMm.h / s <= h) return s;
  return SCALES[SCALES.length - 1];
}

const cx = (r) => r.x + r.w / 2;
const cy = (r) => r.y + r.h / 2;

export class Sheet {
  constructor(root, { blockName, size = 'A1', scale = 100, frame = {} }) {
    this.root = root;
    this.blockName = blockName;
    this.blk = root.block(blockName);
    this.S = scale;
    this.size = frame.size || size;
    this.L = layoutFor(this.size, frame);
    const S = this.S;
    const blk = this.blk;
    const M = (p) => ({ x: p.x * S, y: p.y * S });
    // ---- paper pen: coordinates and text heights in paper mm
    this.pp = {
      M,
      line: (x1, y1, x2, y2, o = {}) => blk.line(x1 * S, y1 * S, x2 * S, y2 * S, o),
      rect: (x, y, w, h, o = {}) => blk.rect(x * S, y * S, w * S, h * S, o),
      pline: (pts, o = {}) => blk.pline(pts.map(M), o),
      circle: (x, y, r, o = {}) => blk.circle(x * S, y * S, r * S, o),
      arc: (x, y, r, a1, a2, o = {}) => blk.arc(x * S, y * S, r * S, a1, a2, o),
      text: (x, y, str, o = {}) => blk.text(x * S, y * S, str, { ...o, h: (o.h || 2.5) * S }),
      mtext: (x, y, str, o = {}) => blk.mtext(x * S, y * S, str, { ...o, h: (o.h || 2.5) * S, width: (o.width || 0) * S }),
      hatch: (polys, o = {}) => blk.hatch(polys.map((p) => p.map(M)), { ...o, scale: ((o.spacing || 2) * S) / 3.175 }),
      solid: (pts, o = {}) => blk.solid(pts.map(M), o),
      leader: (pts, o = {}) => blk.leader(pts.map(M), { ...o, arrowSize: (o.arrowSize || 2) * S }),
      dim: (p1, p2, off, o = {}) => blk.dim(M(p1), M(p2), off * S, { ...o, h: (o.h || 2) * S, ext: (o.ext || 2) * S, tick: (o.tick || 1.2) * S, text: o.text }),
    };
  }

  /** Place a plan (true-size mm geometry) centred in an area (default: the plan area). */
  setPlan(bboxMm, area = this.L.plan) {
    const S = this.S;
    const ox = cx(area) * S - bboxMm.cx;
    const oy = (cy(area) + 7) * S - bboxMm.cy; // leave room for the plan title below
    const pen = this.makePen((p) => ({ x: p.x + ox, y: p.y + oy }), 1);
    pen.area = area;
    if (!this.pl) this.pl = pen;
    return pen;
  }

  /**
   * Pen for a detail drawn at `detailScale` (e.g. 20 for 1:20) inside a paper
   * box: geometry in mm is centred in the box's inner area. Falls back to the
   * next standard scale when the nominal one overflows the box.
   */
  detailPen(box, detailScale, gb, inner = { top: 9, pad: 6 }) {
    const S = this.S;
    if (box.off) { const scratch = new Canvas('_scratch'); const blk = this.blk; this.blk = scratch; try { return this.makePen((p) => ({ x: p.x, y: p.y }), 1); } finally { this.blk = blk; } }
    const ax = box.x + inner.pad, ay = box.y + inner.pad;
    const aw = box.w - 2 * inner.pad, ah = box.h - inner.top - 2 * inner.pad;
    const gw = (gb.maxX - gb.minX), gh = (gb.maxY - gb.minY);
    const need = Math.max(gw / aw, gh / ah);
    let scale = detailScale;
    if (need > scale) scale = DETAIL_SCALES.find((v) => v >= need) || Math.ceil(need);
    if (box.label && scale !== detailScale && !box.nts) box.label.str = `1:${scale}`;
    const k = S / scale;
    const acx = (ax + aw / 2) * S, acy = (ay + ah / 2) * S;
    const P = (p) => ({ x: acx + (p.x - gb.cx) * k, y: acy + (p.y - gb.cy) * k });
    return this.makePen(P, k);
  }

  /** A pen mapping mm geometry through P (scale k) with paper-mm text heights. */
  makePen(P, k) {
    const S = this.S;
    const blk = this.blk;
    const pen = {
      P, k, S,
      line: (a, b, o = {}) => { const A = P(a), B = P(b); return blk.line(A.x, A.y, B.x, B.y, o); },
      pline: (pts, o = {}) => blk.pline(pts.map(P), o),
      rect: (r, o = {}) => blk.pline([{ x: r.x, y: r.y }, { x: r.x + r.w, y: r.y }, { x: r.x + r.w, y: r.y + r.h }, { x: r.x, y: r.y + r.h }].map(P), { ...o, closed: true }),
      circle: (c, r, o = {}) => { const C = P(c); return blk.circle(C.x, C.y, r * k, o); },
      arc: (c, r, a1, a2, o = {}) => { const C = P(c); return blk.arc(C.x, C.y, r * k, a1, a2, o); },
      text: (p, str, o = {}) => { const Q = P(p); return blk.text(Q.x, Q.y, str, { ...o, h: (o.h || 2.5) * S }); },
      mtext: (p, str, o = {}) => { const Q = P(p); return blk.mtext(Q.x, Q.y, str, { ...o, h: (o.h || 2.5) * S, width: (o.width || 0) * S }); },
      hatch: (polys, o = {}) => blk.hatch(polys.map((poly) => poly.map(P)), { ...o, scale: ((o.spacing || 1.5) * S) / 3.175 }),
      solid: (pts, o = {}) => blk.solid(pts.map(P), o),
      arrow: (a, b, o = {}) => { const A = P(a), B = P(b); return blk.arrow(A.x, A.y, B.x, B.y, (o.size || 1.5) * S, o); },
      leader: (pts, o = {}) => blk.leader(pts.map(P), { ...o, arrowSize: (o.arrowSize || 1.5) * S }),
      dim: (a, b, off, o = {}) => blk.dim(P(a), P(b), off * S, { ...o, h: (o.h || 1.8) * S, ext: (o.ext || 1.5) * S, tick: (o.tick || 1) * S, text: o.text ?? String(Math.round(Math.hypot(b.x - a.x, b.y - a.y))) }),
      /** A real DIMENSION entity (see Canvas.dimension); sizes come from the DIMSTYLE in model units. */
      dimension: (p1, p2, dl, o = {}) => blk.dimension(P(p1), P(p2), P(dl), { ...o, textMid: o.textMid ? P(o.textMid) : undefined }),
      /** Circle with a label, at a plan point, offset in paper mm. */
      bubble: (p, label, o = {}) => {
        const r = (o.r || 3.5) * S;
        const Q = P(p);
        const X = Q.x + (o.dx || 0) * S, Y = Q.y + (o.dy || 0) * S;
        blk.circle(X, Y, r, { layer: o.layer || 'CALLOUT' });
        blk.text(X, Y, label, { layer: o.layer || 'CALLOUT', h: (o.h || 2) * S, align: 'C', valign: 'M' });
        if (o.dx || o.dy) {
          const d = Math.hypot(o.dx || 0, o.dy || 0) * S;
          const ex = X - ((o.dx || 0) * S * r) / d, ey = Y - ((o.dy || 0) * S * r) / d;
          blk.line(ex, ey, Q.x, Q.y, { layer: o.layer || 'CALLOUT' });
        }
        return { x: X, y: Y };
      },
      /** Short perpendicular ticks at both bar ends (bar extent convention). */
      barEnds: (a, b, o = {}) => {
        const A = P(a), B = P(b);
        const L = Math.hypot(B.x - A.x, B.y - A.y) || 1;
        const nx = -(B.y - A.y) / L, ny = (B.x - A.x) / L;
        const t = (o.size || 1) * S;
        blk.line(A.x - nx * t, A.y - ny * t, A.x + nx * t, A.y + ny * t, o);
        blk.line(B.x - nx * t, B.y - ny * t, B.x + nx * t, B.y + ny * t, o);
      },
    };
    return pen;
  }

  // ------------------------------------------------------------ sheet furniture
  frame() {
    const { w, h, frame } = this.L;
    this.pp.rect(0, 0, w, h, { layer: 'FRAME', lw: 13 });
    this.pp.rect(frame.x, frame.y, frame.w, frame.h, { layer: 'FRAME' });
    for (const [x, y, dx, dy] of [[w / 2, 0, 0, 6], [w / 2, h, 0, -6], [0, h / 2, 6, 0], [w, h / 2, -6, 0]]) this.pp.line(x, y, x + dx, y + dy, { layer: 'FRAME' });
    const cols = 8, rows = 6;
    for (let i = 0; i <= cols; i++) {
      const x = frame.x + (frame.w * i) / cols;
      this.pp.line(x, frame.y + frame.h, x, h, { layer: 'FRAME', lw: 13 });
      this.pp.line(x, 0, x, frame.y, { layer: 'FRAME', lw: 13 });
      if (i < cols) {
        this.pp.text(x + frame.w / cols / 2, h - 5, String(i + 1), { layer: 'FRAME', h: 2.5, align: 'C', valign: 'M' });
        this.pp.text(x + frame.w / cols / 2, 5, String(i + 1), { layer: 'FRAME', h: 2.5, align: 'C', valign: 'M' });
      }
    }
    for (let j = 0; j <= rows; j++) {
      const y = frame.y + (frame.h * j) / rows;
      this.pp.line(0, y, frame.x, y, { layer: 'FRAME', lw: 13 });
      this.pp.line(frame.x + frame.w, y, w, y, { layer: 'FRAME', lw: 13 });
      if (j < rows) {
        this.pp.text(frame.x / 2, y + frame.h / rows / 2, 'ABCDEF'[rows - 1 - j], { layer: 'FRAME', h: 2.5, align: 'C', valign: 'M' });
        this.pp.text(w - 5, y + frame.h / rows / 2, 'ABCDEF'[rows - 1 - j], { layer: 'FRAME', h: 2.5, align: 'C', valign: 'M' });
      }
    }
    const { title, refs, notes, schedule, keyplan, plan, strip } = this.L;
    this.pp.line(title.x, frame.y, title.x, frame.y + frame.h, { layer: 'FRAME' });
    if (strip.h) this.pp.line(plan.x, strip.y + strip.h, plan.x + plan.w, strip.y + strip.h, { layer: 'FRAME' });
    for (const r of [refs, notes, schedule, keyplan]) if (r.h) this.pp.line(r.x, r.y, r.x + r.w, r.y, { layer: 'FRAME' });
  }

  /**
   * The office's own frame: the entities of a DXF drawn in paper mm (A1 origin at the bottom-left corner), placed on
   * the sheet in place of the built-in frame, references block and title block. `<TOKENS>` in its texts are replaced
   * with the sheet's data (PROJECT, PROJECT_CODE, CLIENT, CONSULTANT, CONTRACTOR, LOCATION, COMPANY, COMPANY_LINE,
   * TITLE, LEVEL, DRAWING_NO, REV, DATE, SCALE, SHEET, PREPARED, DESIGNER (the engineer who ran the program), CHECKED,
   * APPROVED, STATUS, GRID_REF, INDEX).
   */
  customFrame(entities, fields = {}) {
    const pp = this.pp;
    // tokens are written <PROJECT>, %PROJECT% or {PROJECT} (AutoCAD treats braces in MTEXT as formatting, so the first two are safer)
    const sub = (str) => String(str ?? '').replace(/[<{%]([A-Z][A-Z_]*)[>}%]/g, (m, k) => (fields[k] != null ? String(fields[k]) : m));
    let n = 0;
    for (const e of entities || []) {
      const layer = e.layer && e.layer !== '0' ? `FRAME-${e.layer}` : 'FRAME';
      if (e.type === 'LINE') { pp.line(e.x, e.y, e.x2, e.y2, { layer }); n++; }
      else if (e.type === 'LWPOLYLINE' && e.pts?.length > 1) { pp.pline(e.pts, { layer, closed: !!e.closed }); n++; }
      else if (e.type === 'CIRCLE') { pp.circle(e.x, e.y, e.r, { layer }); n++; }
      else if (e.type === 'ARC') { pp.arc(e.x, e.y, e.r, e.a1 || 0, e.a2 || 360, { layer }); n++; }
      else if (e.type === 'SOLID' || e.type === 'TRACE') { if (e.xs?.length >= 3) { pp.solid(e.xs.map((x, i) => ({ x, y: e.ys[i] })), { layer }); n++; } }
      else if (e.type === 'TEXT' || e.type === 'ATTRIB' || e.type === 'ATTDEF') { const t = sub(e.text); if (t.trim()) { pp.text(e.x, e.y, t, { layer, h: e.height || 2.5, rot: e.rotation || 0, align: e.halign === 1 ? 'C' : e.halign === 2 ? 'R' : 'L', widthFactor: e.sx && e.sx < 2 ? e.sx : undefined }); n++; } }
      else if (e.type === 'MTEXT') { const t = sub(e.text); if (t.trim()) { pp.mtext(e.x, e.y, t, { layer, h: e.height || 2.5, width: e.width || 0, rot: e.rotation || 0 }); n++; } }
    }
    return n;
  }

  /** Key plan box: the slab outline reduced into the box, with a north arrow. */
  keyPlan(outline, label = 'KEY PLAN') {
    const K = this.L.keyplan;
    const pp = this.pp;
    pp.text(K.x + 2, K.y + K.h - 4.5, label, { layer: 'TITLE', h: 2.2 });
    const box = { x: K.x + 40, y: K.y + 3, w: K.w - 80, h: K.h - 9 };
    pp.rect(box.x, box.y, box.w, box.h, { layer: 'TITLE' });
    if (outline && outline.length) {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const p of outline) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); }
      const k = Math.min((box.w - 6) / (maxX - minX || 1), (box.h - 6) / (maxY - minY || 1));
      const pts = outline.map((p) => ({ x: box.x + box.w / 2 + (p.x - (minX + maxX) / 2) * k, y: box.y + box.h / 2 + (p.y - (minY + maxY) / 2) * k }));
      pp.pline(pts, { layer: 'OUTLINE', closed: true });
      pp.hatch([pts], { layer: 'HATCH', pattern: 'ANSI31', spacing: 1.2 });
    }
    const nx = K.x + K.w - 20, ny = K.y + K.h / 2 - 3;
    pp.circle(nx, ny, 6, { layer: 'TEXT' });
    pp.solid([{ x: nx, y: ny + 5 }, { x: nx - 2.5, y: ny - 3.5 }, { x: nx, y: ny - 1.2 }, { x: nx + 2.5, y: ny - 3.5 }], { layer: 'TEXT' });
    pp.text(nx, ny + 7.5, 'N', { layer: 'TEXT', h: 2.5, align: 'C' });
  }

  /** Coordination, contract references and the revision table. */
  refsBlock(meta) {
    const R = this.L.refs;
    const pp = this.pp;
    const x0 = R.x, w = R.w;
    let y = R.y + R.h;
    const row = (h) => { y -= h; pp.line(x0, y, x0 + w, y, { layer: 'TITLE' }); return y; };
    // coordinated with
    let top = y; y = row(5);
    pp.text(x0 + w / 2, top - 2.5, 'COORDINATED WITH THE FOLLOWING DISCIPLINES', { layer: 'TITLE', h: 1.7, align: 'C', valign: 'M' });
    top = y; y = row(6);
    ['ARCH.', 'STRUCT.', 'MEP', 'EL.'].forEach((d, i) => {
      const cxp = x0 + (w * i) / 4;
      if (i) pp.line(cxp, y, cxp, top, { layer: 'TITLE' });
      pp.text(cxp + 1.5, top - 2.2, d, { layer: 'TITLE', h: 1.5 });
      pp.text(cxp + w / 8, y + 1, meta.coordinated?.[i] || '', { layer: 'TEXT-TITLE', h: 1.6, align: 'C' });
    });
    // contract drawing references
    top = y; y = row(5);
    pp.text(x0 + w / 2, top - 2.5, 'CONTRACT DRAWING REFERENCES', { layer: 'TITLE', h: 1.7, align: 'C', valign: 'M' });
    top = y; y = row(4);
    ['ARCHITECTURAL', 'STRUCTURAL', 'MEP'].forEach((d, i) => {
      const cxp = x0 + (w * i) / 3;
      if (i) pp.line(cxp, y, cxp, top, { layer: 'TITLE' });
      pp.text(cxp + w / 6, top - 2, d, { layer: 'TITLE', h: 1.5, align: 'C', valign: 'M' });
    });
    top = y; y = row(4);
    for (let i = 0; i < 3; i++) {
      const cxp = x0 + (w * i) / 3;
      if (i) pp.line(cxp, y, cxp, top, { layer: 'TITLE' });
      pp.line(cxp + w / 3 - 12, y, cxp + w / 3 - 12, top, { layer: 'TITLE' });
      pp.text(cxp + 1.5, top - 2.7, 'DRAWING No.', { layer: 'TITLE', h: 1.3 });
      pp.text(cxp + w / 3 - 6, top - 2.7, 'REV.', { layer: 'TITLE', h: 1.3, align: 'C' });
    }
    const refsList = meta.references || [];
    for (let r = 0; r < 2; r++) {
      top = y; y = row(4);
      for (let i = 0; i < 3; i++) {
        const cxp = x0 + (w * i) / 3;
        if (i) pp.line(cxp, y, cxp, top, { layer: 'TITLE' });
        pp.line(cxp + w / 3 - 12, y, cxp + w / 3 - 12, top, { layer: 'TITLE' });
        const ref = refsList.filter((q) => q.discipline === ['ARCH', 'STRUCT', 'MEP'][i])[r];
        if (ref) { pp.text(cxp + 1.5, y + 1, ref.no, { layer: 'TEXT-TITLE', h: 1.4 }); pp.text(cxp + w / 3 - 6, y + 1, ref.rev || '', { layer: 'TEXT-TITLE', h: 1.4, align: 'C' }); }
      }
    }
    // revisions
    top = y; y = row(4);
    const cols = [[0, 'REV.', 12], [12, 'DESCRIPTION', 118], [130, 'DATE', 30], [160, 'BY', 25]];
    for (const [ox, label, cw] of cols) { if (ox) pp.line(x0 + ox, y, x0 + ox, top, { layer: 'TITLE' }); pp.text(x0 + ox + cw / 2, top - 2, label, { layer: 'TITLE', h: 1.4, align: 'C', valign: 'M' }); }
    const revs = meta.revisions && meta.revisions.length ? meta.revisions : [{ rev: meta.revision || '00', description: meta.issued || 'ISSUED FOR APPROVAL', date: meta.date || '', by: meta.preparedInitials || '' }];
    const rowsLeft = Math.floor((y - R.y) / 4);
    for (let r = 0; r < rowsLeft; r++) {
      top = y; y = row(4);
      const rv = revs[r];
      for (const [ox, , cw] of cols) {
        if (ox) pp.line(x0 + ox, y, x0 + ox, top, { layer: 'TITLE' });
        if (!rv) continue;
        const v = [rv.rev, rv.description, rv.date, rv.by][cols.findIndex((c) => c[0] === ox)] || '';
        pp.text(x0 + ox + (ox === 12 ? 1.5 : cw / 2), y + 1, v, { layer: 'TEXT-TITLE', h: 1.5, align: ox === 12 ? 'L' : 'C' });
      }
    }
  }

  /** Title block: project / client / engineer / contractor / author / title / numbers / signatures. */
  titleBlock(meta) {
    const T = this.L.title;
    const pp = this.pp;
    const x0 = T.x, w = T.w;
    let y = T.y + T.h;
    const row = (h) => { y -= h; pp.line(x0, y, x0 + w, y, { layer: 'TITLE' }); return y; };
    const label = (x, yy, s) => pp.text(x + 1.5, yy - 3, s, { layer: 'TITLE', h: 1.5 });
    const value = (x, yy, s, h = 2.6, o = {}) => pp.text(x + 1.5, yy - 3 - h - 1, s, { layer: 'TEXT-TITLE', h, ...o });
    const vline = (x, y1, y2) => pp.line(x, y1, x, y2, { layer: 'TITLE' });
    const box = (h, lab, val, vh = 2.6, second) => {
      const top = y; y = row(h);
      label(x0, top, lab);
      if (val) value(x0, top, val, vh);
      if (second) pp.text(x0 + 1.5, y + 1.3, second, { layer: 'TITLE', h: 1.7 });
    };
    {
      const top = y; y = row(15);
      label(x0, top, 'PROJECT');
      const lines = wrap((meta.project || '').toUpperCase(), 62).slice(0, 2);
      lines.forEach((ln, i) => pp.text(x0 + 1.5, top - 6.2 - i * 3, ln, { layer: 'TEXT-TITLE', h: 2.1 }));
      pp.text(x0 + 1.5, y + 1.3, [meta.location ? meta.location.toUpperCase() : '', meta.projectCode ? `PROJECT CODE: ${meta.projectCode}` : ''].filter(Boolean).join('   '), { layer: 'TITLE', h: 1.7 });
    }
    box(9, 'THE CLIENT', meta.client || '', 2.2);
    box(9, 'THE ENGINEER (CONSULTANT)', meta.engineer || '', 2.2);
    box(9, 'MAIN CONTRACTOR', meta.contractor || '', 2.2);
    // shop drawing author (company)
    let top = y; y = row(16);
    label(x0, top, 'POST-TENSION SUB-CONTRACTOR / SHOP DRAWINGS BY');
    pp.text(x0 + w / 2, top - 8.5, (meta.company || 'SPAN TECH CONTRACTING').toUpperCase(), { layer: 'TEXT-TITLE', h: 4, align: 'C', valign: 'M', bold: true });
    pp.text(x0 + w / 2, top - 13.5, meta.company_line || 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR', { layer: 'TITLE', h: 1.7, align: 'C', valign: 'M' });
    // title
    top = y; y = row(20);
    label(x0, top, 'DRAWING TITLE');
    const titleLines = wrap([meta.titlePrefix, meta.title].filter(Boolean).join(' - '), 40).slice(0, 3);
    titleLines.forEach((ln, i) => pp.text(x0 + 1.5, top - 7.5 - i * 3.9, ln, { layer: 'TEXT-TITLE', h: 2.9, bold: true }));
    if (meta.level) pp.text(x0 + 1.5, y + 1.3, meta.level, { layer: 'TITLE', h: 2 });
    // drawing no / rev / date
    top = y; y = row(11);
    const c3 = [x0, x0 + w * 0.5, x0 + w * 0.72];
    vline(c3[1], y, top); vline(c3[2], y, top);
    label(c3[0], top, 'DRAWING No.'); value(c3[0], top, meta.drawingNo || '', 3.2);
    label(c3[1], top, 'REV.'); value(c3[1], top, meta.revision || '00', 3.2);
    label(c3[2], top, 'DATE'); value(c3[2], top, meta.date || '', 2.4);
    // scale / sheet / grid ref
    top = y; y = row(11);
    const c3b = [x0, x0 + w * 0.4, x0 + w * 0.66];
    vline(c3b[1], y, top); vline(c3b[2], y, top);
    label(c3b[0], top, 'SCALE (A1)'); value(c3b[0], top, meta.scale || `1:${this.S}`, 2.4);
    label(c3b[1], top, 'SHEET'); value(c3b[1], top, meta.sheet || '', 2.4);
    label(c3b[2], top, 'GRID REFERENCE'); value(c3b[2], top, meta.gridRef || '', 2.2);
    // signatures
    top = y; y = row(15);
    const c3c = [x0, x0 + w / 3, x0 + (2 * w) / 3];
    vline(c3c[1], y, top); vline(c3c[2], y, top);
    // PREPARED carries the engineer who ran the program (meta.designer) - the office name only when no one is logged in
    [['PREPARED / DESIGNED BY', meta.designer || meta.prepared], ['CHECKED', meta.checked], ['APPROVED', meta.approved]].forEach(([k, v], i) => {
      label(c3c[i], top, k);
      pp.text(c3c[i] + 1.5, top - 7.5, (v || '').toUpperCase(), { layer: 'TEXT-TITLE', h: v && v.length > 22 ? 1.6 : 2 });
      pp.text(c3c[i] + 1.5, y + 1.3, 'SIGN / DATE: ..........', { layer: 'TITLE', h: 1.4 });
    });
    // index / code / block
    top = y; y = row(10);
    const c3d = [x0, x0 + w * 0.3, x0 + w * 0.62];
    vline(c3d[1], y, top); vline(c3d[2], y, top);
    label(c3d[0], top, 'DRAWING INDEX'); value(c3d[0], top, meta.index || '', 2);
    label(c3d[1], top, 'CODE REFERENCE'); value(c3d[1], top, meta.codeRef || '', 1.8);
    label(c3d[2], top, 'BLOCK / XREF'); value(c3d[2], top, this.blockName, 1.4);
    // status fills the rest
    const rest = y - T.y;
    pp.text(x0 + w / 2, T.y + rest / 2, meta.status || 'SHOP DRAWING - FOR CONSULTANT APPROVAL', { layer: 'TEXT-TITLE', h: 2.3, align: 'C', valign: 'M', bold: true });
    pp.rect(T.x, T.y, T.w, T.h, { layer: 'TITLE', lw: 50 });
  }

  /** Notes column: general notes, assumptions, code reference, legend. */
  notes({ general = [], assumptions = [], codeRef = '', legend = [], extra = [] }) {
    const N = this.L.notes;
    const pp = this.pp;
    const x = N.x + 3;
    let y = N.y + N.h - 3;
    const head = (en, ar) => {
      y -= 3.2;
      pp.text(x, y, en, { layer: 'TEXT-TITLE', h: 2.4, bold: true });
      if (ar) pp.text(N.x + N.w - 3, y, ar, { layer: 'TEXT-TITLE', h: 2.2, align: 'R' });
      y -= 1.1;
      pp.line(x, y, N.x + N.w - 3, y, { layer: 'NOTES' });
      y -= 1.3;
    };
    const para = (s, h = 1.75) => {
      const lines = wrap(s, Math.floor((N.w - 8) / (h * 0.78)));
      y -= h;
      pp.mtext(x, y + h, s, { layer: 'NOTES', h, width: N.w - 7 });
      y -= (lines.length - 1) * h * 1.55 + 1.3;
    };
    head('GENERAL NOTES', 'ملاحظات عامة');
    general.forEach((g, i) => para(`${i + 1}. ${g}`));
    if (assumptions.length) {
      head('ASSUMPTIONS', 'افتراضات');
      assumptions.forEach((g, i) => para(`A${i + 1}. ${g}`, 1.65));
    }
    head('CODE REFERENCE', 'المرجع الكودي');
    para(codeRef, 1.75);
    for (const e of extra) { head(e.title, e.ar); e.lines.forEach((ln) => para(ln, 1.65)); }
    if (legend.length) {
      head('LEGEND', 'مفتاح الرموز');
      for (const [layer, text, kind] of legend) {
        y -= 2.2;
        if (kind === 'hatch') pp.hatch([[{ x, y: y - 0.8 }, { x: x + 8, y: y - 0.8 }, { x: x + 8, y: y + 1.8 }, { x, y: y + 1.8 }]], { layer, spacing: 1 });
        else if (kind === 'solid') pp.solid([{ x, y: y - 0.8 }, { x: x + 8, y: y - 0.8 }, { x: x + 8, y: y + 1.8 }, { x, y: y + 1.8 }], { layer });
        else pp.line(x, y + 0.5, x + 8, y + 0.5, { layer, lw: kind === 'thick' ? 50 : undefined });
        pp.text(x + 10, y, text, { layer: 'NOTES', h: 1.7 });
        y -= 0.8;
      }
    }
    return y;
  }

  /** Generic table. cols: [{ key, title, w, align }] ; rows: objects. */
  table(x, yTop, cols, rows, { title, rowH = 4, h = 1.7, headH = 5, titleH = 6, maxRows = Infinity, layer = 'SCHEDULE', textLayer = 'SCHEDULE-TEXT', totals = null } = {}) {
    // a table meant for a detail box while the bottom strip is off is not drawn
    if (!(this.L.strip.h > 0) && x < this.L.strip.x + this.L.strip.w && yTop <= this.L.strip.y + 1) return { y: yTop, leftover: [] };
    const pp = this.pp;
    const W = cols.reduce((s, c) => s + c.w, 0);
    let y = yTop;
    if (title) {
      pp.rect(x, y - titleH, W, titleH, { layer });
      pp.text(x + W / 2, y - titleH / 2, title, { layer: 'TEXT-TITLE', h: 2.6, align: 'C', valign: 'M', bold: true });
      y -= titleH;
    }
    pp.rect(x, y - headH, W, headH, { layer });
    let cx0 = x;
    for (const c of cols) {
      const lines = String(c.title).split('\n');
      lines.forEach((ln, i) => pp.text(cx0 + c.w / 2, y - headH / 2 + ((lines.length - 1) / 2 - i) * (h + 0.4), ln, { layer: textLayer, h: h - 0.1, align: 'C', valign: 'M', bold: true }));
      cx0 += c.w;
    }
    y -= headH;
    const shown = rows.slice(0, maxRows);
    const leftover = rows.slice(maxRows);
    for (const r of shown) {
      cx0 = x;
      for (const c of cols) {
        const v = r[c.key] == null ? '' : String(r[c.key]);
        const ax = c.align === 'L' ? cx0 + 1 : c.align === 'R' ? cx0 + c.w - 1 : cx0 + c.w / 2;
        pp.text(ax, y - rowH / 2, v.length > c.max ? v.slice(0, c.max - 1) + '…' : v, { layer: textLayer, h, align: c.align || 'C', valign: 'M' });
        cx0 += c.w;
      }
      y -= rowH;
      pp.line(x, y, x + W, y, { layer, lw: 5 });
    }
    if (totals && !leftover.length) {
      pp.rect(x, y - rowH - 0.5, W, rowH + 0.5, { layer });
      pp.text(x + 2, y - (rowH + 0.5) / 2, totals, { layer: textLayer, h, valign: 'M', bold: true });
      y -= rowH + 0.5;
    }
    cx0 = x;
    const top = yTop - (title ? titleH : 0);
    for (const c of cols) { pp.line(cx0, top, cx0, y, { layer }); cx0 += c.w; }
    pp.line(x + W, top, x + W, y, { layer });
    pp.line(x, y, x + W, y, { layer });
    return { y, leftover };
  }

  /** Box for a detail in the bottom strip, with title strip and scale. */
  detailBox(i, title, scaleLabel) {
    // the office keeps the bottom strip off (the plan takes the whole width): a detail asked for then goes nowhere -
    // a box that is off, whose pen draws into a scratch canvas and whose tables are skipped
    if (!(this.L.strip.h > 0)) return { x: 0, y: 0, w: 0, h: 0, off: true, label: null, nts: true };
    const d = this.L.details[i];
    const pp = this.pp;
    pp.rect(d.x, d.y, d.w, d.h, { layer: 'FRAME' });
    pp.line(d.x, d.y + d.h - 8, d.x + d.w, d.y + d.h - 8, { layer: 'FRAME' });
    pp.circle(d.x + 7, d.y + d.h - 4, 3, { layer: 'CALLOUT' });
    pp.text(d.x + 7, d.y + d.h - 4, String(i + 1), { layer: 'CALLOUT', h: 2.2, align: 'C', valign: 'M' });
    pp.text(d.x + 12, d.y + d.h - 4, title, { layer: 'TEXT-TITLE', h: 2.4, valign: 'M', bold: true });
    d.label = pp.text(d.x + d.w - 2, d.y + d.h - 4, scaleLabel || '', { layer: 'TITLE', h: 1.8, align: 'R', valign: 'M' });
    d.nts = !scaleLabel || /N\.T\.S/.test(scaleLabel);
    return d;
  }

  /** Plan title in the reference style: circled number, underlined title, scale below. */
  planTitleAt(area, n, title, scaleLabel) {
    const pp = this.pp;
    const x = area.x + 10, y = area.y + 6;
    pp.circle(x + 4, y + 1.2, 4, { layer: 'CALLOUT' });
    pp.text(x + 4, y + 1.2, String(n), { layer: 'CALLOUT', h: 3.2, align: 'C', valign: 'M' });
    pp.text(x + 11, y, title, { layer: 'TEXT-TITLE', h: 3.4, bold: true });
    pp.line(x + 11, y - 1.2, x + 11 + title.length * 2.6, y - 1.2, { layer: 'TITLE', lw: 35 });
    pp.text(x + 11, y - 4.2, scaleLabel, { layer: 'TITLE', h: 2 });
  }

  planTitle(title, scaleLabel) { this.planTitleAt(this.L.plan, 1, title, scaleLabel); }

  /** Status stamp in a box (used for the cable template). */
  stamp(text, sub) {
    const P = this.L.plan;
    const w = 150, h = 22;
    const x = P.x + P.w - w - 8, y = P.y + P.h - h - 8;
    this.pp.rect(x, y, w, h, { layer: 'CALLOUT', lw: 50 });
    this.pp.text(x + w / 2, y + h - 7, text, { layer: 'CALLOUT', h: 4, align: 'C', valign: 'M', bold: true });
    if (sub) this.pp.text(x + w / 2, y + 6, sub, { layer: 'CALLOUT', h: 2.2, align: 'C', valign: 'M' });
  }
}
