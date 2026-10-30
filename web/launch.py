"""Start the local app quietly and open the user's normal browser."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8751'
APP_ID = 'p107-public-interface-v1'


def health():
    try:
        with build_opener(ProxyHandler({})).open(URL + '/api/health', timeout=1) as response:
            data = json.load(response)
        if data.get('app') != APP_ID:
            raise RuntimeError('Port 8751 is occupied by another application.')
        return True
    except (OSError, ValueError):
        return False


def main(no_browser=False):
    if not health():
        flags = 0
        if sys.platform == 'win32':
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        with (ROOT / 'server.stdout.log').open('w') as stdout, (ROOT / 'server.stderr.log').open('w') as stderr:
            process = subprocess.Popen(
                [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'server.py'), '--port', '8751'],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                close_fds=True, creationflags=flags,
            )
        (ROOT / 'server.pid').write_text(str(process.pid), encoding='ascii')
        for _ in range(40):
            if health():
                break
            if process.poll() is not None:
                raise RuntimeError('Local server could not start. See server.stderr.log.')
            time.sleep(.15)
        else:
            raise RuntimeError('Local server did not become ready. See server.stderr.log.')
    print('P107 ready: ' + URL)
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
