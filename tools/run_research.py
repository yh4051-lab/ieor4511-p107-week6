"""Run a manual three-level research configuration and export auditable files."""
import argparse
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p107.research import run_research


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--out', type=Path, required=True, help='A new output directory')
    args=parser.parse_args()
    inputs=json.loads(args.config.read_text(encoding='utf-8'))
    result=run_research(inputs)
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'research.json').write_text(json.dumps(dict(inputs=inputs,result=result),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for name in ('daily','annual','trades','positions'):
        rows=result[name]
        if rows:
            with (args.out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(result['summary'],indent=2))
    print('Saved to',args.out)


if __name__=='__main__':
    main()
