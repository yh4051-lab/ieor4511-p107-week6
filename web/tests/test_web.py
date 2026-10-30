import csv
from copy import deepcopy
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import launch


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = server.calculate(server.defaults())

    def test_default_matches_public_cli_outputs(self):
        with (server.MODEL_ROOT / 'results/baseline_comparison.csv').open(newline='', encoding='utf-8') as f:
            expected = list(csv.DictReader(f))
        for actual, prior in zip(self.result['summaries'], expected):
            self.assertEqual(actual['strategy'], prior['strategy'])
            for key in ('terminal_after_tax_wealth', 'incremental_wealth_vs_index', 'incremental_unwind_tax',
                        'cumulative_net_costs', 'net_equity_basis_before_exit'):
                self.assertAlmostEqual(actual[key], float(prior[key]), places=6)
        self.assertEqual(len(self.result['breakeven']['roots_annual_usd']), 1)
        self.assertLess(abs(self.result['breakeven']['root_residual_usd'][0]), .01)

    def test_no_outside_gains_reverses_core_comparison(self):
        inputs = server.defaults()
        inputs['outside_gains'] = 0
        result = server.calculate(inputs)
        core = next(r for r in result['summaries'] if r['strategy'] == 'core_130_30')
        self.assertLess(core['incremental_wealth_vs_index'], 0)

    def test_long_term_switch_clears_short_term_gains(self):
        inputs = server.defaults()
        inputs['outside_character'] = 'lt'
        result = server.calculate(inputs)
        self.assertEqual(result['config']['outside_st_gains'], [0] * 10)
        self.assertEqual(result['config']['outside_lt_gains'], [100000] * 10)
        self.assertEqual(result['breakeven']['outside_character'], 'lt')
        self.assertEqual(result['breakeven']['roots_annual_usd'], [])

    def test_advanced_fields_and_base_remain_separate(self):
        prior = deepcopy(server.BASE)
        inputs = server.defaults()
        inputs.update(tax_st_pct=30, tax_lt_pct=15, financing_pct=6.5, rebate_pct=2, borrow_pct=1,
                      advisor_pct=.2, core_manager_pct=.8, loss_scale_pct=50, horizon_years=3)
        c = server.build_config(inputs)
        core = next(r for r in c['strategies'] if r['name'] == 'core_130_30')
        self.assertEqual((c['tax_st'], c['tax_lt'], c['ordinary_tax_rate']), (.3, .15, .3))
        self.assertAlmostEqual(core['harvest_st_rates'][0], .075)
        self.assertEqual((core['long_financing_rate'], core['short_rebate_rate'], core['short_borrow_rate']), (.065, .02, .01))
        self.assertTrue(all(s['advisor_fee'] == .002 for s in c['strategies']))
        self.assertEqual(server.BASE, prior)

    def test_invalid_input_is_rejected(self):
        for key, value in [('horizon_years', 5.5), ('initial_cash', True), ('price_return_pct', float('nan')),
                           ('outside_gains', -1), ('financing_pct', 100), ('outside_character', 'mixed')]:
            with self.subTest(key=key):
                inputs = server.defaults()
                inputs[key] = value
                with self.assertRaises(ValueError): server.build_config(inputs)
        with self.assertRaises(ValueError): server.build_config({})

    def test_download_reproduces_main_comparison_and_checksums(self):
        bundle = server.result_zip(self.result)
        self.assertEqual(bundle, server.result_zip(self.result))
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            self.assertIsNone(z.testzip())
            manifest = json.loads(z.read('FILE_MANIFEST.json'))
            for name, digest in manifest.items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
            c = json.loads(z.read('scenario.json'))
            summaries, _ = server.compare(c)
            self.assertEqual(summaries, self.result['summaries'])
            rows = list(csv.DictReader(io.StringIO(z.read('baseline_comparison.csv').decode('utf-8-sig'))))
            self.assertEqual(float(rows[2]['terminal_after_tax_wealth']), summaries[2]['terminal_after_tax_wealth'])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = server.AppServer(('127.0.0.1', 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        result = (r.status, r.read(), dict(r.getheaders()))
        c.close()
        return result

    def test_local_page_api_and_download(self):
        status, page, headers = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('After-tax strategy comparison'.encode(), page)
        self.assertIn("connect-src 'self'", headers['Content-Security-Policy'])
        status, data, _ = self.request('POST', '/api/run', json.dumps(server.defaults()), {'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        run_id = json.loads(data)['run_id']
        status, content, headers = self.request('GET', '/api/download/' + run_id)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            self.assertIn('scenario.json', z.namelist())

    def test_launcher_recognizes_running_public_server(self):
        with patch.object(launch, 'URL', f'http://127.0.0.1:{self.server.server_port}'):
            self.assertTrue(launch.health())

    def test_private_files_and_foreign_origins_not_served(self):
        for path in ('/server.py', '/../P107_Week6_Submission/README.md', '/api/download/missing'):
            self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'outside.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/run', '{}', {'Content-Type': 'application/json', 'Origin':'https://outside.example'})[0], 403)

    def test_landing_navigation_from_external_link_is_allowed(self):
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate'}
        self.assertEqual(self.request('GET', '/', headers=headers)[0], 200)
        self.assertEqual(self.request('GET', '/api/defaults', headers=headers)[0], 403)

    def test_bad_json_and_wrong_content_type_return_errors(self):
        for body, content_type in [('{broken', 'application/json'), ('{}', 'text/plain'), ('{}', 'application/json')]:
            status, data, _ = self.request('POST', '/api/run', body, {'Content-Type': content_type})
            self.assertEqual(status, 400)
            self.assertIn('error', json.loads(data))


if __name__ == '__main__':
    unittest.main()
