/**
 * Reads an ASCII DXF (any release from R12 up) into plain entities:
 *   { type, layer, ... } with points in drawing units.
 *
 * Only what the extractor needs is decoded: LINE, LWPOLYLINE, POLYLINE,
 * CIRCLE, ARC, TEXT, MTEXT, INSERT, SOLID, HATCH (boundary paths) and the
 * BLOCKS section so INSERTs can be exploded. Everything else is skipped.
 */

export function decodeText(s) {
  return String(s)
    .replace(/\\U\+([0-9A-Fa-f]{4})/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/\\M\+[0-9A-Fa-f]{5}/g, '?');
}

/** Strip MTEXT inline formatting codes down to readable text. */
export function stripMtext(s) {
  return decodeText(s)
    .replace(/\\P/g, '\n')
    .replace(/\\~/g, ' ')
    .replace(/\\[A-Za-z][^;\\]*;/g, '')
    .replace(/[{}]/g, '')
    .replace(/%%[cCdDpP]/g, (m) => ({ c: 'Ø', d: '°', p: '±' })[m[2].toLowerCase()]);
}

function* pairs(text) {
  const lines = text.split(/\r?\n/);
  for (let i = 0; i + 1 < lines.length; i += 2) {
    const code = parseInt(lines[i].trim(), 10);
    if (Number.isNaN(code)) continue;
    yield [code, lines[i + 1]];
  }
}

const NUMERIC = (code) => (code >= 10 && code <= 59) || (code >= 60 && code <= 79) || (code >= 90 && code <= 99) || (code >= 140 && code <= 149) || (code >= 170 && code <= 179) || (code >= 210 && code <= 239) || (code >= 370 && code <= 389);

/** Turn a run of [code, value] pairs for one entity into an object. */
function buildEntity(type, groups) {
  const e = { type, layer: '0', xs: [], ys: [], bulges: [], _codes: groups };
  let textBuf = '';
  for (const [code, raw] of groups) {
    const v = NUMERIC(code) ? parseFloat(raw) : raw;
    switch (code) {
      case 8: e.layer = raw.trim(); break;
      case 2: e.name = raw.trim(); break;
      case 10: e.xs.push(v); break;
      case 20: e.ys.push(v); break;
      case 11: e.x2 = v; break;
      case 21: e.y2 = v; break;
      case 13: e.x3 = v; break;
      case 23: e.y3 = v; break;
      case 14: e.x4 = v; break;
      case 24: e.y4 = v; break;
      case 7: e.style = raw.trim(); break;
      case 40: e.r = v; e.height = v; break;
      case 41: e.sx = v; if (type === 'MTEXT') e.width = v; break;
      case 42: if (type === 'LWPOLYLINE' || type === 'VERTEX') { e.bulges[e.xs.length - 1] = v; } else if (type === 'DIMENSION') e.measure = v; else e.sy = v; break;
      case 50: e.rotation = v; e.a1 = v; break;
      case 51: e.a2 = v; break;
      case 70: e.flags = v; break;
      case 72: e.halign = v; break;
      case 1: textBuf += raw; break;
      case 3: if (type === 'DIMENSION') e.dimstyle = raw.trim(); else textBuf = raw + textBuf; break; // MTEXT continuation chunks come first
      case 62: e.color = v; break;
      default: break;
    }
  }
  if (type === 'MTEXT') {
    // Codes 3 precede the final 1: rebuild in order.
    const chunks = groups.filter(([c]) => c === 3).map(([, r]) => r);
    const last = groups.find(([c]) => c === 1);
    e.text = stripMtext(chunks.join('') + (last ? last[1] : ''));
  } else if (type === 'TEXT' || type === 'ATTRIB' || type === 'ATTDEF') {
    e.text = stripMtext(textBuf);
  }
  e.x = e.xs[0] ?? 0;
  e.y = e.ys[0] ?? 0;
  if ((type === 'TEXT') && e.halign && e.x2 != null) { e.x = e.x2; e.y = e.y2; }
  if (type === 'DIMENSION') {
    // 10/20 dimension line point, 11/21 text midpoint, 13/23 + 14/24 the measured points, 50 rotation, 70 type, 42 measurement, 1 text override
    e.dimType = (e.flags || 0) & 7;
    e.text = textBuf.trim();
  }
  if (type === 'LWPOLYLINE') {
    e.pts = e.xs.map((x, i) => ({ x, y: e.ys[i], bulge: e.bulges[i] || 0 }));
    e.closed = !!((e.flags || 0) & 1);
  }
  if (type === 'SOLID' || type === 'TRACE') {
    const p = groups.filter(([c]) => c >= 10 && c <= 13).map(([c, r]) => [c, parseFloat(r)]);
    const q = groups.filter(([c]) => c >= 20 && c <= 23).map(([c, r]) => [c, parseFloat(r)]);
    const pts = p.map(([c, x]) => ({ x, y: (q.find(([qc]) => qc === c + 10) || [0, 0])[1] }));
    e.pts = pts.length === 4 ? [pts[0], pts[1], pts[3], pts[2]] : pts;
    e.closed = true;
  }
  if (type === 'HATCH') {
    // Boundary paths: polyline paths (92 & 2) or edge paths made of lines.
    e.paths = [];
    let i = 0;
    const g = groups;
    while (i < g.length) {
      if (g[i][0] === 92) {
        const flags = parseInt(g[i][1], 10);
        const path = [];
        i++;
        if (flags & 2) {
          let n = 0;
          while (i < g.length && g[i][0] !== 97 && g[i][0] !== 92) {
            if (g[i][0] === 93) n = parseInt(g[i][1], 10);
            if (g[i][0] === 10) path.push({ x: parseFloat(g[i][1]), y: parseFloat(g[i + 1] && g[i + 1][0] === 20 ? g[i + 1][1] : 0) });
            i++;
          }
          void n;
        } else {
          while (i < g.length && g[i][0] !== 97 && g[i][0] !== 92) {
            if (g[i][0] === 72 && g[i][1].trim() === '1') {
              // line edge: 10 20 11 21
              const x1 = parseFloat(g[i + 1][1]), y1 = parseFloat(g[i + 2][1]);
              path.push({ x: x1, y: y1 });
              i += 4;
              continue;
            }
            i++;
          }
        }
        if (path.length >= 3) e.paths.push(path);
        continue;
      }
      i++;
    }
    e.pattern = e.name;
  }
  delete e._codes;
  return e;
}

export function parseDxf(text) {
  const header = {};
  const blocks = new Map();
  const entities = [];
  let section = null;
  let current = null; // { type, groups }
  let target = entities;
  let block = null;
  let polyline = null;
  let headerVar = null;

  const flush = () => {
    if (!current) return;
    const ent = buildEntity(current.type, current.groups);
    current = null;
    if (ent.type === 'BLOCK') {
      block = { name: ent.name, base: { x: ent.x, y: ent.y }, entities: [] };
      blocks.set(block.name, block);
      target = block.entities;
      return;
    }
    if (ent.type === 'ENDBLK') { block = null; target = entities; return; }
    if (ent.type === 'POLYLINE') { polyline = { type: 'LWPOLYLINE', layer: ent.layer, pts: [], closed: !!((ent.flags || 0) & 1) }; return; }
    if (ent.type === 'VERTEX' && polyline) { polyline.pts.push({ x: ent.x, y: ent.y, bulge: ent.bulges[0] || 0 }); return; }
    if (ent.type === 'SEQEND') { if (polyline) { target.push(polyline); polyline = null; } return; }
    if (['LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'INSERT', 'SOLID', 'TRACE', 'HATCH', 'ATTRIB', 'POINT', 'DIMENSION'].includes(ent.type)) target.push(ent);
  };

  for (const [code, value] of pairs(text)) {
    if (code === 0) {
      const v = value.trim();
      if (v === 'SECTION') { flush(); section = null; continue; }
      if (v === 'ENDSEC') { flush(); section = null; continue; }
      if (v === 'EOF') { flush(); break; }
      if (section === 'HEADER') continue;
      if (section === 'BLOCKS' || section === 'ENTITIES') {
        flush();
        current = { type: v, groups: [] };
      }
      continue;
    }
    if (code === 2 && section === null && !current) { section = value.trim(); continue; }
    if (section === 'HEADER') {
      if (code === 9) headerVar = value.trim();
      else if (headerVar && (code === 70 || code === 40 || code === 1 || code === 10 || code === 3)) {
        if (!(headerVar in header)) header[headerVar] = NUMERIC(code) ? parseFloat(value) : value.trim();
      }
      continue;
    }
    if (current) current.groups.push([code, value]);
  }
  return { header, blocks, entities };
}
