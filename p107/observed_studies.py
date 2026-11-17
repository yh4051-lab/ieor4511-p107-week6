"""Four employer questions on the same observed-price, tax-lot engine."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

from .observed_engine import simulate_observed
from .market_data import history_data_sha, load_history

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data/raw/observed_2019_2025.json'


def observed_defaults():
    c=json.loads((ROOT/'configs/observed_study.json').read_text(encoding='utf-8'))
    c['substitutes']={t:dict(ticker=s,reviewed_not_substantially_identical=True,
                             review_basis='Explicit different-issuer research assumption; not legal approval')
                       for t,s in zip(c['universe'],c['replacement_tickers'])}
    return c


def strategy_config(config,name):
    c=deepcopy(config)
    if name=='index':
        c.update(positions=[dict(ticker=c.get('benchmark','SPY'),side='long',weight=1)],
                 long_exposure_pct=100,short_exposure_pct=0,harvest_enabled=False,
                 manager_pct=c.get('benchmark_manager_pct',0),rebalance_every_sessions=100000)
    elif name=='long_only_di':
        c['positions']=[dict(ticker=p['ticker'],side='long',weight=1) for p in c['positions']]
        c.update(long_exposure_pct=100,short_exposure_pct=0,harvest_enabled=True,
                 manager_pct=c.get('di_manager_pct',.25))
    elif name=='no_harvest':c['harvest_enabled']=False
    elif name=='core_130_30':c['harvest_enabled']=True
    else:raise ValueError('Unknown strategy')
    return c


def comparison(config,data,policy=None,include_no_harvest=False):
    names=['index','long_only_di','core_130_30']+(['no_harvest'] if include_no_harvest else [])
    runs={n:simulate_observed(strategy_config(config,n),data,policy) for n in names}
    base=runs['index']['summary']['terminal_after_tax_wealth']
    for run in runs.values():
        s=run['summary'];s['incremental_wealth_vs_index']=s['terminal_after_tax_wealth']-base
        s['incremental_wealth_vs_benchmark']=s['incremental_wealth_vs_index']
        s['cumulative_total_tax']=s['total_taxes'];s['cumulative_net_costs']=s['total_financing_and_fees_net_rebate']
    return runs


def search_crossings(evaluate,maximum=5000000.,step=250000.):
    """Evaluate a finite grid, refine each sign change, retain root residuals."""
    if not 0<step<=maximum<=100000000:raise ValueError('Invalid break-even search range')
    if maximum/step>1000:raise ValueError('Search grid is too large')
    points=[];amount=0.
    while amount<maximum:
        points.append((amount,evaluate(amount)));amount+=step
    points.append((maximum,evaluate(maximum)))
    roots=[];residuals=[]
    for x,y in points:
        if abs(y)<.01 and (not roots or abs(x-roots[-1])>.01):roots.append(x);residuals.append(y)
    for (lo,a),(hi,b) in zip(points,points[1:]):
        if a*b>=0:continue
        for _ in range(40):
            mid=(lo+hi)/2;value=evaluate(mid)
            if abs(value)<.01:break
            if a*value<0:hi=mid
            else:lo=mid;a=value
        roots.append(mid);residuals.append(value)
    paired=sorted(zip(roots,residuals))
    return dict(status='crossing_found' if roots else 'no_crossing_in_range',
                roots_usd=[x for x,_ in paired],residuals_usd=[y for _,y in paired],
                minimum_usd=0,maximum_usd=maximum,grid_step_usd=step,
                curve=[dict(gain=x,delta=y) for x,y in points],
                limitation='Finite grid can miss a tangency or a narrow crossing; no extrapolation beyond the range.')


def run_observed_study(request,history_provider=None,progress=None):
    from .studies import _history
    req=deepcopy(request);c=deepcopy(req['config']);mode=req['mode']
    source=req.get('data_source','local_cache')
    if source=='local_cache':
        if not CACHE.exists():raise ValueError('Download the local observed dataset with python tools/fetch_market_study.py, or choose Fetch historical prices.')
        req['history']=json.loads(CACHE.read_text(encoding='utf-8'));req['data_source']='uploaded'
    originals=(c.get('universe',[]) if mode=='cohort' else [p['ticker'] for p in c['positions']])
    if not originals or len(set(originals))!=len(originals):raise ValueError('Supply a nonempty unique research universe')
    subs=c.get('substitutes',{})
    if any(t not in subs for t in originals):raise ValueError('Every research stock needs an explicit replacement')
    names=sorted(set(originals+[subs[t]['ticker'] for t in originals]))
    benchmark=c.get('benchmark','SPY');names=[n for n in names if n!=benchmark]+[benchmark]
    data=_history(req,c,names,history_provider or load_history)
    data['metadata']['data_sha256']=history_data_sha(data)
    req.update(engine='historical_lots',history=data,data_source='uploaded')
    result=dict(mode=mode,engine='historical_lots',data_metadata=data['metadata'])
    warnings=[
        'Observed prices; hypothetical trades. This is not manager performance or an actual client tax return.',
        'FIFO lots match same-ticker long purchases and short openings within 30 days before/after losses, including ordinary rebalances and substitute sales. Quantities, deferred losses and replacement basis are recorded.',
        'The research account has no household/IRA/options activity, no simultaneous long/short position in the same security, and no trades for 30 days after final liquidation. Cross-account matching and corporate-relationship determinations require additional data.',
        'Different-issuer substitutes are explicit research assumptions. They preserve invested notional, not identical market or factor exposure.',
        'Prior-close harvest signals execute next close. Scheduled close rebalancing assumes execution at the observed close; bid/ask spreads, market impact and borrow recalls are not observed.',
        'Annual capital tax is paid on the first observed session on/after February 1 of the following year so the December wash window can finish. All outstanding taxes settle at the horizon. This is a timing convention, not the actual estimated-tax calendar.',
        'Outside events enter investor cash at calendar year-end; incremental proceeds equal taxable gain. Client proceeds and original outside basis are separate missing inputs.',
        'Costs, flat tax rates, borrow availability and the maintenance threshold are assumptions. A daily-close maintenance breach liquidates the account; intraday margin and gap execution are not modeled.',
        'SPY observed prices already reflect fund expenses; benchmark manager fee is only an additional entered fee. Long-only DI is an equal-weight harvesting basket of the same selected names, not a calibrated index-tracking product.',
        'Positive dividends use the entered dividend rate; short payments in lieu reduce cash. Ordinary stock short positions closed within 45 days add those payments to closing basis; itemized interest deductions and extraordinary distributions require client review.'
    ]
    if mode=='historical':
        runs=comparison(c,data,include_no_harvest=True)
        result['results']={'harvest':runs['core_130_30'],'no_harvest':runs['no_harvest'],
                           'benchmark':runs['index'],'long_only_di':runs['long_only_di']}
        result['rows']=[dict(strategy=n,**r['summary']) for n,r in result['results'].items()]
        result['harvesting_benefit']=runs['core_130_30']['summary']['terminal_after_tax_wealth']-runs['no_harvest']['summary']['terminal_after_tax_wealth']
    elif mode=='exits':
        policies=[('Full sale',dict(mode='full_sale'))]
        policies += [(f'{n}-year full-portfolio exit',dict(mode='gradual',years=n)) for n in (3,4,5)]
        policies += [('3-year extension reduction + final sale',dict(mode='extension',years=3)),
                     ('Hold until death',dict(mode='death',transfer_tax_cost=req.get('estate_tax_cost',0))),
                     ('Gift with recipient sale',dict(mode='gift',recipient_tax_st_pct=req.get('recipient_tax_st_pct',40),
                          recipient_tax_lt_pct=req.get('recipient_tax_lt_pct',20),transfer_tax_cost=req.get('gift_tax_cost',0)))]
        rows=[];annual=[];policy_runs={};base={}
        for label,policy in policies:
            if progress:progress('Exit: '+label)
            runs=comparison(c,data,policy)
            policy_runs[label]=runs
            for name,run in runs.items():
                s=run['summary']
                if label=='Full sale':base[name]=s['terminal_after_tax_wealth']
                rows.append(dict(policy=label,strategy=name,**s,difference_vs_full_sale=s['terminal_after_tax_wealth']-base[name]))
                annual.extend(dict(policy=label,strategy=name,**r) for r in run['annual'])
        result.update(rows=rows,annual=annual,policy_runs=policy_runs)
        warnings += ['All exit policies use the same historical prices and actual modeled tax lots. Gradual sales withdraw a fraction at the last session of each of the last 3/4/5 calendar years; remaining assets stay invested.',
                     'Death occurs at the horizon: close shorts in the donor account, adjust eligible long shares individually to FMV, then sell. No automatic adjustment of short liabilities. The assumed ordinary eligible property excludes inheritance exceptions.',
                     'Gift occurs at the horizon: close shorts and fund donor debt/taxes before transferring unencumbered long shares. Recipient sale uses each lot\'s carryover gain basis / gift-date FMV loss basis. Donor carryforwards stay with the donor. Wealth is combined family wealth.',
                     'Estate and gift taxes are explicit optional dollar costs, default zero because household estate, exemptions and transfer history are unavailable. The engine does not determine those taxes.']
    elif mode=='one_time':
        year=int(req.get('event_year',c.get('event_year',2021)));character=req.get('character','st')
        if character not in ('st','lt'):raise ValueError('Choose ST or LT')
        memo={}
        def evaluate(amount):
            if amount not in memo:
                v=deepcopy(c);v['outside_gain_events']=[dict(year=year,amount=amount,character=character)]
                memo[amount]={name:run['summary'] for name,run in comparison(v,data).items()}
                if progress:progress('Outside gain: $'+format(amount,',.0f'))
            return memo[amount]
        rows=[]
        for amount in (0.,1e6,3e6,5e6):rows.extend(dict(outside_gain=amount,event_year=year,character=character,strategy=name,**s) for name,s in evaluate(amount).items())
        searches=[]
        for comparator in ('index','long_only_di'):
            def delta(amount):
                r=evaluate(amount);return r['core_130_30']['terminal_after_tax_wealth']-r[comparator]['terminal_after_tax_wealth']
            searches.append(dict(comparator=comparator,event_year=year,character=character,
                                 **search_crossings(delta,float(req.get('search_max',5e6)),float(req.get('search_step',250000)))))
        result.update(rows=rows,searches=searches)
    elif mode=='cohort':
        draws=req.get('samples',100);seed=req.get('seed',4511);nl=req.get('long_count',3);ns=req.get('short_count',3)
        if any(type(x) is not int for x in (draws,seed,nl,ns)) or not 1<=draws<=200 or min(nl,ns)<1 or nl+ns>len(originals):raise ValueError('Invalid random portfolio settings')
        if c.get('universe_kind')!='fixed_research_universe':raise ValueError('Observed random mode requires explicitly labeled fixed research universe; use the separate PIT route for verified index data')
        rng=random.Random(seed);rows=[]
        benchmark_run=simulate_observed(strategy_config(c,'index'),data)
        benchmark_wealth=benchmark_run['summary']['terminal_after_tax_wealth']
        for k in range(draws):
            names=rng.sample(sorted(originals),nl+ns);longs=sorted(names[:nl]);shorts=sorted(names[nl:])
            v=deepcopy(c);v['positions']=[dict(ticker=t,side=side,weight=1) for side,group in [('long',longs),('short',shorts)] for t in group]
            row=dict(sample_id=k+1,long_names=longs,short_names=shorts,seed=seed,status='completed',benchmark_wealth=benchmark_wealth)
            try:
                h=simulate_observed(strategy_config(v,'core_130_30'),data)['summary']
                n=simulate_observed(strategy_config(v,'no_harvest'),data)['summary']
                row.update(after_tax_terminal_wealth=h['terminal_after_tax_wealth'],no_harvest_wealth=n['terminal_after_tax_wealth'],
                           incremental_wealth_vs_benchmark=h['terminal_after_tax_wealth']-benchmark_wealth,
                           harvesting_benefit=h['terminal_after_tax_wealth']-n['terminal_after_tax_wealth'],
                           harvested_losses=h['cumulative_harvested_losses'],wash_loss_deferred=h['wash_loss_deferred'],
                           margin_liquidations=h['margin_liquidations'],max_identity_error=max(h['max_wealth_identity_error'],h['max_capital_identity_error']))
            except ValueError as error:
                if not any(s in str(error).lower() for s in ('insolven','negative family wealth')):raise
                row.update(status='failed',error=str(error),after_tax_terminal_wealth=None,
                           incremental_wealth_vs_benchmark=None,harvesting_benefit=None)
            rows.append(row)
            if progress:progress(f'Portfolio {k+1}/{draws}: '+row['status'])
        complete=[r for r in rows if r['status']=='completed']
        delta=sorted(r['incremental_wealth_vs_benchmark'] for r in complete)
        def quantile(p):
            if not delta:return None
            k=(len(delta)-1)*p;i=int(k);return delta[i]*(1-(k-i))+delta[min(i+1,len(delta)-1)]*(k-i)
        result.update(rows=rows,draws=draws,seed=seed,formation_date=c['start_date'],failed_count=draws-len(complete),
                      benchmark_win_fraction=sum(x>0 for x in delta)/draws,p05_delta=quantile(.05),median_delta=quantile(.5),p95_delta=quantile(.95))
        warnings += [c.get('universe_note','Fixed research universe, not historical index membership.'),
                     'All sampled portfolios remain in the report, including failures. Quantiles use completed runs; the win fraction uses all requested draws, counting failures as not winning. A fixed seed controls reproducibility, not a probability forecast.']
    else:raise ValueError('Unknown observed study')
    synthetic='synthetic' in json.dumps(data['metadata']).lower()
    result.update(data_label='SYNTHETIC TEST of historical lot engine' if synthetic else 'Observed market prices · hypothetical strategy',warnings=warnings,request=req)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'p107').glob('*.py'))}
    result['metadata']=dict(source_sha256=hashes,request_sha256=hashlib.sha256(json.dumps(req,sort_keys=True,allow_nan=False).encode()).hexdigest())
    result['run_id']=hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()[:20]
    return result
