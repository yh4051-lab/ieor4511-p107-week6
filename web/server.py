"""Local browser interface for the unchanged P107 Week 6 engine (standard library)."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import platform
import sys
import threading
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parent
MODEL_ROOT = ROOT.parent
sys.path.insert(0, str(MODEL_ROOT))
from p107 import __version__
from p107.model import compare, validate
from p107.analysis import breakeven

APP_ID = 'p107-public-interface-v1'
BASE = json.loads((MODEL_ROOT / 'configs/example_hypothetical.json').read_text(encoding='utf-8'))
CORE = next(s for s in BASE['strategies'] if s['name'] == 'core_130_30')
FIELDS = {
    'initial_cash': (10000, 100000000, BASE['initial_cash']),
    'horizon_years': (1, 10, BASE['horizon_years']),
    'price_return_pct': (-20, 20, BASE['market_price_returns'][0] * 100),
    'outside_gains': (0, 10000000, BASE['outside_st_gains'][0]),
    'tax_st_pct': (0, 60, BASE['tax_st'] * 100),
    'tax_lt_pct': (0, 60, BASE['tax_lt'] * 100),
    'core_manager_pct': (0, 5, CORE['manager_fee'] * 100),
    'advisor_pct': (0, 5, CORE['advisor_fee'] * 100),
    'financing_pct': (0, 20, CORE['long_financing_rate'] * 100),
    'rebate_pct': (0, 10, CORE['short_rebate_rate'] * 100),
    'borrow_pct': (0, 10, CORE['short_borrow_rate'] * 100),
    'loss_scale_pct': (0, 100, 100),
}


def defaults():
    return {**{k: round(v[2], 8) for k, v in FIELDS.items()}, 'outside_character': 'st'}


def build_config(inputs):
    if not isinstance(inputs, dict) or set(inputs) != set(defaults()):
        raise ValueError('Some inputs are missing or unknown. Reset the form and try again.')
    for key, (lo, hi, _) in FIELDS.items():
        value = inputs[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'{key} must be a number between {lo} and {hi}.')
    if int(inputs['horizon_years']) != inputs['horizon_years']:
        raise ValueError('The holding period must be a whole number from 1 to 10.')
    if inputs['outside_character'] not in ('st', 'lt'):
        raise ValueError('Choose short-term or long-term outside gains.')
    c = deepcopy(BASE)
    c['initial_cash'] = inputs['initial_cash']
    c['horizon_years'] = int(inputs['horizon_years'])
    c['market_price_returns'] = [inputs['price_return_pct'] / 100] * 10
    c['outside_st_gains'] = [0.0] * 10
    c['outside_lt_gains'] = [0.0] * 10
    c[f"outside_{inputs['outside_character']}_gains"] = [inputs['outside_gains']] * 10
    for key in ('st', 'lt'):
        c[f'tax_{key}'] = inputs[f'tax_{key}_pct'] / 100
    c['ordinary_tax_rate'] = c['tax_st']
    for s in c['strategies']:
        s['advisor_fee'] = inputs['advisor_pct'] / 100
        if s['name'] == 'core_130_30':
            for target, source in [('manager_fee', 'core_manager_pct'), ('long_financing_rate', 'financing_pct'),
                                   ('short_rebate_rate', 'rebate_pct'), ('short_borrow_rate', 'borrow_pct')]:
                s[target] = inputs[source] / 100
            s['harvest_st_rates'] = [v * inputs['loss_scale_pct'] / 100 for v in CORE['harvest_st_rates']]
    c['provenance']['web_interface'] = 'User-selected educational scenario. No observed prices or tax lots.'
    c['provenance']['initial_cash'] = 'User-selected starting cash; the original project starting example is USD 1,000,000.'
    c['provenance']['tax_rates'] = 'User-selected flat scenario rates. UI defaults are round illustrative rates; not verified personal tax rates.'
    c['provenance']['outside_gains'] = 'Equal nominal annual outside gain proceeds in the selected ST or LT character; common outside principal excluded.'
    c['provenance']['market_price_returns'] = 'User-selected constant educational price appreciation; zero dividends, not historical returns.'
    core = next(s for s in c['strategies'] if s['name'] == 'core_130_30')
    core['assumption_note'] += f" Web scenario uses {inputs['loss_scale_pct']}% of the original loss curve."
    validate(c)
    return c


def csv_bytes(rows):
    f = io.StringIO(newline='')
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return f.getvalue().encode('utf-8-sig')


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def calculate(inputs):
    c = build_config(inputs)
    summaries, ledger = compare(c)
    # Constant annual gains of the selected character; the other character is zero.
    maximum = max(c['initial_cash'], inputs['outside_gains'], 100000)
    be, points = breakeven(c, inputs['outside_character'], maximum=maximum, step=maximum / 100)
    horizon_rows = []
    for n in (1, 3, 5, 10):
        alt = deepcopy(c)
        alt['horizon_years'] = n
        try:
            rows, _ = compare(alt)
            horizon_rows.extend(dict(horizon=n, **r) for r in rows)
        except ValueError:
            # A valid current horizon need not imply a valid longer scenario.
            horizon_rows.append(dict(horizon=n, strategy='unavailable', error='The assumptions do not produce a feasible scenario at this horizon.'))
    config_hash = hashlib.sha256(json_bytes(c)).hexdigest()
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((MODEL_ROOT / 'p107').glob('*.py'))}
    run_id = hashlib.sha256(json_bytes({'config': c, 'sources': source_hashes})).hexdigest()[:20]
    curve = [dict(annual_outside_gain=x, core_minus_index=y, hypothetical=True) for x, y in points]
    return dict(run_id=run_id, inputs=inputs, config=c, summaries=summaries, ledger=ledger,
                breakeven=be, curve=curve, horizons=horizon_rows,
                metadata=dict(model_version=__version__, python=platform.python_version(),
                              config_sha256=config_hash, source_code_sha256=source_hashes,
                              hypothetical=True, randomness='none'))


def result_zip(result):
    files = {
        'scenario.json': json_bytes(result['config']),
        'ui_inputs.json': json_bytes(result['inputs']),
        'baseline_comparison.csv': csv_bytes(result['summaries']),
        'annual_ledger.csv': csv_bytes(result['ledger']),
        'breakeven_curve.csv': csv_bytes(result['curve']),
        'breakeven.json': json_bytes(result['breakeven']),
        'run_metadata.json': json_bytes(result['metadata']),
        'README.txt': ('P107 hypothetical scenario, not historical performance or actual tax savings.\n'
                       'Use the P107 engine in the repository root to reproduce the main comparison:\n'
                       'python -m p107 --config /path/to/scenario.json --out reproduced --no-charts\n'
                       'UI break-even uses the selected ST/LT character and search range in breakeven.json.\n'
                       'Terminal wealth includes the same outside gain cash flows for all strategies.\n'
                       'Annual ledger includes all three strategies; last-year tax includes full liquidation.\n'
                       'Original sources remain private. See the model docs for assumptions and limitations.\n').encode(),
    }
    files['FILE_MANIFEST.json'] = json_bytes({n: hashlib.sha256(b).hexdigest() for n, b in files.items()})
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, value)
    return out.getvalue()


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.runs = {}
        self.run_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, mime='application/json; charset=utf-8', filename=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host') not in hosts:
            self.send(403, json_bytes({'error': 'Only local access is allowed.'}))
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in hosts}:
            self.send(403, json_bytes({'error': 'Please use the local application page.'}))
            return False
        # Opening the app from a bookmark/chat is a cross-site navigation, not an API call.
        landing_navigation = self.command == 'GET' and self.path == '/' and self.headers.get('Sec-Fetch-Mode') == 'navigate'
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' and not landing_navigation:
            self.send(403, json_bytes({'error': 'Please use the local application page.'}))
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path == '/api/health':
            self.send(200, json_bytes({'app': APP_ID, 'model_version': __version__}))
        elif path == '/api/defaults':
            self.send(200, json_bytes({'inputs': defaults()}))
        elif path in ('/', '/app.js', '/style.css'):
            name, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
            self.send(200, (ROOT / 'dist' / name).read_bytes(), mime)
        elif path.startswith('/api/download/'):
            run_id = path.rsplit('/', 1)[-1]
            with self.server.run_lock:
                result = self.server.runs.get(run_id)
            if result is None:
                self.send(404, json_bytes({'error': 'This result has expired. Please run the comparison again.'}))
            else:
                self.send(200, result_zip(result), 'application/zip', f'P107_scenario_{run_id[:8]}.zip')
        else:
            self.send(404, json_bytes({'error': 'Page not found.'}))

    def do_POST(self):
        if not self.local_request():
            return
        if self.path != '/api/run':
            self.send(404, json_bytes({'error': 'Operation not found.'}))
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 10000 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Invalid request format.')
            inputs = json.loads(self.rfile.read(length))
            result = calculate(inputs)
            with self.server.run_lock:
                self.server.runs[result['run_id']] = result
                while len(self.server.runs) > 40:
                    self.server.runs.pop(next(iter(self.server.runs)))
            self.send(200, json_bytes(result))
        except (ValueError, TypeError, KeyError) as e:
            message = str(e)
            if message.startswith(('Insolvent', 'Impossible', 'Insufficient')):
                message = 'These inputs produce an infeasible scenario, such as insufficient assets or an invalid cost basis. Try a shorter horizon, adjust the assumptions, or reset the form.'
            self.send(400, json_bytes({'error': message}))
        except Exception:
            self.send(500, json_bytes({'error': 'The calculation did not finish. Please try again; if it keeps failing, check the local server.'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8751)
    args = parser.parse_args()
    server = AppServer(('127.0.0.1', args.port))
    print(f'P107 local interface: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
