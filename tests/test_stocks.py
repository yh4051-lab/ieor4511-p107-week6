import unittest
from datetime import date
from unittest.mock import patch, MagicMock
import sys
from p107.stocks import validate_inputs, simulate, run


def inputs():
    return dict(long_tickers='AAA, BBB', short_tickers='CCC', start='2020-01-01',
                end='2020-01-03', initial_cash=1000, short_pct=30,
                financing_pct=0, borrow_pct=0, fee_pct=0)


def prices():
    return {'AAA': {'2020-01-01': 100, '2020-01-02': 110, '2020-01-03': 120},
            'BBB': {'2020-01-01': 100, '2020-01-02': 100, '2020-01-03': 100},
            'CCC': {'2020-01-01': 100, '2020-01-02': 90, '2020-01-03': 80}}


class StockTests(unittest.TestCase):
    def test_hand_calculated_equal_allocations_and_short_sign(self):
        result = simulate(validate_inputs(inputs()), prices())
        self.assertAlmostEqual(result['summary']['long_pnl'], 130)
        self.assertAlmostEqual(result['summary']['short_pnl'], 60)
        self.assertAlmostEqual(result['summary']['ending_equity'], 1190)
        self.assertAlmostEqual(result['summary']['net_return_pct'], 19)
        self.assertEqual(result['summary']['max_drawdown_pct'], 0)

    def test_costs_use_previous_values_and_calendar_days(self):
        raw = inputs(); raw.update(financing_pct=10, borrow_pct=10, fee_pct=1)
        out = simulate(validate_inputs(raw), prices())['summary']
        finance = 300*.1*2/365
        borrow = (300+270)*.1/365
        fee_day1 = 1000*.01/365
        nav_day1 = 1095-300*.1/365-300*.1/365-fee_day1
        fees = fee_day1+nav_day1*.01/365
        self.assertAlmostEqual(out['financing_cost'], finance)
        self.assertAlmostEqual(out['borrow_cost'], borrow)
        self.assertAlmostEqual(out['management_fee'], fees)
        self.assertAlmostEqual(out['ending_equity'], 1190-finance-borrow-fees)

    def test_price_scaling_preserves_return(self):
        expected = simulate(validate_inputs(inputs()), prices())['summary']
        scaled = {s:{d:v*3 for d,v in series.items()} for s,series in prices().items()}
        self.assertEqual(expected, simulate(validate_inputs(inputs()), scaled)['summary'])

    def test_short_rise_loses_and_drawdown(self):
        p=prices(); p['CCC']['2020-01-03']=200
        out=simulate(validate_inputs(inputs()),p)['summary']
        self.assertEqual(out['short_pnl'],-300)
        self.assertLess(out['max_drawdown_pct'],0)

    def test_missing_session_rejected(self):
        p=prices(); del p['AAA']['2020-01-02']
        with self.assertRaisesRegex(ValueError,'missing trading sessions'):
            simulate(validate_inputs(inputs()),p)

    def test_partial_history_rejected(self):
        raw=inputs();raw['start']='2019-01-01'
        with self.assertRaisesRegex(ValueError,'Full requested history'):
            simulate(validate_inputs(raw),prices())

    def test_insolvency_rejected(self):
        p=prices();p['CCC']['2020-01-03']=1000
        with self.assertRaisesRegex(ValueError,'zero or becomes negative'):
            simulate(validate_inputs(inputs()),p)

    def test_invalid_inputs(self):
        for changes in [dict(long_tickers='AAA,AAA'),dict(short_tickers='AAA'),
                        dict(long_tickers='<script>'),dict(short_tickers=''),
                        dict(initial_cash=True),dict(fee_pct=float('nan')),
                        dict(end='not-date'),dict(end='2099-01-01'),dict(short_pct=-30)]:
            raw=inputs();raw.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_inputs(raw)

    def test_download_errors_and_currency(self):
        fake=MagicMock();fake.Ticker.return_value.history.side_effect=RuntimeError('network')
        with patch.dict(sys.modules,{'yfinance':fake}),self.assertRaisesRegex(ValueError,'Yahoo data unavailable'):
            run(inputs())
        fake.Ticker.return_value.history.side_effect=None
        fake.Ticker.return_value.get_history_metadata.return_value={'currency':'EUR'}
        with patch.dict(sys.modules,{'yfinance':fake}),self.assertRaisesRegex(ValueError,'USD'):
            run(inputs())

    def test_provider_parameters_and_orchestration(self):
        fake=MagicMock();fake.Ticker.return_value.get_history_metadata.return_value={'currency':'USD'}
        frame=MagicMock();frame.empty=False;frame.__contains__.return_value=True
        class Stamp:
            def __init__(self,d):self.d=d
            def date(self):return date.fromisoformat(self.d)
        frame.__getitem__.return_value.items.return_value=[(Stamp('2020-01-01'),100),(Stamp('2020-01-03'),110)]
        fake.Ticker.return_value.history.return_value=frame
        with patch.dict(sys.modules,{'yfinance':fake}):result=run(inputs())
        self.assertAlmostEqual(result['summary']['ending_equity'],1100)
        kwargs=fake.Ticker.return_value.history.call_args.kwargs
        self.assertEqual(kwargs['end'],'2020-01-04')
        self.assertTrue(kwargs['auto_adjust'])
        self.assertEqual(kwargs['timeout'],15)


if __name__ == '__main__':unittest.main()
