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
arrow follows). A body that stands taller than wide is also turned 90° on the
sheet so that its long side lies along the landscape sheet (`spec.rotate`:
`auto` by default, `0` / `90` to force it; the app exposes it as the plan
orientation option); the assumption is printed on the sheets. Grid lines do not exist in RAM, so the grid is derived from
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
the call-out `T10-200 (T)` stacked over `L=2400` on one side of the bar, both starting at the same point (left-aligned in the reading direction), in text style `BW` (isocp.shx) h = 150 parallel to the bar, the
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
detail 4 extra bars; bands shorter than 1.2 m are export artefacts and ignored; `spec.ramBands` = `all` (default), `user`
(only the bands the engineer drew, not the program-generated ones) or `none` (office rules only))
(`T16-150 (T)` over `L=5000`, distribution DIMENSION across the band width, dot, `U500` ends at the edge), walls (line
supports) get a body (`spec.wallThickness`, 250 default), the slab and every thickened zone are tagged with their
thickness, and the rules below are added on top exactly as for an RFT plan.

Each slab outline of the plan becomes a PART (the office splits its plans the same way; a RAM body longer than
`spec.partMax` 60 m is cut into parts along its longer side with `partOverlap` 600 mm, the cut being a drawing joint,
and an isolated wall longer than `topColumns.wallAlongMax` 6 m gets the column group across it only) with four sheets:
01 framing (outline, columns, walls, openings, thickness zones, edge beams, levels, camber), 02 bottom and 03 top
(the designer's bars + the additions, schedule of the additions only; the bottom sheet carries the bottom bars only, every
T&B bar - trimmers, U-bars, diagonals - is drawn on the top sheet), 04 punching (PS types per column),
plus a cover / index. Output goes to `DESIGN_DRAWINGS_PACKAGE.dxf` and one DXF per sheet as before.

| Detail | Rule applied | Where |
|---|---|---|
| Perimeter (office rule) | continuous T12@150 between the column top bars: D6 **U-bar** 4 m (equal top / bottom legs) at a free edge, D1 **L-bar** of the same 4 m total, 400 into the beam + 3600 on top, at an edge beam; curved edges are one run with the length along the edge | every slab edge |
| Bar ends (office rule) | every top bar ending at the outer slab edge ends in a U with a 500 mm bottom leg (`U500`) where the edge is free, in an L 400 mm down into the beam (`L400`) where the outer edge carries a beam parallel to it; at an opening always a U | designer's bars and additions |
| Column top bars (office rule) | two perpendicular groups along the column axis (or the tendon direction), each exactly as long as the drop panel (`dropMax` 6 m tells a drop from a thickened strip) or 4 m and at least 1.5 m past the face each way (`minBeyond`), edge columns 70 % with the U / L at the edge; an isolated wall is reinforced the same way, a core wall (three or more walls around an opening) gets the wall U-bars instead; the designer's bars over the column are re-lengthed and their `L=` rewritten, missing groups added, and each group is distributed over the length of the crossing group (the designer's dimension is re-measured or one is added) | every column |
| Inside the slab | bars and distribution dimensions never leave the slab outline (clipped; perimeter dimensions sit 350 mm inside the edge) and a distribution dimension stops before an opening | everything added |
| D2 slab edge at core / retaining wall | T12@200 U-bar starting at the opening (core) face, through the wall and LA into the slab (LB 1200, LC = t − cover, LA from the designer's wall bar next to it); the 10T12 (T&B) parallel bars only with `walls.parallelBars`; a wall running along the slab edge is a retaining wall and takes this detail (no perimeter U-bars, no column groups there) | every core / retaining wall face that looks onto the slab |
| D3 varying thickness | lap 500 at the step (note) | thickness zones |
| D4 column drop / thickened zone | in a column drop the bottom mesh is `spec.drops` T12@150 (the base slab keeps T10@200), drawn as two groups through the column, each exactly as long as the drop (4 m without one) and at least 1.5 m past the column face, distributed over the crossing group, every bar drawn as a U whose legs continue at an angle out of the drop (a 45° crank over the step) and run 500 beyond it at the slab bottom to lap with the slab bottom bars; the written / cutting length counts the cranks and the 500s, a rise / continuation that would leave the slab or run into an opening is not drawn: the continuation is shortened to what lies in the slab (50 short of the edge / opening) or dropped with its rise where nothing is left, and the written / cutting length follows; a thickened strip without a column gets T12@150 extra bars 50 Ø beyond it | nested outline with a thickness written inside (e.g. `280`), RAM slab areas |
| D5 corners | 3T12 diagonals 2 m T&B at re-entrant slab corners; 3T16 at wall corners only with `walls.cornerDiagonals` | outline (and walls when asked) |
| D7 MEP voids | three groups: G1 / G2 longitudinal T&B parallel to the sides, G3 diagonals at 45° crossing both, per the void size table, with the count of crossing bars | openings **not** enclosed by concrete walls / beams / column faces and not already trimmed by the designer (T&B bars next to them) |
| Enclosed openings | no trimmers: an L-bar `T12-150 LBAR (T)` (400 into the beam + 3600 on top) along every side that runs along a beam, the wall U-bars along the sides at walls | openings enclosed by beams / walls / columns |
| Bottom mesh indication | `BOTTOM MESH T10@200` (optional, `thicknessMesh`) | at every change of slab thickness (thickened zones, RC tags) |
| Interior beams (office rule) | any beam crossing the slab with slab on both sides (a RAM beam object, or a long thickened band up to `beams.bandMaxWidth` 3 m wide) carries a group of top bars across it, `topColumns.length` (4 m) or the beam width + 2 x `minBeyond` (1.5 m) whichever is larger, distributed along the beam, nothing along it; the bars stop at an adjacent parallel beam (its far face), an opening (U) or the slab edge (U). A beam along the slab edge is an edge beam (detail 1) | every interior beam |
| Level steps (office rule) | a slab at another top-of-concrete level (RAM element TOC) is a separate slab entirely: its own outline, part and sheets; the step is a free edge of both slabs (perimeter U-bars, bars stopped with a U, no bar across the step, not a drawing joint) | every TOC in the model |
| Drop bars (D4) | the bottom run stops `drops.bendCover` (50) short of each drop face, rises with a 90° bend over the step and continues `drops.leg` (500) at the slab bottom, or further where the office length reaches beyond the drop; shape `BEND90` | every drop panel |
| PT cables from RAM (office shop-drawing convention) | one direction per sheet, layers `Tendons-A/B`, `Text-Profile-*(-HIGH/-LOW)`, `Hline-Profile-*`, `PT-HighLow-*`, `Dimensions-Profile-*`, `Dimensions-Sec-*`, `Details-*`; LiveEnd / DeadEnd blocks at the anchors, the five-cell tag (strands / extension / length / mark / No.) on the tendon line out of its live end, anchor spacing dimensioned at the face outside the slab; marks `A.01` shared by tendons of one strand count and one profile, one schedule row per mark (MARK, QTY, ANCHOR NO., STRANDS, LENGTH, LIVE ENDS, EXTENSION, STRAND TYPE, GUTS, JACKING FORCE). Design sheets 05 / 06: the high / low points (a circle on the point) with **the profile value exactly as entered in RAM Concept** (in the model's own reference, above the soffit or below the surface; no chair drop, no rounding), no extension. Shop sheets 07A / 07B: a figure at every station (each profile node and exactly 1000 from it, the odd remainder before the next node dimensioned, the regular metre not): RAM's value as entered at the profile nodes, the CGS above the soffit rounded to 5 at the metre stations (`spec.cables.figures: 'chair'` restores chair heights = CGS − 10 mm rounded to 5 everywhere); extension = sum of both RAM figures (two live ends) or RAM's figure − 6 mm seating (one); chair height schedule (dead-end chairs 300 wide on their own rows), duct schedule 20x50 / 20x70, bill of quantities, stressing record, the seven office notes; no tendon sections. Sheet 07C, the **crossings plan**: both directions together, at every crossing the tendon that passes over drawn continuous and the one under broken, the direction on top and the gap between the duct centres written (`A 45`), tight under the 20 mm duct in yellow, clashes under 10 mm in a red circle and listed in the schedule with both depths from the top; marks at both ends of every tendon | every level with tendons |
| Reference plan (`lib/reference.mjs`, `spec.reference`) | the architect's / structural DXF of the level (grid bubbles, columns, slab edges) fitted on the RAM model automatically by matching its columns (any shift, turned 0 / 90 / 180 / 270; the fit with the most columns on RAM columns wins, refined on the matched pairs) or on a common point given by hand; its grid labels and lines, its columns (as drawn, sized as drawn, tied to the RAM column under each) and its slab outline replace the RAM ones per `use: { grid, columns, outline }`; RAM columns without a drawn column, drawn columns without a RAM column and a slab area differing by over 5 % are reported as assumptions on the sheets | every level with a reference plan |
| Beam design through RAM (`lib/beam-strips.mjs`) | `writeBeamStrips` copies the .cpt and rewrites its design strips: every span segment, strip, span / strip boundary, design section and strip result dropped; one span segment on the centre line of every beam span (cut at the columns and walls crossing the beam, support widths at its ends, latitude / longitude by direction, designed as `beam`, UIDs above everything, sibling chains kept) with the strip of the beam width and a strip boundary (splitter) on each edge of the beam. `beamSchedule` reads the calculated model back: per beam the heaviest RAM band on top and on the bottom in it and the closest stirrup region; the project's unified schedule (`spec.beamTypes`, the types on record) comes first: a beam takes the lightest record of its section that carries it (top, bottom and stirrup capacity at least what RAM asks, `typeCovers`); the beams no record carries are grouped among themselves (one section, bars within 15 %) into new types numbered after the last record (`added`), and the records are never changed; the framing plan (design) / sheet 09 (shop) labels every beam with its type and section, schedules the types with their sections drawn and stars the new ones | every level with beams |
| Take-off (`lib/quantities.mjs`, `quantities.json` in every package) | steel from the bar schedules of the sheets (by level, face and diameter, kg/m²), concrete from the slab plan (gross / openings / net area, slab volume, the extra of drops and of beams deeper than the slab, soffit + edge formwork), cables from the RAM tendons (tendons, strands, tendon / strand / cutting length with 300 mm per stressed anchor, weight, live / dead anchors, duct 20x50 up to 3 strands / 20x70); `costStudy(quantities, rates)` prices it (steel supply and labour per ton, concrete per m³, formwork per m², strand per kg, anchors each, duct per m, PT labour per m², markup %, VAT %) | every level |
| Distribution dimensions | every drawn bar carries a real DIMENSION (DIM100) with the dot where the bar crosses it: perimeter symbols one per run between supports on each facet (350 inside the edge), column groups over the crossing group's extent (the symbol kept within it, on the slab side at an edge column), any other bar a dimension across its symbol as wide as its group; a vertical DIMENSION reads bottom to top like every other vertical text (no text turn is written on the DIMENSION entity) | every bar |
| App edits | `spec.edits` (delete / length / spec / add by bar id from `plan.json`) are applied after the rules; the sheet says how many were applied | the app's reinforcement editor |
| Sheet frame | `meta.frame` (strip sizes and boxes, `DEFAULT_FRAME` in sheet.mjs) and `meta.frameDxf` (the office frame in paper mm with `<TOKENS>`) | every sheet |
| D8 pour strip (PT details 3) | a RAM slab area of "custom" behaviour up to 1.5 m wide (or a pour strip drawn on the plan) is hatched and takes the office's internal detail exactly: on each side T12@200 TOP & BOTTOM L=2000 lapping across the joint (from the far face of the strip, across it and 1 m into the slab on that side; a pair symbol per side at its own station, its dot on that side's distribution line), a U-bar T12@200 L=2400 at each face closed at the joint with its legs out into the slab, T12@150 T&B along the strip (fixed before the infill pour) (`pourStrip.dia / spacing / length / uDia / uSpacing / uTotal`); a strip cast against a retaining wall takes the office's wall detail exactly: a U-bar T12@200 L=2500 anchored one wall thickness inside the wall and out into the strip, a U-bar T12@200 L=2000 straddling the slab joint, T12@200 top and bottom L=2000 from the wall face into the slab (one TOP&BOTTOM symbol, sliding along the strip clear of column bars), T12@150 T&B along the strip, bonding agent on the joint faces (`pourStrip.wall`). Bars along a strip longer than a stock bar are written as pieces with their lap; every distribution dimension is at least the group's width or a metre, stretched to a bar whose symbol slid past it, its text placed past the end when the dimension is shorter than the text | every pour strip |
| D9 blockwork support beam through void | a slab strip between two openings (150 mm to `blockBeam.maxGap` 500 mm) with no beam / concrete wall in it: 2T16 top & bottom along the strip, TA (tension anchorage) beyond each void, T12@200 links, section on the top sheet | every such pair of openings |
| D12 punching | the office PS detail: closed-stirrup strips leaving every column face, tagged `rows - legs - T12` per direction (short / long), S = 100, with the schedule of PS types; from a RAM model only the columns RAM designed stud rails for (rows cover the rail length, legs match the stud area per face), the others carry none; from an RFT plan PS1 10R-4-T12 / PS2 12R-4-T12 placeholders | every column with a punching design |
| Punching check (`lib/punching.mjs`) | RAM keeps no punching verdict in the file, so every column of a RAM level gets an **indicative** two-way shear check (SBC 304 / ACI 318, PT provisions at interior columns): Vu from RAM's own tributary area (`PunchCheck.AutoTribArea`, else the nearest-column share of the slab) x factored self-weight + the area loads by loading type, the perimeter at d/2 (interior / edge / corner from the slab outline), fpc from the tendons; status `ok` / `reinforce` / `fail` (over φ·0.5√f'c, beyond stirrups). `spec.punching.ramFailed` (ids the engineer reports failing in RAM) always flags. A flagged column blocks the run in the app until the engineer decides; `spec.punching.override = { columns: 'all' \| [ids], by, date, note }` draws the PS detail at those columns sized from the estimate (rows to the perimeter where 0.17√f'c carries, legs from Av/s), boxed `PS AT THE DESIGN ENGINEER'S RESPONSIBILITY` at the column, the engineer's name and date in the notes; `spec.punching.ramOk` clears the flag. `punching.json` and REPORT.md carry the table | every column of a RAM level |
| Office beam design (`lib/beam-design.mjs`, `spec.beamDesign` = `ram` / `office` / `max`) | RAM keeps no strip forces in the .cpt, so every beam is analysed here: a continuous beam over the columns and walls it rests on (the beam-strip spans; end pieces beyond the last support are cantilevers), loaded by the slab it carries (tributary width to the next parallel beam / wall / column line or the slab edge each side, slab self-weight, the beam web, the model's area loads by type; SDL 2.5 / LL 2 kN/m² assumed and reported when the file has none), 1.2 D + 1.6 L with the live load patterned through the three-moment equation; an end framing into a column takes at least wu L²/16 hogging. Flexure as a singly reinforced rectangular section (tension-controlled, As,min, bars from 2..n of T12..T32 fitting the width), shear with two- or four-legged T10 / T12 stirrups (0.17√f'c b d, Vs limits, spacing and minimum-stirrup limits), deflection by the span / depth table then by calculation (Branson's Ie, immediate + long-term λ = 2, L/240 and L/360 live). `beamSchedule` draws RAM's bars, the office bars or the heavier set by set; a beam failing deflection / flexure / shear (or reported failing in RAM, `spec.beams.ramFailed`) blocks the run until the engineer decides; `spec.beams.override` prints the acceptance at the engineer's responsibility on the beam sheet. `beams.json` and REPORT.md carry the forces | every beam of a RAM level |
| Reinforcement defaults (`spec.topColumns` dia / spacing / length, `spec.drops` dia / spacing / leg, `spec.bottom` and `spec.topMesh` dia / spacing, `spec.uEdge` dia / spacing / total, `spec.pourStrip` U-bar and T&B figures, `spec.pourStrip.wall.uTotal / uSlab`) | the office figures the sheets write when the model gives none, including every U-bar length (the perimeter U-bar at a free edge, the pour strip U-bars, the two U-bars at a retaining wall); the app's Drawings settings expose them as fields; a top mesh differing from the bottom one is labelled `BOTTOM MESH … / TOP MESH …` and counted with its own diameter in the take-off | every design level |
| One polyline per bar (`officeBar`, `uEndPoints`) | every bar on the plan is ONE continuous polyline: its run, the rises and continuations of a drop bar, the leg of an L at an edge beam, the U / L ends at a free edge or opening (leg + 500 back) and both legs of a hairpin (pour strip / wall U-bar) are vertices of the same line, never three separate lines; the U500 / L400 tags are written beside it | every drawn bar |
| Adjacent columns (`supportColumns`, `topColumns.mergeGap` 500) | two columns whose faces are closer than the gap and that overlap along the other axis are one support for the top bars: one group of reinforcement each way over the rectangle around both (`C1+C2`), never two overlapping groups; the punching check and the schedules still see the columns themselves | every level |
| Consultant's bars kept as drawn (`spec.designerBars`, `spec.consultant`, `spec.rules`, `spec.topColumns.only`, `spec.beams.topBars`, `spec.beamAssign`, `spec.beams.source`, `spec.grid`) | a slab whose reinforcement outside the office's PT band beams stays the consultant's: every bar of `designerBars` ({id, face T/B/TB, dia, perMetre or count or spacing, a, b (model mm), width or dist {p, q}, zone, beam?, label?}) is drawn as given - the call-out (`7T18/m (T)`, `3T16 (T)`, `T12-150 (T)`), the length and the distribution width - in the office convention (one polyline, call-out above / length under, DIMENSION with the dot, U into an opening, U / L where the continued bar would leave the slab), scheduled under its zone (`DESIGNER`), and left alone by the office rules (`fixed`: the column rule neither re-lengthens it nor adds a group in a direction where it already runs). `topColumns.only` (`'bands'` = the columns standing in a RAM band beam, or column ids - grid reference or the model's own `ramId`) limits the column rule to those columns; `beams.topBars: false` switches the across-beam groups off; `rules {perimeter, walls, drops, corners, voids, pourStrips, blockBeam, punching}` set to `false` switch the General Details rules off one by one; `consultant {name, drawing, notes[]}` names the drawing in the assumptions and prints the notes on the sheets. `beamAssign {BM1: 'K1', ...}` gives a beam a type of `beamTypes` as it is (the consultant's beam schedule): no RAM / office design, no typing, the type counted on the framing plan, `beams.source` named as the design (`QUANTUM GROUP DWG No. 4`). `grid {x: [{label, x}], y: [{label, y}], tolerance 600}` (model coordinates) replaces the derived grid with the project's own and labels the columns by it (`C/3` = row letter / line number). A column standing on a beam (not a band) is carried by the beam: no punching check, no PS (`columnOnBeam`), unless the engineer reports it failing in RAM | a PT band-beam slab inside the consultant's RC design |
| Beam sizes and names on the plan | written to the nearest 50 mm with no decimals (`350x600`) on the plan tags, the beam schedule and the section sketches (`size50`); the name `BMn BEAM 350x600` is written beside the beam (above a horizontal beam, left of a vertical one, on the slab side of an edge beam), never inside it, once per span between the supports crossing it - a RAM beam with a column, a wall or a deeper beam in it reads as separate beams either side | every beam |
| Supports of a beam (`beamSpans`) | the columns and walls crossing a beam, and every deeper beam crossing it (it carries the shallower one), are its supports: the spans of the beam strips, the office design and the plan labels break there | every beam |
| Beams at a drawing joint (`designBeams`) | a beam cut where the slab was split into parts is designed on the whole slab; should the design ever see the part, an end on the drawing joint is an interior support (the beam continues into the neighbouring part), never a cantilever | every split slab |
| Slab tag and drops on the plan | the slab thickness is one boxed two-line tag `POST TENSION SLAB` / `250 mm` (or `RC SLAB`) at the clearest spot of the slab (a 1 m grid search: never over a column, wall, opening, drop or pour strip; the mesh labels go under the box); on the framing plan every drop / thickened zone reads `THK=400` in its lower-left corner, hatched, with its two sizes dimensioned inside it (the width along its top edge, the height along its right edge, DIM100) | every plan |
| Openings, columns and pour strips on the plan | an opening is drawn as its crossed outline only, never labelled `On OPENING w x h`; a column carries no id text beside it (the grid reference locates it); a pour strip is tagged `PSn POUR STRIP` without its width; ids, sizes and widths stay in the element lists, schedules and notes | every plan |
| Bar tags and the take-off from an edited sheet (`lib/dxf-bars.mjs`) | every entity of a bar on the design sheets (its polyline, call-out, length, distribution dimension, dot, detail and U tags) carries the bar's tag as extended data under the application `SPANTECH` (`BAR`, the bar id, the entity's role, the figures as JSON: call-out, length, dia, spacing, count, face, cutting length, drawn length, distribution width, level); the bar with its writing is one selectable GROUP where the sheet is not a block. The engineer edits the sheet in AutoCAD (STRETCH a bar with its dimension, re-write `T16-150`, move the distribution dimension) and uploads the DXF back (`POST /api/drawings/runs/:id/takeoff`, the run page button): `readBars` finds every bar by its tag, `takeoffFromBars` reads what is now drawn (the cutting length follows the drawn line, dia and spacing the call-out, the count the distribution width or a count written in the call-out) and `applyTakeoff` moves the level's steel and the project totals by the difference, bar by bar; untouched bars change nothing; the edited DXF is kept with the run | every design sheet |
| Beams on the framing plan | there is no separate beam sheet in the design package: every typed beam carries `BMn [Bk] BEAM 350x600` beside it and the bars of its type on the other side (`4T16 / 3T16 / T12-2L@125`, `NOT DESIGNED IN RAM`, `NOT PASSING (DEFLECTION)`), hatched; the beam schedule takes the framing sheet's table (types, sections, bars, stirrups, count, beams) and the sections its detail boxes when the bottom strip is on; the design notes follow (`beamScheduleRows`, `drawBeamSections`, `beamScheduleNotes`) | every level with typed beams |
| Bottom strip off | the office frame keeps the bottom detail strip off (`frame.details: false` by default): the plan takes the whole height of the sheet; a detail asked for then goes nowhere (a scratch pen, tables skipped) and the schedule overflow note says where the rest is; the strip can be switched back on in the Drawings settings | every sheet |
| Cable sheet anchor spacing | the anchor spacing dimensions sit halfway between the anchors and the tag blocks (never over the tags) and follow the tendons' drawn direction, also on a plan turned 90° | every cable sheet |
| Parts and bodies (`clipTendon`, `clipPolylineToPolygon`) | a tendon or beam crossing the cut of a PART, or the edge of a separate slab body, is cut there: the piece inside is drawn with its profile interpolated at the cut, `CONT.` in place of an anchor, no live end or elongation at the cut end; the sheet scale is chosen on everything drawn (`contentBbox`) so nothing runs out of the frame; the package DXF carries the anchor / symbol blocks of every sheet and spaces the sheets by the largest scale | every RAM level |
| Slab mesh option (`spec.mesh`) | `bottom` (default) or `both`: the mesh label reads `TOP & BOTTOM TWO WAY`, the top sheet writes `TOP MESH T..@..` at the thickness tag, and the take-off counts the mesh (both directions, faces, 12 % laps) as its own line | every RAM design level |
| Designer's name (`meta.designer`) | the engineer running the program signs `PREPARED / DESIGNED BY` in the title block (token `<DESIGNER>` in a custom frame); the app passes the logged-in user | every sheet |

Every added call-out looks for a free place: the pair `T12-150 U-BAR` / `L=4000` slides along its bar (and may swap
sides), the `D#` tag, the `U500` tags and the zone tags (`THK 360` / `BOTTOM MESH ...`) move likewise, the perimeter
distribution dimensions sit just inside the slab edge. A column bar symbol is drawn beside the column, not through
its centre (a vertical bar half a metre to the left, a horizontal one half a metre above, `spec.barOffset`) unless that
place is taken; the dot sits where the bar crosses its distribution dimension. Columns are filled solid grey (the
office's `s-hatch`); every reinforcement bar is a polyline of constant width 20 (model mm) so the bars stand out among the
plan lines (the reinforcement layers also carry 0.20 mm). Legs and hooks follow the engineering convention: a bottom
bar's legs point up (a horizontal bar) / left (a vertical bar), a top bar's legs point down / right: the plan is read from its bottom edge for horizontal bars and from its RIGHT edge for vertical ones. No text ever reads
upside down, and a vertical text reads bottom to top (the office reads vertical writing standing at the right edge of the sheet, as AutoCAD does): a rotation in (90.5°, 270.5°] is turned by 180° with its anchor mirrored. A hole in the RAM mesh loses its collinear element nodes, so a long void side is one side with one
U-bar symbol. Everything already on the plan (the designer's
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

Per slab level (drawing numbers `SPAN-SD-<LEVEL>-nn`):

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

Plus `SPAN-SD-000` `SHOP_DRAWINGS_COVER_INDEX`: drawing list, levels read, lap
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
`shopdrawings/layers.spantech.json` (prefix `SPAN-`). Edit that file, or pass
another one with `--layers file.json` (or `"layers": "path"` in the config),
to change names, colours, linetypes or lineweights; the generator maps its
internal layer names to yours at write time, so nothing else changes.

| Group | Layers |
|---|---|
| Sheet | `SPAN-SHEET-FRAME`, `SPAN-SHEET-TITLE`, `SPAN-SHEET-TEXT`, `SPAN-SHEET-NOTES`, `SPAN-SHEET-SCHEDULE`, `SPAN-SHEET-SCHEDULE-TEXT`, `SPAN-DETAIL`, `SPAN-DETAIL-HATCH`, `SPAN-XREF` |
| Structure (from the G.A.) | `SPAN-GRID`, `SPAN-GRID-BUBBLE`, `SPAN-SLAB-EDGE`, `SPAN-COL`, `SPAN-COL-HATCH`, `SPAN-BEAM`, `SPAN-STAIR`, `SPAN-OPENING`, `SPAN-VOID`, `SPAN-SUNKEN` (+ `-HATCH`), `SPAN-PT-ZONE` |
| Reinforcement | `SPAN-RB-B1`, `SPAN-RB-B2`, `SPAN-RB-T1`, `SPAN-RB-T2` (bars per layer), `SPAN-RB-UBAR`, `SPAN-RB-TRIM` (trimmers / diagonals), `SPAN-RB-PUNCH`, `SPAN-RB-TEXT` (call-outs, style `SPAN-REBAR` = romans.shx), `SPAN-RB-MESH` (mesh labels), `SPAN-RB-TYPE` (PS labels), `SPAN-RB-RANGE`, `SPAN-RB-BOT` / `SPAN-RB-TOP` (section details) |
| PT | `SPAN-PT-TENDON`, `SPAN-PT-CABLE`, `SPAN-PT-TEXT`, `SPAN-PT-HATCH` |
| General | `SPAN-TEXT`, `SPAN-DIM`, `SPAN-CALLOUT`, `SPAN-HATCH` |

Text styles written: `STANDARD` (arial.ttf), `SPAN-REBAR` (romans.shx, used
for all bar call-outs), `SPAN-TITLE` (arial.ttf).

## In AutoCAD · داخل أوتوكاد

- Insert or Xref any `dxf/*.dxf` at `0,0`, scale 1, units mm. Plan geometry
  is 1:1; the A1 frame is scaled by the sheet scale (1:100 → 84 100 × 59 400).
- Layers per the standard above. Dimensions are plain lines and text on
  `SPAN-DIM` so they stay editable without a dimension style. Arabic is
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
