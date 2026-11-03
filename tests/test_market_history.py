"""Offline corporate-action and coverage tests; no Yahoo or pandas required."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from p107 import market_data as md


def row(day, close, dividend=0., split=0.):
    return dict(date=day, close=float(close), dividend=float(dividend), split=float(split))


class NominalPriceTests(unittest.TestCase):
    def test_hash_survives_browser_integer_float_spelling(self):
        numeric = dict(dates=['2020-01-02','2020-01-03'],prices={'AAPL':[100.0,101.5]},
                       dividends={'AAPL':[0.0,1.0]},splits={'AAPL':[0.0,2.0]})
        exported = deepcopy(numeric)
        for group in ('prices','dividends','splits'):
            exported[group]['AAPL'] = [int(v) if float(v).is_integer() else v for v in numeric[group]['AAPL']]
        self.assertEqual(md.history_data_sha(numeric),md.history_data_sha(exported))
        exported['prices']['AAPL'][0] += 1
        self.assertNotEqual(md.history_data_sha(numeric),md.history_data_sha(exported))

    def test_forward_split_is_undone_only_before_effective_date(self):
        raw = [row('2020-01-02',50,.5),row('2020-01-03',55,0,2),row('2020-01-06',60)]
        result=md.reconstruct_nominal_rows(raw)
        self.assertEqual([r['close'] for r in result],[100,55,60])
        self.assertEqual(result[0]['dividend'],1)
        self.assertEqual(result[1]['split'],2)
        # Two new shares at $55 preserve the split-adjusted marked value.
        self.assertEqual(result[1]['close']*2,110)

    def test_reverse_and_multiple_splits(self):
        raw=[row('2020-01-02',10),row('2020-01-03',20,0,.1),row('2020-01-06',25,0,2)]
        result=md.reconstruct_nominal_rows(raw)
        self.assertEqual([r['close'] for r in result],[2,40,25])

    def test_bad_or_duplicate_observations_are_not_silently_dropped(self):
        for rows in [[row('2020-01-02',float('nan'))],
                     [row('2020-01-02',1),row('2020-01-02',2)],
                     [row('2020-01-02',1,split=-1)],[]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                md.reconstruct_nominal_rows(rows)

    def test_exact_calendar_rejects_preipo_and_missing_sessions(self):
        records={'AAPL':[row('2020-01-03',5)],'SPY':[row('2020-01-02',10),row('2020-01-03',11)]}
        with self.assertRaisesRegex(ValueError,'Missing sessions'):
            md._aligned_result(['AAPL','SPY'],records,date(2020,1,2),date(2020,1,3),{},'now','test')

    def test_numeric_dataset_hash_ignores_fetch_time(self):
        records={'SPY':[row('2020-01-02',10),row('2020-01-03',11)]}
        one=md._aligned_result(['SPY'],records,date(2020,1,2),date(2020,1,3),{},'one','test')
        two=md._aligned_result(['SPY'],records,date(2020,1,2),date(2020,1,3),{},'two','test')
        self.assertEqual(one['metadata']['data_sha256'],two['metadata']['data_sha256'])

    def test_today_future_and_excessive_windows_rejected(self):
        today=datetime.now(ZoneInfo('America/New_York')).date()
        cases=[('2020-01-02',today.isoformat()),('2020-01-02',(today+timedelta(days=1)).isoformat()),('2000-01-02','2020-01-03'),('2020-01-03','2020-01-02'),('20200102','2020-01-03')]
        for start,end in cases:
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                md._validate_window(start,end)

    def test_loader_fetches_beyond_exit_for_splits_and_copies_cache(self):
        calls=[]
        raw=[row('2020-01-02',25,.25),row('2020-01-03',26),row('2020-01-06',27,0,2)]
        class Frame:
            empty=False
            def iterrows(self):
                for r in raw:
                    yield datetime.fromisoformat(r['date']),{'Close':r['close'],'Dividends':r['dividend'],'Stock Splits':r['split']}
        class Ticker:
            def __init__(self,symbol): self.symbol=symbol
            def history(self,**kwargs): calls.append(kwargs);return Frame()
            def get_history_metadata(self): return {'currency':'USD','exchangeName':'NMS','instrumentType':'EQUITY'}
        md._history_cache.clear()
        try:
            with patch.object(md,'_yf',return_value=SimpleNamespace(Ticker=Ticker,__version__='fixture')):
                result=md.load_history(['AAPL'],'2020-01-02','2020-01-03')
                self.assertGreater(calls[0]['end'],'2020-01-06')
                self.assertEqual(result['prices']['AAPL'],[50,52])
                self.assertEqual(result['dividends']['AAPL'],[.5,0])
                self.assertEqual(result['metadata']['tickers']['AAPL']['post_window_split_events'],[{'date':'2020-01-06','ratio':2}])
                result['prices']['AAPL'][0]=999
                again=md.load_history(['AAPL'],'2020-01-02','2020-01-03')
                self.assertEqual(again['prices']['AAPL'][0],50)
                self.assertEqual(len(calls),1)
        finally:
            md._history_cache.clear()


if __name__=='__main__':
    unittest.main()
