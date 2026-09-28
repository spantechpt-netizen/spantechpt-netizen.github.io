/**
 * Plain 2-D geometry on {x, y} points and polygons (arrays of points, first
 * vertex not repeated). Everything is in millimetres in the slab plane.
 */

export const EPS = 1e-6;

export const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export function bbox(points) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 };
}

export function unionBbox(a, b) {
  if (!a) return b;
  if (!b) return a;
  return bbox([{ x: a.minX, y: a.minY }, { x: a.maxX, y: a.maxY }, { x: b.minX, y: b.minY }, { x: b.maxX, y: b.maxY }]);
}

export function expandBbox(b, m) {
  return bbox([{ x: b.minX - m, y: b.minY - m }, { x: b.maxX + m, y: b.maxY + m }]);
}

export const bboxContains = (b, p) => p.x >= b.minX - EPS && p.x <= b.maxX + EPS && p.y >= b.minY - EPS && p.y <= b.maxY + EPS;

/** Signed area (positive when counter-clockwise). */
export function polygonArea(poly) {
  let a = 0;
  for (let i = 0, n = poly.length; i < n; i++) {
    const p = poly[i], q = poly[(i + 1) % n];
    a += p.x * q.y - q.x * p.y;
  }
  return a / 2;
}

export function centroid(poly) {
  const a = polygonArea(poly);
  if (Math.abs(a) < EPS) return bbox(poly);
  let cx = 0, cy = 0;
  for (let i = 0, n = poly.length; i < n; i++) {
    const p = poly[i], q = poly[(i + 1) % n];
    const f = p.x * q.y - q.x * p.y;
    cx += (p.x + q.x) * f;
    cy += (p.y + q.y) * f;
  }
  return { x: cx / (6 * a), y: cy / (6 * a) };
}

export function pointInPolygon(pt, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > pt.y) !== (b.y > pt.y) && pt.x < ((b.x - a.x) * (pt.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

export function perimeter(poly) {
  let l = 0;
  for (let i = 0, n = poly.length; i < n; i++) l += dist(poly[i], poly[(i + 1) % n]);
  return l;
}

/** Polygon edges as [{a, b, length, dx, dy}]. */
export function edges(poly) {
  const out = [];
  for (let i = 0, n = poly.length; i < n; i++) {
    const a = poly[i], b = poly[(i + 1) % n];
    out.push({ a, b, length: dist(a, b), dx: b.x - a.x, dy: b.y - a.y });
  }
  return out;
}

/** Remove a duplicated closing vertex and collinear repeats. */
export function cleanPolygon(poly) {
  const pts = poly.filter((p, i) => i === 0 || dist(p, poly[i - 1]) > 0.5);
  if (pts.length > 1 && dist(pts[0], pts[pts.length - 1]) < 0.5) pts.pop();
  return pts;
}

/** Drop vertices that lie on the straight line between their neighbours (within tol mm). */
export function simplifyPolygon(poly, tol = 1) {
  const pts = cleanPolygon(poly);
  if (pts.length < 4) return pts;
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[(i + pts.length - 1) % pts.length], p = pts[i], b = pts[(i + 1) % pts.length];
    const len = dist(a, b);
    const off = len < 1e-9 ? 0 : Math.abs((b.x - a.x) * (a.y - p.y) - (a.x - p.x) * (b.y - a.y)) / len;
    if (off > tol) out.push(p);
  }
  return out.length >= 3 ? out : pts;
}

/** If the polygon is an axis-aligned rectangle, return it as {x, y, w, h}. */
export function asAxisRect(poly, tol = 1) {
  const pts = cleanPolygon(poly);
  if (pts.length !== 4) return null;
  const b = bbox(pts);
  for (const p of pts) {
    const onX = Math.abs(p.x - b.minX) < tol || Math.abs(p.x - b.maxX) < tol;
    const onY = Math.abs(p.y - b.minY) < tol || Math.abs(p.y - b.maxY) < tol;
    if (!onX || !onY) return null;
  }
  return { x: b.minX, y: b.minY, w: b.w, h: b.h };
}

export const rectPolygon = ({ x, y, w, h }) => [
  { x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h },
];

export const rectCenter = (r) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 });

export const growRect = (r, m) => ({ x: r.x - m, y: r.y - m, w: r.w + 2 * m, h: r.h + 2 * m });

export function circlePolygon(cx, cy, r, n = 32) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2;
    out.push({ x: cx + r * Math.cos(t), y: cy + r * Math.sin(t) });
  }
  return out;
}

/** Horizontal chords [x1, x2] where the line y = Y crosses the polygon (even-odd). */
export function chordsAtY(poly, Y) {
  const xs = [];
  for (let i = 0, n = poly.length; i < n; i++) {
    const a = poly[i], b = poly[(i + 1) % n];
    if (Math.abs(a.y - b.y) < EPS) continue;
    if ((a.y <= Y && b.y > Y) || (b.y <= Y && a.y > Y)) {
      xs.push(a.x + ((Y - a.y) * (b.x - a.x)) / (b.y - a.y));
    }
  }
  xs.sort((p, q) => p - q);
  const out = [];
  for (let i = 0; i + 1 < xs.length; i += 2) if (xs[i + 1] - xs[i] > 1) out.push([xs[i], xs[i + 1]]);
  return out;
}

/** Vertical chords [y1, y2] where the line x = X crosses the polygon. */
export function chordsAtX(poly, X) {
  return chordsAtY(poly.map((p) => ({ x: p.y, y: p.x })), X);
}

/** Subtract cut intervals from a list of [a, b] intervals. */
export function subtractIntervals(intervals, cuts) {
  let out = intervals.map((i) => [...i]);
  for (const [c1, c2] of cuts) {
    if (c2 - c1 <= 0) continue;
    const next = [];
    for (const [a, b] of out) {
      if (c2 <= a || c1 >= b) { next.push([a, b]); continue; }
      if (c1 > a) next.push([a, c1]);
      if (c2 < b) next.push([c2, b]);
    }
    out = next;
  }
  return out.filter(([a, b]) => b - a > 1);
}

export const round = (v, step = 1) => Math.round(v / step) * step;
export const ceilTo = (v, step = 1) => Math.ceil(v / step - 1e-9) * step;

/** Transform a point by an INSERT-style scale / rotation (degrees) / translation. */
export function transformPoint(p, t) {
  const r = ((t.rotation || 0) * Math.PI) / 180;
  const sx = t.sx ?? 1, sy = t.sy ?? 1;
  const x = p.x * sx, y = p.y * sy;
  return {
    x: (t.x || 0) + x * Math.cos(r) - y * Math.sin(r),
    y: (t.y || 0) + x * Math.sin(r) + y * Math.cos(r),
  };
}

/** Clip segment a-b to the inside of a polygon; returns the sub-segments that lie inside. */
export function clipSegmentToPolygon(a, b, poly) {
  const ts = [0, 1];
  const n = poly.length;
  const dx = b.x - a.x, dy = b.y - a.y;
  for (let i = 0; i < n; i++) {
    const p = poly[i], q = poly[(i + 1) % n];
    const ex = q.x - p.x, ey = q.y - p.y;
    const den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-9) continue;
    const t = ((p.x - a.x) * ey - (p.y - a.y) * ex) / den;
    const u = ((p.x - a.x) * dy - (p.y - a.y) * dx) / den;
    if (t > 0 && t < 1 && u >= 0 && u <= 1) ts.push(t);
  }
  ts.sort((x, y) => x - y);
  const out = [];
  for (let i = 0; i < ts.length - 1; i++) {
    const t0 = ts[i], t1 = ts[i + 1];
    if (t1 - t0 < 1e-6) continue;
    const mid = { x: a.x + dx * (t0 + t1) / 2, y: a.y + dy * (t0 + t1) / 2 };
    if (pointInPolygon(mid, poly)) out.push([{ x: a.x + dx * t0, y: a.y + dy * t0 }, { x: a.x + dx * t1, y: a.y + dy * t1 }]);
  }
  return out;
}

/**
 * The longest run of a polyline inside a polygon (points within `tol` of the boundary count as inside), cut exactly
 * where it leaves: `{ pts, from, to, cutStart, cutEnd }` with `from` / `to` the indices of the first and last
 * original points kept, the cut points added at the ends, and the flags saying which ends are cuts. Null when
 * nothing lies inside.
 */
export function clipPolylineToPolygon(pts, poly, tol = 0) {
  if (!pts || pts.length < 2 || !poly || poly.length < 3) return null;
  const inside = (q) => pointInPolygon(q, poly) || (tol > 0 && distToPolygon(q, poly) <= tol);
  const crossing = (a, b) => {
    // the piece of a->b inside the polygon that touches a: its far end is where the polyline leaves
    const pieces = clipSegmentToPolygon(a, b, poly);
    const piece = pieces.find((seg) => Math.hypot(seg[0].x - a.x, seg[0].y - a.y) < 1) || pieces.sort((u, v) => Math.hypot(u[0].x - a.x, u[0].y - a.y) - Math.hypot(v[0].x - a.x, v[0].y - a.y))[0];
    return piece ? piece[1] : a;
  };
  const runs = [];
  let run = null;
  for (let i = 0; i < pts.length; i++) {
    if (inside(pts[i])) {
      if (!run) run = { from: i, to: i, cutStart: i > 0 };
      run.to = i;
    } else if (run) { run.cutEnd = true; runs.push(run); run = null; }
  }
  if (run) { run.cutEnd = false; runs.push(run); }
  if (!runs.length) return null;
  const span = (r) => { let L = 0; for (let i = r.from; i < r.to; i++) L += Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y); return L; };
  const best = runs.sort((a, b) => span(b) - span(a))[0];
  const out = pts.slice(best.from, best.to + 1);
  let cutStart = false, cutEnd = false;
  if (best.cutStart) { const c = crossing(pts[best.from], pts[best.from - 1]); if (Math.hypot(c.x - out[0].x, c.y - out[0].y) > 1) out.unshift(c); cutStart = true; }
  if (best.cutEnd) { const c = crossing(pts[best.to], pts[best.to + 1]); if (Math.hypot(c.x - out[out.length - 1].x, c.y - out[out.length - 1].y) > 1) out.push(c); cutEnd = true; }
  return { pts: out, from: best.from, to: best.to, cutStart, cutEnd };
}

/** Distance from a point to the boundary of a polygon. */
export function distToPolygon(p, poly) {
  let best = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    const dx = b.x - a.x, dy = b.y - a.y;
    const l2 = dx * dx + dy * dy;
    const t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
    best = Math.min(best, Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy)));
  }
  return best;
}
