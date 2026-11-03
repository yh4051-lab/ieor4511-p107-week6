"""Manual, fixed-unit long/short historical total-return experiment (pre-tax)."""
from datetime import date, timedelta, datetime, timezone
import math
import re


def validate_inputs(raw):
    if not isinstance(raw, dict):
        raise ValueError('Inputs must be an object.')
    required = {'long_tickers', 'short_tickers', 'start', 'end', 'initial_cash',
                'short_pct', 'financing_pct', 'borrow_pct', 'fee_pct'}
    if set(raw) != required:
        raise ValueError('Missing or unknown stock inputs.')
    out = dict(raw)
    for side in ('long_tickers', 'short_tickers'):
        if not isinstance(raw[side], str) or len(raw[side]) > 300:
            raise ValueError('Enter ticker symbols separated by commas.')
        symbols = raw[side].upper().replace('，', ',').replace(',', ' ').split()
        if not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols):
            raise ValueError('Enter 1 to 10 unique symbols on each side.')
        if any(not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,14}', s) for s in symbols):
            raise ValueError('Invalid ticker format. Example: AAPL, MSFT or BRK-B.')
        out[side] = symbols
    if set(out['long_tickers']) & set(out['short_tickers']):
        raise ValueError('A symbol cannot be both long and short.')
    try:
        start, end = date.fromisoformat(raw['start']), date.fromisoformat(raw['end'])
    except (ValueError, TypeError):
        raise ValueError('Enter dates as YYYY-MM-DD.') from None
    if not date(1970, 1, 1) <= start < end <= date.today():
        raise ValueError('Choose past dates, with start before end (1970 or later).')
    if (end - start).days > 366 * 20:
        raise ValueError('Use a date range no longer than 20 years.')
    for key, low, high in [('initial_cash', 100, 100000000), ('short_pct', 1, 100),
                           ('financing_pct', 0, 100), ('borrow_pct', 0, 100), ('fee_pct', 0, 20)]:
        v = raw[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f'{key} must be a finite number between {low} and {high}.')
    return out


def download_prices(inputs):
    """Explicitly adjusted series: a total-return proxy, never tax-lot prices."""
    try:
        import yfinance as yf
    except ImportError:
        raise ValueError('Install the stock dependency: py -3.12 -m pip install -r requirements-stocks.txt') from None
    prices = {}
    end_exclusive = (date.fromisoformat(inputs['end']) + timedelta(days=1)).isoformat()
    for symbol in inputs['long_tickers'] + inputs['short_tickers']:
        try:
            ticker = yf.Ticker(symbol)
            frame = ticker.history(start=inputs['start'], end=end_exclusive, interval='1d',
                                   auto_adjust=True, actions=False, timeout=15, raise_errors=True)
            metadata = ticker.get_history_metadata()
        except Exception:
            raise ValueError(f'Yahoo data unavailable for {symbol}. Check the symbol, internet connection, dates or rate limits; no replacement data was used.') from None
        if metadata.get('currency') != 'USD':
            raise ValueError(f'{symbol}: only verified USD price series are supported; no FX conversion is performed.')
        if frame is None or frame.empty or 'Close' not in frame:
            raise ValueError(f'No prices for {symbol} in this period.')
        series = {}
        for timestamp, value in frame['Close'].items():
            v = float(value)
            if math.isfinite(v) and v > 0:
                series[timestamp.date().isoformat()] = v
        if len(series) < 2:
            raise ValueError(f'Not enough valid prices for {symbol}.')
        prices[symbol] = series
    return prices


def simulate(inputs, prices):
    """Hold initial adjusted-price units; equal allocation within each side; no rebalancing."""
    symbols = inputs['long_tickers'] + inputs['short_tickers']
    first = max(min(prices[s]) for s in symbols)
    last = min(max(prices[s]) for s in symbols)
    if first >= last:
        raise ValueError('The selected symbols have no overlapping history.')
    # Do not silently truncate away delistings, later IPOs, or unavailable boundaries.
    for symbol in symbols:
        if (date.fromisoformat(first) - date.fromisoformat(min(prices[symbol]))).days > 7 or (date.fromisoformat(max(prices[symbol])) - date.fromisoformat(last)).days > 7:
            raise ValueError('Price histories have different coverage. Choose dates covered by every selected symbol.')
    if (date.fromisoformat(first) - date.fromisoformat(inputs['start'])).days > 7 or (date.fromisoformat(inputs['end']) - date.fromisoformat(last)).days > 7:
        raise ValueError('Full requested history is unavailable. Choose dates covered by every symbol.')
    sessions = sorted({d for s in symbols for d in prices[s] if first <= d <= last})
    if any(any(d not in prices[s] for s in symbols) for d in sessions):
        raise ValueError('A symbol has missing trading sessions. No missing prices were filled.')
    if len(sessions) < 2:
        raise ValueError('Choose a period containing at least two common trading sessions.')
    initial = inputs['initial_cash']
    short_fraction = inputs['short_pct'] / 100
    allocations = {s: initial * (1 + short_fraction) / len(inputs['long_tickers']) for s in inputs['long_tickers']}
    allocations.update({s: -initial * short_fraction / len(inputs['short_tickers']) for s in inputs['short_tickers']})
    finance = borrow = fees = 0.0
    ledger = []
    peak, drawdown = initial, 0.0
    previous_nav = initial
    for idx, d in enumerate(sessions):
        long_value = sum(allocations[s] * prices[s][d] / prices[s][first] for s in inputs['long_tickers'])
        short_value = sum(-allocations[s] * prices[s][d] / prices[s][first] for s in inputs['short_tickers'])
        if idx:
            previous = ledger[-1]
            years = (date.fromisoformat(d) - date.fromisoformat(sessions[idx-1])).days / 365
            finance += initial * short_fraction * inputs['financing_pct'] / 100 * years
            borrow += previous['short_value'] * inputs['borrow_pct'] / 100 * years
            fees += previous_nav * inputs['fee_pct'] / 100 * years
        nav = long_value - short_value - finance - borrow - fees
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError(f'Equity reaches zero or becomes negative on {d}. This fixed-unit experiment cannot continue through insolvency; reduce exposure or shorten the period.')
        long_pnl = long_value - initial * (1 + short_fraction)
        short_pnl = initial * short_fraction - short_value
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
        ledger.append(dict(date=d, long_value=long_value, short_value=short_value,
                           long_pnl=long_pnl, short_pnl=short_pnl, financing_cost=finance,
                           borrow_cost=borrow, management_fee=fees, equity=nav))
        previous_nav = nav
    positions = [dict(ticker=s, side='long' if allocations[s] > 0 else 'short',
                      initial_notional=abs(allocations[s]),
                      adjusted_start=prices[s][first], adjusted_end=prices[s][last],
                      total_return_pct=(prices[s][last] / prices[s][first] - 1) * 100,
                      pnl=allocations[s] * (prices[s][last] / prices[s][first] - 1)) for s in symbols]
    final = ledger[-1]
    return dict(inputs=inputs, effective_start=first, effective_end=last,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                summary=dict(initial_cash=initial, ending_equity=final['equity'],
                             net_pnl=final['equity']-initial,
                             net_return_pct=(final['equity']/initial-1)*100,
                             long_pnl=final['long_pnl'], short_pnl=final['short_pnl'],
                             financing_cost=finance, borrow_cost=borrow, management_fee=fees,
                             max_drawdown_pct=drawdown*100),
                positions=positions, ledger=ledger,
                adjusted_prices=[dict(date=d, **{s: prices[s][d] for s in symbols}) for d in sessions],
                assumptions=[
                    'Pre-tax historical experiment; not the tax-loss-harvesting model or a direct-indexing strategy.',
                    'Yahoo adjusted Close is a total-return proxy including dividend/split adjustments; not executable prices or tax basis. Short-side dividend effects are approximated by the negative adjusted return.',
                    'Equal initial allocation within each side; fixed adjusted-price units, fractional units, no rebalancing. Exposure drifts.',
                    'Financing on initial short-extension notional; borrow on prior-session short market value; management fee on prior-session equity; ACT/365 daily accrual.',
                    'Short proceeds offset the extra long purchase. Financing is an illustrative extension charge; no cash interest or short rebate.',
                    'No taxes, harvesting, commissions, slippage, margin calls, borrow availability checks or forced covering. Margin calls can occur before equity reaches zero.',
                    'Manual historical selections can contain hindsight and survivorship bias.'])


def run(raw):
    inputs = validate_inputs(raw)
    return simulate(inputs, download_prices(inputs))
