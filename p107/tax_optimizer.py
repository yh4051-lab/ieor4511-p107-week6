"""Conservative, causal tax-aware QP for fixed long/short candidate directions.

This is a local trading objective, not a guarantee of maximum terminal wealth.
Loss credits are deliberately zero in the planning surrogate. Actual losses,
carryforwards, wash deferrals and taxes remain in the full lot-accounting engine.
"""
from bisect import bisect_left
from copy import deepcopy
from datetime import date
from math import isfinite

import cvxpy as cp
import numpy as np

from .lot_accounting import held_more_than_year


DEFAULTS = dict(lookback_sessions=126, min_history_sessions=20,
                risk_aversion=20., tax_penalty=1., turnover_penalty=.0001,
                covariance_shrinkage=.2, max_long_weight=.8,
                max_short_weight=.2, return_model='zero')


def _settings(config):
    raw = config.get('optimizer', {})
    if not isinstance(raw, dict):
        raise ValueError('optimizer settings must be an object')
    unknown = set(raw)-set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown optimizer settings: '+', '.join(sorted(unknown)))
    answer = {**DEFAULTS, **raw}
    for key in ('lookback_sessions', 'min_history_sessions'):
        value = answer[key]
        if type(value) is not int or not 20 <= value <= 1260:
            raise ValueError(key+' must be an integer between 20 and 1260')
    if answer['min_history_sessions'] > answer['lookback_sessions']:
        raise ValueError('Minimum forecast history exceeds lookback length')
    for key in ('risk_aversion', 'tax_penalty', 'turnover_penalty',
                'covariance_shrinkage', 'max_long_weight', 'max_short_weight'):
        value = answer[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError(key+' must be finite and nonnegative')
    if answer['covariance_shrinkage'] > 1:
        raise ValueError('Covariance shrinkage must be between zero and one')
    if answer['max_long_weight'] > 10 or answer['max_short_weight'] > 10:
        raise ValueError('Individual position caps must not exceed 1000% of NAV')
    if answer['return_model'] not in ('zero', 'trailing_mean'):
        raise ValueError('return_model must be zero or trailing_mean')
    return answer


def lot_gain_tax_coefficient(lot, price, when, config):
    """Positive estimated tax dollars per dollar sold, with no loss credit.

    Uses current lot basis and holding period, including existing wash basis
    adjustments. This is a conservative marginal proxy: it does not forecast
    netting, future tax rates or benefits from currently unused losses.
    """
    side = lot['side']
    sign = 1 if side == 'long' else -1
    fee_rate = float(config.get('transaction_pct', .05))/100
    gain = (price-lot['tax_basis'])*sign-price*fee_rate
    if side == 'short' and (when-lot['opened']).days <= 45:
        gain -= lot.get('in_lieu', 0.)
    is_lt = side == 'long' and (lot.get('inherited') or held_more_than_year(
        lot['opened'], when, lot.get('holding_credit', 0)))
    tax_rate = float(config.get('tax_lt_pct' if is_lt else 'tax_st_pct', 20 if is_lt else 40))/100
    return max(0., gain/price)*tax_rate


class TaxAwareAllocator:
    def __init__(self, config, forecast_history):
        self.config = deepcopy(config)
        self.settings = _settings(config)
        if not isinstance(forecast_history, dict):
            raise ValueError('Optimizer requires a complete forecast history including warmup')
        self.history = deepcopy(forecast_history)
        raw_dates = self.history.get('dates')
        if not isinstance(raw_dates, list) or len(raw_dates) < 2:
            raise ValueError('Optimizer forecast history is missing dates')
        try:
            self.dates = [date.fromisoformat(d) for d in raw_dates]
        except (TypeError, ValueError) as error:
            raise ValueError('Optimizer forecast dates must be ISO dates') from error
        if any(a >= b for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError('Optimizer history dates must be ordered and unique')
        self.records = []

    def forecast(self, tickers, when, horizon):
        """Estimate only from observations dated strictly before this trade."""
        stop = bisect_left(self.dates, when)
        start = max(0, stop-self.settings['lookback_sessions']-1)
        count = stop-start-1
        if count < self.settings['min_history_sessions']:
            raise ValueError(f'Optimizer needs at least {self.settings["min_history_sessions"]} past returns before {when}; found {max(count, 0)}')
        returns = []
        for ticker in tickers:
            series = []
            for group in ('prices', 'splits', 'dividends'):
                values = self.history.get(group, {}).get(ticker)
                if not isinstance(values, list) or len(values) != len(self.dates):
                    raise ValueError('Optimizer forecast history missing '+group+' for '+ticker)
                observations = np.asarray(values[start:stop], dtype=float)
                if not np.all(np.isfinite(observations)) or np.any(observations < (1e-12 if group == 'prices' else 0)):
                    raise ValueError('Optimizer forecast has invalid '+group+' for '+ticker)
                series.append(observations)
            prices, splits, dividends = series
            factors = np.where(splits[1:] > 0, splits[1:], 1.)
            returns.append(factors*(prices[1:]+dividends[1:])/prices[:-1]-1)
        matrix = np.column_stack(returns)
        covariance = np.atleast_2d(np.cov(matrix, rowvar=False, ddof=1))
        shrink = self.settings['covariance_shrinkage']
        covariance = (1-shrink)*covariance+shrink*np.diag(np.diag(covariance))
        covariance = (covariance+covariance.T)/2
        # PSD floor is numerical regularization, not invented market variance.
        vals, vectors = np.linalg.eigh(covariance)
        covariance = (vectors*np.maximum(vals, 1e-12))@vectors.T
        covariance *= horizon
        mean = matrix.mean(axis=0)*horizon if self.settings['return_model'] == 'trailing_mean' else np.zeros(len(tickers))
        return covariance, mean, dict(observations=count,
            forecast_start=self.dates[start].isoformat(),
            forecast_cutoff=self.dates[stop-1].isoformat(),
            trade_date=when.isoformat(), horizon_sessions=horizon,
            return_model=self.settings['return_model'])

    def __call__(self, state):
        c, roots, book = state['config'], state['roots'], state['book']
        nav = float(state['nav'])
        if not isfinite(nav) or nav <= 0:
            raise ValueError('Optimizer requires positive net asset value')
        when = state['dates'][state['index']]
        when = date.fromisoformat(when) if isinstance(when, str) else when
        names = sorted(roots)
        if not names:
            raise ValueError('Optimizer needs at least one position')
        long_indices = [i for i, t in enumerate(names) if roots[t]['side'] == 'long']
        short_indices = [i for i, t in enumerate(names) if roots[t]['side'] == 'short']
        targets = state.get('targets', dict(long=float(c.get('long_exposure_pct', 130))/100,
                                          short=float(c.get('short_exposure_pct', 30))/100))
        target_long, target_short = targets['long'], targets['short']
        if target_long > len(long_indices)*self.settings['max_long_weight']+1e-10:
            raise ValueError('Optimizer long cap is infeasible for the number of long stocks')
        if target_short > len(short_indices)*self.settings['max_short_weight']+1e-10:
            raise ValueError('Optimizer short cap is infeasible for the number of short stocks')
        benchmark = c.get('benchmark', 'SPY')
        symbols = sorted(set([roots[t]['active'] for t in names]+[benchmark]))
        horizon = int(c.get('rebalance_every_sessions', 21))
        covariance, means, forecast_record = self.forecast(symbols, when, horizon)
        symbol_index = {t: i for i, t in enumerate(symbols)}
        exposure = np.zeros((len(symbols), len(names)))
        for i, root in enumerate(names):
            exposure[symbol_index[roots[root]['active']], i] = 1 if roots[root]['side'] == 'long' else -1
        baseline = np.zeros(len(symbols)); baseline[symbol_index[benchmark]] = 1
        old = np.array([state['current_notionals'][t]/nav for t in names])
        weight = cp.Variable(len(names), nonneg=True)
        buys = cp.Variable(len(names), nonneg=True)
        lots = []
        per_root = {t: [] for t in names}
        for root in names:
            active, side = roots[root]['active'], roots[root]['side']
            price = state['prices'][active]
            for lot in book.holdings(active, side):
                index = len(lots)
                lots.append(dict(root=root, lot=lot, price=price,
                    capacity=lot['qty']*price/nav,
                    coefficient=lot_gain_tax_coefficient(lot, price, when, c)))
                per_root[root].append(index)
        sells = cp.Variable(len(lots), nonneg=True) if lots else None
        constraints = []
        if long_indices:
            constraints += [cp.sum(weight[long_indices]) == target_long,
                            weight[long_indices] <= self.settings['max_long_weight']]
        elif target_long:
            raise ValueError('Optimizer missing long candidates')
        if short_indices:
            constraints += [cp.sum(weight[short_indices]) == target_short,
                            weight[short_indices] <= self.settings['max_short_weight']]
        elif target_short:
            raise ValueError('Optimizer missing short candidates')
        for i, root in enumerate(names):
            root_sales = cp.sum(sells[per_root[root]]) if per_root[root] else 0
            constraints += [weight[i] == old[i]+buys[i]-root_sales]
        if lots:
            constraints += [sells <= np.array([x['capacity'] for x in lots])]
        turnover = cp.sum(buys)+(cp.sum(sells) if lots else 0)
        transaction = float(c.get('transaction_pct', .05))/100*turnover
        # A uniform financing/borrow rate is constant across weights at fixed
        # total exposures. It is still included and audited, and the simulator
        # charges actual debt and short market values between decisions.
        holding = (max(target_long-1, 0)*float(c.get('financing_pct', 5))/100+
                   target_short*float(c.get('borrow_pct', 1))/100)*horizon/252
        tax = cp.sum(cp.multiply(np.array([x['coefficient'] for x in lots]), sells)) if lots else 0
        active = exposure@weight-baseline
        risk = cp.quad_form(active, cp.psd_wrap(covariance))
        expected_return = means@(exposure@weight)
        regularization = max(float(self.settings['turnover_penalty']), 1e-7)*turnover
        problem = cp.Problem(cp.Minimize(self.settings['risk_aversion']*risk+
            transaction+holding+self.settings['tax_penalty']*tax+regularization-expected_return), constraints)
        # CLARABEL is deterministic, handles this convex QP and the equality
        # constraints accurately. No silent equal-weight fallback is allowed.
        try:
            problem.solve(solver='CLARABEL', tol_gap_abs=1e-9, tol_gap_rel=1e-9,
                          tol_feas=1e-9, max_iter=200)
        except cp.error.SolverError as error:
            raise ValueError('Tax-aware QP solver failed: '+str(error)) from error
        if problem.status != cp.OPTIMAL or weight.value is None:
            raise ValueError('Tax-aware QP did not solve optimally: '+str(problem.status))
        result_weights = np.maximum(np.asarray(weight.value).reshape(-1), 0.)
        # Remove numerical equality residuals before the exact after-fee engine
        # computes quantities. This normalization never changes book direction.
        for indices, target in [(long_indices, target_long), (short_indices, target_short)]:
            if indices:
                total = sum(result_weights[indices])
                if target and total <= 0:
                    raise ValueError('Tax-aware QP returned an empty positive-exposure book')
                result_weights[indices] *= target/total if total else 0
        sale_values = np.maximum(np.asarray(sells.value).reshape(-1), 0.) if lots else np.array([])
        lot_orders = {}
        planned_lots = []
        for root in names:
            candidates = per_root[root]
            # For each root the marginal positive tax is linear. Selling lower
            # marginal-tax lots first implements the selected-lot optimum even
            # when exact after-fee NAV scaling slightly changes sale quantity.
            ordered = sorted(candidates, key=lambda j: (lots[j]['coefficient'],
                                                        -sale_values[j], lots[j]['lot']['id']))
            if ordered:
                lot_orders[root] = [lots[j]['lot']['id'] for j in ordered]
            for j in candidates:
                if sale_values[j] > 1e-8:
                    planned_lots.append(dict(root=root, ticker=roots[root]['active'],
                        lot_id=lots[j]['lot']['id'], planned_sale_shares=float(sale_values[j]*nav/lots[j]['price']),
                        positive_tax_per_dollar=lots[j]['coefficient']))
        active_value = exposure@result_weights-baseline
        record = dict(**forecast_record, reason=state['reason'], solver='CLARABEL', status=problem.status,
            objective=float(problem.value), estimated_tracking_error_annual=float(np.sqrt(max(0, active_value@covariance@active_value)*252/horizon)),
            long_target=target_long, short_target=target_short,
            long_total=float(sum(result_weights[long_indices])), short_total=float(sum(result_weights[short_indices])),
            weights={t: float(result_weights[i]) for i, t in enumerate(names)},
            estimated_transaction_cost_usd=float(transaction.value if hasattr(transaction, 'value') else transaction)*nav,
            estimated_holding_cost_usd=float(holding)*nav,
            estimated_positive_gain_tax_usd=float(tax.value if hasattr(tax, 'value') else tax)*nav,
            expected_return_model=self.settings['return_model'],
            loss_credit_in_objective=0., tax_surrogate='Positive marginal realized-gain taxes only; no immediate loss credits or forecast netting. Actual annual settlement is computed by the lot engine.',
            estimated_trade_nav=nav, planned_lot_sales=planned_lots,
            exposure_note='Weights are planned against current NAV; the engine rescales targets to NAV after actual trading fees. Financed debt/collateral remain separate.')
        self.records.append(record)
        return dict(weights=record['weights'], lot_orders=lot_orders, record=record)


def build_tax_allocator(config, forecast_history):
    return TaxAwareAllocator(config, forecast_history)
