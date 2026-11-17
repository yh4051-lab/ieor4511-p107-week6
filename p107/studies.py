"""Reproducible sponsor studies shared by the browser and CLI."""
from copy import deepcopy
from datetime import date
import csv
import hashlib
import io
import json
from pathlib import Path

from .analysis import one_time_gain_breakeven
from .model import compare, with_gains
from .dom_historical import historical_comparison
from .dom_sampling import evaluate_portfolio_cohort, _members_at_date
from .market_data import load_history, normalize_ticker

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def membership_rows(text):
    rows=list(csv.DictReader(io.StringIO(text)))
    for row in rows:
        row['point_in_time_verified']=str(row.get('point_in_time_verified','')).strip().lower()=='true'
    return rows


def defaults():
    from .observed_studies import observed_defaults, CACHE
    return dict(annual=read_json(ROOT/'configs/example_hypothetical.json'),
                observed=observed_defaults(),observed_cache_available=CACHE.exists(),
                historical=read_json(ROOT/'configs/example_dom_historical.json'),
                memberships_csv=(ROOT/'examples/dom_synthetic_memberships.csv').read_text(encoding='utf-8'),
                note='The included stock prices and memberships are synthetic software fixtures, not market history.')


def _history(request, config, names, provider):
    source=request.get('data_source','synthetic')
    if source=='synthetic':
        data=read_json(ROOT/'examples/dom_synthetic_history.json')
    elif source=='uploaded':
        data=deepcopy(request.get('history'))
    elif source=='live':
        # The quote adapter accepts at most 22 names per call. A cohort needs
        # the entire universe plus substitutes, not just one selected portfolio.
        batches=[provider(names[i:i+22],config['start_date'],config['end_date'])
                 for i in range(0,len(names),22)]
        data=deepcopy(batches[0])
        for batch in batches[1:]:
            if batch['dates']!=data['dates']:
                raise ValueError('Price batches have inconsistent calendars; no sessions were silently dropped')
            for group in ('prices','splits','dividends'):
                data[group].update(batch[group])
        data['metadata']={'source':'Supplied market-data adapter',
                          'batches':[batch['metadata'] for batch in batches]}
    else:
        raise ValueError('Choose synthetic, uploaded or live history')
    if not isinstance(data,dict) or not data.get('metadata'):
        raise ValueError('History JSON must include source metadata')
    all_dates=data.get('dates',[])
    indices=[i for i,d in enumerate(all_dates) if config['start_date']<=d<=config['end_date']]
    if len(indices)<2:
        raise ValueError('Fewer than two price sessions in the requested period')
    result={'dates':[all_dates[i] for i in indices],'metadata':deepcopy(data['metadata'])}
    first,last=map(date.fromisoformat,(result['dates'][0],result['dates'][-1]))
    if (first-date.fromisoformat(config['start_date'])).days>7 or (date.fromisoformat(config['end_date'])-last).days>7:
        raise ValueError('Price history does not cover the requested period (more than seven calendar days missing at a boundary)')
    result['metadata'].update(actual_start=first.isoformat(),actual_end=last.isoformat(),
                              sessions=len(indices))
    for group in ('prices','splits','dividends'):
        result[group]={}
        for name in names:
            arr=data.get(group,{}).get(name)
            if not isinstance(arr,list) or len(arr)!=len(all_dates):
                raise ValueError(f'Missing or inconsistent {group} for {name}; no securities were silently dropped')
            result[group][name]=[arr[i] for i in indices]
    return result


def run_study(request, history_provider=None):
    if not isinstance(request,dict):
        raise ValueError('Study request must be an object')
    if request.get('engine')=='historical_lots':
        from .observed_studies import run_observed_study
        return run_observed_study(request,history_provider)
    request=deepcopy(request)
    mode=request.get('mode')
    c=deepcopy(request.get('config'))
    if not isinstance(c,dict):
        raise ValueError('Supply a complete study configuration')
    result={'mode':mode}
    warnings=[]
    replay=deepcopy(request)
    if mode=='exits':
        c.pop('exit_policy',None)
        base,_=compare(c)
        by_name={r['strategy']:r['terminal_after_tax_wealth'] for r in base}
        stepup=request.get('stepup_long_fraction')
        if stepup is None:
            raise ValueError('Specify the assumed eligible long share of Core embedded gains')
        policies=[('Full sale',{'mode':'full_liquidation'})]
        policies += [(f'{y}-year full-portfolio exit',{'mode':'gradual_liquidation','years':y})
                     for y in (3,4,5) if y<=c['horizon_years']]
        if c['horizon_years']>=3:
            policies += [('3-year extension reduction + final sale',dict(mode='gradual',years=3,
                           extension_embedded_gain_share=request.get('extension_gain_share',.5)))]
        policies += [('Hold until death',dict(mode='death',step_up_long_embedded_fraction=stepup)),
                     ('Gift with recipient sale',dict(mode='gift',gift_year=request.get('gift_year',c['horizon_years']),
                          recipient_liquidates=True,recipient_tax_st=request.get('recipient_tax_st',c['tax_st']),
                          recipient_tax_lt=request.get('recipient_tax_lt',c['tax_lt']),
                          recipient_ordinary_tax=request.get('recipient_tax_st',c['ordinary_tax_rate'])))]
        rows=[];ledger=[]
        for label,policy in policies:
            variant=deepcopy(c);variant['exit_policy']=policy
            summaries,annual=compare(variant)
            for row in summaries:
                rows.append(dict(policy=label,**row,
                                 difference_vs_full_sale=row['terminal_after_tax_wealth']-by_name[row['strategy']]))
            ledger += [dict(policy=label,**r) for r in annual]
        result.update(rows=rows,annual=ledger,policies=[dict(label=l,**p) for l,p in policies])
        warnings += ['Illustrative annual returns and exogenous losses; these exit results are not a historical backtest.',
                     'Full-portfolio exit sells equal fractions of remaining NAV over the last 3-5 years; sale proceeds stay in side cash.',
                     'Extension reduction retains a long-only core until final sale. It is a different exit question.',
                     'Death assumes eligible long-only assets adjust fully to FMV; Core uses the stated share of net embedded gain as a proxy. Short liabilities are not stepped up.',
                     'Gift reports combined donor/recipient wealth. Donor outside gains and retained carryforwards are taxed separately from the recipient portfolio. No gift/estate tax or legal transfer of short liabilities is simulated.',
                     'Below-basis gifts need dual-basis tax lots and are rejected by this aggregate scenario.']
    elif mode=='one_time':
        event_year=request.get('event_year',1)
        character=request.get('character','st')
        rows=[]
        for amount in (0.,1e6,3e6,5e6):
            variant=with_gains(c,amount,character,'year',event_year)
            summaries,_=compare(variant)
            rows.extend(dict(outside_gain=amount,event_year=event_year,character=character,**s) for s in summaries)
        searches=[]
        for comparator in ('index','long_only_di'):
            diagnostics,points=one_time_gain_breakeven(c,event_year,character,comparator=comparator,
                                      maximum=request.get('search_max',5e6),step=request.get('search_step',25000))
            searches.append(dict(**diagnostics,curve=[dict(gain=x,delta=y) for x,y in points]))
        result.update(rows=rows,searches=searches)
        warnings += ['One gain occurs only in the selected year; it is not repeated annually.',
                     'Compare strategy differences: reported wealth includes the same outside proceeds for all strategies.',
                     'The common outside principal is excluded. Incremental cash proceeds equal the gain; these are illustrative client scenarios.',
                     'A finite-grid search may miss tangent roots; no crossing is reported explicitly, not as a zero threshold.']
    elif mode in ('historical','cohort'):
        if mode=='cohort':
            count=request.get('samples',20)
            if type(count) is not int or not 1<=count<=200:
                raise ValueError('Choose 1 to 200 portfolios per study')
            members=request.get('memberships')
            if request.get('data_source','synthetic')=='synthetic' and members is None:
                members=membership_rows((ROOT/'examples/dom_synthetic_memberships.csv').read_text(encoding='utf-8'))
            asof=request.get('as_of',c['start_date'])
            originals=_members_at_date(members,asof)
            replay['memberships']=members
        else:
            originals=[normalize_ticker(p['ticker']) for p in c['positions']]
        subs=c.get('substitutes',{})
        missing=[name for name in originals if name not in subs]
        if missing:
            raise ValueError('Missing replacement mapping for '+', '.join(missing))
        names=sorted(set(originals+[normalize_ticker(subs[t]['ticker']) for t in originals]+
                         [normalize_ticker(c.get('benchmark','SPY'))]))
        data=_history(request,c,names,history_provider or load_history)
        replay.update(data_source='uploaded',history=data)
        result['data_metadata']=data['metadata']
        if mode=='historical':
            comparison=historical_comparison(c,data)
            result.update(comparison)
            result['rows']=[dict(strategy=name,**run['summary']) for name,run in comparison['results'].items()]
        else:
            result.update(evaluate_portfolio_cohort(c,members,asof,request.get('long_count',3),
                           request.get('short_count',3),lambda cfg:historical_comparison(cfg,data),
                           draws=count,seed=request.get('seed',4511)))
            result['rows']=result['results']
        warnings += ['Mapped substitutes are user-reviewed assumptions, not a legal wash-sale determination. Same-ticker harvest reentry waits more than 30 calendar days.',
                     'Periodic rebalancing and substitute disposal can create other losses. Full before/after wash-sale matching, household accounts and special short rules are not implemented.',
                     'Comparisons match outside cash and observed prices. The benchmark is 100% long with its separately stated management rate.',
                     'Historical exits in this study are full liquidation; the exit-options study uses the separate annual scenario model.',
                     'The engine rejects nonpositive equity; it does not model margin calls or borrow recalls.']
        if mode=='cohort':
            warnings += ['Point-in-time membership is supplied and attested by the data owner. This software cannot authenticate index membership.',
                         'Random portfolios do not remove factor bias or missing/delisted-security bias. Quantiles describe this supplied universe, not statistical confidence.']
    else:
        raise ValueError('Choose historical, exits, one_time or cohort')
    source=request.get('data_source','synthetic')
    result['data_label']=('Illustrative assumptions' if mode in ('exits','one_time') else
                          'SYNTHETIC SOFTWARE TEST — NOT MARKET HISTORY' if source=='synthetic' or
                          'synthetic' in json.dumps(result.get('data_metadata',{})).lower() else
                          'Supplied historical data — provenance requires review')
    result['warnings']=warnings
    result['request']=replay
    code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'p107').glob('*.py'))}
    result['metadata']={'source_sha256':code_hashes,
                        'request_sha256':hashlib.sha256(json.dumps(replay,sort_keys=True,allow_nan=False).encode()).hexdigest()}
    result['run_id']=hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()[:20]
    return result
