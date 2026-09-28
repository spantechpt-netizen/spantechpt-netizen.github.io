"""
A tiny RAM Concept model written with sqlite3, shared by the generator and the drawings-module tests.

(Port of test/helpers/synthetic-cpt.mjs.)
"""
import math
import os
import sqlite3


def build_synthetic_cpt(dir, beam=False, step=False, loads=None):
    """A tiny RAM Concept model written with sqlite3: 12 x 8 m slab meshed 3 x 2, five columns, one wall crossing the edge, two tendons, two bands."""
    loads_tag = f"-loads{loads.get('dead') or 0}-{loads.get('live') or 0}" if loads else ''
    path = os.path.join(dir, f"synthetic{'-beam' if beam else ''}{'-step' if step else ''}{loads_tag}.cpt")
    db = sqlite3.connect(path)

    def P(x, y):  # mm → 0.1 mm
        return f'[{x * 10}][{y * 10}]'

    def create(t, cols):
        db.execute(f'create table "{t}" ({",".join(chr(34) + c + chr(34) for c in cols)})')

    def insert(t, rows_to_add):
        for r in rows_to_add:
            db.execute(f'insert into "{t}" ({",".join(chr(34) + k + chr(34) for k in r)}) values ({",".join("?" for _ in r)})', list(r.values()))
    create('Cover', ['Heading1', 'Heading2', 'Heading3', 'Heading4'])
    insert('Cover', [{'Heading1': 'SPAN TECH', 'Heading2': 'SYNTHETIC SLAB', 'Heading3': 'PART 1', 'Heading4': 'R0'}])
    create('Concrete', ['UID', 'Name', 'FcFinal', 'FcuFinal'])
    insert('Concrete', [{'UID': 1, 'Name': 'C32/40', 'FcFinal': 0.32, 'FcuFinal': 0.4}])
    create('Rebar', ['UID', 'Name', 'Fy', 'As'])
    insert('Rebar', [{'UID': 11, 'Name': 'T12', 'Fy': 4.2, 'As': 11300}, {'UID': 16, 'Name': 'T16', 'Fy': 4.2, 'As': 20100}])
    create('SlabArea', ['UID', 'MultiPoint', 'SlabThickness', 'Priority', 'SlabBehavior', 'TOC'])
    insert('SlabArea', [
        {'UID': 21, 'MultiPoint': f'{P(0, 0)}{P(12000, 0)}{P(12000, 8000)}{P(0, 8000)}', 'SlabThickness': 2500, 'Priority': 1, 'SlabBehavior': 0, 'TOC': 0},
        {'UID': 22, 'MultiPoint': f'{P(4000, 0)}{P(8000, 0)}{P(8000, 4000)}{P(4000, 4000)}', 'SlabThickness': 4000, 'Priority': 2, 'SlabBehavior': 0, 'TOC': 0},
    ])
    create('ElementCornerNode', ['UID', 'Point0'])
    create('QuadSlabElement', ['UID', 'CornerNode0', 'CornerNode1', 'CornerNode2', 'CornerNode3', 'SlabThickness', 'TOC'])
    xs, ys = [0, 4000, 8000, 12000], [0, 4000, 8000]
    nodes = [P(x, y) for y in ys for x in xs]
    insert('ElementCornerNode', [{'UID': 100 + i, 'Point0': p} for i, p in enumerate(nodes)])
    quads = []
    # with `step`, the right-hand third of the slab (x 8..12 m) sits 300 mm lower (TOC -300): a separate slab for the office
    for j in range(2):
        for i in range(3):
            quads.append({'UID': 200 + len(quads), 'CornerNode0': P(xs[i], ys[j]), 'CornerNode1': P(xs[i + 1], ys[j]), 'CornerNode2': P(xs[i + 1], ys[j + 1]), 'CornerNode3': P(xs[i], ys[j + 1]), 'SlabThickness': 4000 if i == 1 and j == 0 else 2500, 'TOC': -3000 if step and i == 2 else 0})
    insert('QuadSlabElement', quads)
    create('Column', ['UID', 'Point0', 'B', 'D', 'Angle', 'SupportSet'])
    insert('Column', [
        {'UID': 31, 'Point0': P(0, 0), 'B': 4000, 'D': 8000, 'Angle': 0, 'SupportSet': 'below'}, {'UID': 32, 'Point0': P(12000, 0), 'B': 4000, 'D': 8000, 'Angle': math.pi / 2, 'SupportSet': 'below'},  # the second one turned 90°
        {'UID': 33, 'Point0': P(0, 8000), 'B': 4000, 'D': 8000, 'Angle': 0, 'SupportSet': 'below'}, {'UID': 34, 'Point0': P(12000, 8000), 'B': 4000, 'D': 8000, 'Angle': 0, 'SupportSet': 'below'},
        {'UID': 35, 'Point0': P(6000, 4000), 'B': 0, 'D': 6000, 'Angle': 0, 'SupportSet': 'below'},
    ])
    if beam:
        # an interior beam 300 wide x 600 deep running across the slab at x = 9 m (slab on both sides), and an edge beam along y = 0
        create('Beam', ['UID', 'Point0', 'Point1', 'LeftPt0', 'RightPt0', 'Width', 'SlabThickness', 'TOC', 'Priority', 'BeamBehavior', 'BeamIsMeshedAsSlab'])
        insert('Beam', [
            {'UID': 45, 'Point0': P(9000, 0), 'Point1': P(9000, 8000), 'LeftPt0': P(8850, 0), 'RightPt0': P(9150, 0), 'Width': 3000, 'SlabThickness': 6000, 'TOC': 0, 'Priority': 10, 'BeamBehavior': 'no-torsion two-way slab', 'BeamIsMeshedAsSlab': 1},
            {'UID': 46, 'Point0': P(0, 150), 'Point1': P(12000, 150), 'LeftPt0': P(0, 0), 'RightPt0': P(0, 300), 'Width': 3000, 'SlabThickness': 6000, 'TOC': 0, 'Priority': 10, 'BeamBehavior': 'no-torsion two-way slab', 'BeamIsMeshedAsSlab': 1},
        ])
        # the design strip tables RAM keeps (two old slab strips to be replaced by the beam strips) and their categories
        sib = ['UID', 'ParentUID', 'PreviousSibUID', 'NextSibUID', 'ChildIndex', 'Name', 'Number', 'RssUid']
        for t in ['SpanSegmentCategory', 'SpanSegmentStripCategory', 'StripBoundaryCategory', 'SpanBoundaryCategory']:
            create(t, [*sib, 'SpanSet'])
            insert(t, [{'UID': len(t), 'ParentUID': 526, 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Name': '', 'Number': 0, 'RssUid': 0, 'SpanSet': 'latitude'}, {'UID': len(t) + 100, 'ParentUID': 526, 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 1, 'Name': '', 'Number': 1, 'RssUid': 0, 'SpanSet': 'longitude'}])
        seg_cols = [*sib, 'DeflectionCheckList', 'Point0', 'Point1', 'SkewAngle', 'SpanSet', 'FrameNumber', 'SpanNumber', 'SegmentNumber', 'AtSupport0', 'AtSupport1', 'SupportWidth0', 'SupportWidth1', 'SupportTransverseWidth0', 'SupportTransverseWidth1', 'AutoSupportDetect', 'MinInternalDivisions', 'MaxDivisionSpacing', 'SpanWidthCalc', 'ColumnStripWidthCalc', 'LockStripGeneration', 'ColumnStripDesignSystem', 'MiddleStripDesignSystem', 'ColumnStripTopBar', 'ColumnStripStirrupLegs', 'MiddleStripStirrupLegs', 'MiddleStripUsesColumnStripProps']
        db.execute(f'''create table "SpanSegment" ({",".join(chr(34) + c + chr(34) + (' INTEGER NOT NULL' if c in ['UID', 'ParentUID', 'PreviousSibUID', 'NextSibUID', 'ChildIndex', 'Number'] else ' ') for c in seg_cols)})''')
        db.execute(f'create table "DefaultSpanSegment" ({",".join(chr(34) + c + chr(34) for c in seg_cols)})')
        insert('DefaultSpanSegment', [{'UID': 17, 'ParentUID': 433, 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Name': '', 'Number': 0, 'RssUid': 0, 'DeflectionCheckList': '', 'Point0': '[0][0]', 'Point1': '[0][0]', 'SkewAngle': 0, 'SpanSet': 'latitude', 'FrameNumber': -1, 'SpanNumber': -1, 'SegmentNumber': -1, 'AtSupport0': 1, 'AtSupport1': 1, 'SupportWidth0': 0, 'SupportWidth1': 0, 'SupportTransverseWidth0': 0, 'SupportTransverseWidth1': 0, 'AutoSupportDetect': 1, 'MinInternalDivisions': 4, 'MaxDivisionSpacing': 7500, 'SpanWidthCalc': 'auto', 'ColumnStripWidthCalc': 'full', 'LockStripGeneration': 0, 'ColumnStripDesignSystem': 'two-way slab', 'MiddleStripDesignSystem': 'two-way slab', 'ColumnStripTopBar': 16, 'ColumnStripStirrupLegs': 2, 'MiddleStripStirrupLegs': 2, 'MiddleStripUsesColumnStripProps': 1}])
        insert('SpanSegment', [
            {'UID': 901, 'ParentUID': len('SpanSegmentCategory'), 'PreviousSibUID': 0, 'NextSibUID': 902, 'ChildIndex': 0, 'Name': '1-1', 'Number': 0, 'RssUid': 0, 'DeflectionCheckList': '', 'Point0': P(0, 4000), 'Point1': P(6000, 4000), 'SkewAngle': 0, 'SpanSet': 'latitude', 'FrameNumber': 0, 'SpanNumber': 0, 'SegmentNumber': 0, 'AtSupport0': 1, 'AtSupport1': 1, 'SupportWidth0': 4000, 'SupportWidth1': 6000, 'SupportTransverseWidth0': 8000, 'SupportTransverseWidth1': 6000, 'AutoSupportDetect': 1, 'MinInternalDivisions': 4, 'MaxDivisionSpacing': 7500, 'SpanWidthCalc': 'auto', 'ColumnStripWidthCalc': 'full', 'LockStripGeneration': 0, 'ColumnStripDesignSystem': 'two-way slab', 'MiddleStripDesignSystem': 'two-way slab', 'ColumnStripTopBar': 16, 'ColumnStripStirrupLegs': 2, 'MiddleStripStirrupLegs': 2, 'MiddleStripUsesColumnStripProps': 1},
            {'UID': 902, 'ParentUID': len('SpanSegmentCategory'), 'PreviousSibUID': 901, 'NextSibUID': 0, 'ChildIndex': 1, 'Name': '1-2', 'Number': 1, 'RssUid': 0, 'DeflectionCheckList': '', 'Point0': P(6000, 4000), 'Point1': P(12000, 4000), 'SkewAngle': 0, 'SpanSet': 'latitude', 'FrameNumber': 0, 'SpanNumber': 1, 'SegmentNumber': 0, 'AtSupport0': 1, 'AtSupport1': 1, 'SupportWidth0': 6000, 'SupportWidth1': 4000, 'SupportTransverseWidth0': 6000, 'SupportTransverseWidth1': 8000, 'AutoSupportDetect': 1, 'MinInternalDivisions': 4, 'MaxDivisionSpacing': 7500, 'SpanWidthCalc': 'auto', 'ColumnStripWidthCalc': 'full', 'LockStripGeneration': 0, 'ColumnStripDesignSystem': 'two-way slab', 'MiddleStripDesignSystem': 'two-way slab', 'ColumnStripTopBar': 16, 'ColumnStripStirrupLegs': 2, 'MiddleStripStirrupLegs': 2, 'MiddleStripUsesColumnStripProps': 1},
        ])
        create('SpanSegmentStrip', [*sib, 'Point0', 'Point1', 'ResistanceLeftBoundary', 'ResistanceRightBoundary', 'DemandLeftBoundary', 'DemandRightBoundary', 'SpanSegment', 'StripType', 'AutoTribArea', 'AutoInfluenceArea'])
        insert('SpanSegmentStrip', [{'UID': 911, 'ParentUID': len('SpanSegmentStripCategory'), 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Name': '1C-1', 'Number': 0, 'RssUid': 0, 'Point0': P(0, 4000), 'Point1': P(6000, 4000), 'ResistanceLeftBoundary': '', 'ResistanceRightBoundary': '', 'DemandLeftBoundary': '', 'DemandRightBoundary': '', 'SpanSegment': 901, 'StripType': 'center', 'AutoTribArea': 0, 'AutoInfluenceArea': 0}])
        create('StripBoundary', [*sib, 'Boundary', 'SpanSet'])
        create('SpanBoundary', [*sib, 'Boundary', 'SpanSet'])
        insert('SpanBoundary', [{'UID': 921, 'ParentUID': len('SpanBoundaryCategory'), 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Name': '', 'Number': 0, 'RssUid': 0, 'Boundary': f'[{P(6000, 3000)}][{P(6000, 5000)}]', 'SpanSet': 'latitude'}])
        create('SpanDesign', [*sib, 'MultiPoint', 'FrameNumber', 'SpanNumber', 'SegmentNumber', 'StripType', 'SpanSet'])
        insert('SpanDesign', [{'UID': 931, 'ParentUID': 901, 'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Name': '', 'Number': 0, 'RssUid': 0, 'MultiPoint': '', 'FrameNumber': 0, 'SpanNumber': 0, 'SegmentNumber': 0, 'StripType': 'center', 'SpanSet': 'latitude'}])
    create('LineSupport', ['UID', 'Point0', 'Point1'])
    insert('LineSupport', [{'UID': 41, 'Point0': P(-3000, 2000), 'Point1': P(5000, 2000)}])
    create('TendonLayer', ['UID', 'SpanSet'])
    insert('TendonLayer', [{'UID': 51, 'SpanSet': 'latitude'}, {'UID': 52, 'SpanSet': 'longitude'}])
    create('TendonLevel', ['UID', 'ParentUID'])
    insert('TendonLevel', [{'UID': 61, 'ParentUID': 51}, {'UID': 62, 'ParentUID': 52}])
    create('TendonCategory', ['UID', 'ParentUID'])
    insert('TendonCategory', [{'UID': 71, 'ParentUID': 61}, {'UID': 72, 'ParentUID': 62}])
    create('Tendon', ['UID', 'ParentUID', 'TendonNode0', 'TendonNode1', 'NumStrands', 'Harped'])
    insert('Tendon', [
        {'UID': 81, 'ParentUID': 71, 'TendonNode0': P(0, 2000), 'TendonNode1': P(6000, 2000), 'NumStrands': 4, 'Harped': 0}, {'UID': 82, 'ParentUID': 71, 'TendonNode0': P(6000, 2000), 'TendonNode1': P(12000, 2000), 'NumStrands': 4, 'Harped': 0},
        {'UID': 83, 'ParentUID': 72, 'TendonNode0': P(3000, 0), 'TendonNode1': P(3000, 8000), 'NumStrands': 3, 'Harped': 0},
    ])
    # the CGS profile: nodes above the soffit (reference 4): high at the columns, low at mid-span
    create('TendonNode', ['UID', 'Point0', 'ElevationReference', 'ElevationValue', 'Surface', 'Soffit'])
    insert('TendonNode', [
        {'UID': 85, 'Point0': P(0, 2000), 'ElevationReference': 4, 'ElevationValue': 1250, 'Surface': 0, 'Soffit': -2500},
        {'UID': 86, 'Point0': P(6000, 2000), 'ElevationReference': 4, 'ElevationValue': 2100, 'Surface': 0, 'Soffit': -2500},
        {'UID': 87, 'Point0': P(12000, 2000), 'ElevationReference': 4, 'ElevationValue': 1250, 'Surface': 0, 'Soffit': -2500},
        {'UID': 88, 'Point0': P(3000, 0), 'ElevationReference': 5, 'ElevationValue': 1250, 'Surface': 0, 'Soffit': -2500},
        {'UID': 89, 'Point0': P(3000, 8000), 'ElevationReference': 5, 'ElevationValue': 1250, 'Surface': 0, 'Soffit': -2500},
    ])
    create('Jack', ['UID', 'TendonNode0', 'JackStress', 'Elongation'])
    insert('Jack', [{'UID': 91, 'TendonNode0': P(0, 2000), 'JackStress': 14.88, 'Elongation': 850}])
    create('StrandMaterial', ['UID', 'Aps', 'Fpu'])
    insert('StrandMaterial', [{'UID': 1, 'Aps': 9870, 'Fpu': 18.6}])
    create('ConcentratedRebar', ['UID', 'ParentUID', 'BarFace', 'SpanDirection', 'BarType', 'BarCount', 'BarSpacing', 'Point0', 'Point1', 'LeftPoint', 'RightPoint', 'BarEnd0', 'BarEnd1', 'AbsoluteElevation', 'DesignedBy'])
    insert('ConcentratedRebar', [
        {'UID': 301, 'ParentUID': 1, 'BarFace': 2, 'SpanDirection': 1, 'BarType': 11, 'BarCount': 5, 'BarSpacing': 2000, 'Point0': P(0, 4000), 'Point1': P(12000, 4000), 'LeftPoint': P(6000, 3600), 'RightPoint': P(6000, 4400), 'BarEnd0': 0, 'BarEnd1': 0, 'AbsoluteElevation': -2000},
        {'UID': 302, 'ParentUID': 1, 'BarFace': 1, 'SpanDirection': 2, 'BarType': 16, 'BarCount': 6, 'BarSpacing': 1500, 'Point0': P(6000, 1500), 'Point1': P(6000, 6500), 'LeftPoint': P(5250, 4000), 'RightPoint': P(6750, 4000), 'BarEnd0': 0, 'BarEnd1': 0, 'AbsoluteElevation': -400},
        *([
            {'UID': 303, 'ParentUID': 1, 'BarFace': 1, 'SpanDirection': 2, 'BarType': 16, 'BarCount': 4, 'BarSpacing': 600, 'Point0': P(9000, 0), 'Point1': P(9000, 2000), 'LeftPoint': P(8910, 1000), 'RightPoint': P(9090, 1000), 'BarEnd0': 0, 'BarEnd1': 0, 'AbsoluteElevation': -400, 'DesignedBy': 2},
            {'UID': 304, 'ParentUID': 1, 'BarFace': 1, 'SpanDirection': 2, 'BarType': 16, 'BarCount': 4, 'BarSpacing': 600, 'Point0': P(9000, 6000), 'Point1': P(9000, 8000), 'LeftPoint': P(8910, 7000), 'RightPoint': P(9090, 7000), 'BarEnd0': 0, 'BarEnd1': 0, 'AbsoluteElevation': -400, 'DesignedBy': 2},
            {'UID': 305, 'ParentUID': 1, 'BarFace': 2, 'SpanDirection': 2, 'BarType': 16, 'BarCount': 3, 'BarSpacing': 900, 'Point0': P(9000, 1000), 'Point1': P(9000, 7000), 'LeftPoint': P(8910, 4000), 'RightPoint': P(9090, 4000), 'BarEnd0': 0, 'BarEnd1': 0, 'AbsoluteElevation': -5600, 'DesignedBy': 2},
        ] if beam else []),
    ])
    create('IndividualBars', ['UID', 'BarFace', 'SpanDirection', 'Point0', 'Point1', 'AbsoluteElevation'])
    ys5 = [3600, 3800, 4000, 4200, 4400]
    insert('IndividualBars', [{'UID': 401, 'BarFace': 2, 'SpanDirection': 1, 'Point0': ''.join(P(0, y) for y in ys5), 'Point1': ''.join(P(12000, y) for y in ys5), 'AbsoluteElevation': -2000}])
    create('TransverseRebarRegion', ['UID', 'Point0', 'Point1', 'BarType', 'StirrupLegs', 'StirrupSpacing'])
    insert('TransverseRebarRegion', [{'UID': 501, 'Point0': P(4000, 4000), 'Point1': P(8000, 4000), 'BarType': 11, 'StirrupLegs': 2, 'StirrupSpacing': 1500}, *([{'UID': 502, 'Point0': P(9000, 200), 'Point1': P(9000, 2000), 'BarType': 11, 'StirrupLegs': 2, 'StirrupSpacing': 1250}, {'UID': 503, 'Point0': P(9000, 2000), 'Point1': P(9000, 6000), 'BarType': 11, 'StirrupLegs': 2, 'StirrupSpacing': 2000}] if beam else [])])
    # stud rails designed by RAM at the middle column: 4 rails of 10 studs @100 leaving every face
    create('SsrSystem', ['UID', 'Name', 'StudArea'])
    insert('SsrSystem', [{'UID': 14, 'Name': '10mm SSR', 'StudArea': 7850}])
    create('SsrSet', ['UID', 'Point0', 'Point1', 'DesignedBy', 'SsrSystem', 'StudSpacingFirst', 'StudSpacingTypical', 'StudCount', 'LocationPoint'])
    rails0, rails1 = [], []
    for dx, dy in [[1, 0], [-1, 0], [0, 1], [0, -1]]:
        for k in range(4):
            t = -150 + k * 100
            a = {'x': 6000 + dx * 300 + (0 if dx else t), 'y': 4000 + dy * 300 + (0 if dy else t)}
            rails0.append(P(a['x'], a['y']))
            rails1.append(P(a['x'] + dx * 1000, a['y'] + dy * 1000))
    insert('SsrSet', [{'UID': 701, 'Point0': ''.join(rails0), 'Point1': ''.join(rails1), 'DesignedBy': 2, 'SsrSystem': 14, 'StudSpacingFirst': 1000, 'StudSpacingTypical': 1000, 'StudCount': ''.join('[10]' for _ in rails0), 'LocationPoint': P(6000, 4000)}])
    create('PunchCheck', ['UID', 'Name', 'Point0', 'SsrSystem', 'CoverToCGS', 'TopCover', 'BottomCover', 'AutoTribArea', 'SsrDesignDesired'])
    insert('PunchCheck', [{'UID': 601, 'Name': 'PC1', 'Point0': P(6000, 4000), 'SsrSystem': 'SSR', 'CoverToCGS': 350, 'TopCover': 350, 'BottomCover': 250, 'AutoTribArea': 24e8, 'SsrDesignDesired': 1}])
    if loads:
        # area loads the way RAM keeps them: loading layers by type, a loading level under each, a category under that,
        # the loads under the category; values in N per 0.01 mm² (kN/m² x 1e-5), downwards negative
        create('LoadingLayer', ['UID', 'ParentUID', 'Name', 'LoadingType'])
        insert('LoadingLayer', [{'UID': 79, 'ParentUID': 30, 'Name': 'Self-Dead Loading', 'LoadingType': 'self_dead'}, {'UID': 154, 'ParentUID': 30, 'Name': 'Other Dead Loading', 'LoadingType': 'other_dead'}, {'UID': 156, 'ParentUID': 30, 'Name': 'Live Loading', 'LoadingType': 'live_unreducible'}])
        create('LoadingLevel', ['UID', 'ParentUID', 'Name'])
        insert('LoadingLevel', [{'UID': 569, 'ParentUID': 154, 'Name': 'Level 1'}, {'UID': 576, 'ParentUID': 156, 'Name': 'Level 1'}])
        create('AreaLoadCategory', ['UID', 'ParentUID', 'Name'])
        insert('AreaLoadCategory', [{'UID': 575, 'ParentUID': 569, 'Name': ''}, {'UID': 582, 'ParentUID': 576, 'Name': ''}])
        create('AreaLoad', ['UID', 'ParentUID', 'Name', 'ALFz0', 'ALFz1', 'ALFz2', 'MultiPoint'])
        whole = f'{P(0, 0)}{P(12000, 0)}{P(12000, 8000)}{P(0, 8000)}'
        insert('AreaLoad', [
            {'UID': 801, 'ParentUID': 575, 'Name': '', 'ALFz0': -(loads.get('dead') or 0) * 1e-5, 'ALFz1': -(loads.get('dead') or 0) * 1e-5, 'ALFz2': -(loads.get('dead') or 0) * 1e-5, 'MultiPoint': whole},
            {'UID': 802, 'ParentUID': 582, 'Name': '', 'ALFz0': -(loads.get('live') or 0) * 1e-5, 'ALFz1': -(loads.get('live') or 0) * 1e-5, 'ALFz2': -(loads.get('live') or 0) * 1e-5, 'MultiPoint': whole},
        ])
    db.commit()
    db.close()
    return path
