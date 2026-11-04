"""The pipeline: every engine script as a step with what it needs and what it makes (paths relative to work/).

`{name}` in args / needs / makes is filled from the project (see Workspace.vars); an arg that resolves to a list
is expanded into several arguments. `makes` may hold glob patterns.
"""
from dataclasses import dataclass, field


@dataclass
class Step:
    id: str
    title: str
    group: str                      # read / generate / finish
    module: str                     # feature switch (Workspace.modules)
    script: str = ''                # engine script ('' = built-in step)
    args: list = field(default_factory=list)
    needs: list = field(default_factory=list)
    makes: list = field(default_factory=list)
    hint: str = ''                  # what to do when it is blocked


MODULES = {
    'core': 'Drawing survey, checks, delivery',
    'gb': 'Grade beams per axis (beams, columns, axes of the GB plan)',
    'footings': 'Isolated footings (one sheet per type)',
    'mats': 'Combined footings / rafts of any outline',
    'necks': 'Column necks',
    'cd': 'Concrete dimensions',
    'zones': 'Packages per zone (foundations, necks, cores, strip, GB, concrete)',
    'cores': 'Core (shear-wall) necks',
    'strip': 'Strip footing under walls',
    'stairs': 'Stair starter bars (from the footing, like the necks)',
    'sog': 'Slab on grade between the grade beams (X and Y sheets)',
    'pool': 'Swimming pool / open tank with a sloped floor',
}

STEPS = [
    # ------------------------------------------------------------------ read the drawing
    Step('survey', 'Survey of the drawing (layers, blocks, texts, views)', 'read', 'core', 'survey.py',
         ['{main_dxf}', 'survey'], ['{main_dxf}'], ['survey/survey.md', 'survey/project.draft.json'],
         'add the consultant DWG / DXF (Drawings > Add)'),
    Step('extract', 'Beams, columns and axes', 'read', 'gb', 'extract.py',
         ['project.json'], ['project.json', '{dxf}'], ['runs.pkl', 'cols.pkl', 'axes.json'],
         'project.json: layout, beam_layer, label_layer, col_layers, axis_block'),
    Step('cd_scan', 'Footings, pads and axes on the foundation plan', 'read', 'cd', 'cd_scan.py',
         [], ['project.json', '{dxf}'], ['cd_scan.pkl'], 'project.json: fnd_view, fnd_layers'),
    Step('cd_axes', 'Grid lines of the foundation plan', 'read', 'cd', 'cd_axes.py',
         [], ['cd_scan.pkl'], ['cd_axes.json']),
    Step('pair_necks', 'Column / footing pairs', 'read', 'necks', 'pair_necks.py',
         [], ['project.json', 'footings.json'], ['neck_pairs.pkl', 'neck_pairs.txt'],
         'footings.json (footing schedule) and project.json column_sizes'),
    Step('zones', 'Zones from the AREA clouds of the final plan', 'read', 'zones', 'zones.py',
         ['{final_dxf}', '{final_shift}'], ['project.json', '{final_dxf}'], ['zones.json'],
         'project.json: fnd_final {dxf, shift}'),
    Step('mats_scan', 'Combined footings / rafts on their real outline', 'read', 'mats', 'mats_scan2.py',
         [], ['project.json'], ['mats.pkl']),
    Step('mats_build', 'Raft / CF types and variants', 'read', 'mats', 'mats_build.py',
         [], ['mats.pkl', 'neck_pairs.pkl', 'footings_ext.json'], ['mats.json'],
         'footings_ext.json (CF / RAFT schedule)'),
    Step('slab_scan', 'Foundation slab of a zone (outline, mesh, ramps)', 'read', 'zones', 'slab_scan.py',
         [], ['project.json'], ['slabs.json']),
    Step('pair_cores', 'Cores on their footings', 'read', 'cores', 'pair_cores.py',
         [], ['project.json'], ['core_pairs.json'], 'project.json: core_outline_layer, core_types'),
    # ------------------------------------------------------------------ shop drawings
    Step('gen_gb', 'Grade beams, one set per axis', 'generate', 'gb', 'gen2.py',
         ['{axes}'], ['runs.pkl', 'cols.pkl', 'axes.json'], ['out/GB_AXIS_*.dxf']),
    Step('gen_footings', 'Isolated footings', 'generate', 'footings', 'gen_f.py',
         [], ['footings.json'], ['out/FOOTINGS.dxf']),
    Step('gen_necks', 'Column necks', 'generate', 'necks', 'gen_n.py',
         ['@neck_pairs.txt'], ['neck_pairs.txt', 'footings.json'], ['out/NECKS.dxf']),
    Step('gen_cd', 'Concrete dimensions (plan parts + sections)', 'generate', 'cd', 'gen_cd.py',
         ['--parts'], ['cd_scan.pkl', 'cd_axes.json', 'footings.json'], ['out/CONCRETE_DIM.dxf']),
    Step('zone_fnd', 'Per zone: foundations (key plan, footings, rafts, slab) + BBS', 'generate', 'zones',
         'gen_zones.py', [], ['zones.json', 'mats.json', 'mats.pkl', 'footings.json'],
         ['out/ZONES/*_FOUNDATIONS.dxf']),
    Step('zone_necks', 'Per zone: column necks + BBS', 'generate', 'zones', 'gen_zone_necks.py',
         [], ['zones.json', 'neck_pairs.pkl'], ['out/ZONES/*_NECKS.dxf']),
    Step('zone_cores', 'Per zone: core necks + BBS', 'generate', 'cores', 'gen_zone_cores.py',
         [], ['zones.json', 'core_pairs.json'], ['out/ZONES/*_CORE_NECKS.dxf']),
    Step('zone_stairs', 'Per zone: stair starter bars + BBS', 'generate', 'stairs', 'gen_zone_stairs.py',
         [], ['zones.json', 'project.json'], ['out/ZONES/*_STAIRS.dxf'], 'project.json: stairs (plan, outline layer, bars)'),
    Step('zone_sog', 'Per zone: slab on grade X / Y + BBS', 'generate', 'sog', 'gen_zone_sog.py',
         [], ['zones.json', 'project.json'], ['out/ZONES/*_SOG.dxf'], 'project.json: sog (plan with the S.O.G tags, mesh)'),
    Step('zone_strip', 'Per zone: strip footing + BBS', 'generate', 'strip', 'gen_zone_strip.py',
         [], ['zones.json', 'cd_scan.pkl'], ['out/ZONES/*_STRIP.dxf']),
    Step('zone_gb', 'Per zone: grade beams + BBS', 'generate', 'zones', 'gen_zone_gb.py',
         [], ['zones.json', 'runs.pkl', 'cols.pkl'], ['out/ZONES/*_GRADE_BEAMS.dxf']),
    Step('zone_cd', 'Per zone: concrete dimensions', 'generate', 'zones', 'gen_zone_cd.py',
         [], ['zones.json', 'cd_scan.pkl', 'cd_axes.json'], ['out/ZONES/*_CONCRETE_DIM.dxf']),
    Step('gen_pool', 'Swimming pool: dimensions, floor, walls, corners, sleeves + BBS', 'generate', 'pool',
         'gen_pool.py', ['pool.json'], ['pool.json'], ['out/POOL/*_POOL.dxf'],
         'pool.json from the pool sheets (see pool.example.json in the engine folder)'),
    # ------------------------------------------------------------------ finish
    Step('check', 'Check every DXF (audit, AutoCAD-unsafe objects)', 'finish', 'core', '',
         [], ['out'], ['../logs/check.txt']),
    Step('package', 'Pack the delivery (zip parts under the size limit)', 'finish', 'core', '',
         [], ['../logs/check.txt'], ['../deliveries/*.zip']),
]
BY_ID = {s.id: s for s in STEPS}
