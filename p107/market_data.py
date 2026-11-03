"""Verified-format Yahoo daily observations for US stock research.

Yahoo Close/Dividends are split-adjusted even with auto_adjust=False. Historical
research reverses those adjustments into nominal observations and supplies the
split events separately; the ledger must apply each event once.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
import threading
import time
from zoneinfo import ZoneInfo

_cache = {}
_history_cache = OrderedDict()
_lock = threading.RLock()
US_EXCHANGES = {'NMS', 'NGM', 'NCM', 'NYQ', 'ASE', 'PCX', 'BTS', 'BATS', 'NAS', 'NASDAQ', 'NYSE', 'ARCA'}
PRICE_CONVENTION = 'Nominal daily Close and cash dividend per share, reconstructed from Yahoo split-adjusted observations using all splits after each observation through retrieval; apply returned split events once before that session valuation.'


def normalize_ticker(value):
    if not isinstance(value, str):
        raise ValueError('Ticker must be a string.')
    ticker = value.strip().upper()
    if re.fullmatch(r'[A-Z][A-Z0-9-]{0,14}', ticker) is None:
        raise ValueError('Enter a US ticker such as AAPL, MSFT or BRK-B.')
    return ticker


def _yf():
    try:
        import yfinance as yf
    except ImportError as error:
        raise ValueError('Install the optional stock dependencies with: py -3 -m pip install -r requirements-stock.txt, then restart the server.') from error
    return yf


def _market_metadata(ticker, stock):
    metadata = stock.get_history_metadata()
    if metadata.get('currency') != 'USD' or metadata.get('exchangeName') not in US_EXCHANGES:
        raise ValueError(f'{ticker} is not a supported USD-listed US market security.')
    if metadata.get('instrumentType') not in ('EQUITY', 'ETF'):
        raise ValueError(f'{ticker} is not an equity or ETF.')
    return metadata


def get_quote(symbol):
    """Return the latest available daily bar; today's bar can be incomplete."""
    ticker = normalize_ticker(symbol)
    with _lock:
        cached = _cache.get(ticker)
        if cached and time.monotonic() - cached[0] < 60:
            return dict(cached[1])
    yf = _yf()
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period='5d', interval='1d', auto_adjust=False, actions=True, timeout=12)
        if history.empty:
            raise ValueError(f'No valid price observations were returned for {ticker}.')
        _market_metadata(ticker, stock)
        closes = history['Close'].dropna()
        if closes.empty:
            raise ValueError(f'{ticker} has no daily Close observations.')
        price = float(closes.iloc[-1])
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f'{ticker} has an invalid price.')
        quote = dict(ticker=ticker, price=price, currency='USD',
                     as_of=closes.index[-1].isoformat(), source='Yahoo Finance / yfinance',
                     fetched_at=datetime.now(timezone.utc).isoformat(),
                     price_type='latest_available_daily_bar')
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f'The quote service is unavailable for {ticker}; please try again later.') from error
    with _lock:
        if len(_cache) >= 200:
            _cache.pop(next(iter(_cache)))
        _cache[ticker] = (time.monotonic(), quote)
    return dict(quote)


def _parse_date(value, name):
    if not isinstance(value, str):
        raise ValueError(f'{name} must be an ISO date (YYYY-MM-DD).')
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f'{name} must be an ISO date (YYYY-MM-DD).') from error
    if result.isoformat() != value:
        raise ValueError(f'{name} must be an ISO date (YYYY-MM-DD).')
    return result


def _validate_window(start_date, end_date):
    start, end = _parse_date(start_date, 'Start date'), _parse_date(end_date, 'End date')
    today = datetime.now(ZoneInfo('America/New_York')).date()
    if end >= today:
        raise ValueError('End date must be before today in New York; incomplete current-day bars are excluded.')
    if start >= end:
        raise ValueError('Start date must precede end date.')
    if (end - start).days > 3660:
        raise ValueError('Choose a research interval of at most 10 years (3660 days).')
    return start, end, today


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def history_data_sha(data):
    """Hash numeric observations independently of JSON integer/float spelling.

    Browser JSON exports turn 1.0 into 1; normalize numeric series before hashing.
    """
    canonical = {'dates': data['dates']}
    for group in ('prices', 'dividends', 'splits'):
        canonical[group] = {ticker: [float(value) for value in values]
                            for ticker, values in data[group].items()}
    return _sha(canonical)


def reconstruct_nominal_rows(rows):
    """Pure conversion of chronological Yahoo split-adjusted rows.

    Each row is {date, close, dividend, split}; split=0 means no event. A split
    effective on a date has already been reflected in that date's prices, so
    only STRICTLY LATER events belong in that date's adjustment factor.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError('Historical data is empty.')
    converted, factor = [], 1.0
    previous = None
    for row in rows:
        current = _parse_date(row['date'], 'Observation date')
        if previous is not None and current <= previous:
            raise ValueError('Historical dates must be unique and strictly increasing.')
        previous = current
        for key in ('close', 'dividend', 'split'):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Invalid historical {key} observation on {row["date"]}.')
        if row['close'] <= 0 or row['dividend'] < 0 or row['split'] < 0:
            raise ValueError(f'Invalid historical price or corporate action on {row["date"]}.')
    for row in reversed(rows):
        price, dividend = row['close'] * factor, row['dividend'] * factor
        if not math.isfinite(price) or price <= 0 or not math.isfinite(dividend):
            raise ValueError('Split reconstruction produced an invalid observation.')
        converted.append(dict(date=row['date'], close=price, dividend=dividend,
                              split=row['split'], split_adjustment_factor=factor))
        if row['split']:
            factor *= row['split']
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('Invalid cumulative split adjustment factor.')
    return list(reversed(converted))


def _aligned_result(tickers, records, start, end, ticker_metadata, fetched_at, yf_version):
    """Validate an exact common calendar; never silently intersect missing bars."""
    windows = {ticker: [r for r in records[ticker] if start <= date.fromisoformat(r['date']) <= end]
               for ticker in tickers}
    reference = tickers[-1]
    dates = [r['date'] for r in windows[reference]]
    if len(dates) < 2:
        raise ValueError(f'{reference} has fewer than two trading sessions in the requested interval.')
    for ticker in tickers:
        actual = [r['date'] for r in windows[ticker]]
        if actual != dates:
            missing = sorted(set(dates) - set(actual))
            extra = sorted(set(actual) - set(dates))
            raise ValueError(f'{ticker} does not match the {reference} trading calendar. '
                             f'Missing sessions: {missing[:5]}; unexpected sessions: {extra[:5]}. '
                             'Choose an interval with complete observations for every selected security.')
    result = dict(dates=dates,
                  prices={s: [r['close'] for r in windows[s]] for s in tickers},
                  dividends={s: [r['dividend'] for r in windows[s]] for s in tickers},
                  splits={s: [r['split'] for r in windows[s]] for s in tickers})
    result['metadata'] = dict(source='Yahoo Finance / yfinance', yfinance_version=yf_version,
                              fetched_at=fetched_at, requested_start=start.isoformat(),
                              requested_end=end.isoformat(), actual_start=dates[0], actual_end=dates[-1],
                              calendar_reference=reference, tickers=ticker_metadata,
                              price_convention=PRICE_CONVENTION,
                              assumptions=[
                                  'Every selected security must match the reference trading calendar exactly; no prices are forward-filled.',
                                  'Yahoo Close and Dividends are treated as split-adjusted. Nominal values undo every later split found through retrieval, including post-window events.',
                                  'Splits apply before same-day valuation and dividend payment. Dividend events are cash distributions on Yahoo ex-dates; withholding, qualified status and separate capital-gain distributions are not inferred.',
                                  'US USD equities/ETFs only. Delisted securities, missing observations or unavailable Yahoo history can prevent a run.',
                                  'Current-day bars are excluded from the requested research window. Historical observations can be revised by the provider.'
                              ])
    # Retrieval timestamps do not change the numeric dataset identity.
    result['metadata']['data_sha256'] = history_data_sha(result)
    return result


def load_history(tickers, start_date, end_date):
    """Load inclusive historical sessions and audit metadata for manual portfolios.

    The final ticker is the calendar reference (normally the benchmark). Fetch
    through the current day, even when the requested exit is earlier, because
    Yahoo can adjust older observations for splits AFTER the requested exit.
    """
    if not isinstance(tickers, (list, tuple)) or not 1 <= len(tickers) <= 21:
        raise ValueError('Provide 1 to 21 US ticker symbols, including the benchmark.')
    normalized = [normalize_ticker(s) for s in tickers]
    reference = normalized[-1]
    symbols = [s for s in dict.fromkeys(normalized) if s != reference] + [reference]
    start, end, today = _validate_window(start_date, end_date)
    key = (tuple(symbols), start.isoformat(), end.isoformat(), today.isoformat())
    with _lock:
        cached = _history_cache.get(key)
        if cached and time.monotonic() - cached[0] < 600:
            _history_cache.move_to_end(key)
            return deepcopy(cached[1])
    yf = _yf()
    records, metadata = {}, {}
    for symbol in symbols:
        try:
            stock = yf.Ticker(symbol)
            frame = stock.history(start=start.isoformat(), end=(today + timedelta(days=1)).isoformat(),
                                  interval='1d', auto_adjust=False, back_adjust=False,
                                  actions=True, keepna=True, timeout=15)
            if frame.empty:
                raise ValueError(f'No history returned for {symbol}.')
            info = _market_metadata(symbol, stock)
            raw = []
            for timestamp, row in frame.iterrows():
                # Do not drop NaN prices or silently substitute zero returns.
                raw.append(dict(date=timestamp.date().isoformat(), close=float(row['Close']),
                                dividend=float(row.get('Dividends', 0.0)),
                                split=float(row.get('Stock Splits', 0.0))))
            nominal = reconstruct_nominal_rows(raw)
            records[symbol] = nominal
            metadata[symbol] = dict(currency='USD', exchange=info['exchangeName'],
                                    instrument_type=info['instrumentType'],
                                    timezone=info.get('exchangeTimezoneName'),
                                    raw_history_sha256=_sha(raw),
                                    raw_first_date=raw[0]['date'], raw_last_date=raw[-1]['date'],
                                    post_window_split_events=[dict(date=r['date'], ratio=r['split'])
                                                              for r in nominal if r['split'] and date.fromisoformat(r['date']) > end])
        except ValueError as error:
            raise ValueError(f'{symbol}: {error}') from error
        except Exception as error:
            raise ValueError(f'Yahoo history is unavailable for {symbol}; no fabricated data was substituted.') from error
    result = _aligned_result(symbols, records, start, end, metadata,
                             datetime.now(timezone.utc).isoformat(), getattr(yf, '__version__', 'unknown'))
    with _lock:
        _history_cache[key] = (time.monotonic(), deepcopy(result))
        _history_cache.move_to_end(key)
        while len(_history_cache) > 12:
            _history_cache.popitem(last=False)
    return result
