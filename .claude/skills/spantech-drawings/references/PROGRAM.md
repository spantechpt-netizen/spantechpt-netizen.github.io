# The program — layout, module map, options, outputs, tests, working conventions

Repository: `spantechpt-netizen/spantechpt-netizen.github.io` (the Span Tech PT Suite CRM). The drawings work
lives on a feature branch with a draft PR; the repo zip the user runs is `SPANTECH_PT_SUITE_PROGRAM.zip`, the Python
package alone is `PYDRAWINGS_PYTHON_VERSION.zip`. Node ≥ 22 for the CRM and the Node generator; Python ≥ 3.11
standard library for `pydrawings` (ezdxf optional, tests only).

Contents: 1 module map · 2 data flow · 3 spec / meta keys · 4 outputs · 5 CRM module · 6 `app.py` · 7 tests and parity ·
8 changing code, step by step · 9 sandbox and scratchpad conventions · 10 known traps

---

## 1. Module map (Node ↔ Python, one file each)

| Node `shopdrawings/lib/` | Python `pydrawings/pydrawings/` | what |
|---|---|---|
| `geometry.mjs` | `geometry.py` | points, polygons, clipping, bbox; **JS number semantics** `js_round` (half away from zero), `fmt_num` (no `.0`), `to_fixed`, `js_hypot` — use these for anything that reaches a sheet |
| `canvas.mjs` | `canvas.py` | the drawing model: entities as dicts (`{'t':'pline',...}`), blocks, `text()` and `dimension()` with the **reading-direction normalisation**, groups, XDATA tags |
| `dxf-writer.mjs` | `dxf_writer.py` | AC1015 DXF: tables, layers from `layers.spantech.json`, text styles, DIMSTYLE, blocks + INSERT, HATCH, MTEXT, XDATA, GROUP; handles |
| `dxf-reader.mjs` | `dxf_reader.py` | ASCII DXF → entities (LINE, LWPOLYLINE, CIRCLE, ARC, TEXT, MTEXT, INSERT, HATCH, DIMENSION, attributes, XDATA) |
| `libredwg-json.mjs` | `libredwg_json.py` | LibreDWG `dwgread -O json` → the same entities (DWG input) |
| `svg-writer.mjs`, `preview.mjs` | `svg_writer.py`, `preview.py` | SVG previews of sheets and of input drawings |
| `sheet.mjs` | `sheet.py` | the sheet: `DEFAULT_FRAME`, plan areas and scale choice, right strip boxes, tables, detail boxes, title block, key plan, notes, custom frame DXF with `<TOKENS>` |
| `rebar.mjs` | `rebar.py` | `DEFAULT_SPEC`, SBC 304 lengths (ld, lap, hooks), bar splitting into stock pieces, bar list / marks, shop zone generators (mesh, column bars, U-bars, trimmers, punching links) |
| `details.mjs` | `details.py` | section / plan detail drawings, legends |
| `extract.mjs` | `extract.py` | structural DXF / RFT plan → levels, grid, columns, regions, designer's bars, spec from notes, assumptions |
| `reference.mjs` | `reference.py` | the architect's reference plan: read, fit on RAM (columns / common point), apply (grid, columns, outline) |
| `ram-concept.mjs` | `ram_concept.py` | `.cpt` (SQLite) → bodies by TOC, parts, rotation frame, columns, walls, beams, tendons (with `heights` and `elevs`), bands, SSR, punching checks, loads, pour strips, materials → `ramToModel` / `prepareRamDesign` input; **per-group spec merge** |
| `beam-strips.mjs` | `beam_strips.py` | `beamSpans` (supports incl. deeper beams), `writeBeamStrips` (into a copy of the .cpt), `beamSchedule` + `typeCovers` (unified project schedule) |
| `beam-design.mjs` | `beam_design.py` | the office continuous-beam analysis and design (flexure, shear, deflection) |
| `punching.mjs` | `punching.py` | the indicative two-way shear check, PS sizing for a bypass |
| `quantities.mjs` | `quantities.py` | `quantities()` (steel / concrete / cables per level) and `costStudy(q, rates)` |
| `dxf-bars.mjs` | `dxf_bars.py` | `readBars` (by XDATA tag) / `takeoffFromBars` / `applyTakeoff` — the take-off from a sheet edited in AutoCAD |
| `sheets.mjs` | `sheets.py` | shop sheets: `SHEETS`, framing / bottom / top / RAM additional / U-bars / voids / openings / cables (`CAB`, `cableStations`, `cableMarksOf`, `ramCablesSheet`, `ramCrossingsSheet`) / punching / beams / cover; `composePackage` |
| `design.mjs` | `design.py` | design drawings: `DETAILS` D1..D12, `VOID_TABLE`, the rules (`topAtColumns`, `supportColumns`, `topAtBeams`, `perimeterBars`, `dropBars`, `pourStripBars`, `voidBars`, `openingBars`, `blockBeams`, `cornerBars`), `legSide`, `readableRot`, `Placer` / `textBox`, `officeBar`, `distDim`, `slabTag`, `beamLabels`, `DESIGN_SHEETS`, `prepareRamDesign`, `composeDesignPackage` |
| `cli.mjs` | `cli.py`, `__main__.py` | flags → `generate()` → the package folder; `--sample` |

Porting rules are in `pydrawings/PORTING.md` (dict records with the JS keys unchanged, camelCase kept; snake_case function
names; `raise ValueError` for `throw`; no third-party packages; same file names).

## 2. Data flow

```
.cpt ──ram-concept──▶ ram record ──▶ ramToModel (shop)  ──▶ sheets.composePackage ──▶ Canvas per sheet ──▶ dxf-writer / svg-writer
                                └──▶ prepareRamDesign (design) ──▶ design rules ──▶ composeDesignPackage ──┘
.dxf ──dxf-reader──▶ entities ──extract──▶ model (levels, grid, columns, regions, designer bars, spec, assumptions) ──▶ same
reference.dxf ──reference──▶ fitted grid / columns / outline replacing RAM's (spec.reference)
cli.generate ──▶ <out>/dxf, preview, schedules, package DXF, model.json, plan.json, quantities.json, punching.json, beams.json, REPORT.md
```

`model.spec` = `DEFAULT_SPEC` ⊕ what the notes / model give ⊕ the config `spec` (merged **per group**: `{uEdge:{total:4400}}`
keeps `uEdge.beamLeg`); `model.spec.sources` says where each figure came from and drives the printed assumptions.

## 3. Spec and meta keys (config `{ "meta": {...}, "spec": {...} }`)

`spec` (defaults in `DEFAULT_SPEC`, `rebar.mjs`): `fc` 30, `fy` 420, `cover` 25, `stock` 12000, `bottom {dia 12, spacing 200}`,
`topColumns {dia 16, spacing 150, rule 'office', length 4000, edgeFactor 0.7, dropMargin 0, dropMax 6000, minBeyond 1500,
wallAlongMax 6000, mergeGap 500}`, `uEdge {dia 12, spacing 150, total 4000, beamLeg 400, beamTop 3600, leg 1200}`, `uCircle`,
`edgeBars`, `ringBars`, `voids`, `openings`, `sunken`, `punching {dia 10, legSpacing 100, extentFactor 2, psDia 12, rowSpacing 100,
ramFailed [], override {columns, by, date, note}, ramOk}`, `walls {parallelBars, cornerDiagonals}`, `perimSpan`, `thicknessMesh`,
`drops {dia 12, spacing 150, leg 500, bendCover 50}`, `barOffset 500`, `pourStrip {dia, spacing, length, uDia, uSpacing, uTotal,
longDia, longSpacing, wall {...}}`, `blockBeam`, `topMesh`, `mesh 'bottom'|'both'`, `rotate 'auto'|0|90`, `partMax 60000`,
`partOverlap 600`, `ramBands 'all'|'user'|'none'`, `wallThickness 250`, `beams {bandMaxWidth 3000, ramFailed [], override}`,
`beamDesign 'ram'|'office'|'max'`, `beamTypes [...]` (the project's records; on a G.A. / zone-file design run each record is `{mark, top, bottom, stirrups, legs}` with the table's texts, matched by the mark on the plan), `beamTable {title, note, cols [{key,title,w}], rows [{mark, ...}]}` (the project's own table printed as the framing sheet schedule), `cables {figures 'ram'|'chair'}`,
`reference {file, use {grid, columns, outline}, align {mode 'auto'|'point', ...}}`, `edits [...]` (by bar id from `plan.json`).

`meta`: `project`, `projectAr`, `code`, `client`, `consultant`, `contractor`, `location`, `country`, `company`, `prefix`
(`SPAN-DD` / `SPAN-SD`), `revision`, `date`, `prepared`, `designer`, `checked`, `approved`, `levelId`, `level`, `zone`,
`status`, `notes`, `frame {size, rightWidth, bottomStrip, titleH, refsH, keyH, schedH, keyplan, refs, schedule, details:false}`,
`frameDxf`, `gridTag`.

## 4. Outputs (per run)

`dxf/<DRAWING_NO>_<BLOCK>.dxf` (block + INSERT at 0,0), `DESIGN_DRAWINGS_PACKAGE.dxf` / `SHOP_DRAWINGS_PACKAGE.dxf`,
`preview/*.svg`, `schedules/*.csv`, `model.json`, `plan.json`, `quantities.json`, `punching.json`, `beams.json`, `REPORT.md`
(findings, assumptions, per-column punching table, per-beam forces, sheet list). The CRM / app zip it as
`<prefix>-<project>-<level>_REV<nn>.zip`. `generate()` returns `{sheets, assumptions, findings, quantities, punching, beams,
report, ...}` — the CRM and `app.py` store these on the run.

## 5. The CRM Drawings module (Node)

- `server/drawings.js`: defaults (`DRAWING_DEFAULTS`, frame, rates, submittal template), project code numbering (`P26-001`),
  drawing numbers, upload streaming, generation in a **worker thread**, ZIP (`server/zip.js`), run status
  (`draft` / `issued` / `superseded` / `blocked`), `blockingAfter` (punching) and `beamBlockingAfter`.
- `server/submittals.js`: items from the runs' title blocks (cover left out), sequential `SPAN-SUB-<project>-<nnn>`, `-R1` on
  re-issue, re-submission naming the earlier submittal and revision, printable A4 HTML form.
- `server/routes/drawings.js`: `/api/drawings/projects` (+ `/:id`, `/beam-types`, `/beam-types/import`, `/files`, `/quantities`,
  `/cost`, `/submittals`), `/levels/:id` (+ `/runs`, `/edits`, `/reference`), `/runs/:id` (+ `/takeoff`, `/regenerate`,
  `/punching-decision`, `/beam-decision`, `/plan`, `/beam-strips`, `/quantities`, `/zip`, `/files/:kind/:name`),
  `/files/:id`, `/frame`, `/submittals/:id` (+ `/form`). Permissions `drawings.view / create / delete`.
- Tables: `drawing_projects` (+ `mesh`, `beam_design`, `rotate`, `beam_types_json`), `drawing_levels` (+ `edits_json`, `ref_*`,
  `punching_json`), `drawing_runs` (+ `notes`, `status`, `edits_json`, `quantities_json`, `beams_json`, `beam_strips_json`,
  `mesh`, `beam_design`, `rotate`, `punching_json`, `beam_check_json`), `drawing_files`, `drawing_submittals`.
- UI: `public/views/drawings.js` (list, project page tabs: levels / files / history / submittals / quantities / beam types;
  run page; settings → Drawings), `public/views/rebar-editor.js`, Arabic / English strings in the i18n dictionaries; help pages
  `public/help/ram-drawings-workflow.html`, `ram-file-workflow.html` generated from `docs/*.md` with the skill's `scripts/md2help.py` (repo copy under `.claude/skills/spantech-drawings/scripts/`).
- Tests `test/drawings.test.js` (18) drive the whole module end to end on the synthetic model.

## 6. `pydrawings/app.py` — the one-file app

One stdlib file: `ThreadingHTTPServer` + `BaseHTTPRequestHandler`, a `@route(method, pattern)` regex table, raw-body uploads
with the file name in the query (`?name=`), a JSON `Store` (`data/db.json`: settings, projects, levels, runs, files,
submittals, counters; a lock; atomic save), run folders `data/projects/<pid>/runs/<rid>/{source, out/, package.zip, edited/,
beam-strips.cpt}`, `GEN_LOCK` serialising generation (synchronous in the request; the page waits), `open_in_file_manager`.
Constants mirror the CRM (`MODES`, `RAM_BANDS`, `MESH_FACES`, `BEAM_DESIGN`, `ROTATIONS`, `FILE_CATEGORIES`, `SUBMITTAL_STATUS`,
`SUBMITTAL_PURPOSES`, `FRAME_DEFAULTS`, `RATE_DEFAULTS`, `SUBMITTAL_DEFAULTS`, `DRAWING_DEFAULTS`). `start_run(level, project,
query, source_run, upload)` builds the spec like the CRM. `PAGE = r"""..."""` embeds the CRM's CSS (app.css), the small JS
toolkit (`el / icon / toast / openModal / confirmDialog / field / readForm / dataTable`), a hash router (`#/projects`,
`#/projects/:id[/tab/:tab]`, `#/projects/:id/run/:rid`, `#/settings`, `#/help`) and `DICT` (the CRM strings + `EXTRA`).
Not in the app: users / permissions, the interactive rebar editor. Test: `pydrawings/tests/test_app.py` (in-process server,
end to end incl. submittals). Run: `cd pydrawings && python3 app.py [--port --host --data --no-browser --verbose]`.

When the CRM gains a feature the app should have, add: the constant(s), the route(s), the store table, the page view /
form, the strings (AR + EN), the test steps, the README / workflow §8ب paragraph.

## 7. Tests and parity

```bash
npm test                                                     # 155: CRM + test/shopdrawings.test.js (38) + test/drawings.test.js (18)
cd pydrawings && python3 -m unittest discover -s tests -t .  # 62: foundation, rebar, extract, ram reader, beam/punching/quantities, design, sheets, parity, app
```

- `pydrawings/tests/test_parity.py` runs both CLIs on the bundled sample and synthetic RAM models (plain, beams, stepped; shop
  and design) and compares sheet files, entity counts per type, text multisets, CSVs, JSONs, assumptions; skipped without Node.
- `test_sheets.py` compares against a **stored** Node reference package. After a rule change that legitimately alters the
  sheets, regenerate it: `node shopdrawings/cli.mjs --input <synthetic plain cpt> --out <ref dir> --mode shop --level BASEMENT
  --no-svg` (the synthetic `.cpt` is built by the test helpers). Only after confirming the Node output itself is right.
- With ezdxf installed the Python suite audits every written DXF (zero errors expected).
- `unittest discover -s tests` must be run **from the `pydrawings/` folder**; the skill's `scripts/md2help.py` from the repo root.

## 8. Changing code, step by step

1. Reproduce (synthetic or the user's model in the scratchpad); render the spot (the skill's `scripts/render_dxf.py`, window argument).
2. Node first (`shopdrawings/lib/*.mjs`); assertion in `test/shopdrawings.test.js`.
3. Python port (`pydrawings/pydrawings/*.py`, same names / numbers / strings); `pydrawings/tests/*` updated; parity reference
   regenerated if needed.
4. Option exposed in the CRM (settings / project / run) **and** `app.py` if it is a switch.
5. `npm test`, Python suite, ezdxf audit, render and look, regenerate the user's real model and diff quantities / assumptions.
6. Docs: `shopdrawings/README.md`, `pydrawings/README.md`, `docs/RAM-DRAWINGS-WORKFLOW.md` → `python3 .claude/skills/spantech-drawings/scripts/md2help.py
   docs/RAM-DRAWINGS-WORKFLOW.md`; PR body; this skill's `RULES.md`.
7. Commit (one-line rule statement + why), push, rebuild and send the zips + zooms, short Arabic summary.

## 9. Sandbox and scratchpad conventions

- No RAM, no AutoCAD in the sandbox: verify with ezdxf (`recover.readfile`, `Auditor`) and rendered PNGs (`ezdxf.addons.drawing`
  + matplotlib). Headless Chromium (`chrome --headless=new --no-sandbox --screenshot=... --virtual-time-budget=6000 URL`) for
  UI screenshots of the CRM / app.
- The user's project files (`.cpt`, `.dwg`, `.dxf`, project JSON, the licensed PT Suite `.py`) live in the scratchpad only —
  never `git add` them, never in a PR body, never in a skill. Deliver outputs with the file-sending tool.
- Start a test server with `(node server/index.js > log & echo $! > pid)` and stop it with `kill $(cat pid)`; never
  `pkill -f` / `kill $(pgrep -f ...)`.
- Build zips for delivery from a clean `git archive` / copy (no `node_modules`, no `data/`, no scratch files);
  `pydrawings/.gitignore` excludes `data/`.

## 10. Known traps (each cost time once)

- Python `round` is banker's rounding; JS `Math.round` is not → `js_round`. `str(5.0)` prints `5.0` → `fmt_num`.
- f-strings with backslash-escaped quotes inside HTML builders break: build the row with a helper and plain concatenation.
- A partial spec group override crashed the shop path (`KeyError 'beamLeg'`) until the per-group merge — keep the merge in
  both readers.
- The cwd resets between shell calls in some harnesses: always `cd` explicitly (`pydrawings/` for its tests, repo root for docs).
- A RAM column turned 90° stores its plan sizes swapped; a slab hole loses collinear mesh nodes (one U-bar symbol per side).
- The design sheet does not show tendon ends, so a test asserting an end figure on a design sheet is wrong by construction.
- `t('download','Download')` style fallbacks show English in the Arabic UI — use `isRTL() ? 'تحميل' : 'Download'`.
