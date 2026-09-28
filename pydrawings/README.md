# pydrawings - the standalone Python version of the drawings generator

`pydrawings` is the Span Tech reinforcement / PT drawings generator as a **pure Python package**, with no CRM, no
server and no Node: the same drawings, the same office rules, the same sheets and the same files as the Node
generator under `shopdrawings/`. It reads the consultant's structural DXF (or LibreDWG JSON / DWG through `dwgread`),
the office's own RFT design plan, or a **RAM Concept model (`.cpt`)** directly, and writes the shop-drawing or
design-drawing package: one AutoCAD DXF per sheet (block + insert), the package DXF, SVG previews, CSV schedules,
`model.json`, `plan.json`, `quantities.json`, `punching.json`, `beams.json` and `REPORT.md`.

- Python 3.11 or later, **standard library only** (the `.cpt` is read with `sqlite3`). `ezdxf` is optional and used
  only by the tests to audit the written DXFs.
- Every module of `shopdrawings/lib/*.mjs` has its counterpart here, ported line by line (see `PORTING.md`); the
  data records keep the JS keys, so the JSON files are interchangeable between the two versions.
- **Parity with the Node generator is tested**: the same input through both gives the same sheets, the same texts,
  the same entity counts per sheet, the same schedules and the same quantities (`tests/test_parity.py`).

## Run

```bash
cd pydrawings
python3 -m pydrawings --input STRUCTURAL.dxf --out ./package --config project.json          # shop drawings from the G.A.
python3 -m pydrawings --input SLAB.cpt --out ./shop --mode shop --level "1ST FLOOR"          # shop drawings from RAM Concept
python3 -m pydrawings --input SLAB.cpt --out ./design --mode design --level "1ST FLOOR"      # design drawings from RAM Concept
python3 -m pydrawings --input RFT.dxf --out ./design --mode design --level "TYPICAL FLOOR"   # design drawings from the RFT plan
python3 -m pydrawings --sample --out ./sample-output                                         # the bundled demo
```

Options (the same as the Node CLI):

| flag | meaning |
|---|---|
| `--input <file>` | `.dxf`, `.json` (LibreDWG export), `.dwg` (needs `dwgread` on PATH or `DWGREAD=`), or a RAM Concept `.cpt` |
| `--out <dir>` | the package folder (`dxf/`, `preview/`, `schedules/`, the JSON files, `REPORT.md`) |
| `--mode shop` / `design` | shop drawings (default) or design drawings with the General Details rules |
| `--level "NAME"` | the level name printed on the sheets (default: from the file name) |
| `--level-id B1` | the level code in the drawing numbers (`SPAN-DD-B1-02`; parts take a letter) |
| `--config file.json` | `{ "meta": {...}, "spec": {...}, "layers": "path", "mode": "design" }` - project data and every rule override |
| `--project`, `--client`, `--location`, `--company`, `--prefix`, `--rev`, `--date`, `--prepared`, `--checked`, `--approved` | title-block data |
| `--layers file.json` | the layer standard (default `pydrawings/layers.spantech.json`) |
| `--no-svg` | skip the SVG previews |

The `spec` of the config takes every key the Node version takes: `cover`, `fc`, `fy`, `uEdge`, `topColumns`,
`drops`, `bottom`, `topMesh`, `pourStrip` (with `wall`), `openings`, `punching` (`ramFailed`, `override`, `ramOk`),
`beams` (`ramFailed`, `override`), `beamDesign` (`ram` / `office` / `max`), `beamTypes` (the project's unified beam
schedule), `mesh` (`bottom` / `both`), `rotate` (`auto` / `0` / `90`), `ramBands` (`all` / `user` / `none`),
`partMax`, `reference` (the architect's plan: `file`, `use`, `align`), `edits` (the bar edits by id), ...; `meta`
takes `project`, `client`, `consultant`, `contractor`, `location`, `company`, `prefix`, `revision`, `date`,
`prepared`, `designer`, `checked`, `approved`, `levelId`, `frame` (the sheet frame sizes and boxes; the bottom
detail strip is off by default), `frameDxf` (the office frame with `<TOKENS>`), `status`, ...

## Use it from Python

```python
import sys; sys.path.insert(0, 'pydrawings')
from pydrawings.cli import generate
res = generate(input_dxf='SLAB.cpt', out='./design', mode='design', level_names=['1ST FLOOR'],
               meta={'project': 'MY PROJECT', 'prefix': 'SPAN-DD', 'levelId': 'L01'}, spec={'beamDesign': 'max'})
res['quantities']['totals']['steel']['kg']
```

The lower-level API mirrors the Node modules: `ram_concept.read_ram_concept` / `ram_to_model`,
`extract.extract_model`, `design.prepare_ram_design` / `compose_design_package`, `sheets.compose_package`,
`quantities.quantities` / `cost_study`, `punching.punching_check`, `beam_design.design_beams`,
`beam_strips.write_beam_strips` / `beam_schedule`, `dxf_bars.read_bars` / `takeoff_from_bars` / `apply_takeoff`
(the take-off updated from a sheet edited in AutoCAD), `dxf_writer.to_dxf`, `dxf_reader.parse_dxf`,
`svg_writer.to_svg`, `reference.read_reference_plan` / `apply_reference`.

## Layout

```
pydrawings/
  pydrawings/            the package
    geometry.py          points, polygons, clipping, JS-compatible rounding (js_round, fmt_num, to_fixed, js_hypot)
    canvas.py            the drawing canvas (entities as dicts, blocks, dimensions, groups)
    dxf_writer.py        AC1015 DXF writer (handles, tables, blocks, XDATA, GROUPs)   dxf_reader.py  DXF parser
    svg_writer.py        SVG previews                                                  preview.py     plan previews
    sheet.py             the sheet: frame, plan areas, scales, tables, detail boxes, title block, key plan, notes
    rebar.py             the office reinforcement rules (column bars, U-bars, punching, openings, laps, marks)
    details.py           the detail drawings (sections, trimmers, legends)
    extract.py           the structural / RFT plan reader          libredwg_json.py   LibreDWG JSON input
    reference.py         the architect's reference plan fitted on the RAM model
    ram_concept.py       the RAM Concept .cpt reader and the model builder (bodies, parts, rotation, tendons, bands)
    beam_strips.py       beam spans / supports, the beam strips written into the .cpt, the beam schedule and types
    beam_design.py       the office beam design (continuous beam, flexure, shear, deflection)
    punching.py          the indicative punching check
    quantities.py        the take-off and the cost study
    dxf_bars.py          bars read back from an edited sheet (the bar tags) and the take-off update
    sheets.py            the shop sheets (framing, bars, U-bars, voids, openings, cables, crossings, punching, beams)
    design.py            the design drawings (the D1..D12 rules, the office bar, the design sheets)
    cli.py, __main__.py  the command line and the package writer
    layers.spantech.json the Span Tech layer standard
  tests/                 unit tests per module + the Node parity test (python3 -m unittest discover -s tests -t .)
  PORTING.md             how the port maps to the Node modules
```

## Tests

```bash
cd pydrawings
python3 -m unittest discover -s tests -t .
```

The parity tests run the Node CLI (`node shopdrawings/cli.mjs`) and the Python CLI on the bundled sample and on
synthetic RAM models (plain, with beams, stepped) in shop and design mode and compare sheet by sheet; they are
skipped when Node is not installed. With `ezdxf` installed every written DXF is also audited (zero errors).

## What is not in the Python version

The CRM (projects, levels, runs, revisions, submittals, the editor, the settings screens) stays in the Node
application; `pydrawings` is the generator only. Everything the generator does is here: both modes, every sheet,
the cable sheets and the crossings plan, the beam design and schedule, the punching check, the reference plan, the
bar tags and the take-off update, the quantities and the cost study.
