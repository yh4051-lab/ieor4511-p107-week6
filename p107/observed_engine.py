"""Historical daily research with FIFO tax lots, wash deferrals and exit policies.

Observed prices do not make the hypothetical holdings, financing, tax rates or
execution rules actual manager results. All asset selection is supplied before
the run. The legacy engine remains available for prior-export reproduction.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from math import isfinite

from .lot_accounting import LotBook
from .market_data import normalize_ticker
from .taxes import settle


def simulate_observed(config,data,policy=None):
    c=deepcopy(config);policy=policy or {'mode':'full_sale'}
    mode=policy['mode']
    if mode not in ('full_sale','gradual','extension','death','gift'):raise ValueError('Unknown historical exit')
    initial=float(c['initial_cash'])
    if not isfinite(initial) or initial<=0:raise ValueError('Positive initial cash required')
    dates=[date.fromisoformat(d) for d in data['dates']]
    if len(dates)<2 or any(a>=b for a,b in zip(dates,dates[1:])):raise ValueError('Ordered history required')
    if dates[0]<date.fromisoformat(c['start_date']) or dates[-1]>date.fromisoformat(c['end_date']):raise ValueError('History outside requested period')
    rates={}
    for key,default in [('long_exposure_pct',130),('short_exposure_pct',30),('manager_pct',.4),
                        ('advisor_pct',.1),('financing_pct',5),('borrow_pct',1),('rebate_pct',0),
                        ('transaction_pct',.05),('tax_st_pct',40),('tax_lt_pct',20),
                        ('ordinary_tax_pct',40),('dividend_tax_pct',20),('harvest_threshold_pct',8),
                        ('maintenance_equity_to_gross_pct',30)]:
        value=float(c.get(key,default))/100
        if not isfinite(value) or not 0<=value<10:raise ValueError('Invalid '+key)
        rates[key]=value
    for k in ('tax_st_pct','tax_lt_pct','ordinary_tax_pct','dividend_tax_pct'):
        if rates[k]>=1:raise ValueError('Tax rate must be below 100%')
    if abs(rates['long_exposure_pct']-rates['short_exposure_pct']-1)>1e-10:raise ValueError('Net exposure must be 100%')
    rebalance=c.get('rebalance_every_sessions',21)
    if type(rebalance) is not int or rebalance<1:raise ValueError('Positive integer rebalance period required')
    cooldown=c.get('cooldown_days',30)
    if type(cooldown) is not int or cooldown<30:raise ValueError('Cooldown must be at least 30 calendar days')
    harvesting=c.get('harvest_enabled',True)
    roots={};substitutes=c.get('substitutes',{})
    for row in c['positions']:
        ticker=normalize_ticker(row['ticker']);side=row['side'];weight=float(row['weight'])
        if ticker in roots or side not in ('long','short') or not isfinite(weight) or weight<=0:raise ValueError('Invalid positions')
        sub=substitutes.get(ticker)
        if harvesting and (not sub or not sub.get('reviewed_not_substantially_identical')):raise ValueError('Explicit replacement assumption required for '+ticker)
        roots[ticker]=dict(side=side,weight=weight,active=ticker,sub=sub['ticker'] if sub else None,
                           locked_until=None,pending=False)
    all_names=list(roots)+[r['sub'] for r in roots.values() if harvesting]
    if len(set(all_names))!=len(all_names):raise ValueError('Original and replacement securities must be unique and disjoint')
    for side in ('long','short'):
        total=sum(r['weight'] for r in roots.values() if r['side']==side)
        if rates[side+'_exposure_pct'] and not total:raise ValueError('Missing '+side+' book')
        for r in roots.values():
            if r['side']==side:r['weight']/=total
    for group in ('prices','splits','dividends'):
        for ticker in all_names:
            values=data[group].get(ticker)
            if not isinstance(values,list) or len(values)!=len(dates):raise ValueError('Missing '+group+' for '+ticker)
            if any(not isinstance(x,(int,float)) or not isfinite(x) or x<(1e-12 if group=='prices' else 0) for x in values):raise ValueError('Invalid '+group)
    years=sorted({d.year for d in dates});last_by_year={y:max(i for i,d in enumerate(dates) if d.year==y) for y in years}
    stages=int(policy.get('years',3))
    if mode in ('gradual','extension') and (stages not in (3,4,5) or len(years)<stages):raise ValueError('Staged exit needs 3, 4 or 5 observed calendar years')
    exit_years=years[-stages:]
    outside=defaultdict(lambda:dict(st=0.,lt=0.))
    for event in c.get('outside_gain_events',[]):
        y=event['year'];amount=float(event['amount']);char=event['character']
        if y not in years or char not in ('st','lt') or not isfinite(amount) or amount<0:raise ValueError('Invalid outside gain')
        outside[y][char]+=amount
    book=LotBook();cash=initial;debt=collateral=side_cash=0.
    costs=defaultdict(float);taxes=defaultdict(float)
    carry_st=carry_lt=0.;settled_years=set();received_years=set()
    pnl=dividends=outside_received=harvested=0.
    daily=[];annual=[];trades=[];events=[];closed=False;basis_adjustment=0.
    def px(t,i):return float(data['prices'][t][i])
    def mv(root,i):
        r=roots[root];return book.quantity(r['active'],r['side'])*px(r['active'],i)
    def equity(i):return cash+collateral-debt+sum(mv(t,i)*(1 if r['side']=='long' else -1) for t,r in roots.items())
    def fund():
        nonlocal cash,debt
        if cash<0:debt-=cash;cash=0.
        if cash>0 and debt>0:
            pay=min(cash,debt);cash-=pay;debt-=pay
    def charge(amount):
        nonlocal side_cash,cash
        use=min(side_cash,amount);side_cash-=use;cash-=amount-use;fund()
    def trade(root,delta,i,reason):
        nonlocal cash,collateral,harvested
        if abs(delta)<1e-8:return
        r=roots[root];t=r['active'];side=r['side'];price=px(t,i);qty=abs(delta)
        fee=qty*price*rates['transaction_pct']
        if delta>0:
            if side=='long':cash-=qty*price
            else:collateral+=qty*price
            book.open(t,side,qty,price,dates[i],fee/qty)
        else:
            records=book.close(t,side,qty,price,dates[i],reason,fee/qty)
            if side=='long':cash+=qty*price
            else:
                released=sum(rec['shares']*price+rec['economic_pnl'] for rec in records)
                collateral-=released;cash+=released-qty*price
            if reason=='harvest':harvested+=sum(max(0,-rec['economic_pnl']) for rec in records)
        costs['transactions']+=fee;cash-=fee;fund()
        trades.append(dict(date=dates[i].isoformat(),root=root,ticker=t,side=side,
                           action='increase' if delta>0 else 'reduce',reason=reason,shares=qty,price=price,fee=fee))
    def target_rebalance(i,reason):
        nav=equity(i)
        if nav<=0:raise ValueError('Account is insolvent before rebalance')
        extension=rates['short_exposure_pct']
        if mode=='extension' and dates[i].year in exit_years:
            extension*=max(0,1-(exit_years.index(dates[i].year)+1)/stages)
        weights={t:r['weight']*((1+extension) if r['side']=='long' else extension) for t,r in roots.items()}
        def fee_at(v):return sum(abs(v*weights[t]-mv(t,i)) for t in roots)*rates['transaction_pct']
        lo=0.;hi=nav
        if fee_at(0)>=nav:raise ValueError('Trading costs exceed equity')
        for _ in range(45):
            mid=(lo+hi)/2
            if mid+fee_at(mid)>nav:hi=mid
            else:lo=mid
        changes={t:(lo+hi)/2*weights[t]/px(r['active'],i)-book.quantity(r['active'],r['side']) for t,r in roots.items()}
        for sign in (-1,1):
            for t in sorted(roots):
                if changes[t]*sign>1e-8:trade(t,changes[t],i,reason)
    def switch(root,i,to_sub):
        r=roots[root];notional=mv(root,i)
        trade(root,-book.quantity(r['active'],r['side']),i,'harvest' if to_sub else 'replacement_exit')
        r['active']=r['sub'] if to_sub else root
        r['locked_until']=dates[i]+timedelta(days=cooldown) if to_sub else None;r['pending']=False
        trade(root,notional/px(r['active'],i),i,'replacement_entry' if to_sub else 'original_resume')
    def tax_preview(through_year):
        st,lt=carry_st,carry_lt;rows=[]
        for y in years:
            if y>through_year or y in settled_years:continue
            b=book.buckets(y);ext=outside[y]
            result=settle(b['gain_st']+ext['st'],b['gain_lt']+ext['lt'],b['loss_st'],b['loss_lt'],st,lt,rates['tax_st_pct'],rates['tax_lt_pct'])
            rows.append((y,b,result));st,lt=result.carry_st,result.carry_lt
        return rows
    def pay_taxes(i,through_year):
        nonlocal carry_st,carry_lt
        for y,b,result in tax_preview(through_year):
            charge(result.tax);taxes['capital']+=result.tax;settled_years.add(y)
            carry_st,carry_lt=result.carry_st,result.carry_lt
            annual.append(dict(year=y,payment_date=dates[i].isoformat(),realized_st_gain=b['gain_st'],
                               realized_lt_gain=b['gain_lt'],realized_st_loss=b['loss_st'],realized_lt_loss=b['loss_lt'],
                               outside_st_gain=outside[y]['st'],outside_lt_gain=outside[y]['lt'],tax=result.tax,
                               loss_used_st=result.loss_used_st,loss_used_lt=result.loss_used_lt,
                               carry_st=carry_st,carry_lt=carry_lt))
    def close_fraction(i,fraction,reason):
        nonlocal cash,side_cash
        before=equity(i);cost_before=costs['transactions']
        for t,r in roots.items():trade(t,-book.quantity(r['active'],r['side'])*fraction,i,reason)
        released=max(0,before*fraction-(costs['transactions']-cost_before))
        cash-=released;side_cash+=released;fund()
        events.append(dict(date=dates[i].isoformat(),event=reason,fraction=fraction,net_withdrawal=released))
    target_rebalance(0,'initial_allocation')
    for i,when in enumerate(dates):
        final=i==len(dates)-1;year_end=i==last_by_year[when.year]
        if i:
            elapsed=(when-dates[i-1]).days/365
            nav=equity(i-1);short=sum(mv(t,i-1) for t,r in roots.items() if r['side']=='short')
            charges={'financing':debt*rates['financing_pct']*elapsed,
                     'borrow':short*rates['borrow_pct']*elapsed,
                     'management':max(nav,0)*rates['manager_pct']*elapsed,
                     'advisor':max(nav,0)*rates['advisor_pct']*elapsed,
                     'rebate':-collateral*rates['rebate_pct']*elapsed}
            for k,v in charges.items():costs[k]+=v;cash-=v
            rt=-charges['rebate']*rates['ordinary_tax_pct'];cash-=rt;taxes['rebate']+=rt;fund()
            for t,r in roots.items():
                active=r['active'];q=book.quantity(active,r['side']);factor=data['splits'][active][i] or 1.
                pnl+=q*(factor*px(active,i)-px(active,i-1))*(1 if r['side']=='long' else -1)
                if factor!=1:book.split(active,factor)
                q=book.quantity(active,r['side']);dist=float(data['dividends'][active][i])
                div=q*dist*(1 if r['side']=='long' else -1);dividends+=div;cash+=div
                dt=max(div,0)*rates['dividend_tax_pct'];taxes['dividends']+=dt;cash-=dt
                if r['side']=='short':book.in_lieu(active,dist)
                fund()
            # January trades finish the previous December wash window before
            # the annual settlement. This explicit timing is a research choice.
            if when>=date(when.year,2,1):pay_taxes(i,when.year-1)
            gross=sum(mv(t,i) for t in roots);nav=equity(i)
            if not closed and gross and nav/gross<rates['maintenance_equity_to_gross_pct']:
                if nav<=gross*rates['transaction_pct']:raise ValueError('Insolvent margin liquidation; portfolio retained as failed in batch report')
                close_fraction(i,1,'margin_liquidation');closed=True
            if not final and not closed:
                switched=False
                for t,r in roots.items():
                    if r['pending'] and r['active']==t:switch(t,i,True);switched=True
                    elif r['active']!=t and when>r['locked_until']:switch(t,i,False);switched=True
                if switched or i%rebalance==0 or (mode=='extension' and when.year!=dates[i-1].year):
                    target_rebalance(i,'switch_rebalance' if switched else 'scheduled_rebalance')
        if year_end and when.year not in received_years:
            value=outside[when.year]['st']+outside[when.year]['lt'];outside_received+=value;side_cash+=value;received_years.add(when.year)
        if not final and year_end and mode=='gradual' and when.year in exit_years and not closed:
            close_fraction(i,1/(len(exit_years)-exit_years.index(when.year)),'staged_exit')
        if final:
            if mode in ('death','gift') and not closed:
                # Short liabilities are closed in the donor account. They are
                # neither given away nor assigned a long-asset basis step-up.
                for t,r in roots.items():
                    if r['side']=='short':trade(t,-book.quantity(r['active'],'short'),i,'pre_transfer_short_cover')
                if mode=='gift':
                    # Gift unencumbered shares only. Sell enough long assets to
                    # repay debt and pay the donor's tax, including funding gains.
                    for _ in range(80):
                        due=sum(row[2].tax for row in tax_preview(when.year))
                        needed=max(0,debt+max(0,due-side_cash)-cash)
                        if needed<1e-6:break
                        long_value=sum(mv(t,i) for t,r in roots.items() if r['side']=='long')
                        if needed>=long_value*(1-rates['transaction_pct']):raise ValueError('Insufficient unencumbered assets to gift')
                        fraction=min(1,needed/(long_value*(1-rates['transaction_pct'])))
                        for t,r in roots.items():
                            if r['side']=='long':trade(t,-book.quantity(r['active'],'long')*fraction,i,'gift_funding_sale')
                    else:raise ArithmeticError('Gift funding did not converge')
                pay_taxes(i,when.year)
                marker=len(book.realizations)
                for lot in book.lots:
                    if lot['side']!='long':continue
                    if mode=='death':
                        basis_adjustment+=lot['qty']*(px(lot['ticker'],i)-lot['tax_basis'])
                        lot['tax_basis']=px(lot['ticker'],i);lot['inherited']=True
                    else:lot['gift_fmv']=px(lot['ticker'],i)
                for t,r in roots.items():
                    if r['side']=='long':trade(t,-book.quantity(r['active'],'long'),i,'beneficiary_sale' if mode=='death' else 'recipient_sale')
                b=defaultdict(float)
                for rec in book.realizations[marker:]:b[('gain_' if rec['tax_pnl']>=0 else 'loss_')+rec['character']]+=abs(rec['tax_pnl'])
                recipient=settle(b['gain_st'],b['gain_lt'],b['loss_st'],b['loss_lt'],0,0,
                                  float(policy.get('recipient_tax_st_pct',c.get('tax_st_pct',40)))/100,
                                  float(policy.get('recipient_tax_lt_pct',c.get('tax_lt_pct',20)))/100)
                charge(recipient.tax);taxes['recipient']=recipient.tax
                extra=float(policy.get('transfer_tax_cost',0))
                if not isfinite(extra) or extra<0:raise ValueError('Invalid transfer tax cost')
                charge(extra);taxes['estate_or_gift_input']=extra
                events.append(dict(date=when.isoformat(),event=mode,basis_adjustment=basis_adjustment,
                                   recipient_capital_tax=recipient.tax,recipient_unused_carry_st=recipient.carry_st,
                                   recipient_unused_carry_lt=recipient.carry_lt,transfer_tax_cost=extra))
            else:
                for t,r in roots.items():trade(t,-book.quantity(r['active'],r['side']),i,'final_liquidation')
                pay_taxes(i,when.year)
            closed=True
        if not final and harvesting and not closed:
            for t,r in roots.items():
                if r['active']!=t or r['pending']:continue
                lots=book.holdings(t,r['side'])
                if not lots or any((when-l['opened']).days<=30 for l in lots):continue
                basis=sum(l['qty']*l['tax_basis'] for l in lots)
                gain=(mv(t,i)-basis)*(1 if r['side']=='long' else -1)
                if basis>0 and gain/basis<=-rates['harvest_threshold_pct']:r['pending']=True
        nav=equity(i);wealth=nav+side_cash
        prices={t:px(t,i) for t in all_names}
        embedded=book.economic_embedded(prices)
        capital_error=sum(r['economic_pnl'] for r in book.realizations)+embedded-pnl
        wealth_error=wealth-(initial+outside_received+pnl+dividends-sum(costs.values())-sum(taxes.values()))
        if max(abs(capital_error),abs(wealth_error))>max(.001,initial*1e-9):raise ArithmeticError('Observed ledger conservation failed')
        if wealth<0:raise ValueError('Negative family wealth after modeled liabilities')
        long=sum(mv(t,i) for t,r in roots.items() if r['side']=='long');short=sum(mv(t,i) for t,r in roots.items() if r['side']=='short')
        daily.append(dict(date=when.isoformat(),equity=nav,total_investor_wealth=wealth,
                          long_mv=long,short_mv=short,long_pct=100*long/nav if nav>1e-7 else 0.,
                          short_pct=100*short/nav if nav>1e-7 else 0.,debt=debt,free_cash=cash,
                          short_collateral=collateral,investor_side_cash=side_cash,embedded_gain=book.tax_embedded(prices),
                          capital_identity_error=capital_error,wealth_identity_error=wealth_error,
                          active_substitutes=[r['active'] for t,r in roots.items() if r['active']!=t]))
    summary=dict(initial_cash=initial,terminal_after_tax_wealth=daily[-1]['total_investor_wealth'],
                 cumulative_price_pnl=pnl,cumulative_net_dividends=dividends,
                 outside_gain_proceeds=outside_received,cumulative_harvested_losses=harvested,
                 total_taxes=sum(taxes.values()),total_capital_taxes=taxes['capital']+taxes['recipient'],
                 total_financing_and_fees_net_rebate=sum(costs.values()),cost_breakdown=dict(costs),
                 tax_breakdown=dict(taxes),remaining_carry_st=carry_st,remaining_carry_lt=carry_lt,
                 wash_loss_deferred=sum(x['loss_deferred'] for x in book.matches),wash_matches=len(book.matches),
                 basis_adjustment=basis_adjustment,margin_liquidations=sum(e['event']=='margin_liquidation' for e in events),
                 max_wealth_identity_error=max(abs(d['wealth_identity_error']) for d in daily),
                 max_capital_identity_error=max(abs(d['capital_identity_error']) for d in daily),
                 harvest_enabled=harvesting,exit_policy=mode)
    return dict(summary=summary,daily=daily,annual=annual,trades=trades,
                realizations=book.realizations,wash_matches=book.matches,events=events)
