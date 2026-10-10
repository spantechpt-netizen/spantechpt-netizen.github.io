# The office rules on the drawings — with their reason and where they live in the code

Every rule here has a reason (the engineer's instruction or the project it came from) and the module that
implements it. Node module names are given; the Python module is the same name in snake_case
(`design.mjs` → `design.py`, `dxf-writer.mjs` → `dxf_writer.py`). When a rule changes, change it in both,
then here. The user (the design engineer) owns these rules: their correction wins over this file.

Contents: 0 principles · 1 reading direction and legs · 2 the bar as drawn · 3 plan annotation · 4 top
bars · 5 perimeter and edges · 6 drops, thickness, pour strips, voids · 7 beams · 8 punching · 9 cables ·
10 sheets, frame, layers · 11 RAM reading · 12 things left out on purpose

---

## 0. Principles

| # | rule | why |
|---|---|---|
| 0.1 | Never guess a design figure. What the model / drawing / notes give is used literally; anything missing takes the office default from `DEFAULT_SPEC` (`rebar.mjs`) **and** becomes a numbered assumption printed on every sheet. | A wrong figure on a fabrication drawing is worse than a visible assumption. |
| 0.2 | Every text string on a sheet is identical in Node and Python (the parity test compares text multisets per sheet). | Both versions are "the program"; the office must not see two drawings. |
| 0.3 | The office rules replace RAM's local reinforcement where the office detail exists: RAM top bands over the columns → office column groups; RAM bottom bands local to a drop → detail 4 bars. Bands shorter than 1.2 m are export artefacts. `spec.ramBands` = `all` / `user` / `none`. | The engineer wants the drawing to look like the office's, not like a RAM export. |
| 0.4 | Nothing is drawn outside the slab: bars, dimensions, legs, labels are clipped or dropped (a drop bar beside an edge / opening loses its outside leg and its written length follows). | Fabrication reads what is drawn. |
| 0.5 | Bars never run into an opening: they stop at the opening edge with a U; `L=` and cutting lengths follow. | Site convention. |

## 1. Reading direction and legs (corrected by the engineer — the most sensitive rules)

| # | rule | why / origin | code |
|---|---|---|---|
| 1.1 | **The reader stands at the RIGHT edge of the sheet.** Horizontal text reads left → right; vertical text reads **bottom → top** (rotation 90). Any text rotation in (90.5°, 270.5°] is turned by 180° with its anchor mirrored (L↔R, B↔T). | The first version put the reader at the left edge (vertical text top → bottom); the engineer: "المفروض إننا على يمين اللوحة". AutoCAD renders vertical text that way. | `canvas.mjs` `text()`; atan2 form `if (rot > 90.5 \|\| rot <= -89.5) rot += 180`; `readableRot` in `design.mjs` |
| 1.2 | DIMENSION text follows the same rule and **no text turn is written on DIMENSION entities** (group 53 removed). | It used to carry 53 = 180 on vertical dimensions to read top → bottom; that was the old reader position. | `canvas.mjs` `dimension()`, `dxf-writer.mjs` |
| 1.3 | **Bar legs**: horizontal bottom bar → legs **up**, horizontal top bar → legs **down**; vertical bottom bar → legs **left**, vertical top bar → legs **right**. Face `B` takes the "up / left" normal, `T` the opposite. | Engineering convention read from the bottom edge for horizontal bars and from the right edge for vertical ones (same position as 1.1). Before the correction vertical legs were mirrored. | `legSide(u, face)` in `design.mjs`: `n = (-u.y, u.x); if (n.y < 0 \|\| (n.y == 0 && n.x > 0)) n = -n; return face==='B' ? n : -n` |
| 1.4 | Call-out **above** the bar, length **under** it, in the reading direction, both left-aligned at the same start point. On a vertical bar: call-out on the **left**, length on the **right**. | The two texts must be read together; `flip` from `readableRot` swaps the side when the bar's direction is opposite to the reading direction. | `officeBar` in `design.mjs` (`side = it.side * flip`) |
| 1.5 | No text ever reads upside down; labels slide along their bar or sideways to the first free place, clear of the designer's text, dimensions, columns, walls, openings and notes; least overlap when nothing is free. | Legibility on A1 at 1:100. | `Placer`, `textBox` in `design.mjs` |

## 2. The bar as drawn

| # | rule | why | code |
|---|---|---|---|
| 2.1 | **One continuous LWPOLYLINE per bar**, constant width 20 model mm: run + 90° rises of a drop bar + L leg + U ends (leg and the 500 back) + both hairpin legs are vertices of the same line. A U-bar is one line, never three. | The CAD user picks a bar in one click; the drawing reads as the bar it is. | `officeBar`, `uEndPoints` (`design.mjs`) |
| 2.2 | Every entity of a bar carries XDATA app `SPANTECH` (`BAR`, id, role, figures JSON) and, in model space, the bar + call-out + length + dimension + dot are one GROUP. | The take-off can be recomputed from a sheet edited in AutoCAD (`dxf-bars.mjs`). | `tagEntity`, `dxf-writer.mjs` XDATA/GROUP |
| 2.3 | **Every drawn bar carries a distribution dimension**: a real DIMENSION, style `DIM100` (text 250, oblique ticks 150, no extension lines, text above the line), with the **dot** where the bar crosses it; width = the group (count × spacing; at least the spacing or 1 m); text past the end when the dimension is shorter than the text; perimeter dimensions 350 inside the edge; a dimension stops before an opening. | Office convention; the dimension *is* the count. | `distDim`, `officeDot` (`design.mjs`) |
| 2.4 | Call-out format `T12-150 (B)` / `(T)` / `T&B`; length `L=5200`; U / L end tags `U500`, `L400` beside the bar; every added bar carries a circled `D#` on layer `DETAIL-REF` (freeze to hide). | Matches the office RFT plans; D# says which General Detail asked for the bar. | `design.mjs` |
| 2.5 | Marks per cutting length on the shop sheets (`T2-05` style); laps Class B `1.3·ld ≥ 300`, ≤ 50 % lapped at a section, alternate bars start with half a stock length (12 m). | SBC 304-18 §25.4 / §25.5. | `rebar.mjs` |
| 2.6 | Bar symbol beside the column, not through its centre: a vertical bar 500 to the **left**, a horizontal one 500 **above** (`spec.barOffset`), unless taken; always within its group and inside the slab; on the slab side at an edge column. | Keeps the column readable. | `posCands` in `topAtColumns` |

## 3. Plan annotation

| # | rule | why | code |
|---|---|---|---|
| 3.1 | Slab tag: one boxed two-line label `POST TENSION SLAB` / `250 mm` (or `RC SLAB`) at the clearest spot (1 m grid search; never over a column, wall, opening, drop, pour strip); mesh labels go under the box. | One tag, found at a glance. | `slabTag` (`design.mjs`) |
| 3.2 | Drops / thickened zones on the framing plan: `THK=400` in the lower-left corner, hatched, the two sizes dimensioned inside (width along the top edge, height along the right edge, DIM100). | Engineer's instruction. | `framingSheet` |
| 3.3 | Beams named **beside** them, never inside: `BM3 [B2] BEAM 350x600` above a horizontal beam, left of a vertical one, on the slab side of an edge beam; **once per span between supports**; short spans take the mark alone; sizes to the nearest 50 mm, no decimals (`size50`). | Labels never overlap; sizes read as built. | `beamLabels`, `size50` |
| 3.4 | Columns solid grey (`s-hatch`) with **no id text**; openings crossed and **never labelled**; pour strips tagged `PSn POUR STRIP` **without width**; ids / sizes live in the element lists and schedules. | Engineer's instruction (clutter). | `drawBase` |
| 3.5 | Grid bubbles at both ends; grid from the reference plan when there is one, else derived from the columns (RAM has no grid) and reported as an assumption. | RAM models carry no grid. | `ram-concept.mjs`, `reference.mjs` |

## 4. Top bars over columns, walls and beams

| # | rule | why | code |
|---|---|---|---|
| 4.1 | Two perpendicular groups per column along the column axis / tendon direction, each as long as the drop panel (`dropMax` 6 m tells a drop from a strip) or `topColumns.length` 4 m, and at least `minBeyond` 1.5 m past the face; edge columns 70 % on top (`edgeFactor`) with the U (free edge) / L (edge beam) at the edge; distributed over the crossing group's length. `rule: 'code'` keeps the SBC option (c2 + 1.5h, ≥ ln/6, ≥ 4 bars, As ≥ 0.00075·Acf). | Office General Details. | `topAtColumns` |
| 4.2 | **Two columns closer than `mergeGap` 500 mm** (faces) that overlap along the other axis are **one support**: one group each way over the rectangle around both (`C1+C2`), never two overlapping groups. Punching and schedules still see the columns. | Engineer's correction (twin columns). | `supportColumns` |
| 4.3 | An isolated wall (line support) shorter than `wallAlongMax` 6 m is reinforced like a column; longer gets the group across it only; a core wall (≥ 3 walls around an opening) or a retaining wall along the edge gets the D2 wall U-bars instead. | Office details D2 / D5. | `classifyWalls` |
| 4.4 | **Interior beams** (slab on both sides; RAM beam objects or a thickened band up to `beams.bandMaxWidth` 3 m): a group across, 4 m or width + 2 × 1.5 m whichever is larger, distributed along the beam; stops at an adjacent parallel beam (far face), an opening (U) or the slab edge (U). An edge beam takes detail 1. | Office rule. | `topAtBeams` |
| 4.5 | D5 corners: 3T12 diagonals 2 m T&B at re-entrant slab corners; 3T16 at wall corners only with `walls.cornerDiagonals`. | General Details. | `cornerBars` |
| 4.6 | **The consultant's bars kept as drawn** (`spec.designerBars`): drawn exactly as given (call-out `7T18/m (T)` / `3T16 (T)` / `T12-150 (T)`, length, distribution width) in the office convention, scheduled under their zone, marked `fixed`: the column rule never re-lengthens them and adds no group in a direction where they already run at a column; `topColumns.only` (`'bands'` or ids) limits the column rule to the PT band columns; `beams.topBars: false` switches the across-beam groups off; `spec.rules.<name>: false` switches a General Details rule off. A consultant bar ends with a U only where its continuation would enter an opening, with the edge U / L only where it would leave the slab; a bar alongside an opening ends plain; a bar crossing an opening is cut there (U). | GYM ground slab (2026-10): only the band beams are PT, the rest of the slab keeps Quantum's RC reinforcement. | `designerItems`, `applyColumnRule` (`fixed`), `designAdditions` (`rules`) |

## 5. Perimeter and edges

| # | rule | why | code |
|---|---|---|---|
| 5.1 | Between the column groups along every edge: continuous `T12@150` — D6 **U-bar** 4 m total (equal legs) at a free edge, D1 **L-bar** of the same 4 m (400 into the beam + 3600 on top) at an edge beam; one symbol per run between supports with its own distribution dimension; curved edges one run. `uEdge.total / beamLeg / beamTop / leg`. | General Details D1 / D6. | `perimeterBars` |
| 5.2 | Every top bar ending at the outer edge or an opening ends in a **U** with a 500 bottom leg (`U500`); at an edge beam in an **L** 400 down (`L400`); legs added to the cutting length. | Anchorage convention. | `uEndPoints` |
| 5.3 | A slab at another top-of-concrete level (RAM element TOC) is a **separate slab**: own outline, part, sheets; the step is a free edge of both (U-bars, U ends, no bar across, never a drawing joint). | Office practice; the engineer confirmed. | `ram-concept.mjs` bodies by TOC |
| 5.4 | An edge with a retaining wall takes the D2 wall U-bars, no perimeter U-bars and no column groups there. | D2. | `classifyWalls` |

## 6. Drops, thickness changes, pour strips, voids, openings

| # | rule | why | code |
|---|---|---|---|
| 6.1 | **D4 column drop**: bottom mesh inside the drop `drops` T12@150 (base slab keeps `bottom` T10@200) as two groups through the column, each as long as the drop (4 m without one) and ≥ 1.5 m past the column face, distributed over the crossing group. The run stops `drops.bendCover` 50 short of each drop face, **rises with a 90° bend** over the step and continues `drops.leg` 500 at the slab bottom (or further where the office length reaches beyond the drop). No rise / continuation where it would leave the slab or enter an opening (`noA` / `noB`) — shortened to 50 short of the edge, written length follows. Shape `BEND90`. | Engineer's corrections in two rounds (first the 45° crank, then the 90° bend with 50 cover; then "no leg outside the slab"). | `dropBars` |
| 6.2 | D3: `BOTTOM MESH T10@200` written at every change of thickness (`thicknessMesh`, optional); lap 500 at the step (note). A thickened strip without a column gets T12@150 extras 50 Ø beyond it. | General Details. | `thicknessTags` |
| 6.3 | **D8 internal pour strip** (a RAM "custom" area ≤ 1.5 m wide, or one drawn): on each side T12@200 TOP & BOTTOM L=2000 lapping across the joint (far face → across → 1 m into the slab; pair symbol per side with its dot on that side's line); a U-bar T12@200 L=2400 at each face closed at the joint, legs out into the slab; T12@150 T&B along the strip. **Against a retaining wall**: U-bar T12@200 L=2500 anchored one wall thickness inside the wall and out into the strip; U-bar T12@200 L=2000 from the slab side; T12@200 T&B L=2000 from the wall face into the slab; T12@150 T&B along; bonding agent. Bars longer than stock written as pieces with laps. `pourStrip.*`, `pourStrip.wall.*`. | Office PT Details 3, copied exactly at the engineer's request. | `pourStripBars` |
| 6.4 | D7 MEP voids: G1 / G2 T&B parallel to the sides, G3 diagonals at 45°, per `VOID_TABLE`; only openings **not** enclosed by walls / beams / column faces and not already trimmed by the designer. Enclosed openings: no trimmers — an L-bar `T12-150 LBAR (T)` along beam sides, wall U-bars along wall sides. Lift / stair shafts take the perimeter U-bars. | General Details. | `voidBars`, `openingBars` |
| 6.5 | D9 blockwork support beam through void: a slab strip 150..`blockBeam.maxGap` 500 between two openings with no beam / wall: 2T16 T&B along, TA beyond each void, T12@200 links, section on the top sheet. | Site detail; applies only where such a pair exists. | `blockBeams` |
| 6.6 | The bottom sheet carries **bottom bars only**; every T&B item (trimmers, U-bars, diagonals) is drawn on the top sheet. | Engineer's correction. | sheet composers |

## 7. Beams

| # | rule | why | code |
|---|---|---|---|
| 7.1 | A beam's supports are the columns and walls crossing it **and every deeper beam crossing it**; the spans of the RAM beam strips, the office design and the plan labels break there. | Engineer: a deeper beam carries the shallower one. | `beamSpans` (`beam-strips.mjs`) |
| 7.2 | Beam strips written into the `.cpt` (`writeBeamStrips`): every span segment / strip / boundary / design section / result dropped; one span segment on the centre line of every beam span, support widths at its ends, designed as `beam`, with a splitter on each edge of the beam; UIDs above everything; RAM units (0.1 mm, `[x][y]` points). RAM still has to Calc All. | The engineer's RAM procedure; the program never runs RAM. | `beam-strips.mjs` |
| 7.3 | `beamSchedule`: the project's **unified schedule** first — a beam takes the lightest record of its section that carries it (`typeCovers`: top, bottom, stirrup capacity ≥ demand); uncovered beams grouped into new types numbered after the last record and **appended**; records never changed; new types starred on the sheet. | One beam schedule per project across levels and projects. | `beam-strips.mjs`, CRM `beam_types_json` |
| 7.4 | Office beam design (`spec.beamDesign` `ram` / `office` / `max`): continuous beam over its supports, tributary-width loading, 1.2D + 1.6L patterned (three-moment), ≥ wuL²/16 hogging at a column end, singly reinforced flexure, T10/T12 stirrups, deflection by table then Branson (L/240, L/360 live). Indicative — RAM's report governs. An end at a drawing joint is an **interior support, never a cantilever**. | RAM keeps no strip forces in the file; the engineer wanted the office check. Cantilever bug found on the south tower. | `beam-design.mjs`, `designBeams` |
| 7.5 | A beam failing deflection / flexure / shear (office check) or reported failing in RAM (`spec.beams.ramFailed`) **blocks the run** (no issue, no submittal) until the engineer decides: deepen (stays blocked), passes in RAM (`ramOk`), or bypass at own responsibility (`override` with name, date, reason → `NOT PASSING (DEFLECTION)` at the beam + the acceptance on the framing sheet). | Same discipline as punching. | CRM `beam-decision`, `app.py` |
| 7.6 | No separate beam sheet in the design package: typed beams hatched on the framing plan with `BMn [Bk] BEAM 350x600` beside and the type's bars on the other side (`4T16 / 3T16 / T12-2L@125`, `NOT DESIGNED IN RAM`); schedule in the framing sheet's table, sections in the detail boxes when the bottom strip is on. | Engineer's instruction (sheet 07 dropped). | `framingSheet` |
| 7.7 | `spec.beamAssign {BM1: 'K1'}` gives a beam a record of `spec.beamTypes` **as it is** (the consultant's beam schedule): no RAM / office design, no typing, no check; the framing plan names `spec.beams.source` as the design and the note says whose bars they are; a beam named with no record on file is listed as `NO TYPE ON RECORD`. | GYM: the consultant's K types kept. | `beamSchedule` (`assigned`), `designBeams` |

## 8. Punching

| # | rule | why | code |
|---|---|---|---|
| 8.1 | D12 PS detail: closed-stirrup strips leaving every column face, tagged `rows - legs - T12` per direction (short / long), S = 100, PS type schedule. From RAM only the columns with **stud rails designed** (rows cover the rail length, legs from the stud area per face); others none. From an RFT plan PS1 `10R-4-T12` / PS2 `12R-4-T12` placeholders. | Office D12; RAM SSR sets are the design. | `punchingSheet`, `psFromSSR` |
| 8.2 | Indicative two-way shear check on every RAM column (`punching.mjs`): Vu from RAM's tributary area (else nearest-column share) × (self-weight + area loads by type, 1.2D + 1.6L), perimeter at d/2 by location, SBC 304 / ACI 318 with PT provisions at interior columns, fpc from the tendons; `ok` / `reinforce` / `fail`. `spec.punching.ramFailed` always flags. | RAM keeps no punching verdict in the `.cpt`; the engineer types the failing columns. | `punching.mjs` |
| 8.3 | A flagged column **blocks the run**; decisions: thicken (blocked), passes in RAM (`ramOk`), bypass (`override`: PS sized from the estimate — rows to where 0.17√f'c carries, legs from Av/s — boxed `NOT PASSING (vu/φvc …) - PS AT THE DESIGN ENGINEER'S RESPONSIBILITY` at the column, boxed note on the top sheet, name / date / reason in the notes). Estimate says reinforce while RAM has no SSR → yellow warning only. | Nothing fails silently onto a drawing. | CRM `punching-decision`, `app.py` |
| 8.4 | Shop preliminary links: T10 closed links, first row d/2, rows d/2, legs at 100 along the face, 2h extent, none on a face at a slab edge; "to be confirmed". | Shop convention pending the design. | `rebar.mjs` punching |
| 8.5 | A column standing on a beam (edge or interior beam, **not** a band, which is slab) is carried by the beam: no punching check, status `on beam`, no PS, counted apart in the sheet note; the engineer's `ramFailed` report still wins (checked and flagged). `spec.rules.punching: false` switches the D12 detail off. | GYM: the columns on K beams. | `columnOnBeam` (`rebar.mjs`), `punching.mjs` |

## 9. PT cable sheets (office shop-drawing convention, Auto PT Suite look)

| # | rule | why | code |
|---|---|---|---|
| 9.1 | One direction per sheet (07A latitude / 07B longitude shop; 05 / 06 design), office layers `Tendons-A/B`, `Text-Profile-*` (`-HIGH` / `-LOW`), `Hline-Profile-*`, `PT-HighLow-*`, `Dimensions-Profile-*`, `Dimensions-Sec-*`, `Details-*`; text style `PT-PROFILE`, 2.0 mm text, 1.6 mm dimension text on paper. | Same layers as the office program. | `OFFICE_LAYERS`, `CAB` |
| 9.2 | **Profile figures are RAM's own numbers**: at every high / low point (and at every profile node on the shop sheets) the value **exactly as entered in RAM Concept** in the model's own reference (above soffit ref 4, below surface ref 5, mid-depth ref 6) — no chair drop, no rounding, no conversion. At the metre stations between nodes: the CGS above the soffit rounded to 5. `spec.cables.figures: 'chair'` restores the old chair heights (CGS − 10, rounded to 5). Notes, legend, plan title (`TENDON PROFILES - …`) and box title (`PROFILE FIGURE SCHEDULE`) follow the mode. | Engineer: "اكتب نفس الأرقام اللي في الرام بدون تغيير" — the first version measured from the top surface with a chair drop. | `cableStations(t, thicknessAt, {figures})`, `elevs: [{v, ref}]` on each tendon (`ram-concept.mjs`) |
| 9.3 | Stations at every profile node and exactly 1000 from it; the odd remainder before the next node is dimensioned, the regular metre is not (`dimSkip` 980..1020). High / low points bigger and on their own layers. | Office chairs convention. | `cableStations` |
| 9.4 | Extension = sum of both RAM figures (two live ends) or RAM's figure − 6 mm seating (one live end); design sheets show tags without extension. | Office note 5. | `extensionOf` |
| 9.5 | LiveEnd / DeadEnd blocks at every anchor (live where a jack sits); the five-cell tag (strands / extension / length / mark / No.) on the tendon line out of its live end, stepped 250 aside when it would sit in the slab; **anchor spacing dimensioned halfway between the anchors and the tag blocks, never over the tags**, following the tendons' drawn direction (also on a 90°-turned plan). | Engineer's correction (dimensions used to sit on the tags). | `ramCablesSheet` |
| 9.6 | Marks `A.01` / `B.01`: tendons of one strand count and one profile (stations within 100 mm, figures within 5 mm) share a mark; one schedule row per mark: MARK, QTY, ANCHOR NO., STRANDS, LENGTH (M), LIVE ENDS, EXTENSION (MM), STRAND TYPE, GUTS (KN), JACKING FORCE PER STRAND (KN). | Office schedule. | `cableMarksOf` |
| 9.7 | Shop extras: profile figure schedule (dead-end chairs 300 wide on own rows), duct schedule 20x50 ≤ 3 strands / 20x70 above, bill of quantities (tendons, strands, strand length at cutting length + 300 per stressed anchor, net area, kg, kg/m², strand-m/m²), stressing record, the seven office notes, slab / cover line. **No tendon sections** (the engineer does not want them). | Office sheet content. | `ramCablesSheet` |
| 9.8 | 07C crossings plan: both directions; at every crossing the tendon over continuous, the one under **broken**; the direction on top and the gap between duct centres written (`A 45`); tight < 20 mm yellow; clash < 10 mm red circle + schedule (marks, tendons, grid, depths from top, gap, over); marks at both ends of every tendon. It reports, it does not move profiles. | The office program's "No Clashes" check, as a drawing. | `ramCrossingsSheet` |
| 9.9 | A tendon crossing a PART cut or a body edge is cut there: profile interpolated at the cut, `CONT.` in place of an anchor, no live end / extension at the cut. | Parts are drawing joints. | `clipTendon` |

## 10. Sheets, frame, layers, package

| # | rule | why | code |
|---|---|---|---|
| 10.1 | Shop (`SPAN-SD`): 01 framing, 02 bottom, 03 top, 02A / 03A RAM additional, 04 U-bars, 05 voids, 06 openings, 07A / 07B cables + 07C crossings (RAM) or 07 empty template, 08 punching, 09 beam marks & schedule (RAM with designed beams), cover 000. Design (`SPAN-DD`): 01 framing (+ beams), 02 bottom, 03 top, 04 punching, 05 / 06 cables, cover. Numbers `<prefix>-<project>-<level>-<nn>`; parts take a letter (`B1A`). | `SHEETS` in `sheets.mjs`, `DESIGN_SHEETS` in `design.mjs` |
| 10.2 | **Bottom detail strip off by default** (`frame.details: false`): the plan takes the whole sheet height; a detail asked for goes to a scratch pen and the overflow note says so. Switchable in Drawings settings. | Engineer's instruction. | `DEFAULT_FRAME` (`sheet.mjs`) |
| 10.3 | A body taller than wide is turned 90° on the landscape sheet (`spec.rotate` `auto` / `0` / `90`), north arrow follows, assumption printed; the scale is chosen on everything drawn (`contentBbox`, up to 6 m outside the slab) so nothing leaves the frame; one plan per layer side by side or stacked, whichever gives the larger scale; a body > `partMax` 60 m is cut into PARTS with 600 overlap. | Fit and scale (south tower 1:150 → 1:100). | `sheet.mjs`, `ram-concept.mjs` |
| 10.4 | Right strip: key plan, schedule, notes + assumptions, references, revision table, title block; sizes / boxes in `meta.frame`; or the office's own frame DXF in paper mm with `<TOKENS>` (`<PROJECT>`, `<CLIENT>`, `<DRAWING_NO>`, `<REV>`, `<DESIGNER>` / `<PREPARED>` …) in place of the built-in one. | Office title block. | `sheet.mjs`, CRM frame upload |
| 10.5 | Design-sheet layers follow the office RFT convention: `REO-TOP` (HIDDEN, 0.20), `REO-BOT` (0.20), `REO-TXT`, `diamension`, `DOTS`, `9_TEXT`, `s-hatch`, `PS-TAG` / `PS-ROW` / `REBAR-PUNCH`, `DETAIL-REF`; shop / frame layers per `layers.spantech.json` (`SPAN-*`). Text style `BW` (isocp.shx) h 150 on design plans; `SPAN-REBAR` (romans) on shop sheets. | The office opens the DXF in its own template. | `layers.spantech.json`, `dxf-writer.mjs` |
| 10.6 | Output per run: `dxf/<DRAWING_NO>_<BLOCK>.dxf` (block + one INSERT at 0,0 — attach as Xref), `DESIGN_DRAWINGS_PACKAGE.dxf` / `SHOP_DRAWINGS_PACKAGE.dxf` (all sheets as blocks spaced by the largest scale, anchor / symbol blocks included), `preview/*.svg`, `schedules/*.csv`, `model.json`, `plan.json` (every bar with its id, for the editor), `quantities.json`, `punching.json`, `beams.json`, `REPORT.md`. AC1015, handles, DIMSTYLE records, XDATA, GROUPs; **ezdxf audit zero errors**. | Deliverable contract. | `cli.mjs` |
| 10.7 | `PREPARED / DESIGNED BY` = the engineer who generated the run (`meta.designer`, the CRM's logged-in user, the app's settings name); recorded on the punching / beam decisions too. | Accountability on the sheet. | `sheet.mjs` title block |

## 11. Reading the RAM model (`ram-concept.mjs`)

- `.cpt` is SQLite; read directly (`node:sqlite` / `sqlite3`). Internal units: lengths 0.1 mm, stress 100 MPa, areas 0.01 mm², loads N per 0.01 mm². Tendon node `ElevationReference`: 4 above soffit, 5 below surface, 6 mid-depth; each node keeps `heights` (above soffit, for interpolation / crossings) and `elevs [{v, ref}]` (the raw figure for the sheets).
- Slab mesh → outline per body (split by element TOC), thickness per element, thickened areas; columns (rectangular with angle — a column turned 90° stores its plan sizes swapped — or round); walls / line supports clipped to the slab; beams (axis, width, depth); tendons chained node to node with strands / jacks / stress / elongation per end; `ConcentratedRebar` bands with every bar; shear regions; punching checks with tributary areas; stud rail sets; area loads by loading type; pour strips (custom areas ≤ 1.5 m); materials; the four title headings.
- The office / project `spec` overrides the RAM base spec **per group** (`uEdge: {total: 4400}` keeps the base legs), never replaces a whole group. (Bug found: a partial override crashed the shop path with `KeyError 'beamLeg'`.)
- The reference plan (`reference.mjs`, `spec.reference {file, use, align}`): the architect's DXF fitted by matching columns (shift + 0/90/180/270; most matches wins; refined on pairs) or on a common point; its grid, columns and outline replace RAM's per `use`; mismatches reported as assumptions.
- The project's grid (`spec.grid {x, y, tolerance}`, model coordinates) replaces the derived one; the columns are labelled `row letter / line number` (`C/3`) within the tolerance, else keep the model's number; `ramId` always keeps the RAM number.
- Nothing is written into the user's `.cpt` except by `writeBeamStrips`, and that on a **copy**.

## 12. Left out on purpose (do not "add" them without asking)

- Longitudinal tendon sections on the cable sheets; the crossings plan does not move profiles.
- A separate beam sheet in the design package; column id texts; opening labels; pour strip widths on the plan.
- Anchorage-dependent details (slab edge at live anchors, bursting spirals, pan-box trimmers) — need the tendon layout; site-specific details (crane / placing-boom openings) apply only where drawn.
- Running RAM or AutoCAD; the program writes files RAM / AutoCAD open.
- Concrete of columns and walls in the take-off; line / point loads in the punching and beam checks (area loads only).
