"""Experimental 130/30 historical lot ledger with substitution during a cooldown.

Research approximation only, NOT a determination of wash-sale deductibility.
An advisor/tax professional must independently review substantially identical
securities, cross-account trades, options, short sales and broker tax reporting.
"""
from collections import defaultdict
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
    if not specs or len(specs) < 2:
        raise ValueError('Supply long and short positions')
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
    if not all(sides.values()):
        raise ValueError('At least one long and short position required')
    subs = config.get('substitutes', {})
    if not isinstance(subs, dict):
        raise ValueError('substitutes must be a security-review mapping')
    replacements = {}
    for original in used:
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
                          ('manager_pct',0.4),('transaction_pct',0.05),
                          ('tax_st_pct',40),('tax_lt_pct',20),
                          ('ordinary_tax_pct',40),('dividend_tax_pct',20),
                          ('harvest_threshold_pct',10)]:
        val=float(config.get(key,default))
        if not isfinite(val) or not 0 <= val < 1000:
            raise ValueError('Invalid parameter '+key)
        pct[key]=val/100
    if abs(pct['long_exposure_pct']-pct['short_exposure_pct']-1)>1e-12:
        raise ValueError('This engine requires 100% net target exposure')
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
                               'sub':replacements[ticker],'lots':[],'locked_until':None,
                               'pending':False}
    cash=cash0; debt=0.; collateral=0.
    trades=[]; daily=[]; annual=[]
    total_costs=total_tax=total_harvest=0.; tax_rebate=0.
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
        nonlocal cash,collateral,total_costs,total_harvest
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
        changes={}
        for root,p in positions.items():
            target=e*pct[p['side']+'_exposure_pct']*p['weight']/price(p['active'],i)
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
        prior_tax=total_tax;prior_cost=total_costs;prior_harvest=total_harvest
        if i:
            d=(when-dates[i-1]).days/365
            prior_nav=equity(i-1)
            prior_short=sum(market(root,i-1) for root,p in positions.items() if p['side']=='short')
            interest=debt*pct['financing_pct']*d
            borrow=prior_short*pct['borrow_pct']*d
            rebate=collateral*pct['rebate_pct']*d
            fee=max(prior_nav,0.)*pct['manager_pct']*d
            rebate_tax=max(rebate,0)*pct['ordinary_tax_pct']
            cash-=interest+borrow+fee-rebate+rebate_tax
            tax_rebate+=rebate_tax
            total_costs+=interest+borrow+fee-rebate
            for name,value in (('financing',interest),('borrow',borrow),('management',fee),('rebate',rebate)):
                cost_parts[name]+=value
            fund()
            for root,p in positions.items():
                factor=data['splits'][p['active']][i] or 1.
                if factor!=1:
                    for lot in p['lots']:
                        lot['qty']*=factor;lot['basis']/=factor
                qty=sum(l['qty'] for l in p['lots'])
                div=qty*data['dividends'][p['active']][i]*(1 if p['side']=='long' else -1)
                cash+=div-max(div,0)*pct['dividend_tax_pct']
                fund()
            switched=False
            for root,p in positions.items():
                if p['pending'] and p['active']==root:
                    switch(root,i,True,'harvest')
                    switched=True
                elif p['active']!=root and when>p['locked_until']:
                    switch(root,i,False,'cooldown_expired')
                    switched=True
            if switched or i%rebalance_every==0:
                rebalance(i,'rebalance_after_switch' if switched else 'scheduled_rebalance')
        final=i==len(dates)-1
        year_end=final or dates[i+1].year!=when.year
        if final:
            for root,p in positions.items():
                qty=sum(l['qty'] for l in p['lots'])
                if qty>0:transaction(root,-qty,i,'final_liquidation')
        if year_end:
            taxable_outside=outside[when.year]
            cash+=taxable_outside['st']+taxable_outside['lt'];fund()
            settled=settle(buckets['gain_st']+taxable_outside['st'],
                           buckets['gain_lt']+taxable_outside['lt'],
                           buckets['loss_st'],buckets['loss_lt'],carry_st,carry_lt,
                           pct['tax_st_pct'],pct['tax_lt_pct'])
            cash-=settled.tax;fund();total_tax+=settled.tax
            carry_st,carry_lt=settled.carry_st,settled.carry_lt
            annual.append({'year':when.year,'realized_st_gain':buckets['gain_st'],
                          'realized_lt_gain':buckets['gain_lt'],'realized_st_loss':buckets['loss_st'],
                          'realized_lt_loss':buckets['loss_lt'],'outside_st_gain':taxable_outside['st'],
                          'outside_lt_gain':taxable_outside['lt'],'tax':settled.tax,
                          'carry_st':carry_st,'carry_lt':carry_lt})
            buckets=defaultdict(float)
        if not final:
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
        long_mv=sum(market(root,i) for root,p in positions.items() if p['side']=='long')
        short_mv=sum(market(root,i) for root,p in positions.items() if p['side']=='short')
        daily.append({'date':when.isoformat(),'equity':e,'long_mv':long_mv,'short_mv':short_mv,
                      'long_pct':100*long_mv/e,'short_pct':100*short_mv/e,
                      'free_cash':cash,'debt':debt,'short_collateral':collateral,
                      'cost_this_session':total_costs-prior_cost,'tax_this_session':total_tax-prior_tax,
                      'harvested_loss_this_session':total_harvest-prior_harvest,
                      'active_substitutes':[p['active'] for p in positions.values() if p['active'] in replacements.values()]})
    summary={'initial_cash':cash0,'terminal_after_tax_wealth':equity(len(dates)-1),
             'cumulative_harvested_losses':total_harvest,'total_capital_taxes':total_tax,
             'total_financing_and_fees_net_rebate':total_costs,
             'cost_breakdown':dict(cost_parts),'remaining_carry_st':carry_st,
             'remaining_carry_lt':carry_lt,'target_long_pct':100*pct['long_exposure_pct'],
             'target_short_pct':100*pct['short_exposure_pct'],
             'substitute_switches':sum(t['reason']=='harvest' for t in trades),
             'wash_sale_status':'NOT VERIFIED; mapped substitutes are user-reviewed assumptions'}
    return {'summary':summary,'daily':daily,'annual':annual,'trades':trades,
            'metadata':{'source':data.get('metadata',{}),'mode':'rebalance_with_substitution',
                        'rebalancing_sessions':rebalance_every,'cooldown_days':cooldown,
                        'limits':['One lot per purchase; FIFO on closing; no cross-account wash test.',
                                  'Single daily close execution with close-based rebalance is idealized.',
                                  'No borrow recalls, margin maintenance, spreads, market impact or estate tax.',
                                  'Short holding character treated as ST proxy; client-specific tax review required.']}}
