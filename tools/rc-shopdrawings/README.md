# RC shop drawings from the consultant's structural DWG (grade beams per axis)

Generates Span Tech style reinforcement shop drawings for **grade beams, one sheet set per grid axis**,
from the consultant's structural drawing. Footings / tanks generators follow the same pattern (in progress).

Project drawings (DWG / DXF / PDF) never go into this repository — keep them next to the scripts in a
scratch folder. Only the scripts and the method live here.

## Pipeline

```
consultant .dwg ──LibreDWG dwg2dxf──► drawing.dxf ──extract.py──► runs.pkl / cols.pkl / axes.json
                                                       │
                                  project.json (layers + beam schedule)
                                                       ▼
                                   gen2.py <axis…>  ──► out/GB_AXIS_<axis>.dxf  ──topdf.py──► PDF
```

1. **DWG → DXF.** Build LibreDWG from git master (the 0.13 release fails on many R2013 files):
   ```bash
   git clone --depth 1 https://github.com/LibreDWG/libredwg.git && cd libredwg
   git submodule update --init --depth 1
   sh autogen.sh && ./configure --disable-bindings --disable-docs --disable-shared --prefix=$PWD/inst
   make -j16 && make install
   inst/bin/dwg2dxf -y -o drawing.dxf drawing.dwg
   ```
2. **project.json** (copy `project.example.json`): the layout whose viewport frames the GB plan, the GB edge
   layer, the GB tag layer, column layers, the grid-bubble block and its attribute tags, and the
   **GROUND BEAM SCHEDULE** typed in from the drawing (`b`,`h` mm; `nb`/`db` bottom bars, `nt`/`dt` top bars,
   `ds` stirrup dia, `s` stirrup spacing; 8 stirrups/m → `s`=125).
3. `pip install ezdxf matplotlib` then `python3 extract.py project.json` → prints window, axis count, beam runs
   (pairs of parallel edge lines at the scheduled widths, merged along a centreline, tagged with the nearest
   GBn text, assigned to the nearest axis with its offset) and columns (model-space outlines **and** outlines
   inside large blocks — canopy columns on pads were hidden in a block in the first project).
4. `python3 gen2.py X11 Y05 …` → one DXF per axis, A3 frames at 1:100 stacked every 32 000 units in model
   space; `python3 topdf.py out/GB_AXIS_X11.dxf out/GB_AXIS_X11.pdf <sheets>` → black-and-white PDF.
5. Look at every sheet (`python3 rend.py drawing.dxf out.png xmin,ymin,xmax,ymax 4000` renders any window of
   the source drawing fast; the skill's `render_dxf.py` renders sheets).

## Office drafting conventions (learned from the approved Roya school package, Rev 00, May 2026)

- A3, 1:100, title block on the right (client, project, consultant, contractor, *Shop Drawings Prepared By:
  SPAN TECH*, drawing title, reference file = consultant drawing name + date, authored / checked / approved,
  drawing number, scale, size, rev table, general notes).
- Grade beams: bars drawn as heavy polylines **beside** the beam on plan; call-out above the bar
  `(mark) 4T 16 mm L=5880mm T|B`, the straight length under it (`5680 mm`), leg lengths written at the legs.
  `L` = straight + legs. Legs seen: 200 / 300 mm. Marks numbered per sheet; same mark = same shape.
- Stock bar 12 000 mm; laps **60 d** (T12 720, T14 840, T16 960, T18 1080) dimensioned with a short dimension.
- Stirrups T10 @125, 135° hooks 100 + 100: `L = 2(a + b) + 200`, `a = b_beam − 2c` (c = 30 for 200/300 wide,
  40 for ≥ 350), `b = h − 80`. Examples 200×700 → 1720, 300×700 → 1920, 400×700 → 2080, 400×900 → 2520,
  400×1100 → 2880. Call-out with the count: `(34) 866T 10mm L=2080mm @125mm`.
- Sections: section box with cover dims + the stirrup shape drawn beside it with its inside dims.
- General notes: covers super-structure slabs/walls 25, beams 40, columns 40; contact with soil SOG 50,
  GB 40, footings 70, walls 30; fc' 35; fy 420; Ld ≥ 60 d; SBC.

## What is new for the axis sets (engineer's request, Oct 2026)

- One set per grid axis with **all** grade beams on that axis (beams off the grid are grouped with the
  nearest axis and their offset).
- Each sheet: plan strip (top bars above the beam, bottom bars below, crossing axes with bubbles),
  **longitudinal section** (bars with legs, laps, stirrups @s per clear span, span dimensions, one stirrup
  call-out per beam type), **cross sections 1:20** at the start of every beam and at every change of type /
  reinforcement, with the cut marks on the longitudinal section.
- Detailing rules in `gen2.py` (open points are confirmed with the engineer before a full run):
  bars anchor to the far face of the end support − cover 40; legs 200 (≤ T16) / 250 (T18+);
  bars longer than 12 m are split into equal pieces lapped 60 d, top laps in the middle third of a span,
  bottom laps at the supports; stirrups counted per clear span, first 50 mm off the face.

## Files

| file | role |
|---|---|
| `extract.py` | DXF → beam runs, columns, axes |
| `gen.py` | sheet frame / title block / DXF helpers, schedule loader, layers, dim style |
| `gen2.py` | per-axis sheets: supports, bar splitting, plan, elevation, sections |
| `gen_f.py` | isolated footings, one sheet per type (bottom / top X&Y plans, side bars, section) from `footings.json` |
| `gen_n.py` | column necks per (column type, footing) pair: elevation, section from the COLUMN SCH block, ties, BBS |
| `topdf.py` | DXF sheets → multi-page PDF |
| `rend.py` | fast PNG render of a window of a big source DXF |
| `project.example.json` | template of the project file |

## Known limits of the DWG route

- Drawings detailed with **AutoCAD Structural Detailing (ASD)** store every bar as an ASD object
  (`RBCR_EN_BAR`, `RBCRREBAR`, `RBCRREBARTABLET` …). LibreDWG drops them: outlines, dimensions and texts
  survive, the bars and their call-outs do not. For such references ask for the plotted **PDF**, or a copy of
  the DWG where ASD has converted the bars to plain AutoCAD geometry.
- A 20 MB ASD drawing becomes a ~240 MB DXF (block definitions); reading it with `ezdxf.recover` takes ~15 s.

## Footings (from the approved Roya footing package, exploded ASD drawings)

- One sheet per footing type: name, thickness in a circle, `NO=n` (count on the plan), PC and RC sizes.
- Panels: `FOUNDATION BOTTOM REINFORCEMENT PLAN @ X&Y DIRECTION`, `FOUNDATION TOP REINFORCEMENT PLAN @ X&Y DIRECTION`
  (rafts: X and Y on separate panels, plus ADD bottom / ADD top), `FOUNDATION SIDE REINFORCEMENT`.
- One representative bar per direction drawn as a U (bottom legs up, top legs down) with the straight length and
  the legs written in metres (`4.36`, `0.52`), a distribution line with a dot where it crosses the bar, the
  overall sizes dimensioned in mm, the column hatched.
- Call-out: `(mark) 40Ø18  L=9.38m  S=12.5cm  - B1` ; layers B1 (outer, long direction) / B2, T1 / T2 (outer, long
  direction), ADD-B1 / ADD-B2 for additional bars; side bars `1Ø12 L=11.88m ... SB`; chairs `41Ø16 L=1.88m S=100*100CM`.
- Cover 70: straight = size − 140, leg = thickness − 140, count = ceil((width − 140) / s) + 1, n bars/m → s = 1000/n.
- Rafts: bars longer than 12 m lapped 60 d (T20 → 1200), lap shown with a short dimension.

## Engineer's rules added (Oct 2026)

- **Call-out format** on every bar: `15 T 12-00-12000-150 -STG -B1` (dashes between diameter, mark, length and spacing - engineer's note) = no. of bars, T (high tensile), diameter,
  bar mark, length (mm), spacing (mm, when distributed), `-STG` when staggered, layer position. The key of the
  format is drawn on every sheet (`draw_legend`).
- **BBS** after each set (`draw_bbs`): Position | Steel grade | Diameter | Number (in the element, of elements, total) |
  Symbol (sketch with segment lengths) | Length (m) | Mass (kg) = n x L x d^2/162 | Total mass (kg) = Mass x elements.
  Marks are package-wide; for footings "of elements" is the number of footings of the type (`NO=`).
- **Side bars of footings are placed inside the main bars** (inside BOTH the bottom and the top U legs; the top U sits
  inside the bottom U legs, and its corner bar sits in its bend): the 70 mm cover stays on the main U-bars, the side loop
  is reduced by the main bar diameters and its own; loops longer than 12 m are equal pieces lapped 60 d.
- **GB stirrups stop at the column face** (column ties continue through the joint); clear spans between support faces.
- **Levels** (`project.json` -> `levels`): founding level (bottom of PC) and top of grade beams; written on the footing
  section (F.L, T.O.PC, T.O.F, neck height up to T.O.GB) and on the GB longitudinal section (T.O.GB / B.O.GB).

- **Bars are bent, never sharp**: every bend drawn with a curve (`fillet`, `Sheet.pline(r=)`): U-bars, L-feet, GB legs,
  ties / stirrups (radius = bar radius + tie radius around the corner bar), bending sketches and BBS symbols; hooks via
  `hooked_tie` (shared by GB stirrups and column ties).
- Break lines (`Sheet.break_line`): straight line past both faces with one zig-zag in the middle (neck top, column above).
- No text on lines: panel names above the outlines, leg lengths inside the bends, Y-bar call-outs along the bar, title
  block values squeezed to the box (`Sheet.text(maxw=)`).

## Column necks (`gen_n.py`, sample Oct 2026)

- Arrangement of the vertical bars and the tie set are read from the consultant's `COLUMN SCH` block (to-scale
  section); sizes from the plan labels (`C1 30X80`) given in `project.json -> column_sizes`.
- Vertical bars: 90-degree foot (max(12d, 300)) standing on the bottom mesh, up to T.O.GB plus the column lap 60 d.
- Bars INSIDE the ties: corner bars centred at cover 40 + tie dia + d/2 from the faces, the other bars spaced as the
  designer drew them. Each tie wraps exactly the bars it holds in the designer's section (same shape: rectangle,
  hexagon ...), cut flat at the outer tie; L = out-to-out perimeter + two 135-deg hooks x 100; mirrored ties share one mark.
  On the section each tie is open at a square top corner and both ends wrap 135 deg around the corner bar, then run into
  the core. Bending sketches: only one or two sides dimensioned (+ one slanted side), the hook drawn with its 100 mm; n sets x 8/m -> @125 from T.O.F + 50 to
  T.O.GB (the ties continue through the GB joint) + 2 ties inside the footing. Identical ties share one mark.
- Usage: `python3 gen_n.py C1:F6:11 C3:F2:15 ...` (column type : footing type : number of necks).
- Necks (engineer's notes on the sample): the 135-degree hooks drawn on every tie in the section at its top-left
  corner bar; a vertical distribution line with ticks over the ties and a leader to the tie call-outs; the section
  cut A-A marked on the elevation. Founding level of the project -3.00.
