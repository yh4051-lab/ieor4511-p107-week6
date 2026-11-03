"""Independent price-only position experiment; no tax-loss harvesting claims."""
import math
from .market_data import get_quote, normalize_ticker


def number(value, name, minimum=0, maximum=1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}.')
    return float(value)


def calculate_portfolio(inputs, quote_provider=None):
    if not isinstance(inputs, dict):
        raise ValueError('Invalid input format.')
    equity = number(inputs.get('initial_cash'), 'Initial equity', 1)
    days = number(inputs.get('holding_days'), 'Holding days', 0, 36500)
    finance = number(inputs.get('financing_pct'), 'Annual financing rate', 0, 100) / 100
    borrow = number(inputs.get('borrow_pct'), 'Annual borrow fee', 0, 100) / 100
    rebate = number(inputs.get('rebate_pct'), 'Annual short rebate', 0, 100) / 100
    fee = number(inputs.get('manager_pct'), 'Annual management fee', 0, 100) / 100
    trade = number(inputs.get('transaction_pct'), 'One-way trading fee', 0, 20) / 100
    positions = inputs.get('positions')
    if not isinstance(positions, list) or not 1 <= len(positions) <= 20:
        raise ValueError('Provide 1 to 20 positions.')
    # Validate every row before initiating any external requests.
    prepared, seen = [], set()
    for row in positions:
        if not isinstance(row, dict):
            raise ValueError('Invalid position format.')
        ticker = normalize_ticker(row.get('ticker'))
        side = row.get('side')
        if side not in ('long', 'short'):
            raise ValueError('Side must be long or short.')
        if ticker in seen:
            raise ValueError(f'Combine duplicate ticker {ticker} into a single net position.')
        seen.add(ticker)
        shares = number(row.get('shares'), 'Shares', 0.000001, 1e8)
        entry = number(row.get('entry_price'), 'Entry price', 0.000001, 1e8)
        prepared.append((ticker, side, shares, entry))
    provider = quote_provider or get_quote
    rows, long_entry, short_entry, long_now, short_now, pnl = [], 0., 0., 0., 0., 0.
    for ticker, side, shares, entry in prepared:
        quote = provider(ticker)
        price = number(quote['price'], 'Quote price', 0.000001, 1e8)
        if quote.get('currency') != 'USD':
            raise ValueError('Only USD prices are supported.')
        initial, current = shares * entry, shares * price
        gain = (current - initial) * (1 if side == 'long' else -1)
        if side == 'long':
            long_entry += initial; long_now += current
        else:
            short_entry += initial; short_now += current
        pnl += gain
        rows.append(dict(ticker=ticker, side=side, shares=shares, entry_price=entry,
                         price=price, market_value=current, price_pnl=gain,
                         currency='USD', as_of=quote['as_of'], fetched_at=quote.get('fetched_at'), source=quote.get('source', 'test fixture')))
    years = days / 365
    debt = max(long_entry - equity, 0)
    short_average = (short_entry + short_now) / 2
    costs = dict(financing=debt * finance * years, borrow=short_average * borrow * years,
                 rebate=short_average * rebate * years, management=equity * fee * years,
                 transaction=(long_entry + short_entry + long_now + short_now) * trade)
    net_cost = costs['financing'] + costs['borrow'] + costs['management'] + costs['transaction'] - costs['rebate']
    ending = equity + pnl - net_cost
    # Short-sale proceeds are collateral, not extra initial investor wealth.
    return dict(positions=rows, initial_cash=equity, long_entry=long_entry, short_entry=short_entry,
                long_current=long_now, short_current=short_now,
                initial_net_exposure=(long_entry-short_entry)/equity,
                initial_gross_exposure=(long_entry+short_entry)/equity,
                current_net_exposure=(long_now-short_now)/ending if ending > 0 else None,
                current_gross_exposure=(long_now+short_now)/ending if ending > 0 else None,
                financing_principal=debt, short_collateral=short_entry,
                price_pnl=pnl, costs=costs, net_cost=net_cost, net_pnl=pnl-net_cost,
                estimated_equity=ending, return_pct=(pnl-net_cost)/equity*100,
                holding_days=days, currency='USD', tax_included=False,
                scope='Price-only snapshot with estimated costs; no dividends, taxes, margin liquidation, historical rebalancing or tax-loss harvesting. No intermediate cash flows. Entry prices and holding days are user assumptions; quote is the latest available daily bar, potentially incomplete during a trading session.')
