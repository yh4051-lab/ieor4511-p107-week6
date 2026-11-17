"""Download observed prices locally; no restricted provider data or public upload."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from p107.market_data import load_history, history_data_sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/observed_study.json')
    parser.add_argument('--out',type=Path,default=ROOT/'data/raw/observed_2019_2025.json')
    args=parser.parse_args()
    c=json.loads(args.config.read_text(encoding='utf-8'))
    symbols=sorted(set(c['universe']+c['replacement_tickers']))
    benchmark=c['benchmark']; symbols=[s for s in symbols if s!=benchmark]
    parts=[]
    for i in range(0,len(symbols),20):
        names=symbols[i:i+20]+[benchmark]
        print('Fetching '+', '.join(names),flush=True)
        parts.append(load_history(names,c['start_date'],c['end_date']))
    data=deepcopy(parts[0])
    for part in parts[1:]:
        if part['dates']!=data['dates']:raise ValueError('Batches do not share the exact trading calendar')
        for group in ('prices','splits','dividends'):data[group].update(part[group])
    data['metadata']={'source':'Yahoo Finance / yfinance','data_kind':'observed_market_prices',
                      'batches':[p['metadata'] for p in parts],
                      'universe_kind':c['universe_kind'],'universe_note':c['universe_note'],
                      'redistribution':'Local research cache; fetch independently or use an authorized private export.'}
    data['metadata']['data_sha256']=history_data_sha(data)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'file':str(args.out),'sessions':len(data['dates']),'securities':len(data['prices']),
                      'first':data['dates'][0],'last':data['dates'][-1],'sha256':data['metadata']['data_sha256']}))


if __name__=='__main__':main()
