import unittest
from copy import deepcopy
from p107.portfolio import calculate_portfolio
from p107.market_data import normalize_ticker


def inputs():
    return dict(initial_cash=100,holding_days=365,financing_pct=0,borrow_pct=0,rebate_pct=0,
                manager_pct=0,transaction_pct=0,positions=[dict(ticker='AAPL',side='long',shares=130,entry_price=1),dict(ticker='MSFT',side='short',shares=30,entry_price=1)])


def quote(ticker):
    return dict(price={'AAPL':1.1,'MSFT':1.2}[ticker],currency='USD',as_of='2026-10-30T00:00:00-04:00')


class PortfolioTests(unittest.TestCase):
    def test_130_30_return_and_no_free_short_proceeds(self):
        data=inputs();before=deepcopy(data);r=calculate_portfolio(data,quote)
        self.assertAlmostEqual(r['price_pnl'],7)
        self.assertAlmostEqual(r['estimated_equity'],107)
        self.assertAlmostEqual(r['return_pct'],7)
        self.assertAlmostEqual(r['initial_gross_exposure'],1.6)
        self.assertAlmostEqual(r['initial_net_exposure'],1)
        self.assertEqual(data,before)

    def test_explicit_cost_conventions(self):
        data=inputs();data.update(financing_pct=10,borrow_pct=20,rebate_pct=10,manager_pct=1,transaction_pct=1)
        r=calculate_portfolio(data,quote)
        for key,expected in dict(financing=3,borrow=6.6,rebate=3.3,management=1,transaction=3.39).items():
            self.assertAlmostEqual(r['costs'][key],expected)
        self.assertAlmostEqual(r['net_pnl'],-3.69)

    def test_invalid_rows_rejected_before_quotes(self):
        for key,value in [('shares',0),('entry_price',-1),('side','buy'),('ticker','2330.TW')]:
            data=inputs();data['positions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                calculate_portfolio(data,lambda ticker:self.fail('Must validate before external request'))

    def test_duplicate_symbols_and_nonfinite_equity(self):
        data=inputs();data['positions'][1]['ticker']='aapl'
        with self.assertRaises(ValueError):calculate_portfolio(data,quote)
        data=inputs();data['initial_cash']=float('nan')
        with self.assertRaises(ValueError):calculate_portfolio(data,quote)

    def test_no_cost_when_days_zero_except_trading(self):
        data=inputs();data.update(holding_days=0,financing_pct=10,borrow_pct=10,manager_pct=10)
        self.assertAlmostEqual(calculate_portfolio(data,quote)['net_cost'],0)

    def test_usd_required_and_nonpositive_equity_exposure(self):
        with self.assertRaises(ValueError):calculate_portfolio(inputs(),lambda ticker:dict(price=1,currency='TWD',as_of='x'))
        r=calculate_portfolio(inputs(),lambda ticker:dict(price=100 if ticker=='MSFT' else 1,currency='USD',as_of='x'))
        self.assertLess(r['estimated_equity'],0)
        self.assertIsNone(r['current_gross_exposure'])

    def test_ticker_normalization(self):
        self.assertEqual(normalize_ticker(' brk-b '),'BRK-B')
        for value in ['',None,'AAPL MSFT','<script>']:
            with self.assertRaises(ValueError):normalize_ticker(value)
