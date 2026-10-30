"""Aggregate net-equity basis model with an explicit investor cash account.

Realized losses are EXOGENOUS scenario inputs, never a trading simulation.
Expenses are funded by proportional sales; gains on those sales are taxed.
All final-year realizations are netted together before assessing exit taxes.
"""
from copy import deepcopy
from math import isclose, isfinite
from .taxes import settle


def validate(config):
    n = config['horizon_years']
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 10:
        raise ValueError('Horizon must be an integer from 1 to 10; no extrapolation')
    if not isfinite(config['initial_cash']) or config['initial_cash'] <= 0:
        raise ValueError('Positive finite initial cash required')
    for k in ['market_price_returns', 'outside_st_gains', 'outside_lt_gains']:
        if len(config[k]) < n or any(not isfinite(v) for v in config[k]):
            raise ValueError(f'Invalid series: {k}')
    if any(v <= -1 for v in config['market_price_returns']):
        raise ValueError('Market return must exceed -100%')
    if any(v < 0 for k in ['outside_st_gains', 'outside_lt_gains'] for v in config[k]):
        raise ValueError('Outside gains must be nonnegative')
    for k in ['tax_st', 'tax_lt', 'ordinary_tax_rate', 'cash_return_after_tax']:
        if not isfinite(config[k]) or not 0 <= config[k] < 1:
            raise ValueError(f'Invalid rate: {k}')
    names = [s['name'] for s in config['strategies']]
    if len(names) != len(set(names)) or 'index' not in names:
        raise ValueError('Unique strategies including index required')
    for s in config['strategies']:
        for k in ['long_exposure','short_exposure','manager_fee','advisor_fee',
                  'long_financing_rate','short_rebate_rate','short_borrow_rate',
                  'transaction_cost_rate','exit_transaction_rate']:
            if not isfinite(s[k]) or s[k] < 0:
                raise ValueError(f'Invalid strategy parameter: {k}')
        if not isclose(s['long_exposure'] - s['short_exposure'], 1, abs_tol=1e-12):
            raise ValueError('This prototype requires 100% net exposure')
        if s.get('return_basis') != 'gross_price_return':
            raise ValueError('Net provider returns would double-charge costs')
        if not isfinite(s['alpha_pre_cost']):
            raise ValueError('Alpha must be finite')
        for k in ['realization_st_fraction', 'interest_deduction_fraction']:
            if not isfinite(s[k]) or not 0 <= s[k] <= 1:
                raise ValueError(f'Invalid fraction: {k}')
        for k in ['harvest_st_rates', 'harvest_lt_rates', 'realized_st_gain_rates', 'realized_lt_gain_rates']:
            if len(s[k]) < n or any(not isfinite(v) or v < 0 for v in s[k]):
                raise ValueError(f'Invalid strategy series: {k}')


def _split(amount, st_fraction):
    return (max(amount, 0) * st_fraction, max(amount, 0) * (1-st_fraction),
            max(-amount, 0) * st_fraction, max(-amount, 0) * (1-st_fraction))


def simulate(config, strategy_name):
    validate(config)
    s = next(x for x in config['strategies'] if x['name'] == strategy_name)
    nav = basis = config['initial_cash']
    cash = carry_s = carry_l = 0.0
    rows = []
    n = config['horizon_years']
    cumulative_harvest = cumulative_costs = cumulative_pnl = 0.0
    cumulative_tax = cumulative_capital_realized = 0.0
    outside_aftertax_without_strategy = 0.0
    max_identity_error = 0.0
    for i in range(n):
        start, basis_start, cs0, cl0, cash0 = nav, basis, carry_s, carry_l, cash
        year = i + 1
        # Exactly one year is ST; later years use an explicit, uncalibrated mixture.
        st_frac = 1.0 if year == 1 else s['realization_st_fraction']
        pnl = start * (config['market_price_returns'][i] + s['alpha_pre_cost'])
        manager, advisor = start * s['manager_fee'], start * s['advisor_fee']
        financing = start * (s['long_exposure'] - 1) * s['long_financing_rate']
        rebate = start * s['short_exposure'] * s['short_rebate_rate']
        borrow = start * s['short_exposure'] * s['short_borrow_rate']
        trade_cost = start * s['transaction_cost_rate']
        expenses = manager + advisor + financing + borrow + trade_cost
        # Rebate is cash income, not capital appreciation; reinvesting adds basis.
        v = start + pnl + rebate
        hs, hl = start * s['harvest_st_rates'][i], start * s['harvest_lt_rates'][i]
        rg_s, rg_l = start * s['realized_st_gain_rates'][i], start * s['realized_lt_gain_rates'][i]
        b = basis + rebate - hs - hl + rg_s + rg_l
        if v <= expenses or v <= 0:
            raise ValueError('Insolvent scenario before annual expenses')
        if s['short_exposure'] == 0 and b < -1e-8:
            raise ValueError('Impossible negative long-only aggregate basis')
        # A signed net basis is possible with short liabilities; it is not a lot basis.
        basis_sold = expenses * b / v
        expense_gain = expenses - basis_sold
        v -= expenses
        b -= basis_sold
        es, el, ls, ll = _split(expense_gain, st_frac)
        gains_s, gains_l = rg_s + es, rg_l + el
        losses_s, losses_l = hs + ls, hl + ll
        outside_s, outside_l = config['outside_st_gains'][i], config['outside_lt_gains'][i]
        interest_tax = max(rebate - financing * s['interest_deduction_fraction'], 0) * config['ordinary_tax_rate']
        cash_interest = cash * config['cash_return_after_tax']
        available_cash = cash + cash_interest + outside_s + outside_l
        outside_aftertax_without_strategy = (
            outside_aftertax_without_strategy * (1+config['cash_return_after_tax'])
            + outside_s * (1-config['tax_st']) + outside_l * (1-config['tax_lt']))

        def tax_at_sale(withdrawal, exit_cost=0):
            gain = withdrawal * (1-b/v) - exit_cost
            a, c, d, e = _split(gain, st_frac)
            return settle(outside_s + gains_s + a, outside_l + gains_l + c,
                          losses_s + d, losses_l + e, cs0, cl0,
                          config['tax_st'], config['tax_lt'])

        pre_exit = tax_at_sale(0)
        internal_only = settle(gains_s, gains_l, losses_s, losses_l, cs0, cl0,
                               config['tax_st'], config['tax_lt'])
        # Tax change caused by adding outside gains; bounds avoid attributing internal offsets to outside gains.
        outside_tax_without_losses = outside_s*config['tax_st'] + outside_l*config['tax_lt']
        outside_relief = outside_tax_without_losses - (pre_exit.tax - internal_only.tax)
        tax_sale = tax_sale_gain = exit_cost = exit_tax = terminal = 0.0
        if year == n:
            exit_cost = v * (s['long_exposure']+s['short_exposure']) * s['exit_transaction_rate']
            tax_final = tax_at_sale(v, exit_cost)
            exit_tax = tax_final.tax - pre_exit.tax  # may be negative in a loss-making exit
            terminal = v - exit_cost + available_cash - tax_final.tax - interest_tax
            if terminal < -1e-8:
                raise ValueError('Insolvent full-liquidation scenario')
            nav, basis, cash = v, b, available_cash - pre_exit.tax - interest_tax
        else:
            def funding_gap(w):
                return w + available_cash - tax_at_sale(w).tax - interest_tax
            if funding_gap(0) < -1e-9:
                if funding_gap(v) < 0:
                    raise ValueError('Insufficient assets to pay taxes')
                lo, hi = 0.0, v
                for _ in range(70):
                    mid = (lo+hi)/2
                    if funding_gap(mid) < 0: lo = mid
                    else: hi = mid
                tax_sale = hi
            tax_final = tax_at_sale(tax_sale)
            tax_sale_gain = tax_sale * (1-b/v)
            basis_removed_tax = tax_sale * b/v
            nav, basis = v - tax_sale, b - basis_removed_tax
            cash = available_cash + tax_sale - tax_final.tax - interest_tax
            basis_sold += basis_removed_tax
        carry_s, carry_l = tax_final.carry_st, tax_final.carry_lt
        tax_gs,tax_gl,tax_ls,tax_ll = _split(tax_sale_gain,st_frac)
        exit_gs,exit_gl,exit_ls,exit_ll = _split(v-b-exit_cost,st_frac) if year==n else (0,0,0,0)
        cumulative_harvest += hs + hl
        cumulative_costs += expenses - rebate + exit_cost
        cumulative_pnl += pnl
        cumulative_tax += tax_final.tax + interest_tax
        cumulative_capital_realized += rg_s + rg_l - hs - hl + expense_gain + tax_sale_gain
        embedded = nav - basis
        identity_error = embedded + cumulative_capital_realized - cumulative_pnl
        max_identity_error = max(max_identity_error, abs(identity_error))
        if abs(identity_error) > 0.0001:
            raise ArithmeticError('Realized plus unrealized capital P&L does not reconcile')
        row = dict(strategy=strategy_name, year=year, hypothetical=True,
                   nav_start=start, long_market_value=start*s['long_exposure'],
                   short_market_value_abs=start*s['short_exposure'],
                   net_exposure=s['long_exposure']-s['short_exposure'],
                   gross_exposure=s['long_exposure']+s['short_exposure'],
                   market_price_return=config['market_price_returns'][i], alpha_pre_cost=s['alpha_pre_cost'],
                   pre_cost_investment_pnl=pnl, manager_fee=manager, advisor_fee=advisor,
                   long_financing_cost=financing, short_rebate=rebate, short_borrow_cost=borrow,
                   transaction_cost=trade_cost, net_annual_cost=expenses-rebate,
                   ordinary_interest_tax=interest_tax, harvested_st_loss=hs, harvested_lt_loss=hl,
                   planned_realized_st_gain=rg_s, planned_realized_lt_gain=rg_l,
                   expense_funding_realized_gain=expense_gain, tax_funding_sale=tax_sale,
                   tax_funding_realized_gain=tax_sale_gain, outside_st_gain=outside_s, outside_lt_gain=outside_l,
                   portfolio_realized_st_gain_before_exit=gains_s+tax_gs,
                   portfolio_realized_lt_gain_before_exit=gains_l+tax_gl,
                   portfolio_realized_st_loss_before_exit=losses_s+tax_ls,
                   portfolio_realized_lt_loss_before_exit=losses_l+tax_ll,
                   carry_st_start=cs0, carry_lt_start=cl0, carry_st_end=carry_s, carry_lt_end=carry_l,
                   loss_used_st=tax_final.loss_used_st, loss_used_lt=tax_final.loss_used_lt,
                   pre_exit_capital_tax=pre_exit.tax, actual_capital_tax=tax_final.tax,
                   current_outside_tax_relief_before_exit=outside_relief,
                   net_equity_basis_start=basis_start, net_equity_basis_pre_exit=basis,
                   nav_after_costs_pre_exit=nav, embedded_gain_pre_exit=embedded,
                   embedded_gain_per_cumulative_harvest=embedded/cumulative_harvest if cumulative_harvest else None,
                   investor_cash_start=cash0, investor_cash_interest=cash_interest,
                   investor_cash_pre_exit=cash, realization_st_fraction=st_frac,
                   exit_transaction_cost=exit_cost, incremental_unwind_tax=exit_tax,
                   exit_realized_st_gain=exit_gs,exit_realized_lt_gain=exit_gl,
                   exit_realized_st_loss=exit_ls,exit_realized_lt_loss=exit_ll,
                   nav_after_exit=0.0 if year==n else None,
                   net_equity_basis_after_exit=0.0 if year==n else None,
                   terminal_after_tax_wealth=terminal if year==n else None,
                   capital_pnl_identity_error=identity_error)
        rows.append(row)
    last = rows[-1]
    summary = dict(strategy=strategy_name, hypothetical=True, horizon_years=n,
                   initial_cash=config['initial_cash'],
                   outside_gross_gain_proceeds=sum(config['outside_st_gains'][:n])+sum(config['outside_lt_gains'][:n]),
                   terminal_after_tax_wealth=terminal,
                   wealth_net_of_common_outside_cash=terminal-outside_aftertax_without_strategy,
                   nav_before_full_exit=nav, net_equity_basis_before_exit=basis,
                   embedded_gain_before_exit=nav-basis,
                   cumulative_harvested_st_loss=sum(r['harvested_st_loss'] for r in rows),
                   cumulative_harvested_lt_loss=sum(r['harvested_lt_loss'] for r in rows),
                   cumulative_net_costs=cumulative_costs, cumulative_pre_cost_pnl=cumulative_pnl,
                   cumulative_total_tax=cumulative_tax,
                   current_outside_relief_before_exit=sum(r['current_outside_tax_relief_before_exit'] for r in rows),
                   incremental_unwind_tax=last['incremental_unwind_tax'],
                   carry_st_after_exit=carry_s, carry_lt_after_exit=carry_l,
                   unused_carryforward_cash_value=0.0,
                   max_capital_identity_error=max_identity_error)
    return summary, rows


def compare(config):
    results = [simulate(config, s['name']) for s in config['strategies']]
    base = next(x[0]['terminal_after_tax_wealth'] for x in results if x[0]['strategy']=='index')
    for summary, _ in results:
        summary['incremental_wealth_vs_index'] = summary['terminal_after_tax_wealth']-base
    return [x[0] for x in results], [r for x in results for r in x[1]]


def with_gains(config, amount, character='st', timing='annual'):
    c = deepcopy(config)
    n = len(c['market_price_returns'])
    c['outside_st_gains'] = [0.0]*n
    c['outside_lt_gains'] = [0.0]*n
    if character not in ('st','lt') or timing not in ('annual','initial','terminal'):
        raise ValueError('Unsupported gain character or timing')
    arr = c[f'outside_{character}_gains']
    if timing == 'annual': arr[:] = [amount]*n
    else: arr[0 if timing=='initial' else c['horizon_years']-1] = amount
    return c
