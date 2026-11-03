"""Replay an exported historical research JSON using its saved data, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p107.research import run_research
from p107.market_data import history_data_sha


def replay(path):
    exported = json.loads(Path(path).read_text(encoding='utf-8'))
    previous = exported.get('result', exported)
    inputs = exported.get('inputs', previous['metadata']['inputs'])
    data = previous['data']
    digest = history_data_sha(data)
    if digest != data['metadata'].get('data_sha256'):
        raise ValueError('Saved historical data does not match its recorded SHA-256.')
    result = run_research(inputs, lambda tickers,start,end: data)
    for field in ('summary', 'daily', 'annual', 'trades', 'positions'):
        if result[field] != previous[field]:
            raise ValueError(f'Replayed {field} differs. Check model version and assumptions.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    result = replay(args.file)
    print('PASS: saved data hash, summary, daily/annual ledgers, trades and positions reproduce exactly without Yahoo.')
    print('Level:',result['level'],'Terminal wealth:',result['summary']['terminal_wealth'])
