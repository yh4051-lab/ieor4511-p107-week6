import argparse,json
from pathlib import Path
from .reporting import run


def main():
    p=argparse.ArgumentParser(description='P107 hypothetical educational scenario engine')
    p.add_argument('--config',type=Path,default=Path('configs/example_hypothetical.json'))
    p.add_argument('--out',type=Path,default=Path('results'))
    p.add_argument('--no-charts',action='store_true',help='CSV-only run using Python standard library')
    args=p.parse_args()
    config=json.loads(args.config.read_text(encoding='utf-8'))
    summaries,be=run(config,args.out,args.config,not args.no_charts)
    print('HYPOTHETICAL; not historical backtest or actual tax savings')
    for r in summaries:
        print(f"{r['strategy']}: terminal USD {r['terminal_after_tax_wealth']:,.2f}; vs index {r['incremental_wealth_vs_index']:+,.2f}")
    print('Annual ST outside-gain break-even roots (USD):',be['roots_annual_usd'])
    print('Status:',be['status'])


if __name__=='__main__': main()
