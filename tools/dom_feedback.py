"""Reproducible Dom-feedback research: no proprietary data in this public repo."""
import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from p107.analysis import one_time_gain_comparison, one_time_gain_breakeven
from p107.model import compare
from p107.research import run_research
from p107.dom_sampling import sample_portfolios, evaluate_portfolio_cohort
from p107.dom_historical import historical_13030


def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def scenario(config, out, event_year, stepup):
    base, _=compare(config)
    gains=one_time_gain_comparison(config,(1000000,3000000,5000000),
                                    event_year=event_year)
    root,points=one_time_gain_breakeven(config,event_year=event_year,maximum=5000000,
                                        step=25000)
    exits=[]
    policies=[dict(mode='full_liquidation'),dict(mode='gift',recipient_liquidates=True),
              dict(mode='death',step_up_long_embedded_fraction=stepup)]
    policies += [dict(mode='gradual',years=k,extension_embedded_gain_share=.5)
                 for k in (3,4,5) if k<=config['horizon_years']]
    for policy in policies:
        c=deepcopy(config);c['exit_policy']=policy
        summaries,_=compare(c)
        exits.append(dict(policy=policy,strategies=summaries))
    dump(out,dict(hypothetical=True,source_config=config.get('label'),
                  one_time_event_year=event_year,baseline=base,
                  one_time_gains=gains,breakeven=root,
                  breakeven_curve=[dict(outside_gain=x,incremental_wealth=y) for x,y in points],
                  exit_scenarios=exits,
                  limitations=['Gift proxy assumes immediate heir/recipient sale: no automatic gain escape.',
                               'Step-up uses user-supplied allocation of embedded gain to eligible long book.',
                               'Gradual exit reallocates aggregate exposure; not a trade-by-trade tax-lot model.',
                               'Outside gross proceeds equal gain in this prototype; replace for real clients.']))


def historical(config, observations, out):
    data=json.loads(observations.read_text(encoding='utf-8'))
    r=run_research(config,lambda tickers,start,end:deepcopy(data))
    dump(out,r)


def sampling(config, memberships_csv, asof, count, longs, shorts, seed, out):
    with memberships_csv.open(encoding='utf-8-sig',newline='') as file:
        rows=list(csv.DictReader(file))
    for row in rows:
        row['point_in_time_verified']=row.get('point_in_time_verified','').lower()=='true'
    samples=sample_portfolios(rows,asof,longs,shorts,count,seed,
                              config.get('substitutes'))
    dump(out,dict(samples=samples,warning='Input membership provenance must be independently audited. '
                     'This file alone does not establish historic S&P 500 membership.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('scenario','historical','sample'))
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--historical-data',type=Path)
    parser.add_argument('--memberships',type=Path)
    parser.add_argument('--asof',default='2020-01-01')
    parser.add_argument('--samples',type=int,default=100)
    parser.add_argument('--long-count',type=int,default=10)
    parser.add_argument('--short-count',type=int,default=10)
    parser.add_argument('--seed',type=int,default=4511)
    parser.add_argument('--event-year',type=int,default=1)
    parser.add_argument('--stepup-long-fraction',type=float,default=None)
    a=parser.parse_args()
    c=json.loads(a.config.read_text(encoding='utf-8'))
    if a.mode=='scenario':
        if a.stepup_long_fraction is None:
            parser.error('Scenario study requires explicitly assumed --stepup-long-fraction')
        scenario(c,a.out,a.event_year,a.stepup_long_fraction)
    elif a.mode=='historical':
        if not a.historical_data:parser.error('--historical-data JSON is required')
        historical(c,a.historical_data,a.out)
    else:
        if not a.memberships:parser.error('--memberships CSV is required')
        sampling(c,a.memberships,a.asof,a.samples,a.long_count,a.short_count,a.seed,a.out)
    print('Saved',a.out)


if __name__=='__main__':main()
