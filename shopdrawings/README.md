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

Input must be **DXF** (any release, ASCII). From DWG: `DXFOUT` in AutoCAD.
From PDF: `PDFIMPORT` in AutoCAD, then `DXFOUT`. Units are read from
`$INSUNITS` or inferred from the extents (mm / cm / m).

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
| 02 | `FRAMING_REBAR_SLAB_PT_BOTTOM_<L>` | bottom mesh in PT zones, runs split with staggered laps, stopped at openings |
| 03 | `FRAMING_REBAR_ADDITIONAL_AT_COLUMNS_<L>` | top bars over every column: ln/6 extension, c+3h band, As,min check, bar types |
| 04 | `FRAMING_REBAR_U_BARS_AROUND_REGIONS_<L>` | U-bars along PT anchorage edges + edge bars; radial U-bars and rings around circular regions |
| 05 | `FRAMING_REBAR_AROUND_VOIDS_ACUARS_<L>` | trimmer bars T&B around each void, anchored ld beyond corners |
| 06 | `FRAMING_REBAR_AROUND_OPENINGS_<L>` | trimmers, corner diagonals and edge U-bars around each opening |
| 07 | `CABLES_SCHEDULE_EMPTY_TEMPLATE_<L>` | **empty** tendon schedule, profile and stressing-record templates; filled after the PT design |

Plus `ST-SD-000` `SHOP_DRAWINGS_COVER_INDEX`: drawing list, levels read, lap
table, how to use the blocks.

Every sheet carries an A1 frame with zone rulers, a title band (project,
company, title, drawing no, revision, date, prepared / checked / approved,
scale, sheet, grid reference, drawing index, code reference, block name),
general notes, **assumptions**, code reference, legend, a bar bending schedule
(mark · Ø · shape · spacing · length · qty · total m · kg · zones) and up to
three details (sections / plan details) with call-outs.

## What is read from the drawing · ما يُستخرج تلقائياً

Layers are matched by name (`COL`, `GRID`, `SLAB`, `PT`, `OPEN`, `VOID`,
`U-BAR`, Arabic equivalents…); when a layer is missing the extractor falls
back to geometry (largest closed polylines = slab outlines, small closed
rectangles = columns, grid from column lines, text nearby to tell a void from
an opening). Each closed slab outline becomes a level, named from the nearest
plan title, with its thickness read from `SLAB THK 250` style text.

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

All of these are the defaults in `lib/rebar.mjs` and are overridden by the
drawing notes or by `--config`.

## In AutoCAD · داخل أوتوكاد

- Insert or Xref any `dxf/*.dxf` at `0,0`, scale 1, units mm. Plan geometry
  is 1:1; the A1 frame is scaled by the sheet scale (1:100 → 84 100 × 59 400).
- Layers: `REBAR-BOT`, `REBAR-TOP`, `REBAR-U`, `REBAR-TRIM`, `REBAR-TEXT`,
  `CALLOUT`, `SCHEDULE`, `NOTES`, `GRID`, `OUTLINE`, `COLUMN`, `OPENING`,
  `VOID`, `PT-ZONE`, `CABLE`, `FRAME`, `TITLE`, `DIM`, `DETAIL`.
- Dimensions are plain lines and text on `DIM` so they stay editable without
  a dimension style. Text style `STANDARD` on `arial.ttf`; Arabic is carried
  as `\U+` escapes (AutoCAD 2007+).
- Explode a block to edit; re-run the generator after the consultant revises
  the structural drawings and re-attach.

## Code · الكود

```
shopdrawings/
  cli.mjs                    command line + generate()
  lib/dxf-reader.mjs         ASCII DXF → entities (LINE, LWPOLYLINE, CIRCLE, TEXT, MTEXT, INSERT, HATCH…)
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
