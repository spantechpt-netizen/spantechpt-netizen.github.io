# Porting guide - `shopdrawings/` (Node) -> `pydrawings/` (pure Python)

`pydrawings` is the standalone Python version of the drawings generator: the same drawings, the same rules, the same
files, with no CRM and no Node. Every module of `shopdrawings/lib/*.mjs` becomes one Python module of the package
`pydrawings/pydrawings/`. The port is **faithful, line by line**: the same rules, the same numbers, the same text strings
on the sheets, the same layer names, the same file names. Nothing is simplified, nothing is "improved", nothing is
left out with a TODO. When a JS line looks odd, port it as it is and add a short comment.

## Rules

- Python 3.11, **standard library only** (`sqlite3` for the RAM `.cpt`, `json`, `math`, `re`, `pathlib`, `zipfile`,
  `dataclasses` if useful). No numpy, no ezdxf, no third-party packages.
- **Module names**: `geometry.mjs` -> `geometry.py`, `dxf-writer.mjs` -> `dxf_writer.py`, `ram-concept.mjs` ->
  `ram_concept.py`, `beam-strips.mjs` -> `beam_strips.py`, `beam-design.mjs` -> `beam_design.py`,
  `dxf-bars.mjs` -> `dxf_bars.py`, `libredwg-json.mjs` -> `libredwg_json.py`, `svg-writer.mjs` -> `svg_writer.py`,
  `cli.mjs` -> `cli.py` (+ `__main__.py`). One module per JS file; keep the functions in the same order.
- **Function names**: the JS export name in snake_case (`pointInPolygon` -> `point_in_polygon`, `ramToModel` ->
  `ram_to_model`, `topAtColumns` -> `top_at_columns`, `officeBar` -> `office_bar`). Keep the same argument order and
  the same defaults. Module-level JS constants keep their names (`DEFAULT_SPEC`, `U_BOTTOM_LEG`, `DIM100`, `CAB`,
  `SHEETS`, `DESIGN_SHEETS`, `OFFICE_LAYERS`, `DETAILS`, `VOID_TABLE`, `XDATA_APP` ...).
- **Data records are plain dicts with the JS keys unchanged (camelCase kept)**: a level is
  `{'id': ..., 'thickness': ..., 'thickZones': [...], 'pourStrips': [...], 'existing': {...}, 'ram': {...}}`, a
  point is `{'x': ..., 'y': ...}`, a bar item keeps `l1`, `l2`, `uEnd`, `posCands`, `distCands` ... exactly as in JS.
  This keeps `model.json`, `plan.json`, `quantities.json`, `punching.json`, `beams.json` byte-for-byte compatible with
  the Node output. Read keys with `.get()` where JS reads a possibly missing property (`level.walls || []` ->
  `level.get('walls') or []`); `undefined`/`null` -> `None`.
- JS `Math.round` rounds half away from zero for positives (`Math.round(2.5) === 3`, `Math.round(-2.5) === -2`):
  use the helper `js_round` from `geometry.py` (floor(x + 0.5)), never Python's banker's `round`. `Math.floor`,
  `Math.ceil`, `Math.hypot`, `Math.atan2` -> `math.*`. `toFixed(n)` -> `f'{v:.{n}f}'`. `String(v)` of a float that is
  a whole number prints without `.0` in JS: use `fmt_num` from `geometry.py` for text that reaches the sheets.
- Integer-keyed sort / string compare exactly as JS (`localeCompare` -> plain `<` on str is fine for ASCII ids).
- `Array.prototype.sort` in JS is stable; Python's is stable too. `[...new Set(a)]` -> `list(dict.fromkeys(a))`
  (order kept).
- Text on the sheets: copy every string literally (English, upper case where the JS has it, `·`, `≈`,
  the `%%c` / `\U+00B0` conventions of the DXF writer included).
- Classes: `Canvas`, `Sheet`, `BarList`, `Placer`-like helper objects keep their names and method names in
  snake_case (`pl.pline(...)`, `pl.text(...)`, `pl.dimension(...)`, `sheet.detail_box(...)`, `sheet.detail_pen(...)`,
  `sheet.table(...)`, `sheet.set_plan(...)`). Method options that are a JS object become `**kw` or an `o: dict`
  parameter: `pl.text(x, y, s, layer='TEXT', h=2.5, align='C', valign='M', rot=0, style=..., width_factor=...)`,
  with the option keys in snake_case (`widthFactor` -> `width_factor`, `textMid` -> `text_mid`, `styleDef` ->
  `style_def`). Entities the canvas stores are dicts with the JS keys (`{'t': 'pline', 'pts': [...], 'layer': ...}`)
  so `dxf_writer.to_dxf` and `svg_writer.to_svg` read them the same way.
- Module-private JS helpers become module-level Python functions with a leading underscore only if they are not
  exported in JS; exported JS functions are public.
- Errors: `throw new Error(msg)` -> `raise ValueError(msg)` (or a `DrawingsError(Exception)` defined in `geometry.py`
  and reused).
- File output (`cli.py`): the same folder layout and file names as Node (`dxf/<DRAWING_NO>_<TITLE>.dxf`,
  `DESIGN_DRAWINGS_PACKAGE.dxf` / `SHOP_DRAWINGS_PACKAGE.dxf`, `preview/*.svg`, `schedules/*.csv`, `model.json`,
  `plan.json`, `quantities.json`, `punching.json`, `beams.json`, `REPORT.md`); same CLI flags
  (`--input --out --mode --level --level-id --config --no-svg --layers`), run as `python -m pydrawings ...`.
- Every module ends with nothing else than its code (no demo `main`). Every module compiles
  (`python3 -m py_compile`). Type hints are welcome but optional; docstrings copied from the JS comments.
- Do NOT edit `shopdrawings/` (the Node version stays the reference) and do NOT edit modules you were not asked to
  port. Put shared small helpers only in `geometry.py` (`js_round`, `fmt_num`, `ceil_to`, `DrawingsError`).

## Cross-module API (what the other modules will call)

The Python signatures follow the JS ones; these are the ones every module relies on:

- `geometry.py`: `dist(a, b)`, `bbox(points) -> {'minX','minY','maxX','maxY','w','h','cx','cy'}`, `expand_bbox`,
  `polygon_area`, `centroid`, `point_in_polygon(p, poly)`, `dist_to_polygon`, `dist_to_seg(p, a, b)`,
  `clip_segment_to_polygon(a, b, poly) -> list of [p, q]`, `clip_polyline_to_polygon`, `rect_polygon({'x','y','w','h'})`,
  `circle_polygon`, `edges(poly)`, `as_axis_rect`, `clean_polygon`, `simplify_polygon`, `ceil_to(v, step)`,
  `js_round`, `fmt_num`, `unit(a, b)`, `perp(u)`, `add(p, u, k)`, `mid(a, b)`, `DrawingsError`.
- `canvas.py`: `class Canvas(name='*Model_Space', root=None)` with `.entities`, `.blocks` (dict name -> Canvas),
  `.layers`, `.dim_styles`, `.text_styles`, `.groups`; methods `layer(name, def=None)`, `block(name)`, `add(e)`,
  `line`, `pline`, `rect`, `circle`, `arc`, `text`, `mtext`, `hatch`, `solid`, `insert`, `dimension`,
  `dim_style_def(name, d)`, `text_style_def(name, d)`, `group(name, entities, desc=None)`, `arrow`, `leader`, `dim`.
- `dxf_writer.py`: `to_dxf(root, opts=None) -> str`, `encode_text(s)`, `XDATA_APP`.
  `dxf_reader.py`: `parse_dxf(text) -> {'header','blocks' (dict name->{'name','base','entities'}),'entities'}`.
- `sheet.py`: `DEFAULT_FRAME`, `SHEET_SIZES`, `layout_for(size, frame_opts)`, `choose_scale(bbox, area, margin=12)`,
  `class Sheet(root, block_name=..., size='A1', scale=100, frame=None)` with `.S`, `.L`, `.blk`, `.pp`, `.pl`,
  `frame()`, `set_plan(bbox, area)`, `table(...)`, `detail_box(i, title, scale_label)`, `detail_pen(box, scale, gb, inner=None)`,
  `make_pen(P, k)`, `stamp(...)`, `title_block(...)`, `key_plan(...)`, `notes(...)`, `legend(...)`, `refs(...)` (whatever the JS has).
- `rebar.py`: `DEFAULT_SPEC`, `U_BOTTOM_LEG`, `bar_weight_per_m(dia)`, `class BarList`, `lap_length`, `development_length`,
  `hook_leg`, `split_run`, `top_at_columns(level, spec)`, `support_columns(level, gap=500)`, `punching(level, spec)`,
  `perimeter(...)`, `openings(...)`, `sunken(...)`, `region_polygon(o)`, `polygon_of(o)`, `side_lining`, `edge_has_beam`,
  `edge_runs_between_columns`, `length_table`, ... (every export of rebar.mjs).
- `ram_concept.py`: `read_ram_concept(path)`, `ram_to_model(ram, level_name='1ST FLOOR', level_id=None, spec=None)`,
  `clip_tendon(t, poly, tol)`, `write_beam_strips(...)`, `mode_angle`, ... (every export).
- `extract.py`: `extract_model(dxf, options)`, `classify_layer`, `read_spec_from_text`, `chain_segments`, ...
- `sheets.py`: `SHEETS`, `build_sheet(model=, level=, def_=, meta=, index=, total=, draw=)`, `draw_base(sheet, pl, level, o)`,
  `common_notes`, `level_assumptions`, `grid_ref`, `fmt_mm`, `pack_sheets`, `ram_cables_sheet`, `beams_sheet`,
  `compose_package(model, meta)`, `content_bbox`, the beam schedule helpers, ...
- `design.py`: `extract_design`, `prepare_ram_design`, `compose_design_package`, `design_additions`, `mark_core_walls`,
  `clip_to_slab`, `clip_at_openings`, `office_bar`, `draw_existing`, `apply_column_rule`, `bar_id`, `plan_data`,
  `apply_edits`, `DESIGN_SHEETS`, `DETAILS`, `VOID_TABLE`, `DIM100`, `OFFICE_LAYERS`, `OFFICE_TEXT_STYLE`, ...
- `quantities.py`: `quantities(model, pack)`, `steel_of`, `mesh_of`, `concrete_of`, `cables_of`, `cost_study(q, rates)`.
- `punching.py`: `punching_check(level, spec)`, `blocking_after`, ...; `beam_design.py`: `design_beams(level, spec)`,
  `analyse_beam`, `three_moment`, `flexure_as`, `pick_bars`, `shear_design`, `deflection_check`, `beam_blocking_after`;
  `beam_strips.py`: `beam_spans(beam, columns, walls, beams=None)`, `beam_schedule(ram, level, library=None, design='ram', office=None)`,
  `type_covers`, `size50`, `write_beam_strips` (if it lives there in JS), ...
- `dxf_bars.py`: `read_bars`, `parse_callout`, `bar_figures`, `takeoff_from_bars`, `apply_takeoff`.
- `svg_writer.py`: `to_svg(root, opts)`; `libredwg_json.py`: `from_libredwg_json(obj)`; `reference.py`: every export.

When a module you port needs a function from a module ported by someone else, import it by the snake_case name
above (`from .geometry import dist, bbox`) and trust the signature; do not re-implement it locally.
