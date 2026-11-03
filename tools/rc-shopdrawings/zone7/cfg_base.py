import json, sys
# schedule as read from the consultant's GROUND BEAM SCHEDULE (same on the three sheets); stirrups 8 T10/m' (T10 @125)
sched = {'GB1': dict(h=700, nt=4, dt=16, nb=4, db=16, ds=10, s=125), 'GB2': dict(h=700, nt=4, dt=16, nb=4, db=16, ds=10, s=125),
         'GB3': dict(h=700, nt=4, dt=18, nb=4, db=18, ds=10, s=125), 'GB4': dict(h=700, nt=4, dt=18, nb=4, db=18, ds=10, s=125),
         'TB1': dict(h=600, nt=6, dt=18, nb=6, db=18, ds=10, s=125)}
# column schedule (approved Roya column schedule, RFI-07): bars from the neck to the G.F, ties T10 8/m
cols = {'C1': dict(n=18, d=18, td=10, ts=125), 'C3': dict(n=20, d=16, td=10, ts=125), 'C8': dict(n=24, d=16, td=10, ts=125)}
C = dict(schedule=sched, columns=cols, levels={'top_gb': 850},
         frame=dict(dxf=sys.argv[1], block='LAY',
                    title={'t1': [1106.2, 144.0, 4.08], 't2': [1106.2, 137.4, 4.08], 'ref': [1106.2, 115.7, 3.4], 'dwg': [1084.0, 48.0, 3.2],
                           'area': [1119.3, 21.3, 3.4], 'venue': [1139.5, 21.3, 3.4], 'seq': [1157.8, 21.3, 3.4], 'rev': [1172.9, 21.3, 3.4],
                           'date': [1130.6, 392.0, 2.68]},
                    defaults={'ref': 'Roya New School - FINAL FOUNDATION 17-10-2026', 'area': 'Z07', 'venue': 'GB', 'rev': '00'}))
json.dump(C, open(sys.argv[2], 'w'), indent=1); print('ok')
