"""One-factor observed-price sensitivities; no estimated performance distribution."""
import csv,json,sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from p107.observed_studies import observed_defaults,comparison,CACHE
from p107.studies import _history

def main():
    base=observed_defaults();raw=json.loads(CACHE.read_text(encoding='utf-8'))
    cases=[('financing_pct',v) for v in (3,5,7)]+[('borrow_pct',v) for v in (.5,1,2)]+[('tax_rates',v) for v in ((30,15),(40,20),(50,25))]+[('start_date',v) for v in ('2019-01-02','2021-01-04')]
    rows=[]
    for key,value in cases:
        c=deepcopy(base)
        if key=='tax_rates':c['tax_st_pct'],c['tax_lt_pct']=value;c['ordinary_tax_pct']=value[0];c['dividend_tax_pct']=value[1]
        else:c[key]=value
        d=_history(dict(data_source='uploaded',history=raw),c,list(raw['prices']),None)
        for strategy,run in comparison(c,d).items():
            s=run['summary'];rows.append(dict(parameter=key,value=str(value),strategy=strategy,
                terminal_after_tax_wealth=s['terminal_after_tax_wealth'],difference_vs_index=s['incremental_wealth_vs_index'],
                harvested_losses=s['cumulative_harvested_losses'],total_taxes=s['total_taxes'],net_costs=s['total_financing_and_fees_net_rebate']))
    path=ROOT/'results_observed/sensitivity.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('PASS: '+str(len(rows))+' observed-price sensitivity rows.')

if __name__=='__main__':main()
