"""Integrated after-tax harvesting research with an explicit equity ledger.

This is a transparent educational tax model, not a complete US tax return.
Legacy price-only and no-harvest API levels remain available for saved runs.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math

from .market_data import normalize_ticker
from .taxes import settle


def _number(value, name, low=0, high=1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number between {low} and {high}.')
    return float(value)


def _config(inputs):
    if not isinstance(inputs, dict):
        raise ValueError('Expected a research configuration object.')
    c = deepcopy(inputs)
    if type(c.get('level')) is not int or c['level'] not in (1, 2, 3):
        raise ValueError('Research level must be 1, 2 or 3.')
    try:
        start, end = date.fromisoformat(c['start_date']), date.fromisoformat(c['end_date'])
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('Use ISO start_date and end_date.') from error
    if not 0 < (end-start).days <= 3660:
        raise ValueError('Choose an increasing date range of at most ten years.')
    c['initial_cash'] = _number(c.get('initial_cash'), 'Initial equity', 1, 1e10)
    c['benchmark'] = normalize_ticker(c.get('benchmark', 'SPY'))
    c['allocation_mode'] = c.get('allocation_mode', 'shares')
    if c['allocation_mode'] not in ('shares', 'target_exposure'):
        raise ValueError('Allocation mode must be shares or target_exposure.')
    if c['allocation_mode'] == 'target_exposure':
        for key, default in (('long_exposure_pct', 130), ('short_exposure_pct', 30)):
            c[key] = _number(c.get(key, default), key, 0, 1000)
        if c['long_exposure_pct'] + c['short_exposure_pct'] == 0:
            raise ValueError('Choose a positive long or short exposure.')
    if not isinstance(c.get('positions'), list) or not 1 <= len(c['positions']) <= 20:
        raise ValueError('Provide 1 to 20 manually selected positions.')
    seen = set()
    for p in c['positions']:
        if not isinstance(p, dict):
            raise ValueError('Each position must be an object.')
        p['ticker'] = normalize_ticker(p.get('ticker'))
        if p['ticker'] in seen:
            raise ValueError('Combine duplicate tickers into one net position.')
        seen.add(p['ticker'])
        if p.get('side') not in ('long', 'short'):
            raise ValueError('Position side must be long or short.')
        if c['allocation_mode'] == 'shares':
            p['shares'] = _number(p.get('shares'), 'Shares', .000001, 1e8)
        else:
            p['weight'] = _number(p.get('weight'), 'Position weight', .000001, 1e6)
    if c['allocation_mode'] == 'target_exposure':
        for side in ('long', 'short'):
            has_positions = any(p['side'] == side for p in c['positions'])
            exposure = c[f'{side}_exposure_pct']
            if exposure > 0 and not has_positions:
                raise ValueError(f'Add at least one {side} position for its positive exposure.')
            if exposure == 0 and has_positions:
                raise ValueError(f'Remove {side} positions or choose a positive {side} exposure.')
    for key, default in dict(financing_pct=5, borrow_pct=1, rebate_pct=0, manager_pct=0, transaction_pct=0,
                             tax_st_pct=40, tax_lt_pct=20, dividend_tax_pct=20).items():
        c[key] = _number(c.get(key, default), key, 0, 99.99) / 100
    for key in ('outside_st_gain', 'outside_lt_gain'):
        c[key] = _number(c.get(key, 0), key, 0, 1e9)
    c['harvest_threshold_pct'] = _number(c.get('harvest_threshold_pct', 10), 'Loss threshold', .01, 1000) / 100
    cooldown = c.get('cooldown_days', 30)
    if type(cooldown) is not int or not 30 <= cooldown <= 3650:
        raise ValueError('Cooldown must be an integer of at least 30 calendar days.')
    c['cooldown_days'] = cooldown
    return c


def _validate_data(data, tickers, start, end):
    if not isinstance(data, dict) or not isinstance(data.get('dates'), list) or len(data['dates']) < 2:
        raise ValueError('At least two complete historical trading sessions are required.')
    try:
        dates = [date.fromisoformat(d) for d in data['dates']]
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid historical dates.') from error
    if any(a >= b for a, b in zip(dates, dates[1:])) or dates[0] < date.fromisoformat(start) or dates[-1] > date.fromisoformat(end):
        raise ValueError('History must be ordered, unique, and within the requested date range.')
    for group in ('prices', 'dividends', 'splits'):
        if not isinstance(data.get(group), dict):
            raise ValueError(f'History is missing {group}.')
        for symbol in tickers:
            series = data[group].get(symbol)
            if not isinstance(series, list) or len(series) != len(dates):
                raise ValueError(f'{symbol}: incomplete {group}.')
            for value in series:
                _number(value, group, .00000001 if group == 'prices' else 0, 1e12)
    return dates


def _resolve_allocation(c, data):
    """Size once at the first historical close, preserving fractional shares.

    Each leg has its own dollar budget and normalized relative weights. Cash,
    financing, collateral and opening fees are then handled by the same ledger
    as manual shares; short proceeds never increase the long budget.
    """
    if c['allocation_mode'] == 'target_exposure':
        for side in ('long', 'short'):
            leg = [p for p in c['positions'] if p['side'] == side]
            total_weight = sum(p['weight'] for p in leg)
            budget = c['initial_cash'] * c[f'{side}_exposure_pct'] / 100
            for p in leg:
                value = budget * (p['weight'] / total_weight)
                p['shares'] = _number(value / data['prices'][p['ticker']][0], 'Resolved shares', 1e-18, 1e20)
    resolved = []
    for p in c['positions']:
        price = data['prices'][p['ticker']][0]
        resolved.append(dict(ticker=p['ticker'], side=p['side'], shares=p['shares'],
                             start_price=price, initial_value=p['shares'] * price))
    long_value = sum(p['initial_value'] for p in resolved if p['side'] == 'long')
    short_value = sum(p['initial_value'] for p in resolved if p['side'] == 'short')
    for p in resolved:
        leg_value = long_value if p['side'] == 'long' else short_value
        p['weight'] = p['initial_value'] / leg_value
    allocation = dict(mode=c['allocation_mode'], long_value=long_value, short_value=short_value,
                      long_exposure_pct=long_value/c['initial_cash']*100,
                      short_exposure_pct=short_value/c['initial_cash']*100,
                      gross_exposure_pct=(long_value+short_value)/c['initial_cash']*100,
                      net_exposure_pct=(long_value-short_value)/c['initial_cash']*100,
                      resolved_positions=resolved)
    if c['allocation_mode'] == 'target_exposure':
        allocation['requested_long_exposure_pct'] = c['long_exposure_pct']
        allocation['requested_short_exposure_pct'] = c['short_exposure_pct']
    return allocation


def _simulate(c, data, dates, level, benchmark=False):
    prices, dividends, splits = data['prices'], data['dividends'], data['splits']
    initial = c['initial_cash']
    definitions = ([dict(ticker=c['benchmark'], side='long', shares=initial/prices[c['benchmark']][0])]
                   if benchmark else c['positions'])
    states = [dict(ticker=p['ticker'], side=p['side'], target=p['shares'], q=0., entry=0., opened=None,
                   closed=None, pending=False, collateral=0.) for p in definitions]
    cash, debt, collateral = initial, 0., 0.
    totals = dict(price_pnl=0., dividend_cash=0., dividend_tax=0., costs=0., capital_tax=0.,
                  harvested_loss=0., loss_used=0., outside=0., capital_tax_before_exit=0., rebate_tax=0.)
    cost_breakdown = dict(financing=0., borrow=0., management=0., trading=0., rebate=0.)
    buckets = dict(gain_st=0., gain_lt=0., loss_st=0., loss_lt=0.)
    carry_st = carry_lt = 0.
    trades, daily, annual = [], [], []
    initial_long = sum(p['shares']*prices[p['ticker']][0] for p in definitions if p['side']=='long')
    initial_short = sum(p['shares']*prices[p['ticker']][0] for p in definitions if p['side']=='short')
    exit_tax = unrealized = 0.

    def fund():
        nonlocal cash, debt
        if cash < 0:
            debt -= cash; cash = 0.
        if cash > 0 and debt > 0:
            repayment = min(cash, debt); cash -= repayment; debt -= repayment

    def amount(delta):
        nonlocal cash
        cash += delta; fund()

    def nav(i):
        return cash + collateral - debt + sum(s['q']*prices[s['ticker']][i]*(1 if s['side']=='long' else -1) for s in states)

    def trade(s, i, event):
        nonlocal collateral
        symbol, when = s['ticker'], dates[i]
        price = prices[symbol][i]
        opening = event in ('open', 'reentry')
        q = s['target'] if opening else s['q']
        if not q:
            return
        cost = 0 if level == 1 else q*price*c['transaction_pct']
        gain, character = 0., None
        if opening:
            if s['side']=='long':
                amount(-q*price)
            else:
                s['collateral'] = q*price; collateral += s['collateral']
            s['q'], s['entry'], s['opened'], s['closed'], s['pending'] = q, price, when, None, False
        else:
            gain = q*(price-s['entry'])*(1 if s['side']=='long' else -1)
            character = 'lt' if s['side']=='long' and (when-s['opened']).days > 365 else 'st'
            if s['side']=='long':
                amount(q*price)
            else:
                collateral -= s['collateral']; amount(s['collateral']-q*price); s['collateral'] = 0.
            if level >= 2:
                buckets[('gain_' if gain >= 0 else 'loss_')+character] += abs(gain)
            if event == 'harvest':
                totals['harvested_loss'] += max(-gain, 0)
            s['q'], s['closed'], s['pending'] = 0., when, False
        if cost:
            amount(-cost); totals['costs'] += cost; cost_breakdown['trading'] += cost
        trades.append(dict(date=when.isoformat(),ticker=symbol,side=s['side'],event=event,
                           shares=q,price=price,pnl=gain,character=character,transaction_cost=cost))

    for i, when in enumerate(dates):
        day_cost = day_div = day_tax = day_harvest = 0.
        prior_harvest, prior_cost = totals['harvested_loss'], totals['costs']
        if i == 0:
            for s in states:
                trade(s, i, 'open')
        else:
            dt = (when-dates[i-1]).days/365
            previous_nav = nav(i-1)
            previous_short = sum(s['q']*prices[s['ticker']][i-1] for s in states if s['side']=='short')
            if level >= 2:
                financing = debt*c['financing_pct']*dt
                borrow = previous_short*c['borrow_pct']*dt
                management = 0 if benchmark else max(previous_nav,0)*c['manager_pct']*dt
                rebate = collateral*c['rebate_pct']*dt
                expense = financing+borrow+management-rebate
                amount(-expense); totals['costs'] += expense
                rebate_tax = rebate*c['tax_st_pct']
                amount(-rebate_tax); totals['rebate_tax'] += rebate_tax
                for name, value in [('financing',financing),('borrow',borrow),('management',management),('rebate',rebate)]:
                    cost_breakdown[name] += value
            for s in states:
                ratio = splits[s['ticker']][i] or 1
                old_q = s['q']
                totals['price_pnl'] += old_q*(ratio*prices[s['ticker']][i]-prices[s['ticker']][i-1])*(1 if s['side']=='long' else -1)
                if ratio != 1:
                    s['target'] *= ratio
                    s['q'] *= ratio
                    s['entry'] /= ratio
                if level >= 2 and s['q']:
                    distribution = s['q']*dividends[s['ticker']][i]*(1 if s['side']=='long' else -1)
                    tax = max(distribution,0)*c['dividend_tax_pct']
                    amount(distribution-tax)
                    totals['dividend_cash'] += distribution; totals['dividend_tax'] += tax; day_div += distribution
            if level == 3 and i < len(dates)-1:
                for s in states:
                    if s['q'] and s['pending']:
                        # A prior-close signal executes at this close, not retrospectively.
                        trade(s,i,'harvest')
                    elif not s['q'] and s['closed'] is not None and (when-s['closed']).days > c['cooldown_days']:
                        trade(s,i,'reentry')
        last = i == len(dates)-1
        year_end = last or dates[i+1].year != when.year
        outside_s = c['outside_st_gain'] if year_end and level >= 2 else 0.
        outside_l = c['outside_lt_gain'] if year_end and level >= 2 else 0.
        before_exit_tax = None
        if last:
            unrealized = sum(s['q']*(prices[s['ticker']][i]-s['entry'])*(1 if s['side']=='long' else -1) for s in states)
            if level >= 2:
                before_exit_tax = settle(buckets['gain_st']+outside_s,buckets['gain_lt']+outside_l,
                                         buckets['loss_st'],buckets['loss_lt'],carry_st,carry_lt,c['tax_st_pct'],c['tax_lt_pct']).tax
            for s in states:
                trade(s,i,'exit')
        if year_end and level >= 2:
            amount(outside_s+outside_l); totals['outside'] += outside_s+outside_l
            tax = settle(buckets['gain_st']+outside_s,buckets['gain_lt']+outside_l,
                         buckets['loss_st'],buckets['loss_lt'],carry_st,carry_lt,c['tax_st_pct'],c['tax_lt_pct'])
            day_tax = tax.tax; amount(-tax.tax); totals['capital_tax'] += tax.tax
            used = tax.loss_used_st+tax.loss_used_lt; totals['loss_used'] += used
            carry_st, carry_lt = tax.carry_st, tax.carry_lt
            if last:
                exit_tax = tax.tax-before_exit_tax
                totals['capital_tax_before_exit'] += before_exit_tax
            else:
                totals['capital_tax_before_exit'] += tax.tax
            annual.append(dict(year=when.year,**buckets,tax=tax.tax,loss_used=used,
                               carry_st=carry_st,carry_lt=carry_lt,outside_proceeds=outside_s+outside_l,
                               exit_tax=exit_tax if last else 0.))
            buckets = dict(gain_st=0., gain_lt=0., loss_st=0., loss_lt=0.)
        if level == 3 and not last:
            for s in states:
                if s['q'] and (when-s['opened']).days > 30:
                    signed_loss = (prices[s['ticker']][i]-s['entry'])/s['entry']*(1 if s['side']=='long' else -1)
                    s['pending'] = signed_loss <= -c['harvest_threshold_pct']
        equity = nav(i)
        if equity <= 0:
            raise ValueError(f'Nonpositive equity on {when}; this scenario requires a margin/liquidation model and is not continued.')
        long_mv = sum(s['q']*prices[s['ticker']][i] for s in states if s['side']=='long')
        short_mv = sum(s['q']*prices[s['ticker']][i] for s in states if s['side']=='short')
        daily.append(dict(date=when.isoformat(),equity=equity,net_exposure=(long_mv-short_mv)/equity,
                          gross_exposure=(long_mv+short_mv)/equity,cost=totals['costs']-prior_cost,
                          capital_tax=day_tax,dividend_cash=day_div,harvested_loss=totals['harvested_loss']-prior_harvest,
                          free_cash=cash,debt=debt,short_collateral=collateral))
    terminal = nav(len(dates)-1)
    identity = initial+totals['outside']+totals['price_pnl']+totals['dividend_cash']-totals['dividend_tax']-totals['rebate_tax']-totals['costs']-totals['capital_tax']-terminal
    if abs(identity) > max(.001, initial*1e-8):
        raise ArithmeticError('Investor wealth does not reconcile.')
    summary = dict(initial_cash=initial,terminal_wealth=terminal,
                   return_pct=(terminal-initial-totals['outside'])/initial*100,
                   price_pnl=totals['price_pnl'],dividend_cash=totals['dividend_cash'],dividend_tax=totals['dividend_tax'],
                   costs=totals['costs'],cost_breakdown=cost_breakdown,rebate_tax=totals['rebate_tax'],capital_tax=totals['capital_tax'],capital_tax_before_exit=totals['capital_tax_before_exit'],exit_tax=exit_tax,
                   harvested_loss=totals['harvested_loss'],loss_used=totals['loss_used'],remaining_carry_st=carry_st,remaining_carry_lt=carry_lt,
                   initial_net_exposure=(initial_long-initial_short)/initial,initial_gross_exposure=(initial_long+initial_short)/initial,
                   unrealized_before_exit=unrealized,outside_gross_proceeds=totals['outside'],wealth_identity_error=identity)
    return dict(summary=summary,daily=daily,annual=annual,trades=trades,
                positions=[dict(ticker=p['ticker'],side=p['side'],shares=p['shares'],
                                start_price=prices[p['ticker']][0],end_price=prices[p['ticker']][-1]) for p in definitions])


def run_research(inputs, history_provider=None):
    c = _config(inputs)
    if history_provider is None:
        from .market_data import load_history
        history_provider = load_history
    tickers = list(dict.fromkeys([p['ticker'] for p in c['positions'] if p['ticker'] != c['benchmark']]+[c['benchmark']]))
    data = history_provider(tickers,c['start_date'],c['end_date'])
    dates = _validate_data(data,tickers,c['start_date'],c['end_date'])
    allocation = _resolve_allocation(c, data)
    result = _simulate(c,data,dates,c['level'])
    benchmark = _simulate(c,data,dates,min(c['level'],2),benchmark=True)
    result['level'] = c['level']
    result['summary']['benchmark_wealth'] = benchmark['summary']['terminal_wealth']
    result['summary']['incremental_wealth'] = result['summary']['terminal_wealth']-benchmark['summary']['terminal_wealth']
    result['benchmark'] = benchmark
    if c['level'] == 3:
        control = _simulate(c,data,dates,2)
        actual, base = result['summary'], control['summary']
        actual['incremental_wealth_vs_no_harvest'] = actual['terminal_wealth']-base['terminal_wealth']
        actual['tax_relief_before_exit_vs_no_harvest'] = base['capital_tax_before_exit']-actual['capital_tax_before_exit']
        actual['extra_exit_tax_vs_no_harvest'] = actual['exit_tax']-base['exit_tax']
        actual['total_capital_tax_saving_vs_no_harvest'] = base['capital_tax']-actual['capital_tax']
        actual['extra_cost_vs_no_harvest'] = actual['costs']-base['costs']
        actual['price_pnl_difference_vs_no_harvest'] = actual['price_pnl']-base['price_pnl']
        result['no_harvest_control'] = control
    result['metadata'] = dict(model='integrated-historical-harvesting-v2',currency='USD',
                              requested_start=c['start_date'],requested_end=c['end_date'],
                              actual_start=dates[0].isoformat(),actual_end=dates[-1].isoformat(),
                              annualized_return=False,inputs=deepcopy(inputs),data_metadata=data.get('metadata', {}),
                              engine_sha256=hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest())
    result['metadata']['allocation'] = allocation
    result['metadata']['benchmark_allocation'] = dict(long_exposure_pct=100, short_exposure_pct=0,
        description='100% long benchmark; matched initial equity and outside cash flows, not matched leverage.')
    result['assumptions'] = [
        'Tickers are manually chosen. Exposure sizing converts each leg budget and normalized relative weights to fractional shares at the first available close, before opening fees. Manual shares remain supported. Initial exposures drift; no continuous fixed-weight rebalancing or stock-selection alpha is assumed.',
        'Level 1 is historical price-only P&L. Levels 2 and 3 add dividends, ACT/365 daily costs, annual tax settlement and full liquidation.',
        'Long gains held more than 365 days use the long-term rate; all short-cover gains/losses use a conservative short-term proxy, not complete US short-sale tax law.',
        'Dividend entitlement and tax are recorded on ex-dates at one user-specified flat rate; short dividends are cash payments with no tax deduction. No dividend reinvestment.',
        'Trade fees, financing, management and borrow costs are nondeductible cash expenses in this model. Short rebate is taxed using the short-term rate as an ordinary-income proxy. Management fees apply to prior total account equity including side cash. Benchmark ETF fund expenses are already in observed prices, so custom management fees are not charged to the benchmark.',
        'Short proceeds remain restricted collateral. Negative free cash is financed, positive free cash repays debt; financing uses actual debt and rebates use collateral. No margin thresholds, recalls or forced liquidation are modeled; nonpositive equity stops the run.',
        'Level 3 observes a closing-price loss threshold after holding more than 30 calendar days and executes at the next available close, whose actual loss can differ from the signal. It repurchases the same share quantity only after more than cooldown_days, minimum 30, following a close. Capital stays in cash while out; split actions adjust quantities.',
        'This own-account cooldown is not a complete wash-sale or substantially-identical-security test across household accounts, options or external trades. It does not guarantee legally deductible losses.',
        'Outside gains and identical gross cash proceeds are added at each modeled calendar year end, including partial first/last years, without proration. Unused capital losses carry forward without a cash refund or terminal value.',
        'Return % removes gross outside cash proceeds from wealth change and divides by initial equity; it is not TWR, IRR or CAGR. Terminal after-tax wealth comparisons use matched external cash flows.',
        'Only full final liquidation is modeled. Gradual exits, liquidity shocks, death/basis step-up, detailed state rules and household tax returns remain outside this version.',
        'No survivorship-free universe, borrow-availability verification, historical execution spreads or market-impact calibration is supplied by Yahoo. Historical outcomes and simplified tax assumptions are research scenarios, not client recommendations.'
    ]
    # Include the exact dataset so a downloaded run can be replayed without Yahoo.
    result['data'] = data
    digest = json.dumps(dict(inputs=inputs,data=data),sort_keys=True,allow_nan=False).encode()
    result['metadata']['run_id'] = hashlib.sha256(digest).hexdigest()[:20]
    return result
