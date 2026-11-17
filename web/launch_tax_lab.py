"""Open the isolated tax-aware research branch on its own local port."""
import argparse
import os
from pathlib import Path
import webbrowser
import launch_stock


def main(no_browser=False, port=None):
    cache = Path(__file__).resolve().parents[1] / 'work' / 'lab-cache'
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('XDG_CACHE_HOME', str(cache))
    launch_stock.URL = 'http://127.0.0.1:8777'
    address = launch_stock.main(no_browser=True, port=port)
    target = address + '/tax-lab'
    print('Tax-aware research branch: ' + target)
    if not no_browser:
        webbrowser.open(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    main(args.no_browser, args.port)
