import csv
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import launch
import launch_stock
from build_info import build_id


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

    def test_build_identity_tracks_source_assets_and_config_not_documentation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('p107/research.py', 'web/server.py', 'web/dist/index.html', 'configs/example.json'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('original')
            baseline = build_id(root)
            self.assertEqual(build_id(root), baseline)
            (root / 'README.md').write_text('documentation only')
            self.assertEqual(build_id(root), baseline)
            for name in ('p107/research.py', 'web/server.py', 'web/dist/index.html', 'configs/example.json'):
                with self.subTest(file=name):
                    path = root / name
                    path.write_text('modified')
                    self.assertNotEqual(build_id(root), baseline)
                    path.write_text('original')

    def test_launcher_starts_on_free_default_port_and_opens_actual_url(self):
        output = io.StringIO()
        with patch.object(launch_stock, 'health', return_value=False), \
             patch.object(launch_stock, '_port_available', return_value=True), \
             patch.object(launch_stock, '_start') as start, \
             patch.object(launch_stock.webbrowser, 'open') as browser, redirect_stdout(output):
            actual = launch_stock.main()
        self.assertEqual(actual, 'http://127.0.0.1:8754')
        self.assertEqual(start.call_args.args, (actual, build_id()))
        browser.assert_called_once_with(actual)
        self.assertEqual(output.getvalue(), 'Ready: ' + actual + '\n')

    def test_launcher_skips_old_build_without_stopping_its_process(self):
        output = io.StringIO()
        with patch.object(launch_stock, 'health', side_effect=[RuntimeError('different build'), False]), \
             patch.object(launch_stock, '_port_available', return_value=True), \
             patch.object(launch_stock, '_start') as start, \
             patch.object(launch_stock.webbrowser, 'open') as browser, redirect_stdout(output):
            actual = launch_stock.main()
        self.assertEqual(actual, 'http://127.0.0.1:8755')
        self.assertEqual(start.call_args.args[0], actual)
        browser.assert_called_once_with(actual)
        self.assertEqual(output.getvalue(), 'Ready: ' + actual + '\n')

    def test_explicit_occupied_port_is_not_silently_changed(self):
        with patch.object(launch_stock, 'health', side_effect=RuntimeError('different build')), \
             patch.object(launch_stock, '_start') as start:
            with self.assertRaisesRegex(RuntimeError, 'different build'):
                launch_stock.main(no_browser=True, port=8754)
        start.assert_not_called()

    def test_child_start_uses_selected_port_and_waits_for_matching_health(self):
        child = Mock(pid=12345)
        child.poll.return_value = None
        with tempfile.TemporaryDirectory() as folder, patch.object(launch_stock, 'ROOT', Path(folder)), \
             patch.object(launch_stock.subprocess, 'Popen', return_value=child) as spawn, \
             patch.object(launch_stock, 'health', side_effect=[False, True]) as health, \
             patch.object(launch_stock.time, 'sleep'):
            launch_stock._start('http://127.0.0.1:8761', 'expected-build')
            command = spawn.call_args.args[0]
            self.assertEqual(command[-2:], ['--port', '8761'])
            self.assertEqual((Path(folder) / 'stock.pid').read_text(), '12345')
            self.assertEqual(health.call_count, 2)
            health.assert_called_with('http://127.0.0.1:8761', 'expected-build')
        child.terminate.assert_not_called()

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

    def test_portfolio_api_and_assets(self):
        quote = {'ticker': 'AAPL', 'price': 110, 'currency': 'USD', 'as_of': '2026-10-30', 'fetched_at': '2026-10-30T20:00:00Z'}
        headers = {'Content-Type': 'application/json'}
        with patch.object(server, 'get_quote', return_value=quote):
            status, raw, _ = self.request('POST', '/api/portfolio/quotes', json.dumps({'tickers': ['aapl']}), headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['quotes'][0]['price'], 110)
        payload = dict(initial_cash=1000, holding_days=0, financing_pct=0, borrow_pct=0, rebate_pct=0, manager_pct=0, transaction_pct=0,
                       positions=[dict(ticker='AAPL', side='long', shares=10, entry_price=100)])
        with patch('p107.portfolio.get_quote', return_value=quote):
            status, raw, _ = self.request('POST', '/api/portfolio/run', json.dumps(payload), headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['price_pnl'], 100)
        for path in ('/portfolio.js', '/portfolio.css'):
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_three_level_research_endpoint(self):
        dataset = dict(dates=['2020-01-02','2020-01-03'],
                       prices={'AAPL':[100,110], 'SPY':[100,100]},
                       dividends={'AAPL':[0,0], 'SPY':[0,0]},
                       splits={'AAPL':[0,0], 'SPY':[0,0]}, metadata={'source':'unit test'})
        payload = dict(level=1,initial_cash=1000,start_date='2020-01-02',end_date='2020-01-03',benchmark='SPY',
                       positions=[dict(ticker='AAPL',side='long',shares=10)],transaction_pct=0)
        headers = {'Content-Type':'application/json'}
        with patch('p107.market_data.load_history', return_value=dataset):
            for level, expected in [(1,1100),(2,1060),(3,1060)]:
                payload['level'] = level
                status, raw, _ = self.request('POST','/api/research/run',json.dumps(payload),headers)
                self.assertEqual(status,200)
                self.assertAlmostEqual(json.loads(raw)['summary']['terminal_wealth'],expected)
        self.assertEqual(self.request('POST','/api/research/run','{}',headers)[0],400)
        self.assertEqual(self.request('POST','/api/research/run','{}',{**headers,'Origin':'https://foreign.example'})[0],403)

    def test_integrated_exposure_allocation_endpoint_and_launcher(self):
        dataset = dict(dates=['2020-01-02', '2020-01-03'],
                       prices={'AAPL': [100, 110], 'MSFT': [200, 240], 'SPY': [100, 105]},
                       dividends={s: [0, 0] for s in ('AAPL', 'MSFT', 'SPY')},
                       splits={s: [0, 0] for s in ('AAPL', 'MSFT', 'SPY')}, metadata={'source': 'unit test'})
        payload = dict(level=3, initial_cash=1000000, start_date='2020-01-02', end_date='2020-01-03',
                       benchmark='SPY', allocation_mode='target_exposure', long_exposure_pct=130, short_exposure_pct=30,
                       positions=[dict(ticker='AAPL', side='long', weight=1), dict(ticker='MSFT', side='short', weight=1)],
                       financing_pct=0, borrow_pct=0, transaction_pct=0)
        headers = {'Content-Type': 'application/json'}
        with patch('p107.market_data.load_history', return_value=dataset):
            status, raw, _ = self.request('POST', '/api/research/run', json.dumps(payload), headers)
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertAlmostEqual(result['summary']['terminal_wealth'], 1042000)
        self.assertAlmostEqual(result['summary']['initial_gross_exposure'], 1.6)
        self.assertAlmostEqual(result['summary']['incremental_wealth_vs_no_harvest'], 0)
        self.assertEqual(result['metadata']['allocation']['long_value'], 1300000)
        self.assertEqual(result['metadata']['allocation']['short_value'], 300000)
        with patch.object(launch_stock, 'URL', f'http://127.0.0.1:{self.server.server_port}'):
            self.assertTrue(launch_stock.health())

    def test_spy_target_is_independent_of_selected_benchmark(self):
        tickers = ('AAPL', 'QQQ', 'SPY')
        dataset = dict(dates=['2020-01-02', '2020-01-03'],
                       prices={'AAPL': [100, 110], 'QQQ': [100, 105], 'SPY': [100, 120]},
                       dividends={symbol: [0, 0] for symbol in tickers},
                       splits={symbol: [0, 0] for symbol in tickers}, metadata={'source': 'unit test'})
        payload = dict(level=3, initial_cash=1000, start_date='2020-01-02', end_date='2020-01-03',
                       benchmark='QQQ', evaluate_spy=True, financing_pct=0, transaction_pct=0,
                       positions=[dict(ticker='AAPL', side='long', shares=10)])
        headers = {'Content-Type': 'application/json'}
        with patch('p107.market_data.load_history', return_value=dataset) as history:
            status, raw, _ = self.request('POST', '/api/research/run', json.dumps(payload), headers)
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(result['summary']['spy_status'], 'fail')
        self.assertAlmostEqual(result['summary']['terminal_wealth'], 1060)
        self.assertAlmostEqual(result['summary']['benchmark_wealth'], 1030)
        self.assertAlmostEqual(result['summary']['spy_benchmark_wealth'], 1120)
        self.assertAlmostEqual(result['summary']['spy_display_difference'], -60)
        self.assertEqual(result['spy_benchmark']['positions'][0]['ticker'], 'SPY')
        self.assertEqual(history.call_args.args[0], ['AAPL', 'SPY', 'QQQ'])
        payload['evaluate_spy'] = 'true'
        with patch('p107.market_data.load_history') as history:
            self.assertEqual(self.request('POST', '/api/research/run', json.dumps(payload), headers)[0], 400)
            history.assert_not_called()

    def test_stock_launcher_rejects_prior_research_server(self):
        for launcher in (launch, launch_stock):
            prior = io.BytesIO(json.dumps({'app': server.APP_ID, 'features': ['three_level_research']}).encode())
            with self.subTest(launcher=launcher.__name__), patch.object(launch_stock, 'build_opener') as opener:
                opener.return_value.open.return_value = prior
                with self.assertRaisesRegex(RuntimeError, 'older or unrelated'):
                    launcher.health()

    def test_launcher_rejects_integrated_server_with_missing_or_different_build(self):
        for saved_build in (None, 'previous-build'):
            payload = dict(app=server.APP_ID, features=['integrated_research_v2'])
            if saved_build is not None:
                payload['build_id'] = saved_build
            prior = io.BytesIO(json.dumps(payload).encode())
            with self.subTest(build=saved_build), patch.object(launch_stock, 'build_opener') as opener:
                opener.return_value.open.return_value = prior
                with self.assertRaisesRegex(RuntimeError, 'different application build'):
                    launch_stock.health()

    def test_original_launcher_uses_integrated_server_and_honors_no_browser(self):
        url = f'http://127.0.0.1:{self.server.server_port}'
        for no_browser in (False, True):
            output = io.StringIO()
            with self.subTest(no_browser=no_browser), patch.object(launch_stock, 'URL', url), \
                 patch.object(launch_stock.subprocess, 'Popen') as spawn, \
                 patch.object(launch_stock.webbrowser, 'open') as browser, redirect_stdout(output):
                launch.main(no_browser=no_browser)
                spawn.assert_not_called()
                if no_browser:
                    browser.assert_not_called()
                else:
                    browser.assert_called_once_with(url)
            self.assertEqual(output.getvalue(), 'Ready: ' + url + '\n')
        self.assertEqual(launch.URL, 'http://127.0.0.1:8754')

    def test_portfolio_bad_requests(self):
        headers = {'Content-Type': 'application/json'}
        for path in ('/api/portfolio/quotes', '/api/portfolio/run'):
            self.assertEqual(self.request('POST', path, '{}', headers)[0], 400)
            self.assertEqual(self.request('POST', path, '{}', {**headers, 'Origin': 'https://foreign.example'})[0], 403)

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
