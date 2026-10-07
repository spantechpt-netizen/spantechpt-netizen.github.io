# Reading a consultant's structural drawing (any office) — the method

Every consultant draws differently: other layer names, other block names, labels as TEXT or as block attributes,
grids as blocks or as circles + texts, columns as polylines or hatched blocks, plans in model space or behind
viewports, schedules as tables or as blocks, sometimes in cm or in metres. **Never assume a name. Discover it,
check it on a render, write it in `project.json`, then run the generators.** The generators only read
`project.json` / `footings.json` / `mats.json`; everything office-specific is decided here.

Tools (all take the converted DXF; nested blocks are always expanded; an entity on layer `0` inside a block is
reported on the INSERT's layer, as AutoCAD shows it):

| tool | question it answers |
|---|---|
| `survey.py drawing.dxf [outdir]` | what is in the file: layers, blocks + attributes, separate drawings, viewports, label families, candidates for grid / columns / beams / footings / schedules, units; writes `survey.md`, `texts.csv`, `project.draft.json` |
| `probe.py drawing.dxf text "F3A"` (`--re`) | where is this text (position, layer, block path) |
| `probe.py drawing.dxf at x,y [r]` | what is drawn at this point (type, layer, block, size, text) |
| `probe.py drawing.dxf around "C5" 3000` | the texts around every "C5" (schedule rows, labels next to a mark) |
| `table_dump.py drawing.dxf "FOOTINGS SCHEDULE" [x0,y0,x1,y1]` | a schedule table as rows / cells → `table.csv` |
| `table_dump.py drawing.dxf --block "COLUMN SCH"` | all texts of one block as rows |
| `rend.py drawing.dxf out.png x0,y0,x1,y1 4000` | a picture of any window, to look at |

---

## Step 0 — get a readable file

1. **DWG → DXF** with LibreDWG from git master (see SKILL.md §2). Read with `ezdxf.recover.readfile` (tolerates the
   converter's small faults; `audit` fixes are normal, errors are not).
2. **Several DWGs** (one per sheet, or plan + schedules separate): convert each; survey each; they may share
   coordinates (same building origin) or not — never mix coordinates of two files without checking a common grid
   bubble.
3. **Proxy / ASD objects** (`RBCR*` classes, `ACAD_PROXY_ENTITY`): reinforcement drawn with Autodesk Structural
   Detailing (or other vertical apps) disappears in the conversion — outlines and texts stay, bars vanish. The
   survey warns. Ask for an *exploded* DWG (EXPLODE / "Export to AutoCAD") or the plotted PDF.
4. **External references**: bound xrefs are fine — their layers get a prefix (`$0$CORE-COLS-IDEN`,
   `GROUND FLOOR PLAN$0$...$0$A-GLAZ-CRWL`; the last part after `$0$` is the original layer). Unbound xrefs are
   *not in the file*: if the grid / columns live in an xref (survey shows almost nothing on the plan), ask for a
   bound copy (XREF → Bind) or for the xref files.
5. **Units**: `$INSUNITS` often lies (Roya says *inch*, drawn in mm). Trust geometry: a typical column side of
   ~200–1000 units → mm; 20–100 → cm; 0.2–1.0 → m (old ASD drawings were in metres). Scale to mm before using the
   readers (or scale the thresholds).
6. **Only a PDF**: schedules and notes can be read with `pdftotext -layout`; plan geometry cannot be measured
   reliably — ask for the DWG.

## Step 1 — survey (`survey.py`)

Run it once per drawing and **read `survey.md` top to bottom**. What each part tells:

- **§2 layers**: the layer naming convention of the office (AIA / NCS `S-COLS`, Saudi offices `CORE-FNDN-GRBM`,
  free names like `1-beam-str`); how much of each layer lives inside blocks (high "in blocks" = the element is
  drawn as blocks or comes from an xref). Architectural layers (`A-`, furniture, glazing) are noise — ignore them.
- **§3 blocks**: grid bubbles (many inserts, short attribute values like `01`, `Y`), level marks (`+0.50`),
  section marks, column blocks (small, inserted hundreds of times on a column layer), and **schedule blocks**
  (big, many texts inside: `COLUMN SCH`). Anonymous `*U…` blocks are dynamic-block copies — their geometry is
  still readable.
- **§4 islands**: every separate drawing in model space (plans of each floor, schedules, details, title blocks)
  with its biggest texts. A structural package usually has one plan per floor *at different coordinates*, all
  with the same grid.
- **§5 viewports**: which model window each paper layout shows, its scale, and the titles inside → which window
  is the foundation plan, which is the GB / SOG plan, where the schedules are. (Roya: `3-FND` = foundation layout,
  `4-SOG` = basement slab with the grade beams, `10-DETAILS` = beam / footing schedules, `2-COL` = column layout.)
- **§6 text families**: how the office names each element (`GB1`/`TB1`/`B01`, `C1 30X80`, `F3A`, `CF2`,
  `RAFT-01`, `ST-01`, `FF2`), rebar notations (`8 Ø 14 / M`, `6 %%C 14/M'- TOP`, `T 20 @ 100 ADD TOP`,
  `STIRRUPS : 4X8 T10 /M`), levels — and on which layer / inside which block each family lives.
- **§7 candidates**: grid bubble block + attribute tags, column outline layers with their size histogram, footing
  outline layers (how many contain a footing label; RC vs PC outline), beam edge layers (pairs of parallel lines,
  gap histogram = beam widths, number of GB labels lying on them), schedule titles with their position / block.
- **§8 units**, **§9 draft `project.json`** — a starting point, not an answer.

Then **render every window you will use** (`rend.py`) and look: the plan, its grid, a few columns, a few beams,
the schedules. Decide by looking, not by counting alone.

## Step 2 — the plan windows

- The **GB plan** = the plan where the GB/TB labels are (survey picks the viewport holding most of them →
  `project.json → layout`; `extract.py` reads the window of that layout's biggest viewport).
- The **foundation plan** = the window holding most footing labels → `fnd_view: [cx, cy, height]` (width =
  1.6 × height). Columns on the FND plan are read in this window, not in the GB plan window.
- If there are no viewports, use the island windows of §4 (or the extents of the labels) — write them explicitly.
- **Each plan has its own grid bubbles**: always restrict the reading to the window, otherwise the same axis is
  found once per floor.
- A new revision can **move** a whole plan (Roya Rev.02: FND plan +1882 in y) — compare a grid bubble of the plan
  between revisions and shift the window.

## Step 3 — the grid

Ways offices draw a grid bubble (in decreasing order of convenience):

1. **Block with attributes** (Roya `A-AX`: tag `00` = number, tag `X` = family letter `X`/`Y`). Name = family +
   number. Survey §3 / §7 shows the tags and sample values → `axis_block`, `axis_attr`, `axis_family_attr`.
2. **Block with a plain TEXT inside** (no attributes): read the virtual text of each insert.
3. **Circle + text** on grid layers (Roya also has `AXIS-All$0$A-GRID-SYMB-100` circles + `S-TEXT (AXIS TAG)`
   texts inside a block): pair each circle with the text whose insert lies inside it.
4. Grid **lines** (`A-AXIS-ST`, `S-GRID`, centre-line linetype): the coordinate of the axis is the line's x (vertical
   line) or y (horizontal). A bubble at the end of a vertical line names a vertical axis.

Checks: number of axes of each family; names monotonic along the coordinate; primed axes (`01'`) and off-grid
lines kept; bubbles at both ends give the same coordinate (dedupe within 50). Which family is vertical? The family
whose bubbles share the same y (bubbles lined up along the top / bottom) names vertical lines → coordinate = x.

## Step 4 — columns

Where columns hide (Roya had all of these at once — read them all, then dedupe by centre within 50):

- closed `LWPOLYLINE` rectangles on a column layer (`CORE-COLS-CONC`, `COLUMN MAIN`, `S-COLS`);
- **small blocks** inserted on a column layer (hatched column symbols) → use the block extents;
- rectangles **inside big blocks** (a canopy / annex inserted as one block `GJ` with its columns on pads) → walk the
  nested entities, keep rectangles on a layer containing `COL`;
- only a **hatch** (no outline) → use the hatch boundary path extents;
- circular columns → `CIRCLE` on the column layer (diameter = size).

Typing a column (which `C…` it is):
1. plan label next to it (`C1 30X80`, cm or mm; `C- 400*400`) → `column_sizes`;
2. by size: rectangle size → the type with that size (both orientations);
3. two types with the same size → the nearest label wins (`pair_necks.py`); still ambiguous → flag it.

The **column schedule** (`COLUMN SCH` block in Roya; can also be a table with sketches):
- one row per type: the type text (`C3`), the bar text (`12 T 16` / `12Ø16`), the stirrup text
  (`STIRRUPS : 4X8 T10 /M` = 4 sets × 8 per metre), and a **to-scale sketch**: circles (or small hatches) = bars,
  closed polylines = ties.
- rows are separated by the y of the type texts; the sketch is the left-most group of circles in the row; the
  scale is found from the column size; sketches showing half the bars are mirrored; bars snapped to rows/columns.
  (`gen_n.read_schedule2`.)
- some rows use other layers or nested blocks — never filter the schedule by layer; filter by position.

## Step 5 — grade beams

- **Edges**: two parallel lines at a beam width apart on the beam layer. The survey's beam candidates show the gap
  histogram (= widths drawn) and how many GB labels lie on each layer's pairs — the layer with the labels is the
  grade-beam layer (Roya `CORE-FNDN-GRBM`; slab beams `1-beam-str` and walls `A-WALL` also give pairs — wrong
  plan / wrong element).
- `extract.py`: horizontal and vertical segments (LINE + LWPOLYLINE pieces), paired when the gap is one of `widths`
  (±25) and they overlap > 200; pieces on the same centreline merged into runs; each run gets the nearest label
  (within 900 across, along its length ±200) and the nearest axis (offset kept).
- **Labels**: TEXT on a label layer (Roya: bound-xref layer `$0$CORE-COLS-IDEN`, shared with column and footing
  labels), sometimes a block with attributes (`B-TIL` with `B`/`00`/`(25X60)` = name + size). Labels can be rotated
  for vertical beams. Unlabelled runs → type by drawn width (flag).
- **Schedule** (`GROUND BEAM SCHEDULE`, `SCHEDULE OF BEAMS`): read with `table_dump.py`, type it into
  `project.json → schedule` as `b, h, nb, db, nt, dt, ds, s` (8 stirrups/m → s = 125). The schedule governs the
  section; the drawn width only identifies the beam (flag differences).
- Traps: the same beam drawn twice (two identical lines) → dedupe; double beams 200–400 apart → separate lines;
  beams interrupted at every column → runs merged across the column; inclined / curved beams → not handled, flag.

## Step 6 — footings, combined footings, rafts, strips

- **Outlines**: closed polylines on the footing layer(s). Offices draw RC and PC outlines (Roya `CORE-FNDN` = RC,
  `CORE-FNDN-FTNG-PC` = PC, `CORE-FNDN-FTNG-RC` also used). The PC outline = RC + 2 × projection: take the one whose
  sizes match the RC sizes of the schedule.
- **Labels** (`F1`, `F3A`, `Fx`, `CF2`, `RAFT-01`, `ST-01`, `FF3`): regex on all texts in the FND window. Each label
  → the **smallest outline containing it** (else the nearest within 600). Count per type = `NO`.
- **Schedule** (`FOOTINGS SCHEDULE`): often **in cm** (PC L×W×D / RC L×W×D / bottom short, long / top short, long as
  `8 Ø 14 / M`). Read with `table_dump.py`, convert to mm and bars per metre → `footings.json`
  (`L, W, h, pcL, pcW, pcH, no, bot:[n/m, d, n/m, d], top:[…] or zeros`).
- Rows `SEE PLAN` (combined footings, rafts): the depth / steel are written on the plan next to the outline —
  `mats_scan.py` collects outline + label + nearby rebar texts; typed into `footings_ext.json`.
- **Additional bars** (`T 20 @ 100 ADD TOP`, `L = 3000`): text on its own layer (Roya `ADD OVER W`) + the bar lines
  near it → `mats_scan.py`.
- **Strip footings** under walls: the label sits on a long narrow outline; a wide zone outline around the strip is
  not the strip — check on the render (Roya ST-01: detailed per metre run).
- Drawn size ≠ schedule size → ask once which governs (Roya: the schedule).
- Columns inside each outline give the column rectangle position for the footing sheet and the neck pairs.

## Step 7 — levels and notes

- Level marks are blocks with attributes (`A-LV-P`: `+0.50`, `T.O.S`) or texts like `+0.85`, `-3.00`, `FFL`.
- Needed: founding level (bottom of PC), T.O.GB, PC thickness, covers, lap length, steel grade, fc'. Read the
  general notes (`GENERAL NOTES:` window, survey §5) and the typical sections; type them into `project.json`.

## Step 8 — check what was read before drawing anything

- Overlay: render the plan window and the extracted runs / columns / footing outlines in another colour (or print
  counts per axis and compare with the render).
- Counts: footings per type vs the plan (and the schedule `NO` if given); columns per type vs labels; every GB run
  labelled or typed by width; every column paired with a footing (lists of unmatched columns / labels → the
  engineer).
- Write what was found and every assumption in `STUDY_NOTES.md` of the project (not in the repo) and in the
  remarks sent with the delivery.

## Where each decision goes (`project.json` keys — every consultant-specific name lives here)

| key | meaning | found with |
|---|---|---|
| `dxf` | the converted drawing | — |
| `layout` | paper layout whose biggest viewport frames the GB plan | survey §5 (viewport with most GB labels) |
| `axis_block`, `axis_attr`, `axis_family_attr` | grid bubble block, attribute tag of the number, of the family letter | survey §3 / §7 |
| `beam_layer`, `widths` | GB edge layer, drawn beam widths to pair | survey §7 (pairs + labels on them) |
| `label_layer` | layer of the GB labels | survey §6 |
| `col_layers` | column outline layers (GB plan) | survey §7 |
| `col_keys`, `col_block_keys` | substrings of layers holding columns inside big blocks / small column blocks | survey §2 (in blocks), probe `at` |
| `fnd_view` | `[cx, cy, height]` of the foundation plan window | survey §5 (viewport with most footing labels) |
| `fnd_layers`, `fnd_col_layers` | footing outline layer(s) (RC, suffix match) and column layer(s) on the FND plan | survey §7 |
| `footing_label_re` | regular expression of all footing labels | survey §6 |
| `column_schedule_block`, `sched_outline_layers` | block holding the column sections; layers of the column outline / labels in it (not ties) | survey §3, probe `--block` |
| `column_sizes` | type → [b, h] mm | survey §9 (plan labels) |
| `schedule` | GB types `b, h, nb, db, nt, dt, ds, s` | `table_dump.py` |
| `levels`, `meta`, `strip` | founding / T.O.GB, title block, strip footing data | notes, sections, title block |

Layer names are matched by **suffix** (`endswith`), so bound-xref prefixes (`$0$…`) do not matter.

## Pitfalls met so far (check each on a new drawing)

- **Layer 0 inside blocks**: the entity shows on the INSERT's layer — readers must use the parent layer
  (`survey.py` / `probe.py` do; a reader filtering on `e.dxf.layer` of virtual entities misses them).
- **Exploded vs block**: a revision may explode blocks (Roya Rev.02 FND plan) — always read model space *and* nested
  blocks, so both versions read the same.
- **Same element twice**: duplicated lines / outlines (copy on top of itself, RC + PC outline, column on two layers)
  → dedupe by geometry (centre within 50–200, overlap ≥ 80 %).
- **Texts**: MTEXT carries format codes → `plain_text()`; `%%c` / `Ø` / `Φ` / `#` all mean diameter; a call-out can
  be split in pieces (`4` and `T16`) → join texts on the same baseline within 1.5 × height; labels can be ATTRIBs
  of a block (`B-TIL`: `B` + `00` + `(200X700)`); vertical beams have rotated labels; Arabic notes in SHX fonts come
  out as Latin gibberish (`Hgr'HU ,HgjsgdP`) → read them on the render / PDF, not as text.
- **Units / decimals**: schedules in cm (`295`), plan labels in cm (`C1 30X80`) or mm (`C- 400*400`), levels in m.
- **Viewports at 1:1 near the origin** are title-block viewports — ignore them (survey drops those without labels).
- **Strays far from the drawing** (a line at 10⁹) blow up the extents — the survey ignores the outer 0.1 %.
- **Dynamic blocks** appear as anonymous `*U…` blocks — the geometry is right, the name is not meaningful.
- **Several schedules side by side**: `table_dump.py`'s automatic window can take the neighbour's rows — pass the
  window explicitly (from `rend.py` / survey §5).
- **Bars per metre vs spacing**: `8 Ø 14 / M` → spacing = 1000 / 8 floored to 5 mm (125); `T16@125` is a spacing.
- **Stirrup notation**: `STIRRUPS : 4X8 T10 /M` = 4 sets × 8 per metre; GB `8 10/m'` = 8 stirrups T10 per metre.

## Worked example — Roya school (consultant Rev.02)

| item | how it was drawn | how it was read |
|---|---|---|
| plans | model space, one per floor at different coordinates; layouts `3-FND`, `4-SOG`, `2-COL`, `10-DETAILS` | viewport window of each layout (survey §5) |
| grid | block `A-AX` on `A-SYM`, tags `00` (number), `X` (family) + lines on `A-AXIS-ST` | `axis_block / axis_attr / axis_family_attr` |
| grade beams | LINE/LWPOLYLINE pairs on `CORE-FNDN-GRBM`, widths 200 / 350 / 400 | `extract.py` (`beam_layer`, `widths`) |
| GB labels | TEXT on `$0$CORE-COLS-IDEN` (bound xref layer, shared with columns / footings) | `label_layer` |
| columns | rectangles on `CORE-COLS-CONC` and `COLUMN MAIN`; small blocks on a `COLS-CONC` layer; rectangles inside the big block `GJ` | `extract.py` (`col_layers` + block walk) |
| column types | plan texts `C1 30X80` (cm) | `column_sizes` |
| column schedule | block `COLUMN SCH` (rows with type / bars / stirrup texts + to-scale sketch; some rows on other layers and nested blocks) | `gen_n.read_schedule2` |
| footings | RC outlines on `CORE-FNDN`, PC on `CORE-FNDN-FTNG-PC`; labels on `$0$CORE-COLS-IDEN`; Rev.02 exploded the FND blocks | `fnd` scan: label → smallest containing outline |
| footing schedule | `FOOTINGS SCHEDULE` table in cm, `SEE PLAN` rows for CF / RAFT | `table_dump.py` → `footings.json`, plan notes → `footings_ext.json` |
| additional bars | `T 20 @ 100 ADD TOP` on `ADD OVER W` | `mats_scan.py` |
| levels | blocks `A-LV-P`, notes | typed into `levels` |
