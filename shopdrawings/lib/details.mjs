/**
 * Small section / plan details drawn at large scale in the bottom strip of a
 * sheet. Each builder returns { bbox, draw(pen) } with geometry in mm.
 */
import { circlePolygon, rectPolygon } from './geometry.mjs';

const conc = (pen, poly, spacing = 1.6) => pen.hatch([poly], { layer: 'DETAIL-HATCH', pattern: 'ANSI31', spacing });

export function sectionMesh({ h, cover, dia, lap, spacing }) {
  const L = 2600;
  const y0 = cover + dia / 2;
  return {
    bbox: { minX: -250, maxX: L + 250, minY: -520, maxY: h + 420, cx: L / 2, cy: (h - 100) / 2 },
    draw(pen) {
      pen.rect({ x: 0, y: 0, w: L, h }, { layer: 'DETAIL', lw: 35 });
      conc(pen, rectPolygon({ x: 0, y: 0, w: L, h }));
      pen.line({ x: 100, y: y0 }, { x: L / 2 + lap / 2, y: y0 }, { layer: 'REBAR-BOT', lw: 70 });
      pen.line({ x: L / 2 - lap / 2, y: y0 + dia * 1.4 }, { x: L - 100, y: y0 + dia * 1.4 }, { layer: 'REBAR-BOT', lw: 70 });
      pen.barEnds({ x: 100, y: y0 }, { x: L / 2 + lap / 2, y: y0 }, { layer: 'REBAR-BOT' });
      pen.barEnds({ x: L / 2 - lap / 2, y: y0 + dia * 1.4 }, { x: L - 100, y: y0 + dia * 1.4 }, { layer: 'REBAR-BOT' });
      // cross bars of the mesh (other direction) as dots
      for (let x = 250; x < L; x += spacing) pen.circle({ x, y: y0 + dia * 2.6 }, dia / 2, { layer: 'REBAR-BOT' });
      pen.dim({ x: L / 2 - lap / 2, y: 0 }, { x: L / 2 + lap / 2, y: 0 }, -7, { text: `LAP ${lap}` });
      pen.dim({ x: 0, y: 0 }, { x: 0, y: h }, 6, { text: `${h}` });
      pen.dim({ x: L, y: 0 }, { x: L, y: cover }, -6, { text: `${cover}` });
      pen.text({ x: L / 2, y: h + 120 }, `T${dia}@${spacing} B.W. BOTTOM MESH - CLASS B LAP, STAGGERED`, { layer: 'REBAR-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: L / 2, y: -420 }, 'BOTTOM BARS CONTINUOUS THROUGH COLUMNS, STOPPED AT OPENINGS', { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function sectionColumn({ h, c1, ext, dia, spacing, cover, hookLeg, shape, uReturn = 0 }) {
  const half = c1 / 2 + ext + 350;
  return {
    bbox: { minX: -half - 200, maxX: half + 200, minY: -1000, maxY: h + 520, cx: 0, cy: (h - 500) / 2 },
    draw(pen) {
      pen.rect({ x: -half, y: 0, w: 2 * half, h }, { layer: 'DETAIL', lw: 35 });
      conc(pen, rectPolygon({ x: -half, y: 0, w: 2 * half, h }));
      pen.rect({ x: -c1 / 2, y: -900, w: c1, h: 900 }, { layer: 'COLUMN', lw: 35 });
      conc(pen, rectPolygon({ x: -c1 / 2, y: -900, w: c1, h: 900 }), 2.2);
      const yt = h - cover - dia / 2;
      const xa = -c1 / 2 - ext, xb = c1 / 2 + ext;
      const pts = [];
      const yb = cover + dia / 2 + 40; // bottom leg of a U end, just above the bottom mesh
      const uEnd = uReturn > 0 && /U/.test(shape);
      if (uEnd) pts.push({ x: xa + uReturn, y: yb }, { x: xa, y: yb });
      else if (shape !== 'STR') pts.push({ x: xa, y: yt - hookLeg });
      pts.push({ x: xa, y: yt }, { x: xb, y: yt });
      if (shape === 'UU' && uEnd) pts.push({ x: xb, y: yb }, { x: xb - uReturn, y: yb });
      else if (shape === 'C') pts.push({ x: xb, y: yt - hookLeg });
      pen.pline(pts, { layer: 'REBAR-TOP', lw: 70 });
      if (uEnd) pen.dim({ x: xa, y: yb - 60 }, { x: xa + uReturn, y: yb - 60 }, -5, { text: `${uReturn}` });
      pen.barEnds({ x: xa, y: yt }, { x: xb, y: yt }, { layer: 'REBAR-TOP' });
      // bottom mesh
      pen.line({ x: -half + 60, y: cover + 6 }, { x: half - 60, y: cover + 6 }, { layer: 'REBAR-BOT', lw: 35 });
      // tendon (schematic)
      pen.pline([{ x: -half, y: h / 2 - 40 }, { x: -c1 / 2, y: h - cover - 45 }, { x: c1 / 2, y: h - cover - 45 }, { x: half, y: h / 2 - 40 }], { layer: 'PT-TENDON', ltype: 'DASHED' });
      pen.dim({ x: xa, y: h }, { x: -c1 / 2, y: h }, 7, { text: `${Math.round(ext)} (≥ ln/6)` });
      pen.dim({ x: c1 / 2, y: h }, { x: xb, y: h }, 7, { text: `${Math.round(ext)} (≥ ln/6)` });
      pen.dim({ x: -c1 / 2, y: h }, { x: c1 / 2, y: h }, 7, { text: `${c1}` });
      pen.dim({ x: half, y: 0 }, { x: half, y: h }, -6, { text: `${h}` });
      pen.text({ x: 0, y: h + 320 }, uReturn > 0 ? `T${dia}@${spacing} TOP E.W. OVER THE COLUMN - LENGTH PER THE OFFICE RULE (SEE NOTES)` : `T${dia}@${spacing} TOP E.W. WITHIN c + 3h - EXTEND ≥ ln/6 FROM FACE OF SUPPORT`, { layer: 'REBAR-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: 0, y: -980 }, uReturn > 0 ? `COLUMN  ·  BAR ENDING AT THE SLAB EDGE / AN OPENING ENDS IN A U: DOWN THE SLAB, ${uReturn} BACK AT THE BOTTOM` : `COLUMN  ·  90° HOOK ${hookLeg} (12Ø) WHERE BAR ENDS AT SLAB EDGE`, { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function sectionUEdge({ h, cover, leg, dia, edgeDia, spacing }) {
  const L = leg + 500;
  return {
    bbox: { minX: -420, maxX: L + 150, minY: -480, maxY: h + 460, cx: (L - 300) / 2, cy: h / 2 },
    draw(pen) {
      pen.rect({ x: 0, y: 0, w: L, h }, { layer: 'DETAIL', lw: 35 });
      conc(pen, rectPolygon({ x: 0, y: 0, w: L, h }));
      const c = cover + dia / 2;
      pen.pline([{ x: leg, y: c }, { x: c, y: c }, { x: c, y: h - c }, { x: leg, y: h - c }], { layer: 'REBAR-U', lw: 70 });
      pen.barEnds({ x: leg, y: c }, { x: leg, y: c }, { layer: 'REBAR-U' });
      pen.barEnds({ x: leg, y: h - c }, { x: leg, y: h - c }, { layer: 'REBAR-U' });
      // longitudinal edge bars T&B
      for (const y of [c + dia + 4, h - c - dia - 4]) for (const x of [c + dia + 20, c + dia + 110]) pen.circle({ x, y }, edgeDia / 2, { layer: 'REBAR-U' });
      // anchorage block at the edge
      pen.rect({ x: 0, y: h / 2 - 90, w: 260, h: 180 }, { layer: 'PT-TENDON', lw: 35 });
      pen.text({ x: 300, y: h / 2 - 20 }, 'PT ANCHORAGE', { layer: 'PT-TENDON', h: 1.5 });
      pen.pline([{ x: 260, y: h / 2 }, { x: L, y: h / 2 - 30 }], { layer: 'PT-TENDON', ltype: 'DASHED' });
      pen.dim({ x: 0, y: 0 }, { x: leg, y: 0 }, -7, { text: `LEG ${leg}` });
      pen.dim({ x: L, y: 0 }, { x: L, y: h }, -6, { text: `${h}` });
      pen.dim({ x: 0, y: h }, { x: cover, y: h }, 6, { text: `${cover}` });
      pen.text({ x: L / 2, y: h + 300 }, `T${dia}@${spacing} U-BARS AT SLAB EDGE + 2T${edgeDia} T&B LONGITUDINAL`, { layer: 'REBAR-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: L / 2, y: -400 }, 'BURSTING / SPALLING STEEL AT PT ANCHORAGE ZONE, ALL FREE EDGES', { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function planUCircle({ r, cover, leg, spacing, dia, ringR, ringDia }) {
  const R = r + cover + leg + 450;
  return {
    bbox: { minX: -R, maxX: R, minY: -R - 250, maxY: R + 250, cx: 0, cy: 0 },
    draw(pen) {
      pen.circle({ x: 0, y: 0 }, r, { layer: 'OPENING', lw: 35 });
      pen.hatch([circlePolygon(0, 0, r, 40)], { layer: 'OPENING-HATCH', pattern: 'ANSI37', spacing: 2 });
      pen.circle({ x: 0, y: 0 }, ringR, { layer: 'REBAR-U', lw: 50 });
      pen.circle({ x: 0, y: 0 }, ringR + 60, { layer: 'REBAR-U', lw: 50 });
      const n = Math.ceil((2 * Math.PI * (r + cover)) / spacing);
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2;
        const ca = Math.cos(a), sa = Math.sin(a);
        const r0 = r + cover, r1 = r + cover + leg;
        const off = 35;
        pen.line({ x: r0 * ca - off * sa, y: r0 * sa + off * ca }, { x: r1 * ca - off * sa, y: r1 * sa + off * ca }, { layer: 'REBAR-U', lw: 50 });
        pen.line({ x: r0 * ca + off * sa, y: r0 * sa - off * ca }, { x: r1 * ca + off * sa, y: r1 * sa - off * ca }, { layer: 'REBAR-U', lw: 50 });
        pen.arc({ x: r0 * ca, y: r0 * sa }, off, (a * 180) / Math.PI + 90, (a * 180) / Math.PI + 270, { layer: 'REBAR-U', lw: 50 });
      }
      pen.dim({ x: 0, y: 0 }, { x: r, y: 0 }, -5, { text: `R ${Math.round(r)}` });
      pen.dim({ x: r + cover, y: 0 }, { x: r + cover + leg, y: 0 }, -5, { text: `${leg}` });
      pen.text({ x: 0, y: R - 120 }, `${n}T${dia}@${spacing} RADIAL U-BARS (LEGS ${leg}) + ${2}T${ringDia} RINGS T&B`, { layer: 'REBAR-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: 0, y: -R + 40 }, 'U-BARS TOP & BOTTOM LEGS; RINGS LAPPED CLASS B', { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function planTrimmers({ w, h, ld, count, dia, diag, diagDia, diagL, uSpacing, uDia, label }) {
  const m = ld + 420;
  return {
    bbox: { minX: -m, maxX: w + m, minY: -m - 350, maxY: h + m + 250, cx: w / 2, cy: h / 2 - 50 },
    draw(pen) {
      pen.rect({ x: 0, y: 0, w, h }, { layer: 'OPENING', lw: 35 });
      pen.line({ x: 0, y: 0 }, { x: w, y: h }, { layer: 'OPENING' });
      pen.line({ x: w, y: 0 }, { x: 0, y: h }, { layer: 'OPENING' });
      pen.text({ x: w / 2, y: h / 2 + 60 }, label || 'OPENING', { layer: 'OPENING', h: 1.8, align: 'C' });
      for (let k = 0; k < count; k++) {
        const o = 60 + k * 75;
        // bottom & top edges
        pen.line({ x: -ld, y: -o }, { x: w + ld, y: -o }, { layer: 'REBAR-TRIM', lw: 60 });
        pen.line({ x: -ld, y: h + o }, { x: w + ld, y: h + o }, { layer: 'REBAR-TRIM', lw: 60 });
        pen.line({ x: -o, y: -ld }, { x: -o, y: h + ld }, { layer: 'REBAR-TRIM', lw: 60 });
        pen.line({ x: w + o, y: -ld }, { x: w + o, y: h + ld }, { layer: 'REBAR-TRIM', lw: 60 });
        pen.barEnds({ x: -ld, y: -o }, { x: w + ld, y: -o }, { layer: 'REBAR-TRIM' });
        pen.barEnds({ x: -o, y: -ld }, { x: -o, y: h + ld }, { layer: 'REBAR-TRIM' });
      }
      if (diag) {
        const d = diagL / 2 / Math.SQRT2;
        for (const [cx, cy, sx, sy] of [[0, 0, -1, -1], [w, 0, 1, -1], [w, h, 1, 1], [0, h, -1, 1]]) {
          const c = { x: cx + sx * 140, y: cy + sy * 140 };
          for (const off of [-40, 40]) {
            const ox = -sy * off / Math.SQRT2, oy = sx * off / Math.SQRT2;
            pen.line({ x: c.x - sy * d + ox, y: c.y + sx * d + oy }, { x: c.x + sy * d + ox, y: c.y - sx * d + oy }, { layer: 'REBAR-TRIM', lw: 60 });
          }
        }
      }
      if (uSpacing) {
        for (let x = 100; x < w; x += uSpacing) { pen.line({ x, y: 0 }, { x, y: -300 }, { layer: 'REBAR-U' }); pen.line({ x, y: h }, { x, y: h + 300 }, { layer: 'REBAR-U' }); }
        for (let y = 100; y < h; y += uSpacing) { pen.line({ x: 0, y }, { x: -300, y }, { layer: 'REBAR-U' }); pen.line({ x: w, y }, { x: w + 300, y }, { layer: 'REBAR-U' }); }
      }
      pen.dim({ x: -ld, y: -m + 250 }, { x: 0, y: -m + 250 }, 0, { text: `ld ${ld}` });
      pen.dim({ x: w, y: -m + 250 }, { x: w + ld, y: -m + 250 }, 0, { text: `ld ${ld}` });
      pen.dim({ x: 0, y: -m + 250 }, { x: w, y: -m + 250 }, 0, { text: 'W' });
      pen.text({ x: w / 2, y: h + m - 60 }, `${count}T${dia} T&B EACH SIDE, ANCHORED ld BEYOND CORNERS${diag ? `  +  2T${diagDia} DIAG. T&B L=${diagL}` : ''}${uSpacing ? `  +  T${uDia}@${uSpacing} U-BARS AT FREE EDGES` : ''}`, { layer: 'REBAR-TEXT', h: 1.8, align: 'C' });
    },
  };
}

export function sectionTrimmer({ h, cover, count, dia, uLeg, uDia, withU }) {
  const L = Math.max(uLeg + 500, 1400);
  return {
    bbox: { minX: -420, maxX: L + 150, minY: -450, maxY: h + 380, cx: (L - 300) / 2, cy: h / 2 },
    draw(pen) {
      pen.rect({ x: 0, y: 0, w: L, h }, { layer: 'DETAIL', lw: 35 });
      conc(pen, rectPolygon({ x: 0, y: 0, w: L, h }));
      pen.text({ x: -60, y: h / 2 }, 'OPENING', { layer: 'OPENING', h: 1.8, align: 'R', valign: 'M' });
      const c = cover + dia / 2;
      for (let k = 0; k < count; k++) {
        const x = c + 40 + k * 75;
        pen.circle({ x, y: c + 10 }, dia / 2, { layer: 'REBAR-TRIM' });
        pen.circle({ x, y: h - c - 10 }, dia / 2, { layer: 'REBAR-TRIM' });
      }
      if (withU) pen.pline([{ x: uLeg, y: c }, { x: c, y: c }, { x: c, y: h - c }, { x: uLeg, y: h - c }], { layer: 'REBAR-U', lw: 60 });
      pen.line({ x: 300, y: c + 30 }, { x: L - 60, y: c + 30 }, { layer: 'REBAR-BOT', lw: 35 });
      pen.dim({ x: L, y: 0 }, { x: L, y: h }, -6, { text: `${h}` });
      if (withU) pen.dim({ x: 0, y: 0 }, { x: uLeg, y: 0 }, -7, { text: `LEG ${uLeg}` });
      pen.text({ x: L / 2, y: h + 200 }, `${count}T${dia} TRIMMERS T&B${withU ? ` + T${uDia} U-BAR` : ''} - SECTION AT EDGE`, { layer: 'REBAR-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: L / 2, y: -380 }, 'TRIMMERS PLACED IN THE SAME LAYER AS THE MAIN MESH', { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function tendonProfile({ span, h }) {
  return {
    bbox: { minX: -400, maxX: span + 400, minY: -800, maxY: h + 450, cx: span / 2, cy: (h - 350) / 2 },
    draw(pen) {
      pen.rect({ x: 0, y: 0, w: span, h }, { layer: 'DETAIL', lw: 35 });
      for (const x of [0, span]) pen.rect({ x: x - 250, y: -700, w: 500, h: 700 }, { layer: 'COLUMN' });
      const pts = [];
      for (let i = 0; i <= 20; i++) { const t = i / 20; const x = span * t; const y = h - 60 - (h - 120) * 4 * t * (1 - t); pts.push({ x, y }); }
      pen.pline(pts, { layer: 'PT-TENDON', ltype: 'DASHED', lw: 50 });
      for (let i = 1; i < 4; i++) pen.dim({ x: (span * i) / 4, y: 0 }, { x: (span * i) / 4, y: 60 + (h - 120) * 4 * (i / 4) * (1 - i / 4) }, 0, { text: '____' });
      pen.text({ x: span / 2, y: h + 250 }, 'TYPICAL TENDON PROFILE - HEIGHTS TO BE FILLED AFTER PT DESIGN', { layer: 'CABLE-TEXT', h: 1.9, align: 'C' });
      pen.text({ x: span / 2, y: -300 }, 'DRAPE POINTS AT L/4 - L/2 - 3L/4 (TEMPLATE)', { layer: 'NOTES', h: 1.6, align: 'C' });
    },
  };
}

export function tendonLegend() {
  const rows = [
    ['LIVE (STRESSING) END', (pen, x, y) => { pen.line({ x, y }, { x: x + 600, y }, { layer: 'CABLE', lw: 50 }); pen.solid([{ x: x + 600, y: y - 60 }, { x: x + 720, y }, { x: x + 600, y: y + 60 }, { x: x + 600, y: y + 60 }], { layer: 'CABLE' }); }],
    ['DEAD END', (pen, x, y) => { pen.line({ x, y }, { x: x + 600, y }, { layer: 'CABLE', lw: 50 }); pen.circle({ x: x + 640, y }, 50, { layer: 'CABLE', lw: 50 }); }],
    ['INTERMEDIATE STRESSING', (pen, x, y) => { pen.line({ x, y }, { x: x + 720, y }, { layer: 'CABLE', lw: 50 }); pen.line({ x: x + 360, y: y - 80 }, { x: x + 360, y: y + 80 }, { layer: 'CABLE', lw: 50 }); }],
    ['TENDON GROUP (n STRANDS)', (pen, x, y) => { pen.line({ x, y }, { x: x + 720, y }, { layer: 'CABLE', lw: 50 }); pen.text({ x: x + 360, y: y + 60 }, 'n x 15.24', { layer: 'CABLE-TEXT', h: 1.6, align: 'C' }); }],
    ['ADDED BAR AT ANCHOR', (pen, x, y) => { pen.line({ x, y: y - 80 }, { x: x + 720, y: y - 80 }, { layer: 'REBAR-U', lw: 50 }); }],
  ];
  return {
    bbox: { minX: -100, maxX: 3400, minY: -rows.length * 260, maxY: 250, cx: 1650, cy: -rows.length * 130 + 90 },
    draw(pen) {
      pen.text({ x: 0, y: 60 }, 'TENDON SYMBOLS (TO BE USED WHEN THE LAYOUT IS ADDED)', { layer: 'CABLE-TEXT', h: 1.8 });
      rows.forEach(([label, fn], i) => { const y = -180 - i * 260; fn(pen, 0, y); pen.text({ x: 900, y: y - 40 }, label, { layer: 'NOTES', h: 1.7 }); });
    },
  };
}

export function notationLegend({ thickness, fc, fy, cover }) {
  const items = [
    ['OUTLINE', 'thick', 'SLAB EDGE / OUTLINE'],
    ['COLUMN', 'hatch', 'COLUMN BELOW'],
    ['OPENING', 'line', 'OPENING (CROSSED)'],
    ['VOID', 'hatch2', 'VOID / ACUAR FORMER ZONE'],
    ['PT-ZONE', 'line', 'PT SLAB ZONE BOUNDARY'],
    ['REBAR-U', 'line', 'U-BAR REGION (CIRCULAR)'],
    ['GRID', 'line', 'GRID LINE'],
  ];
  return {
    bbox: { minX: -100, maxX: 3400, minY: -items.length * 230 - 300, maxY: 250, cx: 1650, cy: -items.length * 115 - 20 },
    draw(pen) {
      pen.text({ x: 0, y: 60 }, `SLAB ${thickness} mm  ·  f'c ${fc} MPa  ·  fy ${fy} MPa  ·  COVER ${cover} mm`, { layer: 'TEXT-TITLE', h: 1.8 });
      items.forEach(([layer, kind, label], i) => {
        const y = -160 - i * 230;
        if (kind === 'hatch' || kind === 'hatch2') { pen.rect({ x: 0, y: y - 70, w: 600, h: 140 }, { layer }); pen.hatch([rectPolygon({ x: 0, y: y - 70, w: 600, h: 140 })], { layer: layer + '-HATCH', pattern: kind === 'hatch2' ? 'ANSI37' : 'ANSI31', spacing: 1 }); }
        else pen.line({ x: 0, y }, { x: 600, y }, { layer, lw: kind === 'thick' ? 50 : undefined });
        pen.text({ x: 760, y: y - 50 }, label, { layer: 'NOTES', h: 1.7 });
      });
    },
  };
}

/** Punching link (closed C-link) shape with its bending dimensions, reference style. */
export function punchingLink({ h, cover, dia, rowSpacing, legSpacing, rows }) {
  const web = h - 2 * cover;
  return {
    bbox: { minX: -700, maxX: 1500, minY: -web - 500, maxY: 450, cx: 400, cy: -web / 2 },
    draw(pen) {
      // link in elevation
      pen.pline([{ x: 0, y: 0 }, { x: 110, y: 0 }, { x: 110, y: -web }, { x: 0, y: -web }], { layer: 'REBAR-PUNCH', lw: 70 });
      pen.line({ x: 0, y: 0 }, { x: 0, y: -60 }, { layer: 'REBAR-PUNCH', lw: 70 });
      pen.line({ x: 0, y: -web }, { x: 0, y: -web + 60 }, { layer: 'REBAR-PUNCH', lw: 70 });
      pen.dim({ x: 0, y: 0 }, { x: 110, y: 0 }, 4, { text: '110' });
      pen.dim({ x: 110, y: 0 }, { x: 110, y: -web }, -4, { text: String(web) });
      pen.dim({ x: 0, y: -web }, { x: 110, y: -web }, -4, { text: '110' });
      pen.text({ x: 55, y: 120 }, `T${dia} LINK`, { layer: 'REBAR-TEXT', h: 1.8, align: 'C' });
      // plan arrangement beside it
      const ox = 600;
      pen.rect({ x: ox, y: -web - 100, w: 300, h: web + 100 }, { layer: 'COLUMN' });
      pen.solid([{ x: ox, y: -web - 100 }, { x: ox + 300, y: -web - 100 }, { x: ox + 300, y: 0 }, { x: ox, y: 0 }], { layer: 'COLUMN-HATCH' });
      for (let r = 1; r <= rows; r++) {
        const x = ox + 300 + r * rowSpacing;
        pen.line({ x, y: -web - 100 }, { x, y: 0 }, { layer: 'REBAR-PUNCH' });
        for (let yy = -web - 100 + 40; yy < 0; yy += legSpacing / 2) pen.circle({ x, y: yy }, 8, { layer: 'REBAR-PUNCH' });
      }
      pen.dim({ x: ox + 300, y: 40 }, { x: ox + 300 + rowSpacing, y: 40 }, 3, { text: `${rowSpacing} (d/2)` });
      pen.dim({ x: ox + 300, y: -web - 160 }, { x: ox + 300 + rows * rowSpacing, y: -web - 160 }, -3, { text: `${rows} ROWS` });
      pen.text({ x: ox + 150, y: -web / 2 }, 'COL.', { layer: 'TEXT', h: 1.6, align: 'C', valign: 'M', color: 7 });
      pen.text({ x: 400, y: -web - 380 }, `LINKS T${dia}: ${rows} ROWS @ ${rowSpacing} FROM FACE, LEGS @ ${legSpacing} ALONG THE FACE`, { layer: 'REBAR-TEXT', h: 1.7, align: 'C' });
    },
  };
}

/**
 * The office punching detail (PS types): stirrup strips leaving every column face, `legs` legs (legs / 2 closed
 * stirrups side by side) in `rows` rows at S from the face. Plan at the column, the strip section (number of legs)
 * and the strip elevation (number of rows) with the tag key.
 */
export function punchingStrips({ h, cover, dia, s, rows, legs }) {
  const ns = Math.max(1, legs / 2);
  const c1 = 700, len = rows * s, pitch = c1 / ns, sw = pitch - 60;
  const web = h - 2 * cover;
  return {
    bbox: { minX: -c1 / 2 - len - 350, maxX: c1 / 2 + len + 1500, minY: -c1 / 2 - len - 700, maxY: c1 / 2 + len + 950, cx: 500, cy: 0 },
    draw(pen) {
      // plan
      pen.solid([{ x: -c1 / 2, y: -c1 / 2 }, { x: c1 / 2, y: -c1 / 2 }, { x: c1 / 2, y: c1 / 2 }, { x: -c1 / 2, y: c1 / 2 }], { layer: 'COLUMN-HATCH' });
      pen.rect({ x: -c1 / 2, y: -c1 / 2, w: c1, h: c1 }, { layer: 'COLUMN' });
      for (const dir of ['x', 'y']) for (const sg of [-1, 1]) for (let i = 0; i < ns; i++) {
        const t0 = -c1 / 2 + pitch * i + 30;
        const face = sg * c1 / 2;
        const r = dir === 'x' ? { x: Math.min(face, face + sg * len), y: t0, w: len, h: sw } : { x: t0, y: Math.min(face, face + sg * len), w: sw, h: len };
        pen.rect(r, { layer: 'REBAR-PUNCH', lw: 35 });
        for (let k = 1; k <= rows; k++) { const o = face + sg * k * s; if (dir === 'x') pen.line({ x: o, y: t0 }, { x: o, y: t0 + sw }, { layer: 'DETAIL' }); else pen.line({ x: t0, y: o }, { x: t0 + sw, y: o }, { layer: 'DETAIL' }); }
      }
      pen.dim({ x: c1 / 2, y: -c1 / 2 - 150 }, { x: c1 / 2 + s, y: -c1 / 2 - 150 }, -3, { text: `S=${s}` });
      pen.dim({ x: c1 / 2, y: c1 / 2 + 150 }, { x: c1 / 2 + len, y: c1 / 2 + 150 }, 3, { text: `${rows} ROWS` });
      pen.text({ x: 0, y: -c1 / 2 - len - 380 }, `PLAN: ${rows}R-${legs}-T${dia} EACH SIDE, S=${s}`, { layer: 'REBAR-TEXT', h: 1.7, align: 'C' });
      // strip section: the closed stirrups side by side (number of legs) - to the right
      const ox = c1 / 2 + len + 350, oy = -c1 / 2 - len - 100;
      pen.rect({ x: ox, y: oy, w: ns * pitch + 60, h: web + 2 * cover }, { layer: 'DETAIL', lw: 35 });
      for (let i = 0; i < ns; i++) {
        const x0 = ox + 30 + pitch * i + 30;
        pen.rect({ x: x0, y: oy + cover, w: sw, h: web }, { layer: 'REBAR-PUNCH', lw: 50 });
        for (const [xx, yy] of [[x0, oy + cover], [x0 + sw, oy + cover], [x0, oy + cover + web], [x0 + sw, oy + cover + web]]) pen.circle({ x: xx, y: yy }, 12, { layer: 'REBAR-PUNCH' });
      }
      pen.text({ x: ox + (ns * pitch + 60) / 2, y: oy - 260 }, `SECTION: ${legs} LEGS (${ns} STIRRUPS T${dia})`, { layer: 'REBAR-TEXT', h: 1.6, align: 'C' });
      // strip elevation: the rows - above the section
      const ey = oy + web + 2 * cover + 350;
      pen.rect({ x: ox, y: ey, w: len + 200, h: web + 2 * cover }, { layer: 'DETAIL', lw: 35 });
      for (let k = 1; k <= rows; k++) pen.line({ x: ox + k * s, y: ey + cover }, { x: ox + k * s, y: ey + cover + web }, { layer: 'REBAR-PUNCH', lw: 50 });
      pen.dim({ x: ox, y: ey + web + 2 * cover + 40 }, { x: ox + rows * s, y: ey + web + 2 * cover + 40 }, 3, { text: `${rows} ROWS @ S=${s}` });
      pen.text({ x: ox + (len + 200) / 2, y: ey - 220 }, 'ELEVATION: NO. OF ROWS FROM THE COLUMN FACE', { layer: 'REBAR-TEXT', h: 1.6, align: 'C' });
    },
  };
}

/** Detail 9: blockwork support beam through the void between two openings - section through the strip. */
export function blockBeamSection({ h, cover, width, dia, count, linkDia, linkSpacing, ta }) {
  const w = Math.max(width, 150);
  return {
    bbox: { minX: -w / 2 - 900, maxX: w / 2 + 900, minY: -700, maxY: h + 1100, cx: 0, cy: h / 2 },
    draw(pen) {
      pen.rect({ x: -w / 2, y: 0, w, h }, { layer: 'DETAIL', lw: 35 });
      conc(pen, rectPolygon({ x: -w / 2, y: 0, w, h }));
      pen.rect({ x: -w / 2 - 800, y: 0, w: 800, h }, { layer: 'DETAIL' }); pen.rect({ x: w / 2, y: 0, w: 800, h }, { layer: 'DETAIL' });
      pen.text({ x: -w / 2 - 400, y: h / 2 }, 'VOID', { layer: 'TEXT', h: 1.6, align: 'C', valign: 'M' }); pen.text({ x: w / 2 + 400, y: h / 2 }, 'VOID', { layer: 'TEXT', h: 1.6, align: 'C', valign: 'M' });
      // blockwork above
      for (let y = h; y < h + 600; y += 200) pen.rect({ x: -w / 2, y, w, h: 200 }, { layer: 'DETAIL' });
      pen.text({ x: 0, y: h + 700 }, 'BLOCKWORK WALL ABOVE', { layer: 'TEXT', h: 1.6, align: 'C' });
      // link and bars
      pen.rect({ x: -w / 2 + cover, y: cover, w: w - 2 * cover, h: h - 2 * cover }, { layer: 'REBAR-PUNCH', lw: 50 });
      const xs = count > 1 ? [-w / 2 + cover + dia, w / 2 - cover - dia] : [0];
      for (const x of xs) { pen.circle({ x, y: cover + dia }, dia / 2 + 2, { layer: 'REBAR-BOT' }); pen.circle({ x, y: h - cover - dia }, dia / 2 + 2, { layer: 'REBAR-TOP' }); }
      pen.dim({ x: -w / 2, y: -120 }, { x: w / 2, y: -120 }, -4, { text: `${Math.round(width)} (150 MIN.)` });
      pen.dim({ x: w / 2 + 850, y: 0 }, { x: w / 2 + 850, y: h }, -4, { text: `${h}` });
      pen.text({ x: 0, y: -520 }, `${count}T${dia} TOP & BOTTOM, EXTEND TA = ${ta} BEYOND EACH VOID · T${linkDia}@${linkSpacing} LINKS`, { layer: 'REBAR-TEXT', h: 1.7, align: 'C' });
    },
  };
}
