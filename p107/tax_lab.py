"""Isolated four-strategy tax-aware research lab.

Replay a frozen export with ``python -m p107.tax_lab --input input.json --out replay.json``.
Portfolio construction is a local convex surrogate; realized wealth is evaluated by
an independent tax-lot ledger and full final liquidation. No forecast probability
or client recommendation is established by this prototype.
"""
from copy import deepcopy
from datetime import date, timedelta
import argparse
import csv
import hashlib
import io
import json
from math import exp, isfinite, sin
from pathlib import Path
import random
import platform
from importlib.metadata import version
import zipfile

import numpy as np

from .market_data import history_data_sha, load_history, normalize_ticker
from .observed_engine import simulate_observed
from .observed_studies import CACHE, observed_defaults, strategy_config
from .studies import _history

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'A': 'A · Index ETF', 'B': 'B · Long-only basket + rule-based TLH',
          'C': 'C · Fixed-weight 130/30, no harvesting',
          'D': 'D · Tax-aware QP weights/lots + rule-based TLH'}
ECONOMIC_FAILURES = ('Account is insolvent before rebalance', 'Insolvent margin liquidation',
                     'Negative family wealth', 'Trading costs exceed equity',
                     'Account became insolvent')


def tax_lab_defaults():
    observed = observed_defaults()
    observed.update(start_date='2020-01-02', end_date='2025-12-31')
    demo = deepcopy(observed)
    demo.update(label='Deterministic synthetic tax-aware lab demonstration',
                start_date='2020-01-02', end_date='2022-12-30', outside_gain_events=[])
    for c in (observed, demo):
        originals = [p['ticker'] for p in c['positions']]
        c['universe'] = originals
        c['replacement_tickers'] = [c['substitutes'][t]['ticker'] for t in originals]
        c['substitutes'] = {t: c['substitutes'][t] for t in originals}
    return dict(demo_config=demo, observed_config=observed, defaults=dict(
        optimization=dict(risk_aversion=50, lookback=126, long_cap_pct=60, short_cap_pct=20),
        sensitivities=dict(enabled=True, financing_rates=[3, 5, 7], borrow_rates=[0, 1, 3]),
        monte_carlo=dict(enabled=False, paths=5, seed=4511)))


def _number(value, name, low=0, high=100):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not isfinite(value) or not low <= value <= high):
        raise ValueError(f'{name} must be a finite number from {low} to {high}')
    return float(value)


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def _boolean(value, name):
    if type(value) is not bool:
        raise ValueError(name + ' must be true or false')
    return value


def _rates(values, name):
    if not isinstance(values, list) or not 1 <= len(values) <= 3:
        raise ValueError(name + ' needs one to three rates')
    answer = [_number(v, name, high=30) for v in values]
    if len(set(answer)) != len(answer):
        raise ValueError(name + ' must not repeat rates')
    return sorted(answer)


def _configuration(raw, optimization):
    if not isinstance(raw, dict):
        raise ValueError('Supply a complete lab configuration')
    c = deepcopy(raw)
    try:
        start, end = date.fromisoformat(c['start_date']), date.fromisoformat(c['end_date'])
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError('Use ISO start_date and end_date') from error
    if not 0 < (end-start).days <= 3660:
        raise ValueError('Choose an increasing evaluation period of at most ten years')
    c['initial_cash'] = _number(c.get('initial_cash'), 'Initial cash', 1, 1e10)
    c['benchmark'] = normalize_ticker(c.get('benchmark', 'SPY'))
    for key, required in [('long_exposure_pct', 130), ('short_exposure_pct', 30)]:
        if _number(c.get(key, required), key, high=1000) != required:
            raise ValueError('The first lab version compares fixed Core 130/30')
        c[key] = required
    defaults = dict(manager_pct=.4, advisor_pct=.1, benchmark_manager_pct=0,
                    di_manager_pct=.25, financing_pct=5, borrow_pct=1, rebate_pct=0,
                    transaction_pct=.05, tax_st_pct=40, tax_lt_pct=20,
                    ordinary_tax_pct=40, dividend_tax_pct=20, harvest_threshold_pct=8,
                    maintenance_equity_to_gross_pct=30)
    for key, default in defaults.items():
        cap = 30 if key in ('financing_pct', 'borrow_pct') else 90
        c[key] = _number(c.get(key, default), key, high=cap)
    c['rebalance_every_sessions'] = _integer(c.get('rebalance_every_sessions', 21), 'Rebalance sessions', 1, 10000)
    c['cooldown_days'] = _integer(c.get('cooldown_days', 30), 'Cooldown calendar days', 30, 3650)
    positions = c.get('positions')
    if not isinstance(positions, list) or not 2 <= len(positions) <= 20:
        raise ValueError('Supply two to twenty positions with long and short books')
    subs = c.get('substitutes')
    if not isinstance(subs, dict):
        raise ValueError('Supply explicit replacement assumptions')
    normalized = {normalize_ticker(k): deepcopy(v) for k, v in subs.items()}
    if len(normalized) != len(subs):
        raise ValueError('Duplicate normalized replacement keys')
    originals, replacements = [], []
    for p in positions:
        if not isinstance(p, dict):
            raise ValueError('Each position must be an object')
        p['ticker'] = normalize_ticker(p.get('ticker'))
        if p.get('side') not in ('long', 'short'):
            raise ValueError('Position direction must be long or short')
        p['weight'] = _number(p.get('weight'), 'Position weight', 1e-9, 1e6)
        originals.append(p['ticker'])
        sub = normalized.get(p['ticker'])
        if not isinstance(sub, dict) or sub.get('reviewed_not_substantially_identical') is not True:
            raise ValueError('Explicit reviewed replacement assumption required for ' + p['ticker'])
        sub['ticker'] = normalize_ticker(sub.get('ticker'))
        replacements.append(sub['ticker'])
    if len(set(originals+replacements)) != len(originals+replacements):
        raise ValueError('Original and replacement tickers must be unique and disjoint in this engine')
    if {p['side'] for p in positions} != {'long', 'short'}:
        raise ValueError('Supply both a long book and a short book')
    c['substitutes'] = {t: normalized[t] for t in originals}
    events = c.get('outside_gain_events', [])
    if not isinstance(events, list) or len(events) > 20:
        raise ValueError('outside_gain_events must be a list of at most twenty events')
    for event in events:
        if (not isinstance(event, dict) or type(event.get('year')) is not int or
                not start.year <= event['year'] <= end.year or event.get('character') not in ('st', 'lt')):
            raise ValueError('Outside gain events require an in-period year and ST/LT character')
        event['amount'] = _number(event.get('amount'), 'Outside gain amount', high=1e10)
    c['outside_gain_events'] = events
    if not isinstance(optimization, dict):
        raise ValueError('optimization must be an object')
    lookback = _integer(optimization.get('lookback', 126), 'Lookback', 20, 504)
    risk = _number(optimization.get('risk_aversion', 50), 'Risk aversion', 0, 10000)
    long_cap = _number(optimization.get('long_cap_pct', 60), 'Long weight cap', 1, 130)/100
    short_cap = _number(optimization.get('short_cap_pct', 20), 'Short weight cap', 1, 30)/100
    if sum(p['side']=='long' for p in positions)*long_cap < 1.3-1e-9:
        raise ValueError('Long caps cannot accommodate 130% exposure; increase caps or add long positions')
    if sum(p['side']=='short' for p in positions)*short_cap < .3-1e-9:
        raise ValueError('Short caps cannot accommodate 30% exposure; increase caps or add short positions')
    c.update(lab_diagnostics=True, optimizer=dict(
        lookback_sessions=lookback, min_history_sessions=20, risk_aversion=risk,
        tax_penalty=1, turnover_penalty=.0001, covariance_shrinkage=.2,
        max_long_weight=long_cap, max_short_weight=short_cap, return_model='zero'))
    return c


def _demo_history():
    c = tax_lab_defaults()['demo_config']
    names = [p['ticker'] for p in c['positions']] + c['replacement_tickers'] + [c['benchmark']]
    dates, day = [], date(2019, 1, 2)
    while day <= date(2022, 12, 30):
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    prices, dividends = {}, {}
    for k, ticker in enumerate(names):
        phase = .63*k
        if ticker == c['benchmark']:
            series = [100*exp(.00023*i + .045*sin(.024*i)) for i in range(len(dates))]
        else:
            series = [100*exp((.00016+.000025*(k%4))*i + .12*(sin(.034*i+phase)-sin(phase)) +
                             .025*(sin(.073*i+.31*k)-sin(.31*k))) for i in range(len(dates))]
        prices[ticker] = series
        dividends[ticker] = [.12 if i and i%63==0 else 0. for i in range(len(dates))]
    return dict(dates=dates, prices=prices, dividends=dividends,
                splits={t:[0.]*len(dates) for t in names}, metadata=dict(
                    source='Deterministic synthetic tax-aware lab demonstration',
                    data_kind='synthetic', source_kind='demo',
                    calendar='Weekdays only, no exchange holiday calibration',
                    note='Fabricated observations for functional exploration, not historical returns.'))


def _validate_history(data, names):
    if not isinstance(data, dict) or not isinstance(data.get('metadata'), dict) or not data['metadata']:
        raise ValueError('History must include nonempty source metadata')
    dates = data.get('dates')
    if not isinstance(dates, list) or not 22 <= len(dates) <= 6000:
        raise ValueError('History needs 22 to 6000 sessions, including pre-start warmup')
    try:
        parsed = [date.fromisoformat(d) for d in dates]
    except (TypeError, ValueError) as error:
        raise ValueError('History dates must use ISO format') from error
    if any(a>=b for a,b in zip(parsed,parsed[1:])):
        raise ValueError('History dates must be ordered and unique')
    for group in ('prices', 'dividends', 'splits'):
        for t in names:
            values = data.get(group, {}).get(t)
            if not isinstance(values,list) or len(values)!=len(dates):
                raise ValueError(f'Missing or inconsistent {group} for {t}; no series were substituted')
            for value in values:
                _number(value, group+' '+t, 1e-12 if group=='prices' else 0, 1e12)
    json.dumps(data['metadata'], allow_nan=False)


def _kind(metadata, source_kind):
    text = json.dumps(metadata, sort_keys=True).lower()
    if source_kind=='demo' or any(s in text for s in ('synthetic','simulated','fabricated','bootstrap')):
        return 'synthetic', 'SYNTHETIC observations · hypothetical strategies'
    if source_kind in ('live','local_cache') or 'yahoo' in text or 'observed_market_prices' in text:
        return 'observed', 'Observed-price source declaration · hypothetical strategies'
    return 'unverified', 'Uploaded prices · source not independently verified'


def _prepare_history(request, c, provider):
    source=request.get('data_source','demo')
    if source not in ('demo','live','uploaded','local_cache'):
        raise ValueError('Choose demo, live, uploaded or local_cache data')
    original_source=request.get('source_kind',source)
    if original_source not in ('demo','live','uploaded','local_cache'):
        raise ValueError('Unknown original source kind')
    names=sorted(({p['ticker'] for p in c['positions']}|{v['ticker'] for v in c['substitutes'].values()})-{c['benchmark']})+[c['benchmark']]
    if source=='demo':
        raw=_demo_history()
    elif source=='uploaded':
        raw=deepcopy(request.get('history'))
    elif source=='local_cache':
        if not CACHE.is_file():
            raise ValueError('Local observed cache missing; choose live prices or upload authorized history with warmup')
        raw=json.loads(CACHE.read_text(encoding='utf-8'))
    else:
        before=date.fromisoformat(c['start_date'])-timedelta(days=c['optimizer']['lookback_sessions']*2+14)
        securities=[name for name in names if name!=c['benchmark']]
        batches=[provider(securities[i:i+21]+[c['benchmark']],before.isoformat(),c['end_date'])
                 for i in range(0,len(securities),21)]
        raw=deepcopy(batches[0])
        for b in batches[1:]:
            if b['dates']!=raw['dates']:
                raise ValueError('History batches have different calendars; no sessions were dropped')
            for group in ('prices','dividends','splits'):raw[group].update(b[group])
        raw['metadata']={'source':'Supplied market-data adapter','batches':[b['metadata'] for b in batches]}
    _validate_history(raw,names)
    warmup=[i for i,d in enumerate(raw['dates']) if d<c['start_date']]
    if len(warmup)<21:
        raise ValueError('At least 21 pre-start prices (20 past returns) are required; provide warmup or move the start date')
    # Export only the required security series, preserving the complete warmup.
    raw={**raw,**{g:{t:raw[g][t] for t in names} for g in ('prices','dividends','splits')}}
    raw['metadata']=deepcopy(raw['metadata'])
    raw['metadata']['data_sha256']=history_data_sha(raw)
    data=_history(dict(data_source='uploaded',history=raw),c,names,None)
    kind,label=_kind(raw['metadata'],original_source)
    return raw,data,kind,label,original_source


def _risk(run, benchmark):
    values=[row.get('investment_return') for row in run['daily']][1:]
    base=[row.get('investment_return') for row in benchmark['daily']][1:]
    if len(values)!=len(base) or not values or any(v is None or not isfinite(v) for v in values+base):
        return dict(tracking_error=None,volatility=None,max_drawdown=None,max_concentration=None,max_gross_exposure=None,
                    note='Investment-return diagnostics unavailable; no risk values were fabricated')
    a=np.asarray(values,dtype=float);b=np.asarray(base,dtype=float)
    wealth=np.cumprod(1+a)
    peaks=np.maximum.accumulate(np.r_[1.,wealth])[1:]
    concentrations=[r.get('max_concentration') for r in run['daily']]
    finite_concentrations=[v for v in concentrations if isinstance(v,(int,float)) and isfinite(v)]
    return dict(tracking_error=float(np.std(a-b,ddof=1)*np.sqrt(252)) if len(a)>1 else 0.,
                volatility=float(np.std(a,ddof=1)*np.sqrt(252)) if len(a)>1 else 0.,
                max_drawdown=float(max(0.,np.max(1-wealth/peaks))),
                max_concentration=max(finite_concentrations) if finite_concentrations else None,
                max_gross_exposure=max((r['long_pct']+r['short_pct'])/100 for r in run['daily']),
                note='Pre-current-cost/tax price-and-dividend investment returns, normalized by prior invested account NAV. External side cash is excluded; this is not a household wealth drawdown.')


def _strategies(c, data, forecast):
    from .tax_optimizer import build_tax_allocator
    configs={'A':strategy_config(c,'index'),'B':strategy_config(c,'long_only_di'),
             'C':strategy_config(c,'no_harvest'),'D':strategy_config(c,'core_130_30')}
    runs={}
    for key,config in configs.items():
        allocator=build_tax_allocator(config,forecast) if key=='D' else None
        run=simulate_observed(config,data,policy={'mode':'full_sale'},allocator=allocator)
        run['label']=LABELS[key]
        if key=='D':run['optimizer_decisions']=run.get('optimization_records',allocator.records)
        runs[key]=run
    for run in runs.values():run['risk']=_risk(run,runs['A'])
    return runs


def _comparison(runs):
    base=runs['A']['summary']['terminal_after_tax_wealth'];control=runs['C']['summary']['terminal_after_tax_wealth']
    rows=[]
    for key,run in runs.items():
        s=run['summary'];r=run['risk']
        rows.append(dict(strategy=key,label=LABELS[key],terminal_wealth=s['terminal_after_tax_wealth'],
                         delta_vs_A=s['terminal_after_tax_wealth']-base,delta_vs_C=s['terminal_after_tax_wealth']-control,
                         total_taxes=s['total_taxes'],total_costs=s['total_financing_and_fees_net_rebate'],
                         harvested_losses=s['cumulative_harvested_losses'],carry_st=s['remaining_carry_st'],carry_lt=s['remaining_carry_lt'],
                         tracking_error=r['tracking_error'],max_drawdown=r['max_drawdown'],volatility=r['volatility'],
                         concentration=r['max_concentration'],margin_liquidations=s['margin_liquidations']))
    return rows


def _economic_failure(error):
    return isinstance(error,ValueError) and any(str(error).startswith(p) for p in ECONOMIC_FAILURES)


def _small_run(c,data,forecast):
    try:
        runs=_strategies(c,data,forecast)
    except ValueError as error:
        if not _economic_failure(error):raise
        return dict(status='failed',error=str(error),wealth_A=None,wealth_B=None,wealth_C=None,wealth_D=None,
                    delta_D_A=None,delta_D_C=None)
    wealth={k:v['summary']['terminal_after_tax_wealth'] for k,v in runs.items()}
    return dict(status='completed',**{'wealth_'+k:v for k,v in wealth.items()},
                delta_D_A=wealth['D']-wealth['A'],delta_D_C=wealth['D']-wealth['C'])


def _sensitivity(spec,c,data,forecast,anchor):
    if not spec['enabled']:return dict(rows=[],summary=dict(completed=0,failed=0))
    memo={(c['financing_pct'],c['borrow_pct']):dict(status='completed',
        **{'wealth_'+k:r['summary']['terminal_after_tax_wealth'] for k,r in anchor.items()},
        delta_D_A=anchor['D']['summary']['terminal_after_tax_wealth']-anchor['A']['summary']['terminal_after_tax_wealth'],
        delta_D_C=anchor['D']['summary']['terminal_after_tax_wealth']-anchor['C']['summary']['terminal_after_tax_wealth'])}
    rows=[]
    for b in spec['borrow_rates']:
        for f in spec['financing_rates']:
            if (f,b) not in memo:
                scenario=deepcopy(c);scenario.update(financing_pct=f,borrow_pct=b)
                memo[f,b]=_small_run(scenario,data,forecast)
            rows.append(dict(financing_pct=f,borrow_pct=b,**memo[f,b]))
    done=[r for r in rows if r['status']=='completed']
    return dict(rows=rows,summary=dict(completed=len(done),failed=len(rows)-len(done)))


def _bootstrap_history(forecast,c,rng,block=20):
    dates=forecast['dates'];past=[i for i,d in enumerate(dates) if d<c['start_date']]
    future=[i for i,d in enumerate(dates) if c['start_date']<=d<=c['end_date']]
    pool=[i for i in past if i>0]
    if len(pool)<20:raise ValueError('Monte Carlo needs at least twenty pre-start return observations')
    sampled=[]
    while len(sampled)<max(0,len(future)-1):
        start=rng.randrange(max(1,len(pool)-block+1));sampled.extend(pool[start:start+block])
    sampled=sampled[:max(0,len(future)-1)]
    selected=past+future;prefix=len(past)
    result=dict(dates=[dates[i] for i in selected],prices={},dividends={},splits={},metadata=dict(
        source='SIMULATED joint historical block bootstrap from pre-start observations only',
        data_kind='synthetic',training_last_date=dates[past[-1]],block_sessions=block,
        note='Conditional model scenarios, not observed returns or real-world probabilities.'))
    for ticker in forecast['prices']:
        px=forecast['prices'][ticker];split=forecast['splits'][ticker];div=forecast['dividends'][ticker]
        prices=[px[i] for i in past]+[px[future[0]]]
        distributions=[div[i] for i in past]+[0.]
        actions=[split[i] for i in past]+[0.]
        for i in sampled:
            adjusted=px[i]*(split[i] or 1)/px[i-1]
            value=prices[-1]*adjusted
            prices.append(value);distributions.append((div[i]/px[i])*value);actions.append(0.)
        result['prices'][ticker]=prices;result['dividends'][ticker]=distributions;result['splits'][ticker]=actions
    return result


def _monte_carlo(spec,c,forecast):
    if not spec['enabled']:return dict(rows=[],summary=dict(completed=0,failed=0,median_delta=None,p05=None,p95=None))
    rng=random.Random(spec['seed']);rows=[]
    names=list(forecast['prices'])
    for k in range(spec['paths']):
        generated=_bootstrap_history(forecast,c,rng)
        evaluation=_history(dict(data_source='uploaded',history=generated),c,names,None)
        rows.append(dict(path=k+1,**_small_run(c,evaluation,generated)))
    values=[r['delta_D_A'] for r in rows if r['status']=='completed']
    return dict(rows=rows,summary=dict(completed=len(values),failed=len(rows)-len(values),
        median_delta=float(np.median(values)) if values else None,
        p05=float(np.quantile(values,.05)) if values else None,p95=float(np.quantile(values,.95)) if values else None),
        method='Joint block bootstrap, twenty-session blocks, fitted exclusively to pre-start history; same path for A–D',
        training_last_date=max(d for d in forecast['dates'] if d<c['start_date']),seed=spec['seed'])


def run_tax_lab(request, history_provider=None):
    if not isinstance(request,dict):raise ValueError('Tax lab request must be an object')
    settings=tax_lab_defaults()['defaults']
    optimization=deepcopy(request.get('optimization',settings['optimization']))
    c=_configuration(request.get('config'),optimization)
    sensitivity=deepcopy(request.get('sensitivities',settings['sensitivities']))
    mc=deepcopy(request.get('monte_carlo',settings['monte_carlo']))
    if not isinstance(sensitivity,dict) or not isinstance(mc,dict):raise ValueError('Sensitivity and Monte Carlo settings must be objects')
    sensitivity['enabled']=_boolean(sensitivity.get('enabled',True),'Sensitivity enabled')
    sensitivity['financing_rates']=_rates(sensitivity.get('financing_rates',[3,5,7]),'Financing rates')
    sensitivity['borrow_rates']=_rates(sensitivity.get('borrow_rates',[0,1,3]),'Borrow rates')
    mc['enabled']=_boolean(mc.get('enabled',False),'Monte Carlo enabled')
    mc['paths']=_integer(mc.get('paths',5),'Monte Carlo paths',1,10)
    mc['seed']=_integer(mc.get('seed',4511),'Random seed',0,2**32-1)
    forecast,data,kind,label,source_kind=_prepare_history(request,c,history_provider or load_history)
    strategies=_strategies(c,data,forecast)
    result=dict(data_kind=kind,data_label=label,data_metadata=dict(data['metadata'],
        forecast_first=forecast['dates'][0],forecast_last=forecast['dates'][-1],warmup_sessions=sum(d<c['start_date'] for d in forecast['dates'])),
        strategies=strategies,comparison=_comparison(strategies),
        sensitivity=_sensitivity(sensitivity,c,data,forecast,strategies),monte_carlo=_monte_carlo(mc,c,forecast),
        request=dict(config=c,data_source='uploaded',source_kind=source_kind,history=forecast,
                     optimization=optimization,sensitivities=sensitivity,monte_carlo=mc),limitations=[
            'A is a 100%-long index ETF. B is a selected-stock long-only harvesting basket, not a calibrated index-tracking product. C is fixed-weight 130/30 without harvesting. D combines a constrained local QP, selected-lot sells and the same rule-based harvesting/replacement mechanism.',
            'D uses a conservative local tax proxy: positive realized gains are penalized; unrealized loss sells receive no immediate cash tax credit in the optimizer. Actual ST/LT netting, carryforwards, wash deferrals and final taxes are settled separately by the lot ledger.',
            'The QP controls a covariance-based active-risk penalty using only pre-trade observations. Zero expected alpha is assumed; no future returns are used. This single-period problem does not maximize final lifetime wealth.',
            'Displayed risk uses price-and-dividend investment returns before current costs/taxes, divided by prior invested account NAV. It excludes outside side cash. These are investment-risk diagnostics, not risk-adjusted tax alpha.',
            'The embedded-tax series is a positive-unrealized-gain tax proxy before loss/carry offsets, not an exact payable liquidation bill. D minus C tax-payment differences also contain changed holdings and realized returns; they are not pure causal tax savings.',
            'Intermediate wealth deducts taxes when actually paid but still includes embedded unpaid tax. The final point closes all positions and settles outstanding capital taxes. Outside cash proceeds equal the supplied outside gain and enter all comparisons identically.',
            'Hypothetical close execution, flat tax rates, available borrow, replacement eligibility and daily-close margin checks remain research assumptions. Household wash sales, intraday gaps and complex offsetting-position tax rules are not modeled.',
            'Sensitivity cells are fixed-period scenarios; positive-cell fractions are not future win probabilities. Monte Carlo is conditional pre-start joint block resampling, not a forecast probability model or an independent source of evidence.'
        ])
    names=['tax_lab.py','tax_optimizer.py','observed_engine.py','lot_accounting.py','taxes.py','market_data.py']
    result['engine_hashes']={name:hashlib.sha256((ROOT/'p107'/name).read_bytes()).hexdigest() for name in names}
    result['runtime_versions']=dict(python=platform.python_version(),numpy=np.__version__,
                                    cvxpy=version('cvxpy'),clarabel=version('clarabel'))
    result['run_id']=hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()[:20]
    return result


def _csv(rows):
    if not rows:return b''
    keys=list(dict.fromkeys(k for row in rows for k in row))
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=keys,lineterminator='\n');writer.writeheader()
    for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    return stream.getvalue().encode('utf-8-sig')


def tax_lab_zip(result):
    encode=lambda x:(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    files={'input.json':encode(result['request']),'result.json':encode(result),'comparison.csv':_csv(result['comparison']),
           'sensitivity.csv':_csv(result['sensitivity']['rows']),'monte_carlo.csv':_csv(result['monte_carlo']['rows']),
           'README.txt':(result['data_label']+'\nReplay offline: python -m p107.tax_lab --input input.json --out replay.json\n'
            'Requires NumPy and CVXPY with a supported convex solver. Input includes the exact warmup and evaluation data.\n'
            'Intermediate wealth still contains unpaid embedded tax; terminal wealth reflects full final liquidation.\n'
            'Risk uses investment returns excluding outside cash. Embedded tax is a gross-positive-gain proxy, not the exact tax payable.\n'
            'Optimization is a local surrogate, not a proof of maximum final wealth. Read result.json limitations.\n').encode()}
    for key,run in result['strategies'].items():
        for field in ('daily','annual','trades','realizations','wash_matches','events','optimizer_decisions'):
            if run.get(field):files[key+'/'+field+'.csv']=_csv(run[field])
    files['FILE_MANIFEST.json']=encode({name:hashlib.sha256(data).hexdigest() for name,data in files.items()})
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    return output.getvalue()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();result=run_tax_lab(json.loads(args.input.read_text(encoding='utf-8')))
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(result['data_label']+'; four strategies evaluated')


if __name__=='__main__':main()
