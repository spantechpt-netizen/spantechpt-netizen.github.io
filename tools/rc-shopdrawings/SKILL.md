---
name: rc-shopdrawings
description: Span Tech RC shop drawings (grade beams per grid axis, isolated / combined footings, rafts, strip footings, column necks) generated from ANY consultant's structural DWG/DXF in the office style approved on the Roya school package, including how to read a new consultant's drawing (layers, blocks, grid, columns, beams, footings, schedules) with survey.py / probe.py / table_dump.py. Use whenever the user (Span Tech) sends a consultant structural drawing and asks for شوب درونج / shop drawings of الجريد بيم / grade beams / tie beams, القواعد / footings, رقاب الأعمدة / column necks, a BBS / جدول تفريد, or sends a screenshot of one of these sheets saying a bar, a tie, a hook, a text, a length or a level is wrong. Covers the pipeline (DWG -> DXF -> extract -> generators -> PDF), every drafting rule the engineer has fixed so far, how to change a rule, how to verify a sheet and how to talk and deliver.
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

## 2a. A drawing from a NEW consultant / another project — read it first (full method: `READING_DRAWINGS.md`)

Nothing in the generators depends on the consultant's layer or block names: everything office-specific is decided
while reading the drawing and written into `project.json` / `footings.json` / `footings_ext.json` / `mats.json`.
**Read `READING_DRAWINGS.md` before touching a new drawing**, then:

1. Convert (LibreDWG, §2). Check: proxy / ASD objects (bars lost → ask for an exploded DWG), unbound xrefs (grid
   or columns missing → ask for a bound DWG), units (column side ~200–1000 → mm; `$INSUNITS` often lies).
2. `python3 survey.py main.dxf survey/` → read `survey/survey.md` top to bottom:
   layers (naming convention, what is inside blocks, bound-xref `$0$` prefixes), blocks (grid bubbles with their
   attribute tags, level marks, schedule blocks), separate drawings in model space, **which model window each
   layout shows** (FND plan, GB plan, schedules, notes), text families (how GB / C / F / CF / RAFT / ST / FF / rebar
   / levels are written and on which layer / in which block), candidates (grid block, column layers with size
   histogram, footing outline layers with label counts, beam edge layer = the pair layer carrying the GB labels,
   the drawn width of every GB label, schedule titles), units, and a **draft `project.json`**.
3. Render every window you will use (`rend.py`) and confirm each candidate by eye. Use
   `probe.py main.dxf text "<label>"` (where is it, which layer / block), `probe.py main.dxf at x,y` (what is drawn
   here), `probe.py main.dxf around "C5" 3000` (texts around a mark).
4. Schedules: `table_dump.py main.dxf "<SCHEDULE TITLE>" [window]` (or `--block "<block>"`) → rows / cells →
   type `schedule` (GB), `footings.json` (cm → mm, n/m → spacing), `footings_ext.json` (`SEE PLAN` rows), levels,
   covers, notes. Column sections come from the schedule block sketch (`gen_n.read_schedule2`).
5. Check before drawing: counts per type vs plan, every GB labelled (or typed by width, flagged), every column
   paired with a footing (`pair_necks.py`), drawn size vs schedule → ask once which governs (default: schedule).
   Note every assumption in the project's `STUDY_NOTES.md` and in the delivery `REMARKS.md`.
6. Only then run the pipeline below — with samples first (one GB axis, 2–3 footings, one neck) for the engineer.

If an element is drawn in a way no reader handles yet (columns only as hatches, circular columns, grid as circle +
text, labels as attributes, inclined beams …), extend the reader **generically** (by geometry + labels, never by
the new office's layer name hard-coded), keep the old behaviour, re-run Roya's survey/extract counts to prove
nothing changed, and add the case to `READING_DRAWINGS.md` (pitfalls / worked examples).

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
| `READING_DRAWINGS.md` | **how to read any consultant's drawing**: file checks, survey, plan windows, grid, columns, GBs, footings / mats / strips, schedules, levels, pitfalls, Roya worked example |
| `survey.py` | first look at a new DXF → `survey.md` (layers, blocks, islands, viewports, text families, candidates, units) + `texts.csv` + `project.draft.json` |
| `probe.py` | `text "<s>"` where is a text; `at x,y` what is drawn here; `around "<s>" r` texts around a mark |
| `table_dump.py` | a schedule (table or block) → rows / cells → `table.csv` |
| `tb_template.py` | office / client title block → template DXF (sheet-specific texts stripped) for `project.json → title_block` |
| `zone_util.py`, `gen_zone_necks.py`, `gen_zone_cores.py`, `gen_zone_strip.py`, `gen_zone_gb.py`, `gen_zone_cd.py` | the other packages per zone (§6b) |
| `mats_scan2.py`, `gen_mat.py`, `gen_zones.py` | mats from a plan in pieces (polygonize) with exact ADD zones; rafts of any outline; packages per zone with key plan + BBS (§6b) |
| `rev_compare.py`, `zones.py` | a new / final foundation plan vs the working one (shift, renamed / gone / new labels); zones (AREA n clouds) → `zones.json` (§8b) |
| `pair_cores.py`, `gen_core.py` | core (shear-wall) necks: cores on the FND plan → plan section + wall section + bar details + BBS (§7a) |
| `strip_net.py`, `gen_st_plan.py` | strip footing network from the plan → strip detailed on plan + real BBS (§6) |
| `cd_scan.py`, `cd_axes.py`, `gen_cd.py` | concrete dimensions of the foundations: plan in parts + sections along every grid line (§7b) |
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

**Office / client title block (engineer, Oct 2026: "نغير الباندا بتاع المشروع كله")** — when the engineer sends a
sheet of the package whose frame must be used (Roya: `10503 - 10506.dwg`, block `LAY` in paper space, A0):
1. Convert it, find the title-block INSERT in the paper layouts (survey §3 / `probe.py`), list its texts with their
   positions / attachment (MTEXT attachment 5 = middle centre) and the cell lines.
2. `python3 tb_template.py sheet.dxf LAY titleblock.dxf "<sheet-specific texts>"…` → template with frame, logos,
   key plan, general notes, revision table, names kept; drawing title / reference / scale / size / area / venue /
   rev / date stripped (the drawing number and Seq. were paper-space texts, outside the block).
3. `project.json → title_block` (project data): `dxf`, `block`, `paper` [x0, y0, x1, y1] = the paper sheet in block
   units (layout limits), `style`, `size`, `code` {project_id, dwg_type, orig, doc_type, area}, `venue_by_title`
   [[title keyword, venue code] …], `seq_start` {venue: first number}, `fields` {title, ref, scale, size, dwg, area,
   venue, seq, rev, date: [x, y, text height, cell width] in block units}.
4. `new_doc()` loads the block once per file (`ezdxf.xref.Loader`); `Sheet.frame()` inserts it scaled so the paper
   sheet = 42000 × 29700 and writes the values (middle-centred, squeezed into the cell). Drawing number =
   `project_id-dwg_type-orig-doc_type-area-venue-seq-rev`, Seq. numbered per venue through the file.
   **AutoCAD strictness** (engineer: "الملفات مش بتفتح" — `Premature end of object in ATTRIB`): entities copied from a
   LibreDWG-converted sheet can carry incomplete embedded objects that ezdxf accepts and AutoCAD rejects (the whole
   file is discarded). `tb_template.py` therefore makes the template plain: ATTRIBs → TEXT, MTEXT column data
   dropped, DIMENSION / LEADER exploded, OLE frames and extension dictionaries removed. After any import from a
   converted drawing check every output: `ATTRIB`, `Embedded Object`, `OLE2FRAME` counts = 0 and audit 0.
   The built-in frame (and its sheet notes) is used only when `title_block` is absent; with the office block the
   block's own GENERAL NOTES are the sheet notes.

## 4. Project-wide drafting rules (engineer, Oct 2026) — apply to EVERY element

1. **Call-out format** on every bar: `n T d-L-s -STG -layer`, dashes between diameter, length and spacing
   (`20 T 14-3752-125 -T2`). **The bar mark is not repeated in the text** (engineer, Oct 2026: it is in the hexagon
   in front only — same as the office key `(00) 00 T 00-00-00-T1`). `callout()` builds it. The key of the format
   (`draw_legend`: hexagon = BAR MARK, then the text parts) is on every sheet.
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

### Combined grade-beam file (engineer: one file like the footings, no near-empty sheets)
- `python3 gen2.py --all <axes>` → `out/GB_ALL.dxf`: every axis line, **package-wide marks, one BBS at the end**.
  Windows hug the beams (gap > 2.5 m → new window); short windows are **packed side by side** (first open sheet with
  room among the last 4); a line that does not overlap the axis beams shares the axis strip (beams labelled
  `GB1 (OFFSET +742)`); windows with < 1 m of beam are dropped.
- Cross sections are **typical per beam type** (A = GB1, B = GB2 …): cut marks with the letter on the longitudinal
  sections, one section per type present at the bottom of each sheet (no repeated identical sections).
- Slot titles under each plan strip (the legend stays at the top right).

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
- **Top U = bottom U** (engineer, Oct 2026): same straight length (size − 2 × 70) and legs; the legs of the two meshes
  stand SIDE BY SIDE at the face (no longer one U inside the other). Same in the strip footing.
- **Side bars (SB)** (engineer, Oct 2026): out-to-out loop = size − 2 × 70 − 2 × the main bar diameter at that face
  (ONE main diameter per face, the top and bottom legs are side by side; CF9 8300, T16 → 8128); rows every ≤ 300 of
  free height. Loop + 60 d ≤ 12000 → one closed loop. Longer → **bent pieces, laps 60 d in the sides, never at a
  corner** (`pieces_of_loop`): 2 U pieces (base = short side, legs = half the long side + lap/2), else 4 corner L
  pieces, plus straight pieces between them when the sides need more parts (fewest pieces, U preferred). One mark per
  piece type with its real shape in the BBS (U / L / straight). Side plan (`draw_side_plan`): the pieces drawn on the
  loop centre line, every second piece offset a little so each lap shows, `LAP 720` at one lap, segment lengths of
  one piece of each type, one call-out block (piece types, note, chairs) in the first spot clear of the columns /
  lap label / thickness tag, short leaders from the hexagon to the nearest piece of that type. Section: the first
  type in the hexagon, the other types as `+ … (MARK nn)`.
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

## 6b. Combined footings / rafts (`mats_scan.py` → `mats_build.py` → `gen_f.py @mats`)
- Outlines on `*CORE-FNDN` containing a CF / RAFT / ST label (CF / RAFT: area > 12 m²); identical label + size +
  additional bars → one type with NO = count (`CF1`, `CF1-B` …); columns inside hatched; depth / steel from
  `footings_ext.json` (schedule "SEE PLAN" rows). Long side always along x (outline turned 90° if needed).
- Same sheet style as the isolated footings; bars > 12 m in **equal pieces lapped 60 d** (end pieces with one leg,
  middle pieces straight; written "(2 PIECES, LAP 960)"); long narrow mats (L/W > 3.2): panels stacked full width,
  call-outs placed clear of the columns and of each other.
- Additional bars written on the plan (`T 20 @ 100 ADD TOP`, `L = 3000`): own sheet `…-ADD` with ADD BOT / ADD TOP
  panels; count = length of the crossing additional bars / spacing + 1.
- Bars split in pieces are DRAWN as pieces on the plan (engineer: "قايل انه فى وصله لكن مش مقطع السيخين"):
  `gen_f.draw_bar` draws every piece (end pieces with their leg), every second piece offset so each lap shows,
  `LAP nnn` at each lap.
- Strip footing under the walls is **detailed on the plan** (engineer: "متاخد فيها قطاع فقط لازم تتسلك … متداخل مع
  القواعد"): `python3 gen_st_plan.py` (after `cd_scan.py`; project.json → `strip`) → `out/STRIP.dxf` = typical
  section 1:20 (`gen_st.section_sheet`) + typical details (corner / T / strip through or into a footing) + plan parts
  1:100 + BBS with the real quantities. `gen_st.py` alone = section + BBS per metre run (no plan available).
  - Network (`strip_net.strip_runs`): pairs of parallel RC edges one width B apart from every source (closed
    outlines, outlines merged with footings, open chains, LINEs, 2-point polylines) → runs; collinear runs joined
    through a footing that fills the gap; dropped: bands inside one footing, bands whose two edges are both footing
    faces (gap between footings that happens to be B), runs < 1.5 m; a T / cross junction (two collinear runs B
    apart with the other strip in the gap) = one through run.
  - Run ends: other strip (corner, stem of a T, sideways jog) → bars to its FAR face − cover; footing ahead (even if
    the drawn strip stops short) → anchored gap + 60 d (≤ far face − cover); footing beside the end square → strip
    turns: to the far face − cover + plan leg into the footing (gap + B/2 − c + 60 d); nothing → stopped at cover and
    bent down (leg h − 2c).
  - Longitudinal bars (B & T, nl per layer, + 2 SB) from end to end of the run THROUGH the isolated footings (on the
    footing mesh); > 12 m equal pieces lapped 60 d, drawn as pieces; U bars (top U = bottom U) @ s per clear stretch
    between footings (none inside a footing; the through strip's U bars run through a T), first 50 from the face.
  - Plan: bottom bar continuous / top dashed (one bar of each set), one U per stretch + distribution line, stretch
    dimensions, end notes (TO FAR FACE / 840 INTO F5 / TURN …), one call-out block per run placed clear of the
    footings and other blocks; a run whose block is on another part gets "R10 - BARS: SEE PART n".
- `BarList`: the same bar in elements with different NO keeps the right total (n_in × n_el summed).

### Rafts / combined footings on their REAL outline — read with care (engineer: "the raft had execution errors")

- `mats_scan2.py` (project.json → `fnd_final {dxf, shift}`): ALL line work of the foundation layers (closed rings,
  open polylines, LINEs, duplicates) is noded and polygonized; each CF / RAFT label takes the smallest face holding it
  = the true outline (stepped / L / skewed). The old `mats_scan.py` needed closed outlines and silently MISSED mats
  drawn in pieces — never trust a mat count without checking every label found a face.
- ADD bars: read from the DRAWN bar (layer `…RBAR…`, 2-point polyline/line, inside the ADD block) = exact length and
  place, and its DIMENSION across = the distribution zone (n = zone / s + 1). NEVER from the text position: the
  consultant writes "T20@100 ADD TOP" about 1 m off the zone (the old generator put the bars there - an execution
  error). Zones come out centred on the columns (check: < 50 mm).
- `mats_build.py`: same mark + same size + same shape + same ADD bars = one type; another variant of a plan mark gets
  **`-T2`, `-T3` …** (never a letter: the consultant's own marks are RAFT-1A, RAFT-2-B; our RAFT-1-B was read as his
  RAFT-1B). Non-rectangular → `gen_mat.py`, rectangles stay in `gen_f.py` (approved sheets; ADD bars now exact).
- `gen_mat.py` (any outline): the polygon eroded by the cover is cut by the bar lines; consecutive rows with the same
  piece(s) (± 50 mm) = one RANGE = one mark + one distribution line; the range changes exactly where the outline
  steps; a row crossing a notch = two separate bars; a row lying ON a step face belongs to the side it stops at.
  Every bar face to face − cover, U legs h − 2c (top U = bottom U), > 12 m equal pieces lapped 60 d drawn as pieces.
  ADD bars clipped to the concrete: shortened bars get their own mark, bars < 60 d dropped — REPORT both to the
  engineer (a design-side error to raise). Re-entrant corners: 2 T16 L=1500 diagonal, bottom (+ top), placed where
  the whole bar is in concrete (Span Tech proposal - say so). Side bars along the real perimeter, laps away from the
  corners; chairs 1 / m². Sheets per type: BOTTOM X, BOTTOM Y, TOP X, TOP Y, ADD + CORNER BARS, SIDE BARS + SECTION;
  every edge of the outline dimensioned, re-entrant corners circled.

### Zone packages (`gen_zones.py` + `gen_zone_*.py`, shared `zone_util.py`)

- Every package is cut per zone, one DXF each: FOUNDATIONS (`gen_zones.py`), NECKS, CORE_NECKS, STRIP, GRADE_BEAMS,
  CONCRETE_DIM (`gen_zone_necks / _cores / _strip / _gb / _cd.py`), each with the BBS of that zone and the zone code
  in the title block. PDFs only when the engineer asks.
- Necks: every column of `neck_pairs.pkl → cl` takes the footing TYPE under it ON THE FINAL PLAN (`zone_util.
  footing_at`: mat type from mats.json, isolated mark of the final plan, else the strip; within 1.5 m of an isolated
  footing = attached + reported); columns on nothing (fence line, removed footings) are listed, not drawn.
- Grade beams: runs (GB plan coordinates) moved to the foundation plan by `gb_to_fnd` (grid lines matched); the
  gaps between the zone clouds belong to the outline-less zone, so a run goes to the CLOUD zone with the larger
  part (≥ 15 %), else to the rest; every run crossing a zone line is listed in REMARKS (split only on request).
- Strip: the whole network is modelled once (ends need neighbours), runs go to the zone with the larger part.
- Concrete dimensions: the plan scan is RELABELLED with the final plan's marks (a re-assigned footing gets its new
  schedule size), footings gone from the final plan are dropped, wall-strip cuts only inside the zone.

### Zone packages - foundations sheet order

- Footings of a zone: labels of the final plan (`…IDEN` layer) inside the zone outline (`zones.json`, `_rest` = the
  zone without one); mats: `mats.json → at` (label positions per type) → count per zone. One DXF per zone:
  sheet 1 = **KEY PLAN of the zone with the TYPE of every footing** (a plan mark detailed as several types must be
  findable on site), then the isolated footings (`gen_f.draw_sheet`, NO = count in the zone), CF / rafts (rect
  `gen_f`, other `gen_mat`), BBS of the zone. Title block Area field = zone code (`meta.area`, `zone_codes` or Z01…).

### Engineer notes on the zone packages (Oct 2026) — keep applying

- **Laps are staggered, never all in one section** ("the laps of the raft are all in its middle"): a bar > 12 m
  is split in two alternating patterns A / B (`gen.lap_patterns`, `gen.lapped_marks`): lap centres of A and B at
  least 1.3 lp apart, every piece its own mark with its length in the BBS and the call-out (`… -STG`). The plan
  draws pattern A on the bar line and pattern B beside it ("ALTERNATE BARS"), with every piece length and
  "LAP n" written — never only the cut between two bars. Same rule in `gen_f` (rect), `gen_mat` (any outline)
  and `gen_st_plan` (strip).
- **Legs are drawn on every polygon raft bar** (`gen_f.draw_bar` with the folded leg and its length), not only
  in the section.
- **Footing on the wall strip** ("the strip bars carry on, the footing bars stop"): `zone_util.strip_bands`
  finds the strips passing THROUGH an isolated footing (≥ 95 % of its extent; a strip that only ends in it does
  not count); the footing becomes a variant `<mark>-ST` (`-ST2` …) whose bars parallel to the strip inside its
  band are omitted, the band is drawn dashed with a note, the call-out says "(n OMITTED IN THE STRIP BAND)".
- **Foundation slab** (a zone with a mat that is not a CF / RAFT): `slab_scan.py` polygonizes the plan, a face
  > 500 m² with a "nnn MM THICK" and an "n T d /m" note is the slab → `slabs.json` (thickness, mesh, outline).
  Ramp corridors (thin parts next to a RAMP text) are cut out; a ramp's own starters are NOT detailed (say so).
  `gen_zones.py` details it with `gen_mat` (`mesh_only`, no legs, slab cover, anchorage 60 d into the strips) on
  A0 BigSheets at a standard scale (1:100 … 1:250, the largest that fits; A3 sheets use 1:50 … 1:250).
  Title-block text of a big sheet keeps its own size (only the drawing text is doubled).

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
- **Neck = same size as the column.** Vertical bars stand on the footing bottom mesh with a 90° foot, run to T.O.GB
  + **lap 60 d**.
- **Development inside the footing (engineer):** Ld = straight part in the footing (T.O.F → bar on the mesh) + foot
  ≥ 60 d (general note "LENGTH DEVELOPMENT ≥ 60 BAR DIAMETER"); foot = max(12 d, 300, 60 d − straight part). Foot
  outwards when it fits inside the footing (½ min(L, W) − cover − bar offset), else turned INWARDS (under the column);
  neither fits → "(!) … CONSULTANT TO CONFIRM" on the sheet + CHECK in the run log. Elevation: dimension of the
  straight part + "Ld = 402 + 560 = 962 ≥ 60d = 960".
- **The bar detailed outside ("تفرد السيخ برة"):** BAR DETAIL at the top left of every neck sheet: the L bar to scale
  with the foot and vertical lengths written on it, T.O.F / T.O.GB / LAP marks along it, call-out + "L = foot +
  vertical = total".
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

## 7a. Core (shear-wall) necks (`pair_cores.py` → `gen_core.py`)

- Read the consultant's **SHEAR WALLS SCHEDULE** (it is a block; render it with `rend.py`, dump its entities in the
  window, scale = outline / real size, e.g. 1:25 drawn ×4): outline (U core: W across the door, H, wall t, return
  length), boundary bars (`nTd` per corner in a 3×3 box, `nTd` per return end), web verticals (`Td@s` with a leader
  to a dot - the dots may be drawn at another spacing: the TEXT governs), horizontals (`Td@s`, leader ends on the
  face line), links (`Td@s VERTICAL / HORIZONTAL`). → `project.json → core_types`.
- `pair_cores.py`: core outlines on the FND plan (12-vertex polylines on `core_outline_layer` of a core-type size,
  copies dropped) + the footing / raft under each → `core_pairs` (a "?" footing is named by hand).
- `gen_core.py` → `out/CORE_NECKS.dxf`, per (core, footing): sheet 1 PLAN SECTION 1:25 with every bar (verticals
  inside the horizontals, cover `core_cover`), outer / inner horizontal bars hooked across the wall at the return
  ends, links every second web bar, corner ties; horizontal bar / link / tie detailed with out-to-out lengths;
  sheet 2 SECTION through the wall (footing, feet, Ld, lap 60 d above T.O.GB, levels) + the vertical bars
  detailed outside with every length. BBS at the end (`OPEN` symbol = open bar to its own proportions).
- Vertical bars: Ld in the footing = straight part + foot ≥ 60 d, feet turned INTO the core (always room).
  Horizontal bars T.O.F + 50 … T.O.GB − 50 @ s + 2 in the footing; links @300 both ways.

## 7b. Concrete dimensions of the foundations (`cd_scan.py` → `cd_axes.py` → `gen_cd.py`)
Engineer (Oct 2026): one setting-out package for the site — RC and PC footings with their sizes and their distances
from / between the grid lines, plan + sections along EVERY grid line (both directions).
- `cd_scan.py`: in the FND window (`fnd_view`) RC outlines (`fnd_layers`), PC outlines (`fnd_pc_layers`), columns,
  footing labels, grid bubbles → `cd_scan.pkl`. `cd_axes.py`: grid lines (`grid_layers`) grouped per coordinate and
  named by the bubble at their end (a kinked axis keeps both segments; an axis with bubbles but no line = the line
  between its bubbles) → `cd_axes.json`.
- The consultant draws footings in PIECES (cut by a beam / wall line: FF1 = two halves 200 apart) or merged with the
  wall strip (F5 / F13 as bumps of ST-01): `merge_split` joins same-span rectangles ≤ 450 apart; a typed footing whose
  outline is still a piece is placed by `fit_rect` (schedule rectangle where its sides lie most on the drawn lines).
  Isolated / fence footings take the SCHEDULE size centred on the drawn one (`(DRAWN axb)` written when different);
  CF / rafts / strips keep the drawn outline; unlabelled narrow outlines = ST-01; thickness from the schedules
  (fence footings: `project.json → fence_footings`).
- **Whole plan on ONE sheet** (engineer: "جمع المخطط كله على بعضه"): default `python3 gen_cd.py` → `out/CONCRETE_DIM_PLAN.dxf`,
  A0 at 1:200 (`BigSheet` 237800 × 168200, dim style GB200, texts ×2, title block scaled, Size A0 / Scale 1:200) +
  `out/CONCRETE_DIM_SECTIONS.dxf` (A3). `--parts` gives the old A3 parts. PDF: `topdf.py plan.dxf plan.pdf --one
  237800,168200,46.81,33.11`.
- **Clear distances between RC footings in every direction** (`gap_dims`): for each footing the nearest footing to its
  right and above whose extent overlaps across; dimension between the two faces in the middle of the overlap (left /
  below come from the neighbour). On the whole plan the overall-size dims are dropped (size is in the label), names
  inside footings ≥ 2400.
- Reading traps of this plan: footings on a second RC layer (`cd_rc_layers_extra`, e.g. `CORE-FNDN-FTNG-RC`); open
  outlines: closed when the missing side is orthogonal, otherwise joined end to end (`chain_open`), never closed with
  a diagonal; wall strips drawn as open lines → in the sections two crossings one strip width apart = a strip cut;
  strip edges are often 2-point polylines or LINEs → `cd_scan` keeps them (they were skipped as "< 3 points").
- Plan 1:100 in parts of 31 × 23 m (match lines, key plan): RC continuous, PC dashed, columns hatched, grid with
  bubbles; per footing name / RC size h / PC size above it, chain axis → edges under it (x) and left of it (y) +
  overall size.
- Sections 1:100 along every grid line: PC + RC cut, neck stubs, F.L / T.O.PC at the left, name + T.O.F on each
  footing (staggered when close), chain 1 = footing edges + grid lines (sizes + clear distances), chain 2 = grid to
  grid; stretches with nothing are shortened with a break (dimensions keep the real distance); long lines in parts
  cut in a gap between footings; parts with no footing dropped; 3 strips per sheet.

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

### The FINAL foundation plan (engineer's edits on the package) — what changes and how to read it

- It may come as a **separate, re-based file** (local coordinates). `python3 rev_compare.py final.dxf` (run where the
  OLD `cd_scan.pkl` is): shift by voting over same-size RC rectangles (hundreds agree = pure translation), then per
  label by position: RENAMED / GONE / NEW (a GONE + NEW pair a few metres apart = the label moved = renamed).
- What the edits were last time (expect the same kind):
  - **types re-assigned on the plan** (a footing keeps its outline, gets another mark: F6 → F6A / F6B, F15 → F15A…D);
    **new schedule rows** for them, an existing row's depth changed → read the new schedule (`table_dump.py`) and
    diff it against `footings.json` row by row, never assume the old values;
  - **an unknown plan label we had mapped to a type is answered** (e.g. a raft label not in the schedule that we took
    as the deepest raft turned out to be the other one) → every mapping we assumed must be listed in the remarks
    and re-checked on each revision;
  - **mat variants named like the program names them**: same label, different additional bars → `NAME-B`, `-C`, `-D`
    (or `1A`, `1B`): keep this naming (`mats_build.py`), it is what the final plan uses;
  - elements of **another package** (fence footings) are left out of the foundation plan: keep them in their own
    package, do not mix.
- Outlines that look GONE in a rectangle diff are usually the same footing drawn in another way (open lines,
  pieces) — compare labels, not raw rectangles.

### Zones (packages per zone: sheets + BBS of that zone only)

- The final plan is cut into zones: **closed polylines (revision clouds, hundreds of vertices, layer 0) with a
  big "AREA n" text inside; one zone has NO outline = everything not inside another zone** (`zones.py final.dxf
  dx,dy` → `zones.json`, `_rest` = that zone).
- Describe each zone to the engineer by its grid range (axes inside its bounds) and its element counts.
- An element belongs to the zone that contains its label / centroid. Elements that CROSS a zone line (strip
  footing runs, grade beams along a zone edge, a raft cut by the cloud) are listed and the engineer decides
  (default: the zone holding the larger part; a run split at the zone line only if he says so).
- Per zone: own sheets (title "… - AREA n"), own BBS with the bars of that zone's elements only; bar marks restart
  per zone; the drawing number carries the zone in the Area field of the title block (`title_block.code.area`).
- **Do not start the zone packages before the engineer says so** (he sends the zones first, the go comes later).

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
- **New project / new consultant in a new chat**: upload `rc-shopdrawings-skill.zip` + the DWG; start at §2a
  (survey → read → project data → samples).
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
