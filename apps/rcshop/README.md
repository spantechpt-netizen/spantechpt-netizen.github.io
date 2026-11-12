# RC Shop — standalone RC shop-drawing program

The consultant's drawing goes in, and the shop drawings come out: DXF sheets and BBS per package or per zone, every file checked, and the delivery zipped. It runs offline. The engine is `tools/rc-shopdrawings`; its method and rules are in that folder's `SKILL.md`.

## Run

```bash
pip install -r requirements.txt
python -m rcshop            # window
python -m rcshop --help     # command line
```

## A project

```
<project>/rcshop.json   name, modules, step history
<project>/input/        drawings as received
<project>/work/         engine folder: project.json, footings.json, footings_ext.json, pool.json, DXF, out/
<project>/logs/         a log per step + check.txt
<project>/deliveries/   zip parts (under the size limit in Settings)
```

1. **New project**, then tick the **modules** you need: grade beams, footings, rafts / CF, necks, concrete dims, packages per zone, cores, stair starters, slab on grade, strip, pool.
2. **Add DWG / DXF.** The DWG is converted with ODA File Converter or LibreDWG, whichever is set in Settings. A DXF saved from AutoCAD is taken as it is.
3. Run **survey**. It writes `survey/survey.md` and a draft `project.json`.
4. **project.json from survey draft**, or apply a **reading profile** for a consultant you have worked with before. Check the values, then add the schedules (`footings.json`, `footings_ext.json`, `pool.json`).
5. **What's missing?** lists every key or file each ticked module still needs.
6. **Run all ready.** Each step shows one of these states:
   - **ready**: its inputs are all there.
   - **blocked**: it says what is missing.
   - **done**
   - **stale**: an input changed after the step ran.
   - **failed**: see its log.

   The **args** field sends arguments to one step, for example `AREA 2` for one zone.
7. **check** audits every DXF and looks for objects AutoCAD rejects. **package** zips the delivery.

**Reading profiles** remember how one consultant draws: layers, blocks, label patterns and views. They are saved from a finished project in `~/.rcshop/profiles/` and applied to that consultant's next project. A profile never holds project data such as schedules, levels or title-block values.

## What's new in 0.3

- **Stair starters** and **slab on grade** modules. The reader has cards for the stair starter outlines and bars, the
  S.O.G tags, the slab thickness tags and the window of the plan that carries them. They are saved into the `stairs`
  and `sog` objects of project.json, and kept in reading profiles.
- Sheet numbers continue across the areas for every package: necks 20100, cores 30100, stairs 40100, grade beams 50100,
  S.O.G 60100.
- The **check** step fails a file with anything drawn outside its sheet frame.
- Core walls: horizontal U-bars per wall face, and starter + neck bar verticals. Grade beams: top legs 600, bottom
  legs 200, grey grid.

## What's new in 0.2

- Ties, stirrups and core corner ties are drawn **opened at the hook corner** (the two 135° hooks apart, the closing
  point visible) on the sheets and in the BBS, with every side written. This covers column necks, grade beams and core necks.
- Column necks: starter bars (full Ld in the footing + 65 d above T.O.F) and separate straight neck bars (T.O.F to
  T.O.GB + 65 d), ties through the whole footing, first tie 50 from T.O.F / T.O.GB.
- When the program is updated, the sheets drawn before the update show as **stale**, so you know to run them again.

## Drawing reader (Phase 2)

The reader page is where the program learns how this consultant draws. It shows the drawing itself, and you can zoom with the wheel at the cursor, pan with the middle or right button, use **Fit**, **Zoom window** and the **View** list (a layout's viewport), and **Find text**.

- **Roles.** The left column lists the cards of what the engine has to find:
  - the GB plan layout
  - GB edges and GB labels
  - columns
  - grid bubbles, with the attribute that holds the axis name
  - the foundation plan window
  - footing / raft outlines
  - PC outlines
  - columns on the foundation plan
  - footing labels
  - grid lines
  - core walls
  - stair starter outlines and their bars
  - S.O.G tags, slab thickness tags and the window of their plan

  Pick a card, then click an example on the drawing. A layer, block or text pattern is learned from that click. Each further click on a label widens the pattern, for example `F6A`, `CF2`, `RAFT-1` give `(F\d+[A-Z]?|CF\d+[A-Z]?|RAFT\-?\d+[A-Z]?)`.
- **Live check.** Everything a role catches is highlighted in the role's colour, and the card counts it, for example "219 labels, 32 distinct: CF1, CF2, ...". **Matches** lists what was caught; double-click an entry to zoom to each instance in turn. **Focus** greys the rest of the drawing.
- **Suggest** fills the empty roles from layer names, label texts, blocks and layout names. A suggestion is marked **?** until you confirm it.
- **Inspector and Layers.** The inspector shows the clicked entity: type, layer, text and block attributes. The Layers tab shows counts and lets you hide, show or isolate layers, or use the selected layers for the active role.
- **Save to project.json** writes the keys the engine reads. **Save as profile** keeps them for this consultant's next project.
- **Shortcuts on the drawing:** `f` fit, `z` zoom window, `1`-`9` pick a role, `Esc` back to pick mode, `Ctrl+S` save.

The drawing is flattened once and cached in `work/.rcshop_cache/`. A 70 MB plan takes about 75 s the first time and opens at once after that. Rendering runs in the background, and while it runs the last image is moved and scaled straight away.

**Review** previews every output DXF sheet by sheet, next to its check result.

## Build for Windows

`build_windows.bat` (Nuitka) produces `RCShop.exe` with the engine in an `engine\` folder beside it. The program runs the engine scripts itself through `RCShop.exe engine <script>`, so no Python is needed on the user's machine.

**DWG conversion:** LibreDWG is GPL. Do not ship it inside a closed build. Point Settings to ODA File Converter (a free download), or work from DXF.

## Test

`python tests/test_smoke.py` runs with no project data. It builds a pool project from the engine's example, then generates the sheets, checks them and packs the delivery.
