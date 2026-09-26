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

Input is a **DXF** (any release, ASCII), a **LibreDWG JSON** export
(`dwgread -O json -o plan.json plan.dwg`), or a **DWG** directly when
`dwgread` from [GNU LibreDWG](https://www.gnu.org/software/libredwg/) is on
the `PATH` (or named in `DWGREAD`). From PDF: `PDFIMPORT` in AutoCAD, then
`DXFOUT`. Units are read from `$INSUNITS` or inferred from the extents.
Bound Xrefs (`XREF_1st FLOOR$0$BBR-COLUMN` style layer names) are exploded
and read like native layers; grid labels inside bubble blocks are read from
their attributes.

`--config` meta fields: `project`, `location`, `projectCode`, `client`,
`engineer`, `contractor`, `company`, `prefix` (drawing number prefix),
`gridTag` (sheet tag under every grid bubble, e.g. `S02`), `revision`,
`issued`, `revisions` (list of `{rev, description, date, by}`),
`references` (list of `{discipline: ARCH|STRUCT|MEP, no, rev}`),
`coordinated` (four initials), `prepared`, `checked`, `approved`.

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
`SUNK`, `BEAM`, `STAIR`, `U-BAR`, Arabic equivalents…); when a layer is
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
- Top bars over columns (PT two-way slab §8.7.5.5): within `c2 + 1.5h` each
  side, extend ≥ `ln/6` from the face of support, ≥ 4 bars, and not less than
  `As = 0.00075·Acf` (§8.6.2.3). Bar count is raised when the minimum governs.
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
