/**
 * A tiny RAM Concept model written with node:sqlite, shared by the generator and the drawings-module tests.
 */
import { join } from 'node:path';

/** A tiny RAM Concept model written with node:sqlite: 12 x 8 m slab meshed 3 x 2, five columns, one wall crossing the edge, two tendons, two bands. */
export async function buildSyntheticCpt(dir, { beam = false, step = false } = {}) {
  const { DatabaseSync } = await import('node:sqlite');
  const path = join(dir, `synthetic${beam ? '-beam' : ''}${step ? '-step' : ''}.cpt`);
  const db = new DatabaseSync(path);
  const P = (x, y) => `[${x * 10}][${y * 10}]`; // mm → 0.1 mm
  const create = (t, cols) => db.exec(`create table "${t}" (${cols.map((c) => `"${c}"`).join(',')})`);
  const insert = (t, rowsToAdd) => { for (const r of rowsToAdd) db.prepare(`insert into "${t}" (${Object.keys(r).map((k) => `"${k}"`).join(',')}) values (${Object.keys(r).map(() => '?').join(',')})`).run(...Object.values(r)); };
  create('Cover', ['Heading1', 'Heading2', 'Heading3', 'Heading4']); insert('Cover', [{ Heading1: 'SPAN TECH', Heading2: 'SYNTHETIC SLAB', Heading3: 'PART 1', Heading4: 'R0' }]);
  create('Concrete', ['UID', 'Name', 'FcFinal', 'FcuFinal']); insert('Concrete', [{ UID: 1, Name: 'C32/40', FcFinal: 0.32, FcuFinal: 0.4 }]);
  create('Rebar', ['UID', 'Name', 'Fy', 'As']); insert('Rebar', [{ UID: 11, Name: 'T12', Fy: 4.2, As: 11300 }, { UID: 16, Name: 'T16', Fy: 4.2, As: 20100 }]);
  create('SlabArea', ['UID', 'MultiPoint', 'SlabThickness', 'Priority', 'SlabBehavior', 'TOC']);
  insert('SlabArea', [
    { UID: 21, MultiPoint: `${P(0, 0)}${P(12000, 0)}${P(12000, 8000)}${P(0, 8000)}`, SlabThickness: 2500, Priority: 1, SlabBehavior: 0, TOC: 0 },
    { UID: 22, MultiPoint: `${P(4000, 0)}${P(8000, 0)}${P(8000, 4000)}${P(4000, 4000)}`, SlabThickness: 4000, Priority: 2, SlabBehavior: 0, TOC: 0 },
  ]);
  create('ElementCornerNode', ['UID', 'Point0']);
  create('QuadSlabElement', ['UID', 'CornerNode0', 'CornerNode1', 'CornerNode2', 'CornerNode3', 'SlabThickness', 'TOC']);
  const xs = [0, 4000, 8000, 12000], ys = [0, 4000, 8000];
  const nodes = []; for (const y of ys) for (const x of xs) nodes.push(P(x, y));
  insert('ElementCornerNode', nodes.map((p, i) => ({ UID: 100 + i, Point0: p })));
  const quads = [];
  // with `step`, the right-hand third of the slab (x 8..12 m) sits 300 mm lower (TOC -300): a separate slab for the office
  for (let j = 0; j < 2; j++) for (let i = 0; i < 3; i++) quads.push({ UID: 200 + quads.length, CornerNode0: P(xs[i], ys[j]), CornerNode1: P(xs[i + 1], ys[j]), CornerNode2: P(xs[i + 1], ys[j + 1]), CornerNode3: P(xs[i], ys[j + 1]), SlabThickness: i === 1 && j === 0 ? 4000 : 2500, TOC: step && i === 2 ? -3000 : 0 });
  insert('QuadSlabElement', quads);
  create('Column', ['UID', 'Point0', 'B', 'D', 'Angle', 'SupportSet']);
  insert('Column', [
    { UID: 31, Point0: P(0, 0), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' }, { UID: 32, Point0: P(12000, 0), B: 4000, D: 8000, Angle: Math.PI / 2, SupportSet: 'below' }, // the second one turned 90°
    { UID: 33, Point0: P(0, 8000), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' }, { UID: 34, Point0: P(12000, 8000), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' },
    { UID: 35, Point0: P(6000, 4000), B: 0, D: 6000, Angle: 0, SupportSet: 'below' },
  ]);
  if (beam) {
    // an interior beam 300 wide x 600 deep running across the slab at x = 9 m (slab on both sides), and an edge beam along y = 0
    create('Beam', ['UID', 'Point0', 'Point1', 'LeftPt0', 'RightPt0', 'Width', 'SlabThickness', 'TOC', 'Priority', 'BeamBehavior', 'BeamIsMeshedAsSlab']);
    insert('Beam', [
      { UID: 45, Point0: P(9000, 0), Point1: P(9000, 8000), LeftPt0: P(8850, 0), RightPt0: P(9150, 0), Width: 3000, SlabThickness: 6000, TOC: 0, Priority: 10, BeamBehavior: 'no-torsion two-way slab', BeamIsMeshedAsSlab: 1 },
      { UID: 46, Point0: P(0, 150), Point1: P(12000, 150), LeftPt0: P(0, 0), RightPt0: P(0, 300), Width: 3000, SlabThickness: 6000, TOC: 0, Priority: 10, BeamBehavior: 'no-torsion two-way slab', BeamIsMeshedAsSlab: 1 },
    ]);
  }
  create('LineSupport', ['UID', 'Point0', 'Point1']); insert('LineSupport', [{ UID: 41, Point0: P(-3000, 2000), Point1: P(5000, 2000) }]);
  create('TendonLayer', ['UID', 'SpanSet']); insert('TendonLayer', [{ UID: 51, SpanSet: 'latitude' }, { UID: 52, SpanSet: 'longitude' }]);
  create('TendonLevel', ['UID', 'ParentUID']); insert('TendonLevel', [{ UID: 61, ParentUID: 51 }, { UID: 62, ParentUID: 52 }]);
  create('TendonCategory', ['UID', 'ParentUID']); insert('TendonCategory', [{ UID: 71, ParentUID: 61 }, { UID: 72, ParentUID: 62 }]);
  create('Tendon', ['UID', 'ParentUID', 'TendonNode0', 'TendonNode1', 'NumStrands', 'Harped']);
  insert('Tendon', [
    { UID: 81, ParentUID: 71, TendonNode0: P(0, 2000), TendonNode1: P(6000, 2000), NumStrands: 4, Harped: 0 }, { UID: 82, ParentUID: 71, TendonNode0: P(6000, 2000), TendonNode1: P(12000, 2000), NumStrands: 4, Harped: 0 },
    { UID: 83, ParentUID: 72, TendonNode0: P(3000, 0), TendonNode1: P(3000, 8000), NumStrands: 3, Harped: 0 },
  ]);
  // the CGS profile: nodes above the soffit (reference 4): high at the columns, low at mid-span
  create('TendonNode', ['UID', 'Point0', 'ElevationReference', 'ElevationValue', 'Surface', 'Soffit']);
  insert('TendonNode', [
    { UID: 85, Point0: P(0, 2000), ElevationReference: 4, ElevationValue: 1250, Surface: 0, Soffit: -2500 },
    { UID: 86, Point0: P(6000, 2000), ElevationReference: 4, ElevationValue: 2100, Surface: 0, Soffit: -2500 },
    { UID: 87, Point0: P(12000, 2000), ElevationReference: 4, ElevationValue: 1250, Surface: 0, Soffit: -2500 },
    { UID: 88, Point0: P(3000, 0), ElevationReference: 5, ElevationValue: 1250, Surface: 0, Soffit: -2500 },
    { UID: 89, Point0: P(3000, 8000), ElevationReference: 5, ElevationValue: 1250, Surface: 0, Soffit: -2500 },
  ]);
  create('Jack', ['UID', 'TendonNode0', 'JackStress', 'Elongation']); insert('Jack', [{ UID: 91, TendonNode0: P(0, 2000), JackStress: 14.88, Elongation: 850 }]);
  create('StrandMaterial', ['UID', 'Aps', 'Fpu']); insert('StrandMaterial', [{ UID: 1, Aps: 9870, Fpu: 18.6 }]);
  create('ConcentratedRebar', ['UID', 'ParentUID', 'BarFace', 'SpanDirection', 'BarType', 'BarCount', 'BarSpacing', 'Point0', 'Point1', 'LeftPoint', 'RightPoint', 'BarEnd0', 'BarEnd1', 'AbsoluteElevation']);
  insert('ConcentratedRebar', [
    { UID: 301, ParentUID: 1, BarFace: 2, SpanDirection: 1, BarType: 11, BarCount: 5, BarSpacing: 2000, Point0: P(0, 4000), Point1: P(12000, 4000), LeftPoint: P(6000, 3600), RightPoint: P(6000, 4400), BarEnd0: 0, BarEnd1: 0, AbsoluteElevation: -2000 },
    { UID: 302, ParentUID: 1, BarFace: 1, SpanDirection: 2, BarType: 16, BarCount: 6, BarSpacing: 1500, Point0: P(6000, 1500), Point1: P(6000, 6500), LeftPoint: P(5250, 4000), RightPoint: P(6750, 4000), BarEnd0: 0, BarEnd1: 0, AbsoluteElevation: -400 },
  ]);
  create('IndividualBars', ['UID', 'BarFace', 'SpanDirection', 'Point0', 'Point1', 'AbsoluteElevation']);
  const ys5 = [3600, 3800, 4000, 4200, 4400];
  insert('IndividualBars', [{ UID: 401, BarFace: 2, SpanDirection: 1, Point0: ys5.map((y) => P(0, y)).join(''), Point1: ys5.map((y) => P(12000, y)).join(''), AbsoluteElevation: -2000 }]);
  create('TransverseRebarRegion', ['UID', 'Point0', 'Point1', 'BarType', 'StirrupLegs', 'StirrupSpacing']);
  insert('TransverseRebarRegion', [{ UID: 501, Point0: P(4000, 4000), Point1: P(8000, 4000), BarType: 11, StirrupLegs: 2, StirrupSpacing: 1500 }]);
  // stud rails designed by RAM at the middle column: 4 rails of 10 studs @100 leaving every face
  create('SsrSystem', ['UID', 'Name', 'StudArea']); insert('SsrSystem', [{ UID: 14, Name: '10mm SSR', StudArea: 7850 }]);
  create('SsrSet', ['UID', 'Point0', 'Point1', 'DesignedBy', 'SsrSystem', 'StudSpacingFirst', 'StudSpacingTypical', 'StudCount', 'LocationPoint']);
  const rails0 = [], rails1 = [];
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) for (let k = 0; k < 4; k++) { const t = -150 + k * 100; const a = { x: 6000 + dx * 300 + (dx ? 0 : t), y: 4000 + dy * 300 + (dy ? 0 : t) }; rails0.push(P(a.x, a.y)); rails1.push(P(a.x + dx * 1000, a.y + dy * 1000)); }
  insert('SsrSet', [{ UID: 701, Point0: rails0.join(''), Point1: rails1.join(''), DesignedBy: 2, SsrSystem: 14, StudSpacingFirst: 1000, StudSpacingTypical: 1000, StudCount: rails0.map(() => '[10]').join(''), LocationPoint: P(6000, 4000) }]);
  create('PunchCheck', ['UID', 'Name', 'Point0', 'SsrSystem', 'CoverToCGS', 'TopCover', 'BottomCover']);
  insert('PunchCheck', [{ UID: 601, Name: 'PC1', Point0: P(6000, 4000), SsrSystem: 'SSR', CoverToCGS: 350, TopCover: 350, BottomCover: 250 }]);
  db.close();
  return path;
}

