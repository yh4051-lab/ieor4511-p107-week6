"""Open the matching application build, choosing a free local port when needed."""
from pathlib import Path
import argparse
import json
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
import webbrowser

from build_info import build_id

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8754'


def health(url=None, expected_build=None):
    address = url or URL
    port = urlsplit(address).port
    try:
        with build_opener(ProxyHandler({})).open(address + '/api/health', timeout=1) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'Port {port} is occupied by another application.') from error
    except (URLError, TimeoutError, OSError):
        return False
    except ValueError as error:
        raise RuntimeError(f'Port {port} is occupied by another application.') from error
    if not isinstance(data, dict) or data.get('app') != 'p107-public-interface-v1' or not isinstance(data.get('features'), list) or 'integrated_research_v2' not in data['features']:
        raise RuntimeError(f'An older or unrelated app is using port {port}.')
    if data.get('build_id') != (expected_build or build_id()):
        raise RuntimeError(f'A different application build is using port {port}.')
    return True


def _port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def _start(address, expected_build):
    port = urlsplit(address).port
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    with (ROOT / 'stock.stdout.log').open('w') as out, (ROOT / 'stock.stderr.log').open('w') as err:
        process = subprocess.Popen(
            [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'server.py'), '--port', str(port)],
            cwd=ROOT.parent, stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=flags,
        )
    (ROOT / 'stock.pid').write_text(str(process.pid))
    try:
        for _ in range(50):
            if health(address, expected_build):
                return
            if process.poll() is not None:
                raise RuntimeError('Server failed. See web/stock.stderr.log.')
            time.sleep(.1)
        raise RuntimeError('Server did not become ready. See web/stock.stderr.log.')
    except Exception:
        # This is only the child started above, never an existing server.
        if process.poll() is None:
            process.terminate()
        raise


def main(no_browser=False, port=None):
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise ValueError('Port must be an integer from 1 to 65535.')
    preferred = port if port is not None else urlsplit(URL).port
    candidates = [preferred] if port is not None else range(preferred, min(preferred + 11, 65536))
    expected_build = build_id()
    address = None
    for candidate in candidates:
        candidate_url = f'http://127.0.0.1:{candidate}'
        try:
            if health(candidate_url, expected_build):
                address = candidate_url
                break
        except RuntimeError:
            if port is not None:
                raise
            continue
        if not _port_available(candidate):
            continue
        _start(candidate_url, expected_build)
        address = candidate_url
        break
    if address is None:
        raise RuntimeError('No available local port was found. Choose one with --port PORT.')
    print('Ready: ' + address)
    if not no_browser:
        webbrowser.open(address)
    return address


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, help='Use this port explicitly; otherwise try 8754 and nearby ports.')
    args = parser.parse_args()
    try:
        main(args.no_browser, args.port)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
