"""
The one-file app (app.py): the local API end to end on a synthetic RAM model - settings, a project and its levels,
a design run (blocked by the punching / beam checks), the engineer's decisions and the regeneration, the files of
the run, the take-off updated from an unchanged sheet, the beam strips model, the project take-off and cost, the
beam types, a shop run, issuing, the page itself.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))

from tests.synthetic_cpt import build_synthetic_cpt  # noqa: E402

spec = importlib.util.spec_from_file_location('spantech_app', PKG / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class AppApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='app-'))
        app.DATA = cls.tmp / 'data'
        app.STORE = app.Store(app.DATA)
        (app.DATA / 'tmp').mkdir(parents=True, exist_ok=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.cpt_beam = build_synthetic_cpt(str(cls.tmp), beam=True)
        (cls.tmp / 'plain').mkdir()
        cls.cpt_plain = build_synthetic_cpt(str(cls.tmp / 'plain'))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, method, path, body=None, raw=None, ok=True):
        data = raw if raw is not None else (json.dumps(body).encode('utf8') if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/octet-stream' if raw is not None else 'application/json'})
        try:
            with urllib.request.urlopen(r) as res:
                ctype = res.headers.get('Content-Type') or ''
                payload = res.read()
                return (json.loads(payload.decode('utf8')) if ctype.startswith('application/json') else payload), res.status
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read().decode('utf8'))
            if ok:
                self.fail(f'{method} {path}: {e.code} {payload}')
            return payload, e.code

    def test_end_to_end(self):
        page, _ = self.req('GET', '/')
        self.assertIn(b'<title>Span Tech', page)
        self.assertIn(b"const DICT = {", page)
        boot, _ = self.req('GET', '/api/bootstrap')
        self.assertEqual(boot['settings']['design_prefix'], 'SPAN-DD')

        # settings: the designer's name, a partial U-bar override (the base spec keeps its other keys), no frame hijack
        s, _ = self.req('PUT', '/api/settings', {'designer': 'ENG. TEST', 'spec': {'uEdge': {'total': 4400}}, 'frame_dxf': 'x'})
        self.assertEqual(s['settings']['designer'], 'ENG. TEST')
        self.assertIsNone(s['settings']['frame_dxf'])

        p, _ = self.req('POST', '/api/projects', {'name': 'TEST TOWER', 'client': 'CLIENT', 'default_mode': 'design', 'beam_design': 'max'})
        pid = p['project']['id']
        self.assertRegex(p['project']['code'], r'^P\d\d-001$')
        dup, code = self.req('POST', '/api/projects', {'name': 'X', 'code': p['project']['code']}, ok=False)
        self.assertEqual(code, 409)
        l, _ = self.req('POST', f'/api/projects/{pid}/levels', {'code': 'B1', 'name': 'BASEMENT', 'ram_failed_columns': 'A/1'})
        lid = l['level']['id']
        self.assertEqual(l['level']['punching']['ram_failed'], ['A/1'])
        l2, _ = self.req('POST', f'/api/projects/{pid}/levels', {'code': 'GF', 'name': 'GROUND FLOOR'})
        lid2 = l2['level']['id']

        # a design run: blocked by the column reported failing in RAM and by the office beam check
        r, _ = self.req('POST', f'/api/levels/{lid}/generate?name=synthetic-beam.cpt&mode=design', raw=Path(self.cpt_beam).read_bytes())
        run = r['run']
        self.assertEqual(run['status'], 'blocked')
        self.assertEqual(run['revision'], '00')
        self.assertEqual(run['prefix'], f"SPAN-DD-{p['project']['code']}")
        self.assertGreaterEqual(run['sheet_count'], 6)
        self.assertEqual(run['punching']['blocking'], ['A/1'])
        self.assertTrue(run['beam_check']['blocking'])
        self.assertEqual(run['created_by_name'], 'ENG. TEST')
        self.assertTrue((app.run_dir(pid, run['id']) / 'package.zip').exists())
        # the level's punching (RAM failed) and the beam check went through the spec; the beam types joined the project
        bt, _ = self.req('GET', f'/api/projects/{pid}/beam-types')
        self.assertTrue(bt['beam_types'])
        self.assertEqual(bt['beam_types'][0]['source']['run_id'], run['id'])

        # the engineer's decisions: the columns pass in RAM, the beams are bypassed -> regenerated at the same revision, the old run superseded
        d, _ = self.req('POST', f"/api/runs/{run['id']}/punching-decision", {'mode': 'ram_ok', 'columns': 'all', 'acknowledge': True, 'note': 'RAM report ok'})
        self.assertEqual(d['previous'], run['id'])
        self.assertEqual(d['run']['punching']['blocking'], [])
        self.assertEqual(d['run']['revision'], '00')
        r2 = d['run']
        self.assertEqual(r2['status'], 'blocked')  # the beams still block
        no_ack, code = self.req('POST', f"/api/runs/{r2['id']}/beam-decision", {'mode': 'bypass'}, ok=False)
        self.assertEqual(code, 400)
        d2, _ = self.req('POST', f"/api/runs/{r2['id']}/beam-decision", {'mode': 'bypass', 'beams': 'all', 'acknowledge': True})
        r3 = d2['run']
        self.assertEqual(r3['status'], 'draft')
        self.assertEqual(r3['beam_check']['decision']['mode'], 'bypass')
        self.assertEqual(r3['beam_check']['decision']['by'], 'ENG. TEST')
        got, _ = self.req('GET', f"/api/runs/{r2['id']}")
        self.assertEqual(got['run']['status'], 'superseded')

        # the run's files, the ZIP, a path escape refused
        got, _ = self.req('GET', f"/api/runs/{r3['id']}")
        self.assertIn('# Design drawing package', got['run']['report_md'])
        sheet = got['run']['sheets'][2]['file']
        svg, _ = self.req('GET', f"/api/runs/{r3['id']}/file/preview/{sheet}.svg")
        self.assertIn(b'<svg', svg)
        dxf, _ = self.req('GET', f"/api/runs/{r3['id']}/file/dxf/{sheet}.dxf")
        self.assertIn(b'SPANTECH', dxf)
        z, _ = self.req('GET', f"/api/runs/{r3['id']}/zip")
        self.assertEqual(z[:2], b'PK')
        _, code = self.req('GET', f"/api/runs/{r3['id']}/file/dxf/..%2F..%2Fdb.json", ok=False)
        self.assertEqual(code, 400)

        # the take-off updated from the (unchanged) bottom sheet: bars found, nothing changed
        tk, _ = self.req('POST', f"/api/runs/{r3['id']}/takeoff?name={sheet}.dxf", raw=dxf)
        self.assertGreater(tk['takeoff']['bars'], 0)
        self.assertEqual(tk['takeoff']['changed'], 0)
        self.assertEqual(tk['run']['quantities']['levels'][0]['edited'][0]['by'], 'ENG. TEST')

        # the beam strips model for RAM
        bs, _ = self.req('POST', f"/api/runs/{r3['id']}/beam-strips")
        self.assertEqual(bs['beam_strips']['beams'], 2)
        cpt, _ = self.req('GET', f"/api/runs/{r3['id']}/beam-strips")
        self.assertEqual(cpt[:15], b'SQLite format 3')

        # a shop run on the other level with the partial U-bar override, then issued
        r4, _ = self.req('POST', f'/api/levels/{lid2}/generate?name=synthetic.cpt&mode=shop&notes=first', raw=Path(self.cpt_plain).read_bytes())
        self.assertEqual(r4['run']['status'], 'draft')
        self.assertTrue(any('U_BARS' in s['file'] for s in r4['run']['sheets']))
        ubars = next(s['file'] for s in r4['run']['sheets'] if 'U_BARS' in s['file'])
        udxf, _ = self.req('GET', f"/api/runs/{r4['run']['id']}/file/dxf/{ubars}.dxf")
        self.assertIn(b'4400', udxf)
        self.assertNotIn(b'NaN', udxf)
        issued, _ = self.req('PATCH', f"/api/runs/{r4['run']['id']}", {'status': 'issued', 'notes': 'issued'})
        self.assertEqual(issued['run']['status'], 'issued')
        blocked_issue, code = self.req('PATCH', f"/api/runs/{run['id']}", {'status': 'issued'}, ok=False)
        self.assertEqual(code, 400)

        # the project: levels with their runs, the take-off from the current run of every level, the cost study
        proj, _ = self.req('GET', f'/api/projects/{pid}')
        self.assertEqual([(lv['code'], lv['run_count']) for lv in proj['levels']], [('B1', 3), ('GF', 1)])
        self.assertEqual(len(proj['runs']), 4)
        q, _ = self.req('GET', f'/api/projects/{pid}/quantities')
        self.assertEqual([x['run_id'] for x in q['runs']], [r3['id'], r4['run']['id']])
        self.assertGreater(q['totals']['steel']['kg'], 0)
        c, _ = self.req('GET', f'/api/projects/{pid}/cost?steel_per_ton=4000')
        self.assertEqual(c['cost']['rates']['steel_per_ton'], 4000)
        self.assertGreater(c['cost']['totals']['total'], 0)

        # submittal forms: the template in the settings, a submittal from the runs (the blocked one refused), the printable
        # form, the status and the consultant's response, a re-issue (-R1), a re-submission naming what it supersedes
        st, _ = self.req('PUT', '/api/settings', {'submittal': {'prefix': 'ST-SUB', 'title': 'DRAWING SUBMITTAL', 'responses': ['APPROVED', 'REJECTED'], 'signatures': ['PREPARED BY']}})
        self.assertEqual(st['settings']['submittal']['prefix'], 'ST-SUB')
        self.assertEqual(st['settings']['submittal']['footer'], app.SUBMITTAL_DEFAULTS['footer'])  # the rest keeps the defaults
        _, code = self.req('POST', f'/api/projects/{pid}/submittals', {'run_ids': [run['id']]}, ok=False)
        self.assertEqual(code, 400)  # the blocked run cannot be submitted
        sb, _ = self.req('POST', f'/api/projects/{pid}/submittals', {'run_ids': [r3['id'], r4['run']['id']], 'attention': 'ENG. X'})
        sub = sb['submittal']
        self.assertEqual(sub['code'], f"ST-SUB-{p['project']['code']}-001")
        self.assertEqual(sub['kind'], 'mixed')
        self.assertEqual(sub['purpose'], 'approval')
        self.assertTrue(sub['subject'].startswith('DESIGN AND SHOP DRAWINGS - '))
        self.assertFalse(any('COVER' in it['title'] for it in sub['items']))
        self.assertEqual(len(sub['items']), r3['sheet_count'] - 1 + r4['run']['sheet_count'] - 1)
        self.assertEqual(sub['to_name'], 'CLIENT' if False else p['project'].get('consultant'))
        html, _ = self.req('GET', f"/api/submittals/{sub['id']}/form")
        self.assertIn(b'DRAWING SUBMITTAL', html)
        self.assertIn(sub['items'][0]['no'].encode(), html)
        self.assertIn(b'ENG. X', html)
        self.assertIn(b'PREPARED BY', html)
        up, _ = self.req('PATCH', f"/api/submittals/{sub['id']}", {'status': 'resubmit', 'response_date': '2026-10-01', 'response_notes': 'revise the top bars', 'response_by': 'CONSULTANT'})
        self.assertEqual((up['submittal']['status'], up['submittal']['response_by']), ('resubmit', 'CONSULTANT'))
        re1, _ = self.req('PATCH', f"/api/submittals/{sub['id']}", {'reissue': True})
        self.assertEqual((re1['submittal']['code'], re1['submittal']['revision'], re1['submittal']['status']), (f"ST-SUB-{p['project']['code']}-001-R1", 1, 'draft'))
        # only some sheets of the design run, submitted again: the items name the earlier submittal and revision
        pick = [sub['items'][0]['no']]
        sb2, _ = self.req('POST', f'/api/projects/{pid}/submittals', {'run_ids': [r3['id']], 'sheets': pick})
        self.assertEqual(len(sb2['submittal']['items']), 1)
        self.assertEqual(sb2['submittal']['items'][0]['prev_submittal'], re1['submittal']['code'])
        self.assertEqual(sb2['submittal']['purpose'], 'resubmission')
        self.assertIn('(RE-SUBMISSION)', sb2['submittal']['subject'])
        proj_s, _ = self.req('GET', f'/api/projects/{pid}')
        self.assertEqual([x['serial'] for x in proj_s['submittals']], [2, 1])
        self.req('DELETE', f"/api/submittals/{sb2['submittal']['id']}")
        _, code = self.req('GET', f"/api/submittals/{sb2['submittal']['id']}", ok=False)
        self.assertEqual(code, 404)

        # project files, beam types imported into another project, deletes
        f, _ = self.req('POST', f'/api/projects/{pid}/files?category=ram&name=model.cpt&level_id={lid}&revision=01', raw=b'abc')
        self.assertEqual(f['file']['level_code'], 'B1')
        back, _ = self.req('GET', f"/api/files/{f['file']['id']}")
        self.assertEqual(back, b'abc')
        p2, _ = self.req('POST', '/api/projects', {'name': 'SECOND'})
        imp, _ = self.req('POST', f"/api/projects/{p2['project']['id']}/beam-types/import", {'from_project_id': pid})
        self.assertEqual(imp['added'], len(bt['beam_types']))
        self.assertEqual(imp['skipped'], 0)
        self.req('DELETE', f"/api/projects/{p2['project']['id']}")
        _, code = self.req('GET', f"/api/projects/{p2['project']['id']}", ok=False)
        self.assertEqual(code, 404)
        self.req('DELETE', f"/api/runs/{run['id']}")
        self.assertFalse(app.run_dir(pid, run['id']).exists())
        bad, code = self.req('POST', f'/api/levels/{lid2}/generate?name=x.txt', raw=b'abc', ok=False)
        self.assertEqual(code, 400)
        self.assertIn('error_ar', bad)


if __name__ == '__main__':
    unittest.main()
