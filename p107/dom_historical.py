"""Experimental 130/30 historical lot ledger with substitution during a cooldown.

Research approximation only, NOT a determination of wash-sale deductibility.
An advisor/tax professional must independently review substantially identical
securities, cross-account trades, options, short sales and broker tax reporting.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from math import isfinite

from .market_data import normalize_ticker
from .taxes import settle


def historical_13030(config, data):
    """Use a supplied split-consistent daily dataset; do not select securities for the user.

    config: initial_cash, positions [{ticker,side,weight}], substitutes {ticker:
    {ticker,reviewed_not_substantially_identical}}, optional percent annual fees,
    rebalance_every_sessions, cooldown_days, harvest_threshold_pct and
    outside_gain_events [{year,amount,character}].

    Splits/dividends use the same nominal price conventions as market_data.py.
    """
    cash0 = float(config['initial_cash'])
    if not isfinite(cash0) or cash0 <= 0:
        raise ValueError('Positive finite initial_cash required')
    specs = config.get('positions', [])
    if not specs:
        raise ValueError('Supply positions')
    sides = {'long': [], 'short': []}
    used = set()
    for raw in specs:
        ticker = normalize_ticker(raw['ticker'])
        side = raw['side']
        weight = float(raw['weight'])
        if ticker in used or side not in sides or not isfinite(weight) or weight <= 0:
            raise ValueError('Unique valid stocks and positive weights required')
        used.add(ticker)
        sides[side].append((ticker, weight))
    harvesting = config.get('harvest_enabled', True)
    if type(harvesting) is not bool:
        raise ValueError('harvest_enabled must be true or false')
    if not sides['long'] or (config.get('short_exposure_pct', 30) > 0 and not sides['short']):
        raise ValueError('Supply positions for every nonzero exposure')
    subs = config.get('substitutes', {})
    if not isinstance(subs, dict):
        raise ValueError('substitutes must be a security-review mapping')
    replacements = {}
    for original in used:
        if not harvesting:
            continue
        desc = subs.get(original)
        if not isinstance(desc, dict) or desc.get('reviewed_not_substantially_identical') is not True:
            raise ValueError(f'{original} requires an expressly reviewed non-identical substitute assumption')
        alternate = normalize_ticker(desc.get('ticker'))
        if alternate in used or alternate == original or alternate in replacements.values():
            raise ValueError('Substitutes must be unique, disjoint from all starting names')
        replacements[original] = alternate
    if len(data.get('dates', [])) < 2:
        raise ValueError('At least two historical sessions required')
    dates = [date.fromisoformat(x) for x in data['dates']]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError('Dates must be strictly increasing')
    start = date.fromisoformat(config.get('start_date', dates[0].isoformat()))
    end = date.fromisoformat(config.get('end_date', dates[-1].isoformat()))
    if start > end or dates[0] < start or dates[-1] > end:
        raise ValueError('History dates must lie within the requested start/end dates')
    all_tickers = used | set(replacements.values())
    for group in ('prices', 'splits', 'dividends'):
        if not isinstance(data.get(group), dict):
            raise ValueError('Dataset missing '+group)
        for ticker in all_tickers:
            values = data[group].get(ticker)
            if not isinstance(values, list) or len(values) != len(dates):
                raise ValueError(f'{ticker} lacks complete {group} series')
            if any(not isinstance(x, (int,float)) or not isfinite(x) or
                   x < (1e-12 if group == 'prices' else 0) for x in values):
                raise ValueError(f'{ticker} has invalid {group}')
    rebalance_every = config.get('rebalance_every_sessions', 21)
    cooldown = config.get('cooldown_days', 30)
    min_hold = config.get('minimum_holding_days', 31)
    if type(rebalance_every) is not int or rebalance_every < 1:
        raise ValueError('Invalid rebalance period')
    if type(cooldown) is not int or cooldown < 30 or type(min_hold) is not int or min_hold < 31:
        raise ValueError('A conservative minimum of 30 calendar-day window is required')
    pct = {}
    for key, default in [('long_exposure_pct',130),('short_exposure_pct',30),
                          ('financing_pct',5),('borrow_pct',1),('rebate_pct',0),
                          ('manager_pct',0.4),('advisor_pct',0),('transaction_pct',0.05),
                          ('tax_st_pct',40),('tax_lt_pct',20),
                          ('ordinary_tax_pct',40),('dividend_tax_pct',20),
                          ('harvest_threshold_pct',10)]:
        val=float(config.get(key,default))
        if not isfinite(val) or not 0 <= val < 1000:
            raise ValueError('Invalid parameter '+key)
        pct[key]=val/100
    if abs(pct['long_exposure_pct']-pct['short_exposure_pct']-1)>1e-12:
        raise ValueError('This engine requires 100% net target exposure')
    if pct['transaction_pct'] * (pct['long_exposure_pct'] + pct['short_exposure_pct']) >= .9:
        raise ValueError('Transaction cost too large for a solvent rebalance')
    if pct['tax_st_pct']>=1 or pct['tax_lt_pct']>=1 or pct['ordinary_tax_pct']>=1 or pct['dividend_tax_pct']>=1:
        raise ValueError('Tax rates must be less than 100%')
    buckets=defaultdict(float)
    carry_st=carry_lt=0.
    outside = defaultdict(lambda: defaultdict(float))
    for event in config.get('outside_gain_events', []):
        year, value, character = event['year'], float(event['amount']), event['character']
        if type(year) is not int or character not in ('st','lt') or not isfinite(value) or value<0:
            raise ValueError('Invalid external gain event')
        if year < dates[0].year or year > dates[-1].year:
            raise ValueError('Outside event outside history')
        outside[year][character]+=value
    positions={}
    for side, entries in sides.items():
        scale=sum(weight for _,weight in entries)
        for ticker,weight in entries:
            positions[ticker]={'side':side,'weight':weight/scale,'active':ticker,
                               'sub':replacements.get(ticker),'lots':[],'locked_until':None,
                               'pending':False}
    cash=cash0; debt=0.; collateral=0.; side_cash=0.
    trades=[]; daily=[]; annual=[]
    total_costs=total_tax=total_harvest=0.; tax_rebate=0.
    dividend_tax = dividends_net = capital_pnl = outside_received = realized_pnl = 0.
    cost_parts=defaultdict(float)
    def fund():
        nonlocal cash,debt
        if cash<0: debt-=cash;cash=0.
        if cash>0 and debt>0:
            reduction=min(cash,debt);cash-=reduction;debt-=reduction
    def price(symbol,i):return float(data['prices'][symbol][i])
    def market(root,i):
        p=positions[root]
        return sum(l['qty'] for l in p['lots'])*price(p['active'],i)
    def equity(i):
        return cash+collateral-debt+sum(market(root,i)*(1 if p['side']=='long' else -1)
                                         for root,p in positions.items())
    def transaction(root,delta,i,reason):
        nonlocal cash,collateral,total_costs,total_harvest,realized_pnl
        if abs(delta)<1e-10:return
        p=positions[root];symbol=p['active'];side=p['side'];px=price(symbol,i)
        q=abs(delta);notional=q*px
        if delta>0:
            if side=='long':cash-=notional
            else:collateral+=notional
            p['lots'].append({'qty':q,'basis':px,'opened':dates[i], 'collateral':notional if side=='short' else 0.})
        else:
            before=sum(l['qty'] for l in p['lots'])
            if q>before+1e-7:raise ArithmeticError('Cannot close more than current position')
            remaining=q
            while remaining>1e-9:
                if not p['lots']:raise ArithmeticError('Missing tax lot')
                lot=p['lots'][0]
                take=min(remaining,lot['qty'])
                pnl=take*(px-lot['basis'])*(1 if side=='long' else -1)
                realized_pnl += pnl
                character='lt' if side=='long' and (dates[i]-lot['opened']).days>365 else 'st'
                buckets[('gain_' if pnl>=0 else 'loss_')+character]+=abs(pnl)
                if reason=='harvest' and pnl<0:total_harvest-=pnl
                if side=='long':cash+=take*px
                else:
                    release=lot['collateral']*take/lot['qty']
                    collateral-=release;cash+=release-take*px
                    lot['collateral']-=release
                lot['qty']-=take;remaining-=take
                if lot['qty']<1e-9:p['lots'].pop(0)
        fee=notional*pct['transaction_pct']
        cash-=fee;total_costs+=fee;cost_parts['transactions']+=fee;fund()
        trades.append({'date':dates[i].isoformat(),'root':root,'ticker':symbol,'side':side,
                       'action':'increase' if delta>0 else 'reduce','reason':reason,
                       'shares':q,'price':px,'fee':fee})
    def rebalance(i,reason):
        e=equity(i)
        if e<=0:raise ValueError('Nonpositive account equity')
        # Solve targets on NAV AFTER all execution charges, not before fees.
        def fee_for(nav):
            return sum(abs(nav*pct[p['side']+'_exposure_pct']*p['weight'] - market(root,i))
                       for root,p in positions.items()) * pct['transaction_pct']
        lo, hi = 0., e
        if fee_for(0) >= e:
            raise ValueError('Insufficient equity for rebalancing costs')
        for _ in range(60):
            mid = (lo+hi)/2
            if mid + fee_for(mid) > e: hi = mid
            else: lo = mid
        target_nav = (lo+hi)/2
        changes={}
        for root,p in positions.items():
            target=target_nav*pct[p['side']+'_exposure_pct']*p['weight']/price(p['active'],i)
            changes[root]=target-sum(x['qty'] for x in p['lots'])
        # Close risk before buying new exposure; this keeps collateral segregated.
        for root in sorted(changes):
            if changes[root]<-1e-9:transaction(root,changes[root],i,reason)
        for root in sorted(changes):
            if changes[root]>1e-9:transaction(root,changes[root],i,reason)
    def switch(root,i,to_sub,reason):
        p=positions[root]
        value=market(root,i)
        symbol=p['active']
        qty=sum(l['qty'] for l in p['lots'])
        if qty>0:transaction(root,-qty,i,reason)
        p['active']=p['sub'] if to_sub else root
        if to_sub:p['locked_until']=dates[i]+timedelta(days=cooldown)
        else:p['locked_until']=None
        transaction(root,value/price(p['active'],i),i,'substitute_open' if to_sub else 'original_resume')
        if reason=='harvest':p['pending']=False
        trades.append({'date':dates[i].isoformat(),'root':root,'ticker':symbol,
                       'side':p['side'],'action':'switch','reason':reason,
                       'shares':0.,'price':0.,'fee':0.})
    rebalance(0,'initial_13030')
    for i,when in enumerate(dates):
        final=i==len(dates)-1
        prior_tax=total_tax+tax_rebate+dividend_tax
        prior_cost=total_costs if i else 0.;prior_harvest=total_harvest
        if i:
            d=(when-dates[i-1]).days/365
            prior_nav=equity(i-1)
            prior_short=sum(market(root,i-1) for root,p in positions.items() if p['side']=='short')
            interest=debt*pct['financing_pct']*d
            borrow=prior_short*pct['borrow_pct']*d
            rebate=collateral*pct['rebate_pct']*d
            fee=max(prior_nav,0.)*pct['manager_pct']*d
            advisor=max(prior_nav,0.)*pct['advisor_pct']*d
            rebate_tax=max(rebate,0)*pct['ordinary_tax_pct']
            cash-=interest+borrow+fee+advisor-rebate+rebate_tax
            tax_rebate+=rebate_tax
            total_costs+=interest+borrow+fee+advisor-rebate
            for name,value in (('financing',interest),('borrow',borrow),('management',fee),('advisor',advisor),('rebate',rebate)):
                cost_parts[name]+=value
            fund()
            for root,p in positions.items():
                factor=data['splits'][p['active']][i] or 1.
                before_qty=sum(l['qty'] for l in p['lots'])
                capital_pnl += before_qty*(factor*price(p['active'],i)-price(p['active'],i-1))*(1 if p['side']=='long' else -1)
                if factor!=1:
                    for lot in p['lots']:
                        lot['qty']*=factor;lot['basis']/=factor
                qty=sum(l['qty'] for l in p['lots'])
                div=qty*data['dividends'][p['active']][i]*(1 if p['side']=='long' else -1)
                div_tax=max(div,0)*pct['dividend_tax_pct']
                dividends_net+=div;dividend_tax+=div_tax
                cash+=div-div_tax
                fund()
            switched=False
            for root,p in positions.items():
                if final: continue
                if p['pending'] and p['active']==root:
                    switch(root,i,True,'harvest')
                    switched=True
                elif p['active']!=root and when>p['locked_until']:
                    switch(root,i,False,'cooldown_expired')
                    switched=True
            if not final and (switched or i%rebalance_every==0):
                rebalance(i,'rebalance_after_switch' if switched else 'scheduled_rebalance')
        year_end=final or dates[i+1].year!=when.year
        if final:
            for root,p in positions.items():
                qty=sum(l['qty'] for l in p['lots'])
                if qty>0:transaction(root,-qty,i,'final_liquidation')
        if year_end:
            taxable_outside=outside[when.year]
            proceeds=taxable_outside['st']+taxable_outside['lt']
            outside_received+=proceeds
            side_cash+=proceeds
            settled=settle(buckets['gain_st']+taxable_outside['st'],
                           buckets['gain_lt']+taxable_outside['lt'],
                           buckets['loss_st'],buckets['loss_lt'],carry_st,carry_lt,
                           pct['tax_st_pct'],pct['tax_lt_pct'])
            side_cash-=settled.tax
            if side_cash < 0:
                cash+=side_cash;side_cash=0.;fund()
            total_tax+=settled.tax
            carry_st,carry_lt=settled.carry_st,settled.carry_lt
            annual.append({'year':when.year,'realized_st_gain':buckets['gain_st'],
                          'realized_lt_gain':buckets['gain_lt'],'realized_st_loss':buckets['loss_st'],
                          'realized_lt_loss':buckets['loss_lt'],'outside_st_gain':taxable_outside['st'],
                          'outside_lt_gain':taxable_outside['lt'],'tax':settled.tax,
                          'loss_used_st':settled.loss_used_st,'loss_used_lt':settled.loss_used_lt,
                          'carry_st':carry_st,'carry_lt':carry_lt})
            buckets=defaultdict(float)
        if not final and harvesting:
            for root,p in positions.items():
                if p['active']!=root or p['pending'] or not p['lots']:continue
                oldest=min(x['opened'] for x in p['lots'])
                # Prior-close signal, executed next close; do not buy this same
                # ticker inside its subsequent 30-day cooling-off interval.
                if (when-oldest).days<min_hold:continue
                if any((when-l['opened']).days<=30 for l in p['lots']):continue
                cost=sum(x['qty']*x['basis'] for x in p['lots'])
                pnl=market(root,i)-cost
                if p['side']=='short':pnl=-pnl
                if cost and pnl/cost<=-pct['harvest_threshold_pct']:
                    p['pending']=True
        e=equity(i)
        if e<=0:raise ValueError('Insolvent or unsupported margin event')
        total_wealth=e+side_cash
        wealth_error=total_wealth-(cash0+outside_received+capital_pnl+dividends_net-total_costs-total_tax-tax_rebate-dividend_tax)
        embedded=sum((market(root,i)-sum(l['qty']*l['basis'] for l in p['lots']))*(1 if p['side']=='long' else -1)
                     for root,p in positions.items())
        capital_error=realized_pnl+embedded-capital_pnl
        if max(abs(wealth_error),abs(capital_error))>max(.0001,cash0*1e-10):
            raise ArithmeticError('Historical accounting identity failed')
        long_mv=sum(market(root,i) for root,p in positions.items() if p['side']=='long')
        short_mv=sum(market(root,i) for root,p in positions.items() if p['side']=='short')
        daily.append({'date':when.isoformat(),'equity':e,'long_mv':long_mv,'short_mv':short_mv,
                      'long_pct':100*long_mv/e,'short_pct':100*short_mv/e,
                      'free_cash':cash,'debt':debt,'short_collateral':collateral,
                      'investor_side_cash':side_cash,'total_investor_wealth':total_wealth,
                      'embedded_gain':embedded,'wealth_identity_error':wealth_error,
                      'capital_identity_error':capital_error,
                      'cost_this_session':total_costs-prior_cost,'tax_this_session':total_tax+tax_rebate+dividend_tax-prior_tax,
                      'harvested_loss_this_session':total_harvest-prior_harvest,
                      'active_substitutes':[p['active'] for p in positions.values() if p['active'] in replacements.values()]})
    summary={'initial_cash':cash0,'terminal_after_tax_wealth':equity(len(dates)-1)+side_cash,
             'cumulative_harvested_losses':total_harvest,'total_capital_taxes':total_tax,
             'total_financing_and_fees_net_rebate':total_costs,
             'cost_breakdown':dict(cost_parts),'remaining_carry_st':carry_st,
             'outside_gain_proceeds':outside_received,'cumulative_price_pnl':capital_pnl,
             'cumulative_net_dividends':dividends_net,'dividend_taxes':dividend_tax,
             'rebate_taxes':tax_rebate,'total_taxes':total_tax+dividend_tax+tax_rebate,
             'harvest_enabled':harvesting,
             'max_wealth_identity_error':max(abs(r['wealth_identity_error']) for r in daily),
             'max_capital_identity_error':max(abs(r['capital_identity_error']) for r in daily),
             'remaining_carry_lt':carry_lt,'target_long_pct':100*pct['long_exposure_pct'],
             'target_short_pct':100*pct['short_exposure_pct'],
             'substitute_switches':sum(t['reason']=='harvest' and t['action']=='switch' for t in trades),
             'wash_sale_status':'NOT VERIFIED; mapped substitutes are user-reviewed assumptions'}
    return {'summary':summary,'daily':daily,'annual':annual,'trades':trades,
            'metadata':{'source':data.get('metadata',{}),'mode':'rebalance_with_substitution',
                        'rebalancing_sessions':rebalance_every,'cooldown_days':cooldown,
                        'limits':['One lot per purchase; FIFO on closing; no cross-account wash test.',
                                  'Single daily close execution with close-based rebalance is idealized.',
                                  'No borrow recalls, margin maintenance, spreads, market impact or estate tax.',
                                  'Short holding character treated as ST proxy; client-specific tax review required.']}}


def historical_comparison(config, data):
    """Matched outside cash, costs and prices; isolate harvesting and stock selection."""
    c = deepcopy(config)
    c['harvest_enabled'] = True
    harvest = historical_13030(c, data)
    c['harvest_enabled'] = False
    no_harvest = historical_13030(c, data)
    c['positions'] = [dict(ticker=normalize_ticker(c.get('benchmark','SPY')),side='long',weight=1)]
    c['long_exposure_pct'], c['short_exposure_pct'] = 100, 0
    c['manager_pct'] = config.get('benchmark_manager_pct', .03)
    c['substitutes'] = {}
    # A passive benchmark only buys at entry and sells at exit.
    c['rebalance_every_sessions'] = len(data['dates']) + 1
    benchmark = historical_13030(c, data)
    results = {'harvest':harvest, 'no_harvest':no_harvest, 'benchmark':benchmark}
    base = benchmark['summary']['terminal_after_tax_wealth']
    for result in results.values():
        result['summary']['incremental_wealth_vs_benchmark'] = result['summary']['terminal_after_tax_wealth'] - base
    return dict(results=results,
                harvesting_benefit=harvest['summary']['terminal_after_tax_wealth']-no_harvest['summary']['terminal_after_tax_wealth'],
                benchmark=config.get('benchmark','SPY'))
