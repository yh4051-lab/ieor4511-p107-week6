"""Open the current integrated app, including when using the original command."""
import argparse
import sys

import launch_stock

URL = launch_stock.URL


def health():
    """Require the integrated research feature, rather than an old app ID alone."""
    return launch_stock.health(URL)


def main(no_browser=False):
    return launch_stock.main(no_browser=no_browser)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        main(args.no_browser)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
