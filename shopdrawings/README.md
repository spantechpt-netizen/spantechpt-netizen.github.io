# Shop Drawings Generator · مولّد لوحات التسليح والكابلات

Turns the consultant's **combined structural drawing** (one DXF with the slab
plans, grid, columns, openings, voids, PT zones and notes) into a submission
package of **reinforcement shop drawings** plus an **empty PT cables template**,
as AutoCAD DXF with every sheet as a **block / Xref**, with previews and
bar bending schedules.

يحوّل المخطط الإنشائي المجمّع (ملف DXF واحد يحتوي مساقط البلاطات، المحاور،
الأعمدة، الفتحات، الأكوار، مناطق الـ PT والملاحظات) إلى حزمة لوحات تسليح جاهزة
للتقديم للاستشاري + قالب فارغ لجداول الكابلات، بصيغة DXF مع كل لوحة كـ Block /
Xref مستقل، مع معاينات وجداول قص وثني.

No dependencies: Node 22 only, like the rest of the CRM.

The drafting follows the convention of the office's existing reinforcement
drawings (BBR-style slab sheets): one representative bar per group with the
call-out `9T12@400-T2-05-(L=11300)` above it, the straight length under the
bar and the hook leg at hooked ends; pieces of a long run called out one by
one with the lap of the next piece drawn offset; `Ø12@200-B1` mesh labels
per bay; one plan per layer (T1/T2, B1/B2) side by side; solid black
columns, hatched walls and sunken slabs, green slab edge and beams, crossed
openings; punching links as rows per column face (`5X15-T12-90`) with red
`PS` type labels.

## Run · التشغيل

```bash
# your drawing
node shopdrawings/cli.mjs --input path/to/STRUCTURAL-COMBINED.dxf --out ./package \
  --project "PROJECT NAME" --client "CLIENT" --location "RIYADH, KSA" \
  --prepared "ENG. NAME" --checked "ENG. NAME" --approved "ENG. NAME" --rev 00

# the bundled demo (writes shopdrawings/samples/output)
npm run shopdrawings:sample
```

`--config file.json` takes `{ "meta": {...}, "spec": {...} }` to override the
title-band fields or any reinforcement assumption (see `DEFAULT_SPEC` in
`lib/rebar.mjs`).

Input is a **DXF** (any release, ASCII), a **RAM Concept** `.cpt` model
(see below), a **LibreDWG JSON** export
(`dwgread -O json -o plan.json plan.dwg`), or a **DWG** directly when
`dwgread` from [GNU LibreDWG](https://www.gnu.org/software/libredwg/) is on
the `PATH` (or named in `DWGREAD`). From PDF: `PDFIMPORT` in AutoCAD, then
`DXFOUT`. Units are read from `$INSUNITS` or inferred from the extents.
Bound Xrefs (`XREF_1st FLOOR$0$BBR-COLUMN` style layer names) are exploded
and read like native layers; grid labels inside bubble blocks are read from
their attributes.

### RAM Concept input · من ملف رام

A `.cpt` file (RAM Concept v8 or later, which is an SQLite database) is read
directly, no export needed:

```bash
node shopdrawings/cli.mjs --input 1st-floor.cpt --out ./package --level "1ST FLOOR" --config majd.json
```

What is taken from the model: the slab mesh (outline of every separate slab
body, thickness per mesh element, thickened areas), columns (rectangular with
their angle, or round), wall line supports (clipped to the slab), the
tendons chained node to node with strand counts, jacks, jacking stress and
elongation, the designed reinforcement bands (`ConcentratedRebar`) with every
individual bar RAM stored, the transverse (shear) regions, punching checks,
materials (f'c, fy, covers) and the four title headings. RAM internal units
(0.1 mm, 100 MPa, 0.01 mm²) are converted on read.

Each separate slab body becomes its own level (`L01`, `L02`, …), rotated into
its own orthogonal frame when its columns are set at an angle (the north
arrow follows). Grid lines do not exist in RAM, so the grid is derived from
the column positions and lettered / numbered consecutively; the assumption is
printed on the sheets. The office standard reinforcement (bottom mesh, top
bars over columns, U-bars, trimmers, punching links) is applied to the RAM
slab exactly as to a G.A. drawing; the bands designed in RAM are drawn on top
of it as additional reinforcement on sheets 02A / 03A (`ADD.B1-01`,
`ADD.T2-03` marks, one representative bar per band with the first / last bar
dashed), and the cables sheet is filled with the RAM tendon layout and
schedule. On curved or skew slab edges the mesh rows are grouped (250 mm
tolerance) and their cut lengths scheduled in 500 mm steps
(`spec.bottom.groupTol`, `spec.bottom.lengthStep`). Punching results are not stored in the file, so the punching sheet
stays the minimum detailing arrangement to be confirmed against the RAM
punching report.

`--config` meta fields: `project`, `location`, `projectCode`, `client`,
`engineer`, `contractor`, `company`, `prefix` (drawing number prefix),
`gridTag` (sheet tag under every grid bubble, e.g. `S02`), `revision`,
`issued`, `revisions` (list of `{rev, description, date, by}`),
`references` (list of `{discipline: ARCH|STRUCT|MEP, no, rev}`),
`coordinated` (four initials), `prepared`, `checked`, `approved`.

### Design drawings · لوحات التصميم

The same generator also produces the **office's own design drawings**: the input is the office's reinforcement
design plan (the RFT drawing as the design team draws it) and the rules of the office's **General Details** sheet
for PT / flat slabs. Everything the designer drew is kept exactly as drawn (bars, call-outs, distribution
dimensions, dots, mesh labels, camber notes, level tags), and the reinforcement the General Details ask for is added
on the plan at the places each detail refers to, in the **same bar convention**: one line on `REO-TOP` / `REO-BOT`,
the call-out `T10-200 (T)` over `L=2400` in text style `BW` (isocp.shx) h = 150 parallel to the bar, the
distribution width as a **real DIMENSION entity in the office style `DIM100`** (text 250, oblique ticks 150, green
number, text above the line, and no extension lines at all — `DIMSE1/DIMSE2` on, `DIMEXE` 0), and a yellow dot where
the bar meets it. The designer's own DIMENSIONs are re-emitted the same way. Every added bar carries a circled `D#`
(layer `DETAIL-REF`, freeze it to hide) naming the General Detail it comes from.

```bash
node shopdrawings/cli.mjs --input RFT_Drawings.dxf --out ./design --mode design --level "TYPICAL FLOOR" --config project.json
node shopdrawings/cli.mjs --input SLAB.cpt --out ./design --mode design --level "1ST FLOOR"     # straight from the RAM Concept model
```

From a RAM Concept `.cpt` the bands designed in RAM become the designer's reinforcement, drawn in the same convention
(RAM's top bands over the columns and its bottom bands local to a drop panel are replaced by the office column bars and the
detail 4 extra bars; bands shorter than 1.2 m are export artefacts and ignored)
(`T16-150 (T)` over `L=5000`, distribution DIMENSION across the band width, dot, `U500` ends at the edge), walls (line
supports) get a body (`spec.wallThickness`, 250 default), the slab and every thickened zone are tagged with their
thickness, and the rules below are added on top exactly as for an RFT plan.

Each slab outline of the plan becomes a PART (the office splits its plans the same way) with four sheets:
01 framing (outline, columns, walls, openings, thickness zones, edge beams, levels, camber), 02 bottom and 03 top
(the designer's bars + the additions, schedule of the additions only), 04 punching (PS tags per column, preliminary),
plus a cover / index. Output goes to `DESIGN_DRAWINGS_PACKAGE.dxf` and one DXF per sheet as before.

| Detail | Rule applied | Where |
|---|---|---|
| Perimeter (office rule) | continuous T12@150 between the column top bars: D6 **U-bar** 4 m (equal top / bottom legs) at a free edge, D1 **L-bar** of the same 4 m total, 400 into the beam + 3600 on top, at an edge beam; curved edges are one run with the length along the edge | every slab edge |
| Bar ends (office rule) | every top bar ending at the outer slab edge ends in a U with a 500 mm bottom leg (`U500`) where the edge is free, in an L 400 mm down into the beam (`L400`) where the outer edge carries a beam parallel to it; at an opening always a U | designer's bars and additions |
| Column top bars (office rule) | two perpendicular groups along the column axis (or the tendon direction), each exactly as long as the drop panel (`dropMax` 6 m tells a drop from a thickened strip) or 4 m, edge columns 70 % with the U / L at the edge; the designer's bars over the column are re-lengthed and their `L=` rewritten, missing groups added, and each group is distributed over the length of the crossing group (the designer's dimension is re-measured or one is added) | every column |
| Inside the slab | bars and distribution dimensions never leave the slab outline (clipped; perimeter dimensions sit 350 mm inside the edge) | everything added |
| D2 slab edge at core / retaining wall | T12@200 U-bar (LB 1200, LC = t − cover, LA from the designer's wall bar next to it); the 10T12 (T&B) parallel bars only with `walls.parallelBars` | every wall face that looks onto the slab |
| D3 varying thickness | lap 500 at the step (note) | thickness zones |
| D4 column drop / thickened zone | T12@250 (B) extra reinforcement both ways, 50 Ø beyond the zone | nested outline with a thickness written inside (e.g. `280`) |
| D5 corners | 3T12 diagonals 2 m T&B at re-entrant slab corners; 3T16 at wall corners only with `walls.cornerDiagonals` | outline (and walls when asked) |
| D7 MEP voids | three groups: G1 / G2 longitudinal T&B parallel to the sides, G3 diagonals at 45° crossing both, per the void size table, with the count of crossing bars | openings **not** enclosed by concrete walls / beams / column faces and not already trimmed by the designer (T&B bars next to them) |
| Enclosed openings | no trimmers: an L-bar `T12-150 LBAR (T)` (400 into the beam + 3600 on top) along every side that runs along a beam, the wall U-bars along the sides at walls | openings enclosed by beams / walls / columns |
| Bottom mesh indication | `BOTTOM MESH T10@200` (optional, `thicknessMesh`) | at every change of slab thickness (thickened zones, RC tags) |
| D12 punching | PS1 10R-4-T12 (interior) / PS2 12R-4-T12 (edge), s = 100, with the schedule | every column, to be confirmed by the punching design |

Every added call-out looks for a free place: the pair `T12-150 U-BAR` / `L=4000` slides along its bar (and may swap
sides), the `D#` tag and the `U500` tags move likewise, the perimeter distribution dimensions sit just outside the slab
edge, and the wall U-bar dimension picks the freest of three offsets. Everything already on the plan (the designer's
call-outs and dimensions, columns, walls, notes) is an obstacle; when no free place exists the least-overlapping one is
used. Anchorage-dependent details (slab edge at live anchors, bursting spirals, pan-box trimmers) need the tendon layout and
are left out on purpose; site-specific details (blockwork support beam, crane and placing-boom openings) apply only
where drawn. What the plan reads: walls = long or non-rectangular shapes on the column layer, thickness from the `RC230`
tag, edge beams from `S-BEAM` line pairs along the outline, the designer's reinforcement from the `REO-*` layers with
its call-outs (`(T)`, `(B)`, `T&B` decide the sheet), DIMENSION entities on `diamension`, `DOT` inserts, mesh labels on
`9_TEXT`, `CAMBER` notes and `T.O.C` tags on `TEXT-4`.

## What comes out · المخرجات

```
<out>/
  SHOP_DRAWINGS_PACKAGE.dxf     every sheet block, laid out side by side
  dxf/<DRAWING_NO>_<BLOCK>.dxf  one file per sheet: the block + one insert at 0,0 (attach as Xref)
  preview/*.svg                 open in any browser
  schedules/*.csv               bar bending schedule per sheet
  model.json                    what was read: levels, grid, columns, regions, spec
  REPORT.md                     findings, assumptions, lengths, sheet list
```

Per slab level (drawing numbers `ST-SD-<LEVEL>-nn`):

| nn | Block / Xref name | Content |
|---|---|---|
| 01 | `FRAMING_FORMWORK_NOTATION_<L>` | grid, columns, outline, openings, voids, PT zones, element schedule, notation |
| 02 | `FRAMING_REBAR_SLAB_PT_BOTTOM_<L>` | bottom mesh in PT zones: plan 1 = B1, plan 2 = B2; runs split into pieces with Class B laps, stopped at openings |
| 03 | `FRAMING_REBAR_ADDITIONAL_AT_COLUMNS_<L>` | top bars over every column: plan 1 = T1, plan 2 = T2; ln/6 extension, c+3h band, As,min check, bar types |
| 02A | `FRAMING_REBAR_ADDITIONAL_BOTTOM_RAM_<L>` | RAM input only: the bottom bands designed in RAM Concept as additional bars (`ADD.B1` / `ADD.B2`), band table |
| 03A | `FRAMING_REBAR_ADDITIONAL_TOP_RAM_<L>` | RAM input only: the top bands designed in RAM Concept as additional bars (`ADD.T1` / `ADD.T2`), band table |
| 04 | `FRAMING_REBAR_U_BARS_AROUND_REGIONS_<L>` | U-bars along PT anchorage edges + edge bars; radial U-bars and rings around circular regions |
| 05 | `FRAMING_REBAR_AROUND_VOIDS_ACUARS_<L>` | trimmer bars T&B around each void and sunken slab, anchored ld beyond corners, hairpins at sunken steps |
| 06 | `FRAMING_REBAR_AROUND_OPENINGS_<L>` | trimmers, corner diagonals and edge U-bars around each opening |
| 07 | `CABLES_SCHEDULE_EMPTY_TEMPLATE_<L>` | **empty** tendon schedule, profile and stressing-record templates; filled after the PT design |
| 08 | `FRAMING_REBAR_PUNCHING_LINKS_<L>` | preliminary punching links per column face (rows at d/2, legs at 100 mm, 2h extent), PS types; to be confirmed against the punching design |

Plus `ST-SD-000` `SHOP_DRAWINGS_COVER_INDEX`: drawing list, levels read, lap
table, how to use the blocks.

Every sheet carries an A1 frame with zone rulers and, in the right-hand
strip: key plan, bar bending schedule (mark · Ø · shape · spacing · length ·
qty · total m · kg · zones; marks are per cutting length, `T2-05` style),
general notes, **assumptions**, code reference, legend, coordination /
contract drawing references, revision table, and the title block (project,
client, engineer, contractor, PT sub-contractor / author, title, drawing no,
revision, date, scale, sheet, grid reference, signatures, index, code
reference, block name). Up to three details (sections / plan details) sit
in the bottom strip.

## What is read from the drawing · ما يُستخرج تلقائياً

Layers are matched by name (`COL`, `GRID`, `SLAB`, `PT`, `OPEN`, `VOID`,
`SUNK`, `DROP`, `WALL`, `POUR STRIP`, `BEAM`, `STAIR`, `U-BAR`, Arabic
equivalents…); walls are read as hatched rectangles (and carry top bars,
not punching links), drop panels as thickened zones of unstated depth, pour
strips as hatched strips on the framing plan, and level tags (`T.O.S +0.60`
block attributes) are printed on the plan: a slab zone drawn as its own
outline with a different level becomes a stepped (sunken / raised) zone; when a layer is
missing the extractor falls back to geometry (largest closed polylines = slab
outlines, small closed rectangles = columns, grid from column lines, text
nearby to tell a void from an opening). Slab edges drawn as separate lines
are chained into an outline; openings drawn as a rectangle with a cross are
read from the cross diagonals. Each closed slab outline becomes a level,
named from the nearest plan title (or the file name), with its thickness
read from `PT SLAB TH=220mm` / `SLAB THK 250` style text (sunken-slab and
beam texts are ignored for that).

From the notes: design code (`SBC 304-18`, `ACI 318`, …), `f'c`, `fy`,
cover, and bar specs with context (`BOTTOM T12@200 B.W.`, `TOP BARS OVER
COLUMNS T16@150`, `U-BARS T12@150`, …). Anything found on the drawing is
used literally; anything missing becomes a numbered **assumption printed on
every sheet**, and the title band says whether the code is *on drawings* or
*assumed*.

## Reinforcement rules · قواعد التسليح

Code basis: **SBC 304-18** (Saudi Building Code, based on ACI 318-14) unless
the drawing names another reference.

- Development length §25.4.2.3: `ld = fy·ψt·ψe / (2.1·λ·√f'c)·db` (Ø ≤ 20),
  `1.7` for larger bars; top bars ×1.3; minimum 300 mm.
- Laps: Class B, `1.3·ld`, ≥ 300 mm, ≤ 50 % of bars lapped at a section,
  alternate bars start with a half stock length.
- Hooks: 90° standard hook `12·db` where a bar ends at a free edge; `ldh`
  per §25.4.3.1.
- Top bars over columns, office rule (`topColumns.rule: "office"`, the
  default): an interior column bar covers the drop panel / thickened zone
  when there is one (+ 200 mm each side), otherwise it is 4 m long
  (`topColumns.length`, optional per slab); an edge column applies the U rule
  at the edge and the top extends 70 % of the interior length
  (`edgeFactor`, 2.80 m for 4 m); with a drop panel the bar is exactly as
  long as the drop (`dropMargin` 0). The bars of one direction are distributed
  over the length of the crossing bars at the same column (the two groups
  cover one square), dimensioned on the plan. A bar ending at an edge beam
  ends in an L (400 into the beam) instead of the U. `rule: "code"` keeps the SBC option:
  within `c2 + 1.5h` each side, extend ≥ `ln/6` from the face of support,
  ≥ 4 bars, and not less than `As = 0.00075·Acf` (§8.6.2.3).
- Every top bar that ends at the outer slab edge or at an opening ends in a
  **U** with a 500 mm bottom leg (`U500` on the plan; the cutting length adds
  `h − 2·cover + 500`).
- Perimeter (office rule): between the column top bars, along every slab
  edge, continuous `T12@150` — a symmetric **U-bar** of 4 m total at a free
  edge, an **L-bar** of the same 4 m total where the edge carries a beam
  (400 mm leg into the beam + 3.6 m on top in the slab;
  `uEdge.total / beamLeg / beamTop`).
- Openings enclosed by concrete walls or beams get **no** additional trimmer
  bars. Others get three groups: G1 parallel to the X sides, G2 parallel to
  the Y sides, G3 at 45° crossing both, with the crossing bars listed.
- The bottom-mesh indication (`BOTTOM MESH T10@200`, `thicknessMesh`,
  optional) is written at every change of slab thickness.
- Bottom mesh: continuous through columns, stopped at the opening face less
  cover.
- Openings: `2T16` T&B each side anchored `ld` beyond the corners, `2T12`
  diagonals T&B at corners, `T12@200` U-bars on free edges.
- Voids / acuars: `2T12` T&B each side anchored `ld` beyond the corners.
- Edge U-bars at PT anchorages: `T12@200`, 1200 mm legs, with `2T12` T&B
  longitudinal bars; circular regions: radial `T12@150` U-bars and `2T12`
  rings T&B.
- Sunken slabs: `2T12` T&B trimmers and `T10@200` hairpins (600 mm legs) at
  the step.
- Punching (preliminary): `T10` closed links, first row at d/2 from the
  face, rows at d/2, legs at 100 mm along the face, 2h extent; faces at a
  slab edge carry none. Sizes to be confirmed against the punching design.

All of these are the defaults in `lib/rebar.mjs` and are overridden by the
drawing notes or by `--config`.

## Layer standard · معيار الطبقات

Generated drawings use the **Span Tech layer standard** in
`shopdrawings/layers.spantech.json` (prefix `ST-`). Edit that file, or pass
another one with `--layers file.json` (or `"layers": "path"` in the config),
to change names, colours, linetypes or lineweights; the generator maps its
internal layer names to yours at write time, so nothing else changes.

| Group | Layers |
|---|---|
| Sheet | `ST-SHEET-FRAME`, `ST-SHEET-TITLE`, `ST-SHEET-TEXT`, `ST-SHEET-NOTES`, `ST-SHEET-SCHEDULE`, `ST-SHEET-SCHEDULE-TEXT`, `ST-DETAIL`, `ST-DETAIL-HATCH`, `ST-XREF` |
| Structure (from the G.A.) | `ST-GRID`, `ST-GRID-BUBBLE`, `ST-SLAB-EDGE`, `ST-COL`, `ST-COL-HATCH`, `ST-BEAM`, `ST-STAIR`, `ST-OPENING`, `ST-VOID`, `ST-SUNKEN` (+ `-HATCH`), `ST-PT-ZONE` |
| Reinforcement | `ST-RB-B1`, `ST-RB-B2`, `ST-RB-T1`, `ST-RB-T2` (bars per layer), `ST-RB-UBAR`, `ST-RB-TRIM` (trimmers / diagonals), `ST-RB-PUNCH`, `ST-RB-TEXT` (call-outs, style `ST-REBAR` = romans.shx), `ST-RB-MESH` (mesh labels), `ST-RB-TYPE` (PS labels), `ST-RB-RANGE`, `ST-RB-BOT` / `ST-RB-TOP` (section details) |
| PT | `ST-PT-TENDON`, `ST-PT-CABLE`, `ST-PT-TEXT`, `ST-PT-HATCH` |
| General | `ST-TEXT`, `ST-DIM`, `ST-CALLOUT`, `ST-HATCH` |

Text styles written: `STANDARD` (arial.ttf), `ST-REBAR` (romans.shx, used
for all bar call-outs), `ST-TITLE` (arial.ttf).

## In AutoCAD · داخل أوتوكاد

- Insert or Xref any `dxf/*.dxf` at `0,0`, scale 1, units mm. Plan geometry
  is 1:1; the A1 frame is scaled by the sheet scale (1:100 → 84 100 × 59 400).
- Layers per the standard above. Dimensions are plain lines and text on
  `ST-DIM` so they stay editable without a dimension style. Arabic is
  carried as `\U+` escapes (AutoCAD 2007+).
- Explode a block to edit; re-run the generator after the consultant revises
  the structural drawings and re-attach.

## Code · الكود

```
shopdrawings/
  cli.mjs                    command line + generate()
  layers.spantech.json       the company layer standard (names, colours, linetypes, lineweights, text styles)
  lib/dxf-reader.mjs         ASCII DXF → entities (LINE, LWPOLYLINE, CIRCLE, TEXT, MTEXT, INSERT, HATCH…)
  lib/libredwg-json.mjs      LibreDWG `dwgread -O json` → the same entities (DWG input)
  lib/preview.mjs            any parsed drawing → Canvas, for SVG previews of input drawings
  lib/ram-concept.mjs        RAM Concept .cpt (SQLite) → slab bodies, columns, tendons, bands → model
  lib/extract.mjs            entities → levels, grid, columns, regions, spec, assumptions
  lib/rebar.mjs              SBC 304 lengths, bar splitting, bar list, zone generators
  lib/sheet.mjs              A1 frame, title band, notes, tables, coordinate pens
  lib/details.mjs            section / plan details
  lib/sheets.mjs             one composer per sheet, cover sheet, package assembly
  lib/canvas.mjs             drawing model shared by the writers
  lib/dxf-writer.mjs         AC1015 DXF writer with blocks, hatches, MTEXT, handles
  lib/svg-writer.mjs         previews
  samples/make-sample-input.mjs   builds the demo structural drawing
  samples/sample-structural-input.dxf
  samples/output/            the demo package, as committed
test/shopdrawings.test.js
```
