"""Launch the integrated stock feature on its own port; do not reuse older servers."""
from pathlib import Path
import json
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
import webbrowser
import argparse

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8754'


def health(url=None):
    try:
        with build_opener(ProxyHandler({})).open((url or URL) + '/api/health', timeout=1) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError('Port 8754 is in use. Close its old server or use web/server.py with another port.') from error
    except URLError:
        return False
    except ValueError as error:
        raise RuntimeError('Port 8754 is occupied by another application.') from error
    if data.get('app') != 'p107-public-interface-v1' or 'integrated_research_v2' not in data.get('features', []):
        raise RuntimeError('An older or unrelated app is using port 8754. Close that app before starting this version.')
    return True


def main(no_browser=False):
    if not health():
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        with (ROOT / 'stock.stdout.log').open('w') as out, (ROOT / 'stock.stderr.log').open('w') as err:
            process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', str(ROOT/'server.py'), '--port', '8754'], cwd=ROOT.parent, stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=flags)
        (ROOT/'stock.pid').write_text(str(process.pid))
        for _ in range(50):
            if health():
                break
            if process.poll() is not None:
                raise RuntimeError('Server failed. See web/stock.stderr.log.')
            time.sleep(.1)
        else:
            raise RuntimeError('Server did not become ready. See web/stock.stderr.log.')
    print('Ready: '+URL)
    if not no_browser:
        webbrowser.open(URL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        main(args.no_browser)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
