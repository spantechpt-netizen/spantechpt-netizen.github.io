---
name: rc-shopdrawings
description: Span Tech RC shop drawings (grade beams per grid axis, isolated footings, column necks) generated from the consultant's structural DWG/DXF in the office style approved on the Roya school package. Use whenever the user (Span Tech) sends a consultant structural drawing and asks for شوب درونج / shop drawings of الجريد بيم / grade beams / tie beams, القواعد / footings, رقاب الأعمدة / column necks, a BBS / جدول تفريد, or sends a screenshot of one of these sheets saying a bar, a tie, a hook, a text, a length or a level is wrong. Covers the pipeline (DWG -> DXF -> extract -> generators -> PDF), every drafting rule the engineer has fixed so far, how to change a rule, how to verify a sheet and how to talk and deliver.
---

# RC shop drawings (Span Tech) — grade beams / footings / column necks

Scripts: `tools/rc-shopdrawings/` in the repo `spantechpt-netizen/spantechpt-netizen.github.io`
(branch `claude/sharp-ramanujan-iqyrfq`, PR #7 at the time of writing). If the scripts are not in the
session, ask the user for the ZIP (`rc-shopdrawings-skill.zip`) or attach the repo.

**Project files (DWG / DXF / PDF / the project's design values) never go into the repository, a PR or this
skill.** Keep them in the scratchpad next to copies of the scripts. Only scripts and the generic method are
committed.

---

## 1. Who / how to talk

- The user is the engineer at Span Tech. Writes Egyptian Arabic; answer in Egyptian Arabic, short, technical,
  no padding. Code, file names and layer names stay in English.
- Every sheet change ends with: regenerate → render → look at it yourself → `ezdxf` audit (0 errors) → copy
  PDF/DXF to the scratchpad root → send the PDF(s) with `SendUserFile` → commit + push the scripts.
- Say what changed in bullet points, say what is still open, then offer the next step
  ("لو كده تمام أبدأ التشغيل الكامل"). Do not start the full run before the engineer approves the sample.
- The engineer reviews by screenshots with red marks. Treat every mark as a rule for **all elements**, not only
  the one in the screenshot ("ثبت كل التفاصيل لكل العناصر بحيث تكون زي بعضها … لانه مشروع واحد").
- At the very end of the project: send one ZIP with everything (sheets PDF + DXF, scripts, this skill).

## 2. Pipeline

```
consultant .dwg ──LibreDWG dwg2dxf──► main.dxf ──extract.py──► runs.pkl / cols.pkl / axes.json
                                   │
              project.json (layers, GB schedule, meta, levels, column sizes)
              footings.json (footing schedule + plan positions)
                                   ▼
  gen2.py <axis…>          → out/GB_AXIS_<axis>.dxf      (grade beams, one set per grid axis + BBS)
  gen_f.py <F…>            → out/FOOTINGS.dxf            (one sheet per footing type + BBS)
  gen_n.py <C:F:no …>      → out/NECKS.dxf               (one sheet per column-type/footing pair + BBS)
  topdf.py in.dxf out.pdf <n_sheets>  → black & white PDF of A3 sheets
```

1. **DWG → DXF**: LibreDWG built from git master (0.13 release fails on R2013 files):
   `git clone --depth 1 https://github.com/LibreDWG/libredwg.git && cd libredwg && git submodule update --init --depth 1 && sh autogen.sh && ./configure --disable-bindings --disable-docs --disable-shared --prefix=$PWD/inst && make -j16 && make install`
   then `inst/bin/dwg2dxf -y -o main.dxf main.dwg`.
   - Drawings detailed with **ASD** (Autodesk Structural Detailing, `RBCR*` objects) lose their bars in the
     conversion — ask for the plotted PDF or an *exploded* DWG.
   - Read with `ezdxf.recover.readfile` (big files: ~15 s).
2. `pip install ezdxf matplotlib shapely` (shapely 2.x is used for the tie geometry).
3. `project.json` from `project.example.json`: layout name whose viewport frames the GB plan, GB edge layer,
   label layer, column layers, grid bubble block + attribute tags, plan widths, **GB schedule** typed from the
   drawing (`b,h,nb,db,nt,dt,ds,s`; 8 stirrups/m → `s`=125), `meta` (title block), `levels`
   (`founding` = bottom of PC, `top_gb`), `column_sizes` from plan labels (`C1 30X80` → `[300, 800]`).
4. `python3 extract.py project.json` → beam runs (pairs of parallel edges at the scheduled widths, tagged with the
   nearest GB label, assigned to the nearest axis), columns (model space **and** inside blocks), axes.
5. `footings.json`: `{name: {name, L, W, h, pcL, pcW, pcH, no, bot:[n_x/m, d_x, n_y/m, d_y], top:[…] or zeros,
   col:[x0,y0,x1,y1] column rect inside the footing, found}}` typed from the footing schedule, counts `no` from
   the plan.
6. Run the generators, `topdf.py`, render PNGs (`pdftoppm -r 110 -png`) and **look at every sheet**.
   `rend.py drawing.dxf out.png xmin,ymin,xmax,ymax 4000` renders any window of the source drawing.

## 3. Files

| file | role |
|---|---|
| `extract.py` | DXF → beam runs, columns, axes |
| `gen.py` | shared: `SCHED`, `COVER`, `leg()`, `lap()`, `new_doc()` (layers, dim style GB100), **style** `ST`, `mm()`, `project_notes()`, `fillet()`, `hooked_tie()`, `tie_bar_centres()`, `Sheet` (frame + title block, `pline(r=)`, `text(maxw=)`, `ctext()`, `mark()`, `break_line()`, `dim()`, `hatch_rect()`), `callout()`, `BarList`, `draw_legend()`, `draw_bbs()` |
| `gen2.py` | GB per axis: supports, bar splitting & laps, plan strip (auto label placement), longitudinal section, cross sections |
| `gen_f.py` | footings: bars, side bars, plan panels (bottom / top / side), section 1-1 |
| `gen_n.py` | column necks: reads the `COLUMN SCH` block (bars + ties as drawn), elevation, section A-A, tie bending sketches |
| `pair_necks.py` | FND plan → every column paired with its footing → `neck_pairs.txt` (input of `gen_n.py @neck_pairs.txt`) |
| `topdf.py` | DXF sheets → multi-page PDF (each page renders only its own entities: fast) |
| `rend.py` | fast PNG of a window of the source DXF |

Sheets are A3 frames at 1:100 in model space (42000 × 29700 units), stacked every −32000 in y.
Title block on the right (client, project, consultant, contractor, *Shop Drawings Prepared By: SPAN TECH*,
drawing title, reference file, authored/checked/approved, general notes, drawing number, scale, rev).

## 4. Project-wide drafting rules (engineer, Oct 2026) — apply to EVERY element

1. **Call-out format** on every bar: `n T d-mark-L-s -STG -layer`, dashes between diameter, mark, length and
   spacing (`15 T 12-00-12000-150 -STG -B1`). `callout()` builds it. The key of the format (`draw_legend`) is on
   every sheet.
2. **Bar mark in a hexagon** in front of every call-out (`Sheet.ctext(mark, text, …)`), two digits (`01`), and in
   the BBS Position column. Circles stay only for grid bubbles, section numbers and the footing thickness tag.
3. **All lengths in mm**, integers, no unit (`mm()`): bar lengths, legs, laps, tie sides, side-bar loops, neck
   height. Levels stay in metres (`+0.85`, `-3.00`). The old Roya package wrote metres — the engineer changed it.
4. **Every bend is curved, never a sharp corner** (`fillet`, `Sheet.pline(..., r=)`): U-bars, L-feet, GB legs,
   ties/stirrups (radius = bar radius + tie radius around the corner bar), bending sketches, BBS symbols.
5. **Hooks 135°**: the tie is open at a square top-left corner; both ends wrap 135° around the corner bar (arc)
   and run 100 mm into the core (`hooked_tie`). Same for GB stirrups and column ties, in sections and sketches.
6. **Break lines** (`Sheet.break_line`): horizontal line past both faces with one zig-zag in the middle (top of
   the neck on the footing section, column above the neck).
7. **No text on lines or on other text**: panel names above outlines, leg lengths inside the bends, Y-bar
   call-outs along the bar between the X bar and the far leg, thickness tag in a free corner, title-block values
   squeezed to the box (`text(maxw=)`), GB plan labels placed by the free-spot search, grid lines broken where
   text is written. After every change, look for overlaps in the render.
8. **One style** (`ST`): name 500, sub-title 280, panel title 260, call-out 250, bar length 220, notes 170.
   **Same general notes** (`project_notes(...)`): dims/lengths/laps in mm, levels in m; element cover line(s);
   lap 60d (SBC), max bar 12000; all bends curved, hooks 135° × 100; fc' 35, fy 420.
9. **BBS** after each set (`draw_bbs`): Position (hexagon) | Steel grade | Diameter | Number (in the element / of
   elements / total) | Symbol (mm, sketch with segment lengths) | Length (m) | Mass (kg) = n·L·d²/162 |
   Total mass (kg) = Mass × elements; total steel weight under the table. Marks are package-wide (`BarList`).
10. **Levels** (`project.json → levels`): founding level = bottom of PC; T.O.PC = +0.10; T.O.F = T.O.PC + h;
    T.O.GB. Written on footing sections, GB longitudinal sections (T.O.GB / B.O.GB) and neck elevations.
11. Laps 60 d; stock bar 12000; bars longer are split in equal pieces lapped 60 d.

## 5. Grade beams (`gen2.py X11 Y05 …`)

- One sheet set per grid axis with all GBs on it (beams off grid → nearest axis with offset); windows of the
  axis split over sheets (1/3, 2/3 …), then the BBS sheet.
- Each sheet: **plan strip 1:100** (top bars above the beam, bottom bars below, two rows alternating, crossing
  grid lines with bubbles), **longitudinal section 1:100** (bars with legs, laps, stirrups, clear spans
  dimensioned, levels T.O.GB / B.O.GB), **cross sections 1:20** at the start of every beam and at every change
  of type/reinforcement, cut marks (numbered circles) on the longitudinal section.
- Cover 40 (side cover 30 for b ≤ 300 as in Roya). Legs 200 (≤ T16) / 250 (T18+). Bars anchor to the far face
  of the end support − cover. Top laps in the middle third of a span, bottom laps at the supports.
- **Bars longer than 12 m are split in EQUAL pieces** (engineer: no short filler bar): each cut aims at an equal share
  of what is left, moves to the nearest allowed lap zone, and never leaves a piece shorter than max(2 × lap + 1500, 4000).
- **Stirrups stop at the column face**; column ties continue through the joint (note on the sheet). Stirrups
  counted per clear span (face to face), first 50 mm off the face. `L = 2(a+b) + 200`, a = b − 2c,
  b = h − 80 (out-to-out).
- Plan labels: bars, legs, laps, beams, beam labels, grid stubs are reserved first; call-out on the **outer**
  side of each bar (above top bars, below bottom bars), lifted with a leader if no room; bar length on the
  **inner** side; laps dimensioned between the two rows. Reserved boxes include the whole hexagon (text box
  1.9 h high) and the dimension ticks. Order of placement: bars → legs → lap dims → call-outs → lengths.
- A lap dimension only for a real lap: same diameter and overlap = 60 d. Bars of two different beams anchored in
  the same column are NOT laps (no dimension).
- **Keep every call-out next to its bar** (engineer): slide it along the bar first, then just beside the bar end at
  the same level, and move it outwards (away from the beam, never towards other elements) only when nothing at the
  bar's level is free. A leader is drawn only when the text was moved off the bar; never along a text.
- Section: stirrup on its centre line with curved corners and the hooked corner, bars as filled dots, cover
  dims, call-outs `4 T 16 -T`, `T10 @125`, stirrup sketch beside with out-to-out dims.

### Full run of the grade beams
- `python3 gen2.py <all axes>` (axes = the `axis` values of `runs.pkl`). Per axis, `axis_lines()` splits the runs into
  lines: the line nearest the axis (≤ 300) is the axis set; every other line is its own set `AXIS Y08 OFFSET -1342`
  (off-grid beams grouped under the nearest axis). A run joins a line only if it does not overlap a run already on it
  (parallel / double beams → separate sets). The same beam drawn twice (centre ≤ 200, overlap ≥ 80 %) is kept once.
- Unlabelled runs: type by drawn width (200 → GB1, wider → GB2) — flag it to the engineer.
- Grid lines closer than 1000 on a strip share one bubble with both names.

## 6. Footings (`gen_f.py F2 F3 …`)

- One sheet per footing type: name, thickness in a circle, `NO=n`, PC and RC sizes; panels
  `FOUNDATION BOTTOM REINFORCEMENT PLAN @ X&Y DIRECTION`, `FOUNDATION TOP REINFORCEMENT PLAN @ X&Y DIRECTION`
  (if top steel), `FOUNDATION SIDE REINFORCEMENT`, `SECTION 1-1`.
- Cover 70. Straight = size − 140, leg = h − 140, count = ceil((width − 140)/s) + 1, n bars/m → s = 1000/n
  floored to 5 mm. Long-direction bars are the outer layer: B1 (long) / B2, T2 (long, outer) / T1 (Roya FC11).
- **Top U sits inside the bottom U legs** (its straight length is reduced by 2 × bottom bar dia).
- **Side bars inside BOTH U layers** (not between them); the 70 cover stays on the main bars; loop reduced by the
  main bar diameters and its own; rows every ≤ 300 of free height; loops > 12 m in equal pieces lapped 60 d.
  **Chairs Ø16 @1000×1000 only when the footing has a top mesh** (no top mesh → no chairs, no BBS row); foot 300 / leg / top 400 / leg / foot 300; leg (out-to-out) = h − 2×70 − both bottom
  layers − both top layers (650 with T14 both ways → 454); L = 2×300 + 2×leg + 400; every side dimensioned in the
  BBS symbol. The chair is drawn in SECTION 1-1 (standing on the bottom mesh, under the top mesh, curved bends,
  300 / leg / 400 / 300 written on it) with its call-out `n T 16-mark-L-1000 -CH` on a leader.
- **Corner bar of the top layer sits inside the bend of the top U**; cut bars are spread between the U bends.
- Plan: one representative bar per direction as a U (legs folded into the plan, curved), straight length and legs
  in mm, distribution line with a small circle at the bar, column hatched, overall dims.
- Section 1-1: PC, footing, curved Us, dots, side bars, call-outs with hexagon marks on leaders to the right;
  **every leader ends ON its own bar** with a small circle: X bars (lines) on the line between two dots, Y bars
  (cut dots) on the second dot from the bend, side bar on its dot (never all on the cover line);
  levels on the left, neck stub with break line, `NECK UP TO T.O.GB`, `NECK H = …` (mm).

## 7. Column necks (`gen_n.py C1:F6:11 C2:F2:15 …` or `gen_n.py @neck_pairs.txt`)

- `pair_necks.py` (needs `project.json → fnd_view: [cx, cy, height]` of the FND window): columns typed by size,
  isolated footings matched label ↔ nearest column (nearest pairs first), CF / RAFT / ST: all columns inside the
  outline, a second column on an isolated footing → the outline around it. Unmatched columns / labels are listed —
  report them. `footings_ext.json` (project data) gives h and steel of CF / RAFT / ST for the neck sheets.
- `read_schedule2()` reads every row of `COLUMN SCH` whatever its layers (nested blocks expanded): bar circles
  de-duplicated, missing symmetric bars mirrored, bars snapped to rows/columns (20 mm) and spaced equally along each
  face (the ties are matched to the bars at their drawn positions).

- Bar arrangement and tie set read from the consultant's **`COLUMN SCH`** block (to-scale section per type);
  sizes from `column_sizes`. Some types use other layers inside the block (check each row: outline layer,
  tie layer, bar circles) — extend `read_schedule()` when a type comes back empty.
- **Neck = same size as the column.** Vertical bars stand on the footing bottom mesh with a **foot of 300**
  (max(12d, 300)), run to T.O.GB + **lap 60 d**.
- **Bars inside the ties**: corner bars centred at cover 40 + tie dia + d/2 from the faces; the others spaced
  as the designer drew them.
- **Every tie keeps the designer's exact shape and size**: each tie wraps exactly the bars it holds in the
  designer's section (convex hull of those bars buffered by d/2 + tie radius, mitred), cut flat at the outer tie
  (hexagons stay hexagons). L = out-to-out perimeter + 2 × 100 hooks. Mirrored ties share one mark (`x2/SET`).
- Ties: n sets × 8/m → @125 from T.O.F + 50 to T.O.GB − 50 (ties continue through the GB joint) + 2 ties inside
  the footing.
- Elevation 1:25: footing, PC, neck, GBs framing in, curved L bars, ties, a **distribution line with ticks and a
  leader to the tie call-outs**, **section cut A-A** marked, dims (neck H, LAP), levels, break line on top.
- Section A-A 1:10: column outline, hooked curved ties, bars inside, dims.
- Tie bending sketches: out-to-out shape, curved corners, hook drawn with `100`, **only one or two sides
  dimensioned** (+ one slanted side for polygons), hexagon mark + size, `L=…` on the next line, one note
  "TIE LENGTHS L INCLUDE TWO 135-DEG HOOKS x 100 (OUT-TO-OUT DIMENSIONS)".

## 8. Changing a rule

1. Find the drawing code: style/notes/hexagon/bends/hooks/break line → `gen.py`; GB → `gen2.py`;
   footings → `gen_f.py`; necks → `gen_n.py`.
2. If the rule is general, put it in `gen.py` and use it from all three generators (never patch one element only).
3. Regenerate all three samples, render, look, audit:
   ```bash
   python3 gen_f.py F2 F3 F6 && python3 gen_n.py C1:F6:11 && python3 gen2.py X11
   python3 topdf.py out/FOOTINGS.dxf out/FOOTINGS.pdf 4; python3 topdf.py out/NECKS.dxf out/NECKS.pdf 2
   python3 topdf.py out/GB_AXIS_X11.dxf out/GB_AXIS_X11.pdf 4
   python3 -c "import ezdxf;[print(f,len(ezdxf.readfile(f).audit().errors)) for f in ('out/NECKS.dxf','out/FOOTINGS.dxf','out/GB_AXIS_X11.dxf')]"
   ```
4. Zoom crops with PIL on a 250–300 dpi render to check bars/ties/hooks/texts.
5. Copy scripts to `tools/rc-shopdrawings/`, update `README.md` and this skill (rule list §4–7), commit, push.

## 8b. A new revision of the consultant drawing arrives

1. Convert it (LibreDWG) next to the old one; keep the old DXF as `main_revNN.dxf`.
2. **Text diff** of all TEXT/MTEXT/ATTRIB (model space, blocks expanded) old vs new: schedules (GB, columns,
   footings), notes, levels — anything reinforcement-like that changed.
3. **Geometry diff** of model-space entities (type, layer, rounded coordinates). Look for a common offset first
   (a whole plan moved, e.g. dy = +1882 for the FND plan in Rev.02) and diff again after removing it.
4. Re-run `extract.py` and compare runs / columns / axes; scan the FND plan (footing outlines on `CORE-FNDN`, the
   label inside each outline → smallest containing outline) and compare drawn sizes with the schedule; locate
   differences by the nearest grid axes (bubble attribute `X` = family + `00` = number).
5. Compare the `COLUMN SCH` block entity by entity (nested inserts too).
6. Render the changed areas old | new side by side and send them to the engineer with a short list; ask which
   governs when the drawn size and the schedule disagree (default: the schedule). Then switch the project data to
   the new revision (`meta.ref`), regenerate the samples and continue.

## 9. Verification checklist (every sheet)

- Bars inside ties/stirrups; side bars inside both U layers; top corner bar inside the top U bend.
- Every bend curved; hooks 135° around the corner bar; break lines zig-zag.
- All lengths in mm; levels in m; call-out format with dashes; hexagon marks; legend on the sheet.
- No text on lines / on text / outside the frame / into the title block.
- Every leader ends on the bar it describes (line or dot), not on the cover line or a neighbour bar.
- Counts and lengths agree between call-outs, sketches and BBS; marks package-wide; mirrored ties merged.
- `ezdxf` audit 0 errors.

## 10. Working across chats (context limit)

The chat history is summarised automatically when it gets long, so one chat can go on for a long time; still, keep
the state in files, never only in the conversation:
- **Rules** live in this skill (update it after every engineer note) and in `README.md`; code in the repo branch.
- **Project state** (not in the repo): `project.json`, `footings.json`, the extracted `*.pkl` / `axes.json`,
  `STUDY_NOTES.md` → zipped as `roya_project_state.zip` and sent to the engineer after each milestone.
- **New chat**: upload `rc-shopdrawings-skill.zip` + `roya_project_state.zip` + the consultant DWG; say which step
  is next. Rebuild LibreDWG only if the DXF is not in the state zip (it is large — usually not).
- Work in batches (one batch per message: e.g. necks of C1–C3, footings F1–F7, GB axes X01–X06), each batch
  rendered, checked, sent and committed before the next — a cut in the chat then loses nothing.

## 11. Status (Oct 2026) and open points

- **Full run done on Rev.02**: GB 125 sets / 369 sheets, footings 18 types + BBS, necks 61 pairs (319 necks) + BBS;
  remarks list in the delivery (`REMARKS.md`): GB2 size, unlabelled beams, 11 columns without footing, 4 footing
  labels without column, CF9 → CF8, RAFT-6 → RAFT-02, not yet detailed: CF / RAFT / ST / fence footings, ADD TOP bars.


- Samples done (Rev.02 data), under the engineer's review: GB axis X11, footings F2/F3/F6, neck C1 on F6 (all rules above applied).
- Next (after the engineer says go): full run — all column types incl. the ones on other layers in
  `COLUMN SCH`; pair every column with its footing (plan labels / FND column rects); all necks + BBS; all
  isolated footings with count > 0 (CF / raft / strap later); all GB axes (off-grid beams grouped to the nearest
  axis); final ZIP.
- Open questions to the engineer (ask once, then use the stated default): drawn GB widths that differ from the
  schedule (use the schedule), GB side bars for h > 600, footing types not found on the plan (column centred),
  project code / drawing numbering, the Roya DWG layer set / title block block (until provided, `new_doc()` layers).
- **Rev.02 (07 Oct 2026) is the final consultant drawing** for the shop drawings. Versus Rev.01: GB plan, columns,
  axes, GB / column / footing schedules unchanged; FND plan moved +1882 in y and its blocks exploded; new type F
  footing (F count 17); `T 20 @ 100 ADD TOP` over walls / rafts (54); 2 extra ties + sketches in the C5 row of
  `COLUMN SCH`. Footings drawn bigger than their schedule (F6 ×2 at Y19, F15 ×5 on Y22, F15A Y22-X16,
  F3A Y16-X07 / Y11-X09, F8 Y10-X26): **engineer's decision — the schedule governs** (type size + reinforcement).
- The commercial ALI-BEAM tool was not reverse-engineered or cloned; the method here is our own.
