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

1. **New project**, then tick the **modules** you need: grade beams, footings, rafts / CF, necks, concrete dims, packages per zone, cores, strip, pool.
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

## Build for Windows

`build_windows.bat` (Nuitka) produces `RCShop.exe` with the engine in an `engine\` folder beside it. The program runs the engine scripts itself through `RCShop.exe engine <script>`, so no Python is needed on the user's machine.

**DWG conversion:** LibreDWG is GPL. Do not ship it inside a closed build. Point Settings to ODA File Converter (a free download), or work from DXF.

## Test

`python tests/test_smoke.py` runs with no project data. It builds a pool project from the engine's example, then generates the sheets, checks them and packs the delivery.
