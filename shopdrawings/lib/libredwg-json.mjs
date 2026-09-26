/**
 * Reads the JSON that LibreDWG's `dwgread -O json` writes for a DWG and
 * turns it into the same entity model `parseDxf` produces, so a DWG can be
 * fed to the extractor without AutoCAD:
 *
 *   dwgread -O json -o drawing.json drawing.dwg
 *   node shopdrawings/cli.mjs --input drawing.json ...
 *
 * Only what the extractor and the preview need is converted.
 */
import { stripMtext } from './dxf-reader.mjs';

const ref = (h) => (Array.isArray(h) ? h[h.length - 1] : null);
const deg = (r) => ((r || 0) * 180) / Math.PI;

const LINEWT = { 29: null, 30: null, 31: null };

export function fromLibredwgJson(json) {
  const objs = json.OBJECTS || [];
  const byHandle = new Map();
  for (const o of objs) byHandle.set(o.handle[2], o);
  const nameOf = (h) => { const o = byHandle.get(ref(h)); return o ? o.name : null; };

  // layers and linetypes
  const layers = new Map();
  for (const o of objs) if (o.object === 'LAYER') {
    layers.set(o.name, { color: o.color?.index ?? 7, ltype: nameOf(o.ltype) || 'CONTINUOUS', lw: o.linewt, off: !!(o.flag0 & 1) && false, frozen: !!((o.flag0 || 0) & 1) });
  }
  const styles = new Map();
  for (const o of objs) if (o.object === 'STYLE') styles.set(o.name, { font: o.font_file });

  const convert = (o) => {
    const layer = nameOf(o.layer) || '0';
    const base = { type: o.entity, layer, color: o.color?.index ?? 256, lw: LINEWT[o.linewt] === undefined ? o.linewt : null, handle: o.handle[2] };
    switch (o.entity) {
      case 'LINE': return { ...base, x: o.start[0], y: o.start[1], x2: o.end[0], y2: o.end[1] };
      case 'LWPOLYLINE': {
        const pts = (o.points || []).map((p, i) => ({ x: p[0], y: p[1], bulge: (o.bulges && o.bulges[i]) || 0 }));
        return { ...base, pts, closed: !!((o.flag || 0) & 512), width: o.const_width || 0 };
      }
      case 'POLYLINE_2D': {
        const pts = [];
        for (const vh of o.vertex || []) { const v = byHandle.get(ref(vh)); if (v && v.point) pts.push({ x: v.point[0], y: v.point[1], bulge: v.bulge || 0 }); }
        return { ...base, type: 'LWPOLYLINE', pts, closed: !!((o.flag || 0) & 1) };
      }
      case 'CIRCLE': return { ...base, x: o.center[0], y: o.center[1], r: o.radius };
      case 'ARC': return { ...base, x: o.center[0], y: o.center[1], r: o.radius, a1: deg(o.start_angle), a2: deg(o.end_angle) };
      case 'TEXT': case 'ATTRIB': case 'ATTDEF': {
        const aligned = (o.horiz_alignment || 0) || (o.vert_alignment || 0);
        const p = aligned && o.alignment_pt ? o.alignment_pt : o.ins_pt;
        return { ...base, type: 'TEXT', x: p[0], y: p[1], height: o.height, text: stripMtext(o.text_value || ''), rotation: deg(o.rotation), halign: o.horiz_alignment || 0, valign: o.vert_alignment || 0, style: nameOf(o.style), tag: o.tag };
      }
      case 'MTEXT': return { ...base, x: o.ins_pt[0], y: o.ins_pt[1], height: o.text_height, width: o.rect_width, text: stripMtext(o.text || ''), attachment: o.attachment, rotation: deg(Math.atan2(o.x_axis_dir?.[1] || 0, o.x_axis_dir?.[0] ?? 1)), style: nameOf(o.style) };
      case 'INSERT': case 'MINSERT': {
        const attribs = [];
        for (const ah of o.attribs || []) { const a = byHandle.get(ref(ah)); if (a && a.entity === 'ATTRIB') attribs.push(convert(a)); }
        return { ...base, type: 'INSERT', name: nameOf(o.block_header), x: o.ins_pt[0], y: o.ins_pt[1], sx: o.scale?.[0] ?? 1, sy: o.scale?.[1] ?? 1, rotation: deg(o.rotation), attribs };
      }
      case 'SOLID': case 'TRACE': {
        const c = [o.corner1, o.corner2, o.corner4 || o.corner3, o.corner3].map((p) => ({ x: p[0], y: p[1] }));
        return { ...base, type: 'SOLID', pts: c, closed: true };
      }
      case 'HATCH': {
        const paths = [];
        for (const p of o.paths || []) {
          if (p.polyline_paths) paths.push(p.polyline_paths.map((q) => ({ x: q.point[0], y: q.point[1], bulge: q.bulge || 0 })));
          else if (p.segs) {
            const pts = [];
            for (const s of p.segs) if (s.curve_type === 1 && s.first_endpoint) pts.push({ x: s.first_endpoint[0], y: s.first_endpoint[1] });
            if (pts.length >= 3) paths.push(pts);
          }
        }
        return { ...base, paths, pattern: o.name, solid: !!o.is_solid_fill };
      }
      case 'LEADER': {
        const pts = (o.points || []).map((p) => ({ x: p[0], y: p[1], bulge: 0 }));
        return { ...base, type: 'LWPOLYLINE', pts, closed: false, leader: true };
      }
      default:
        if (o.entity && o.entity.startsWith('DIMENSION')) {
          const blk = nameOf(o.block);
          return { ...base, type: 'INSERT', name: blk, x: 0, y: 0, sx: 1, sy: 1, rotation: 0, dimension: true, text: o.user_text || '', measurement: o.act_measurement };
        }
        return null;
    }
  };

  const blocks = new Map();
  let modelspace = [];
  let paperspace = [];
  for (const o of objs) if (o.object === 'BLOCK_HEADER') {
    const ents = [];
    for (const h of o.entities || []) { const e = byHandle.get(ref(h)); if (!e || !e.entity) continue; const c = convert(e); if (c) ents.push(c); }
    if (o.name === '*Model_Space') modelspace = ents;
    else if (o.name.startsWith('*Paper_Space')) paperspace.push(...ents);
    blocks.set(o.name, { name: o.name, base: { x: o.base_pt?.[0] || 0, y: o.base_pt?.[1] || 0 }, entities: ents, xref: !!o.blkisxref, xrefPath: o.xref_pname || '' });
  }
  const H = json.HEADER || {};
  const header = { $INSUNITS: H.INSUNITS, $LTSCALE: H.LTSCALE, $DIMSCALE: H.DIMSCALE, $TEXTSIZE: H.TEXTSIZE };
  return { header, blocks, entities: modelspace, paperspace, layers, styles, layouts: [...blocks.keys()].filter((n) => n.startsWith('*Paper_Space')) };
}
