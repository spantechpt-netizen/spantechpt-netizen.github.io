/**
 * Writes a Canvas (model space + block definitions) as an AutoCAD 2000
 * (AC1015) ASCII DXF. No dependencies; every object gets a handle and an
 * owner so AutoCAD opens the file without a recover pass.
 *
 * Text is encoded with \U+XXXX escapes for anything outside ASCII, which is
 * how R2000 DXF carries Arabic; AutoCAD 2007 and later shape it correctly.
 */
import { LINETYPES } from './canvas.mjs';

const HATCH_PATTERNS = {
  ANSI31: [{ angle: 45, base: [0, 0], offset: [0, 3.175], dashes: [] }],
  ANSI37: [
    { angle: 45, base: [0, 0], offset: [0, 3.175], dashes: [] },
    { angle: 135, base: [0, 0], offset: [0, 3.175], dashes: [] },
  ],
  DOTS: [{ angle: 0, base: [0, 0], offset: [0.79, 0.79], dashes: [0, -1.59] }],
  'ANSI31-WIDE': [{ angle: 45, base: [0, 0], offset: [0, 6.35], dashes: [] }],
};

const num = (v) => {
  if (!Number.isFinite(v)) return '0';
  const s = v.toFixed(6).replace(/\.?0+$/, '');
  return s === '-0' ? '0' : s;
};

export function encodeText(str) {
  let out = '';
  for (const ch of String(str)) {
    const c = ch.codePointAt(0);
    if (c < 127) out += ch;
    else if (c <= 0xffff) out += '\\U+' + c.toString(16).toUpperCase().padStart(4, '0');
    else out += '?';
  }
  return out;
}

class Handles {
  constructor() { this.n = 0x100; }
  next() { return (this.n++).toString(16).toUpperCase(); }
}

export function toDxf(root, opts = {}) {
  const H = new Handles();
  const L = [];
  const tag = (code, value) => { L.push(String(code), String(value)); };

  // Fixed object handles.
  const hRootDict = H.next();
  const hGroupDict = H.next();
  const hPlotDict = H.next();
  const hPlaceholder = H.next();
  const hLayoutDict = H.next();
  const hLayoutModel = H.next();
  const hLayoutPaper = H.next();
  const hBlkRecTable = H.next();
  const hMsRec = H.next();
  const hPsRec = H.next();
  const hMsBlock = H.next();
  const hMsEnd = H.next();
  const hPsBlock = H.next();
  const hPsEnd = H.next();
  const blockRec = new Map();
  for (const name of root.blocks.keys()) blockRec.set(name, H.next());

  const ext = root.bbox() || { minX: 0, minY: 0, maxX: 1000, maxY: 1000, w: 1000, h: 1000, cx: 500, cy: 500 };

  // ------------------------------------------------------------ HEADER
  tag(0, 'SECTION'); tag(2, 'HEADER');
  tag(9, '$ACADVER'); tag(1, 'AC1015');
  tag(9, '$DWGCODEPAGE'); tag(3, 'ANSI_1252');
  tag(9, '$INSBASE'); tag(10, 0); tag(20, 0); tag(30, 0);
  tag(9, '$EXTMIN'); tag(10, num(ext.minX)); tag(20, num(ext.minY)); tag(30, 0);
  tag(9, '$EXTMAX'); tag(10, num(ext.maxX)); tag(20, num(ext.maxY)); tag(30, 0);
  tag(9, '$LIMMIN'); tag(10, 0); tag(20, 0);
  tag(9, '$LIMMAX'); tag(10, num(ext.maxX)); tag(20, num(ext.maxY));
  tag(9, '$ORTHOMODE'); tag(70, 0);
  tag(9, '$LTSCALE'); tag(40, num(opts.ltscale ?? 1));
  tag(9, '$TEXTSIZE'); tag(40, 2.5);
  tag(9, '$TEXTSTYLE'); tag(7, 'STANDARD');
  tag(9, '$CLAYER'); tag(8, '0');
  tag(9, '$CELTYPE'); tag(6, 'BYLAYER');
  tag(9, '$CECOLOR'); tag(62, 256);
  tag(9, '$DIMSTYLE'); tag(2, 'STANDARD');
  tag(9, '$INSUNITS'); tag(70, 4); // millimetres
  tag(9, '$MEASUREMENT'); tag(70, 1); // metric
  tag(9, '$PDMODE'); tag(70, 0);
  tag(9, '$PSLTSCALE'); tag(70, 1);
  tag(9, '$TILEMODE'); tag(70, 1);
  tag(9, '$HANDSEED'); tag(5, 'FFFFFF');
  tag(0, 'ENDSEC');

  // ------------------------------------------------------------ CLASSES
  tag(0, 'SECTION'); tag(2, 'CLASSES'); tag(0, 'ENDSEC');

  // ------------------------------------------------------------ TABLES
  tag(0, 'SECTION'); tag(2, 'TABLES');

  const table = (name, records, extra) => {
    const h = name === 'BLOCK_RECORD' ? hBlkRecTable : H.next();
    tag(0, 'TABLE'); tag(2, name); tag(5, h); tag(330, 0); tag(100, 'AcDbSymbolTable'); tag(70, records.length);
    if (extra) extra();
    for (const r of records) r(h);
    tag(0, 'ENDTAB');
  };

  table('VPORT', [(owner) => {
    tag(0, 'VPORT'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbViewportTableRecord');
    tag(2, '*Active'); tag(70, 0);
    tag(10, 0); tag(20, 0); tag(11, 1); tag(21, 1);
    tag(12, num(ext.cx)); tag(22, num(ext.cy));
    tag(13, 0); tag(23, 0); tag(14, 10); tag(24, 10); tag(15, 10); tag(25, 10);
    tag(16, 0); tag(26, 0); tag(36, 1); tag(17, 0); tag(27, 0); tag(37, 0);
    tag(40, num(ext.h * 1.1 || 1000)); tag(41, num((ext.w || 1000) / (ext.h || 1000) * 1.0));
    tag(42, 50); tag(43, 0); tag(44, 0); tag(50, 0); tag(51, 0);
    tag(71, 0); tag(72, 1000); tag(73, 1); tag(74, 3); tag(75, 0); tag(76, 0); tag(77, 0); tag(78, 0);
    tag(281, 0); tag(65, 1); tag(110, 0); tag(120, 0); tag(130, 0); tag(111, 1); tag(121, 0); tag(131, 0);
    tag(112, 0); tag(122, 1); tag(132, 0); tag(79, 0); tag(146, 0);
  }]);

  const ltypeRecord = (name, desc, pattern) => (owner) => {
    tag(0, 'LTYPE'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbLinetypeTableRecord');
    tag(2, name); tag(70, 0); tag(3, desc); tag(72, 65); tag(73, pattern.length);
    tag(40, num(pattern.reduce((s, v) => s + Math.abs(v), 0)));
    for (const d of pattern) { tag(49, num(d)); tag(74, 0); }
  };
  table('LTYPE', [
    ltypeRecord('ByBlock', '', []),
    ltypeRecord('ByLayer', '', []),
    ...Object.entries(LINETYPES).map(([n, d]) => ltypeRecord(n, d.desc, d.pattern)),
  ]);

  table('LAYER', [...root.layers.entries()].map(([name, def]) => (owner) => {
    tag(0, 'LAYER'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbLayerTableRecord');
    tag(2, name); tag(70, 0); tag(62, def.color ?? 7); tag(6, def.ltype || 'CONTINUOUS');
    tag(370, def.lw ?? -3); tag(390, hPlaceholder);
  }));

  const styles = root.textStyles && root.textStyles.size ? [...root.textStyles.entries()] : [['STANDARD', { font: root.textStyle?.font || 'arial.ttf' }]];
  if (!styles.some(([n]) => n === 'STANDARD')) styles.unshift(['STANDARD', { font: 'arial.ttf' }]);
  table('STYLE', styles.map(([name, def]) => (owner) => {
    tag(0, 'STYLE'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbTextStyleTableRecord');
    tag(2, name); tag(70, 0); tag(40, 0); tag(41, def.widthFactor || 1); tag(50, 0); tag(71, 0); tag(42, 2.5); tag(3, def.font || 'arial.ttf'); tag(4, '');
  }));

  table('VIEW', []);
  table('UCS', []);
  table('APPID', [(owner) => {
    tag(0, 'APPID'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbRegAppTableRecord'); tag(2, 'ACAD'); tag(70, 0);
  }]);
  table('DIMSTYLE', [(owner) => {
    tag(0, 'DIMSTYLE'); tag(105, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbDimStyleTableRecord');
    tag(2, 'STANDARD'); tag(70, 0); tag(40, 1); tag(41, 2.5); tag(42, 0.625); tag(43, 3.75); tag(44, 1.25); tag(140, 2.5); tag(141, 2.5); tag(147, 0.625);
  }], () => tag(100, 'AcDbDimStyleTable'));

  const blockRecord = (h, name, layout) => (owner) => {
    tag(0, 'BLOCK_RECORD'); tag(5, h); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbBlockTableRecord');
    tag(2, name); tag(340, layout || 0);
  };
  table('BLOCK_RECORD', [
    blockRecord(hMsRec, '*Model_Space', hLayoutModel),
    blockRecord(hPsRec, '*Paper_Space', hLayoutPaper),
    ...[...blockRec.entries()].map(([name, h]) => blockRecord(h, name, 0)),
  ]);
  tag(0, 'ENDSEC');

  // ------------------------------------------------------------ entities
  const entityHeader = (type, e, owner, paper = false) => {
    tag(0, type); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbEntity');
    if (paper) tag(67, 1);
    tag(8, e.layer || '0');
    if (e.ltype) tag(6, e.ltype);
    if (e.color != null) tag(62, e.color);
    if (e.lw != null) tag(370, e.lw);
  };

  const writeEntity = (e, owner) => {
    switch (e.t) {
      case 'line':
        entityHeader('LINE', e, owner); tag(100, 'AcDbLine');
        tag(10, num(e.x1)); tag(20, num(e.y1)); tag(30, 0); tag(11, num(e.x2)); tag(21, num(e.y2)); tag(31, 0);
        break;
      case 'pline':
        entityHeader('LWPOLYLINE', e, owner); tag(100, 'AcDbPolyline');
        tag(90, e.pts.length); tag(70, e.closed ? 1 : 0); tag(43, num(e.width || 0));
        for (const p of e.pts) { tag(10, num(p.x)); tag(20, num(p.y)); if (p.bulge) tag(42, num(p.bulge)); }
        break;
      case 'circle':
        entityHeader('CIRCLE', e, owner); tag(100, 'AcDbCircle');
        tag(10, num(e.cx)); tag(20, num(e.cy)); tag(30, 0); tag(40, num(e.r));
        break;
      case 'arc':
        entityHeader('ARC', e, owner); tag(100, 'AcDbCircle');
        tag(10, num(e.cx)); tag(20, num(e.cy)); tag(30, 0); tag(40, num(e.r));
        tag(100, 'AcDbArc'); tag(50, num(e.a1)); tag(51, num(e.a2));
        break;
      case 'solid': {
        entityHeader('SOLID', e, owner); tag(100, 'AcDbTrace');
        const p = e.pts;
        const q = [p[0], p[1], p[3] || p[2], p[2]]; // SOLID takes a bow-tie order
        q.forEach((pt, i) => { tag(10 + i, num(pt.x)); tag(20 + i, num(pt.y)); tag(30 + i, 0); });
        break;
      }
      case 'text': {
        entityHeader('TEXT', e, owner); tag(100, 'AcDbText');
        const hAlign = { L: 0, C: 1, R: 2 }[e.align] ?? 0;
        const vAlign = { B: 0, M: 2, T: 3 }[e.valign] ?? 0;
        tag(10, num(e.x)); tag(20, num(e.y)); tag(30, 0); tag(40, num(e.h)); tag(1, encodeText(e.str));
        if (e.rot) tag(50, num(e.rot));
        if (e.widthFactor) tag(41, num(e.widthFactor));
        tag(7, e.style || 'STANDARD'); tag(72, hAlign);
        if (hAlign || vAlign) { tag(11, num(e.x)); tag(21, num(e.y)); tag(31, 0); }
        tag(100, 'AcDbText'); tag(73, vAlign);
        break;
      }
      case 'mtext': {
        entityHeader('MTEXT', e, owner); tag(100, 'AcDbMText');
        tag(10, num(e.x)); tag(20, num(e.y)); tag(30, 0); tag(40, num(e.h));
        if (e.width) tag(41, num(e.width));
        tag(71, e.attach || 1); tag(72, 1);
        const s = encodeText(e.str.replace(/\r?\n/g, '\\P'));
        const chunks = s.match(/.{1,250}/g) || [''];
        chunks.slice(0, -1).forEach((c) => tag(3, c));
        tag(1, chunks[chunks.length - 1]);
        tag(7, e.style || 'STANDARD');
        if (e.rot) tag(50, num(e.rot));
        tag(44, num(e.lineSpacing || 1));
        break;
      }
      case 'hatch': {
        entityHeader('HATCH', e, owner); tag(100, 'AcDbHatch');
        tag(10, 0); tag(20, 0); tag(30, 0); tag(210, 0); tag(220, 0); tag(230, 1);
        const solid = e.pattern === 'SOLID';
        tag(2, e.pattern); tag(70, solid ? 1 : 0); tag(71, 0);
        tag(91, e.polys.length);
        for (const poly of e.polys) {
          tag(92, 2 | (poly === e.polys[0] ? 1 : 16)); tag(72, 0); tag(73, 1); tag(93, poly.length);
          for (const p of poly) { tag(10, num(p.x)); tag(20, num(p.y)); }
          tag(97, 0);
        }
        tag(75, e.polys.length > 1 ? 0 : 1); tag(76, solid ? 1 : 1);
        if (!solid) {
          const def = HATCH_PATTERNS[e.pattern] || HATCH_PATTERNS.ANSI31;
          tag(52, num(e.angle || 0)); tag(41, num(e.scale || 1)); tag(77, 0); tag(78, def.length);
          const sc = e.scale || 1;
          const rot = ((e.angle || 0) * Math.PI) / 180;
          for (const ln of def) {
            const a = ln.angle + (e.angle || 0);
            const t = (ln.angle * Math.PI) / 180 + rot;
            const ox = ln.offset[0] * sc, oy = ln.offset[1] * sc;
            tag(53, num(a)); tag(43, num(ln.base[0] * sc)); tag(44, num(ln.base[1] * sc));
            tag(45, num(ox * Math.cos(t) - oy * Math.sin(t))); tag(46, num(ox * Math.sin(t) + oy * Math.cos(t)));
            tag(79, ln.dashes.length);
            for (const d of ln.dashes) tag(49, num(d * sc));
          }
        }
        // no group 47 (pixel size): AutoCAD reads it only for boundary paths flagged 'derived' (0x4)
        // and otherwise rejects the file with "expected group code 98"
        tag(98, 0);
        break;
      }
      case 'insert':
        entityHeader('INSERT', e, owner); tag(100, 'AcDbBlockReference');
        tag(2, e.name); tag(10, num(e.x)); tag(20, num(e.y)); tag(30, 0);
        tag(41, num(e.sx || 1)); tag(42, num(e.sy || e.sx || 1)); tag(43, 1); tag(50, num(e.rot || 0));
        break;
      default:
        break;
    }
  };

  // ------------------------------------------------------------ BLOCKS
  tag(0, 'SECTION'); tag(2, 'BLOCKS');
  const blockBegin = (h, rec, name, paper) => {
    tag(0, 'BLOCK'); tag(5, h); tag(330, rec); tag(100, 'AcDbEntity'); if (paper) tag(67, 1); tag(8, '0'); tag(100, 'AcDbBlockBegin');
    tag(2, name); tag(70, 0); tag(10, 0); tag(20, 0); tag(30, 0); tag(3, name); tag(1, '');
  };
  const blockEnd = (h, rec, paper) => {
    tag(0, 'ENDBLK'); tag(5, h); tag(330, rec); tag(100, 'AcDbEntity'); if (paper) tag(67, 1); tag(8, '0'); tag(100, 'AcDbBlockEnd');
  };
  blockBegin(hMsBlock, hMsRec, '*Model_Space', false); blockEnd(hMsEnd, hMsRec, false);
  blockBegin(hPsBlock, hPsRec, '*Paper_Space', true); blockEnd(hPsEnd, hPsRec, true);
  for (const [name, blk] of root.blocks) {
    const rec = blockRec.get(name);
    blockBegin(H.next(), rec, name, false);
    for (const e of blk.entities) writeEntity(e, rec);
    blockEnd(H.next(), rec, false);
  }
  tag(0, 'ENDSEC');

  // ------------------------------------------------------------ ENTITIES
  tag(0, 'SECTION'); tag(2, 'ENTITIES');
  for (const e of root.entities) writeEntity(e, hMsRec);
  tag(0, 'ENDSEC');

  // ------------------------------------------------------------ OBJECTS
  tag(0, 'SECTION'); tag(2, 'OBJECTS');
  tag(0, 'DICTIONARY'); tag(5, hRootDict); tag(330, 0); tag(100, 'AcDbDictionary'); tag(281, 1);
  tag(3, 'ACAD_GROUP'); tag(350, hGroupDict);
  tag(3, 'ACAD_LAYOUT'); tag(350, hLayoutDict);
  tag(3, 'ACAD_PLOTSTYLENAME'); tag(350, hPlotDict);
  tag(0, 'DICTIONARY'); tag(5, hGroupDict); tag(330, hRootDict); tag(100, 'AcDbDictionary'); tag(281, 1);
  tag(0, 'ACDBDICTIONARYWDFLT'); tag(5, hPlotDict); tag(330, hRootDict); tag(100, 'AcDbDictionary'); tag(281, 1);
  tag(3, 'Normal'); tag(350, hPlaceholder); tag(100, 'AcDbDictionaryWithDefault'); tag(340, hPlaceholder);
  tag(0, 'ACDBPLACEHOLDER'); tag(5, hPlaceholder); tag(330, hPlotDict);
  tag(0, 'DICTIONARY'); tag(5, hLayoutDict); tag(330, hRootDict); tag(100, 'AcDbDictionary'); tag(281, 1);
  tag(3, 'Model'); tag(350, hLayoutModel);
  tag(3, 'Layout1'); tag(350, hLayoutPaper);
  const layout = (h, name, rec, order, flags) => {
    tag(0, 'LAYOUT'); tag(5, h); tag(330, hLayoutDict);
    tag(100, 'AcDbPlotSettings'); tag(1, ''); tag(2, 'none_device'); tag(4, ''); tag(6, '');
    tag(40, 0); tag(41, 0); tag(42, 0); tag(43, 0); tag(44, 0); tag(45, 0); tag(46, 0); tag(47, 0); tag(48, 0); tag(49, 0);
    tag(140, 0); tag(141, 0); tag(142, 1); tag(143, 1); tag(70, flags); tag(72, 0); tag(73, 0); tag(74, 5); tag(7, ''); tag(75, 16);
    tag(147, 1); tag(148, 0); tag(149, 0);
    tag(100, 'AcDbLayout'); tag(1, name); tag(70, 1); tag(71, order);
    tag(10, 0); tag(20, 0); tag(11, 12); tag(21, 9); tag(12, 0); tag(22, 0); tag(32, 0);
    tag(14, 0); tag(24, 0); tag(34, 0); tag(15, 0); tag(25, 0); tag(35, 0); tag(146, 0);
    tag(13, 0); tag(23, 0); tag(33, 0); tag(16, 1); tag(26, 0); tag(36, 0); tag(17, 0); tag(27, 1); tag(37, 0); tag(76, 0);
    tag(330, rec);
  };
  layout(hLayoutModel, 'Model', hMsRec, 0, 1712);
  layout(hLayoutPaper, 'Layout1', hPsRec, 1, 688);
  tag(0, 'ENDSEC');
  tag(0, 'EOF');

  // Patch the real HANDSEED now that we know it.
  const seed = (H.n + 1).toString(16).toUpperCase();
  const idx = L.indexOf('$HANDSEED');
  L[idx + 2] = seed;
  return L.join('\n') + '\n';
}
