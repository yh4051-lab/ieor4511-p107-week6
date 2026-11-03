"""Independent hand-calculated controls for the three research levels.

All histories are synthetic: these tests never request Yahoo data.
"""
from copy import deepcopy
from datetime import date
import unittest

from p107.research import run_research


def configuration(level=2, start='2020-01-02', end='2020-01-03'):
    return dict(level=level, initial_cash=100, start_date=start, end_date=end,
                benchmark='SPY', positions=[dict(ticker='AAPL', side='long', shares=1)],
                financing_pct=0, borrow_pct=0, rebate_pct=0, manager_pct=0,
                transaction_pct=0, tax_st_pct=40, tax_lt_pct=20,
                dividend_tax_pct=25, outside_st_gain=0, outside_lt_gain=0,
                harvest_threshold_pct=10, cooldown_days=30)


def history(dates, prices, dividends=None, splits=None):
    n = len(dates)
    return dict(dates=dates, prices=prices,
                dividends={s: (dividends or {}).get(s, [0] * n) for s in prices},
                splits={s: (splits or {}).get(s, [0] * n) for s in prices},
                metadata=dict(source='Synthetic unit-test observations',
                              data_sha256='synthetic-fixture', price_convention='Nominal prices'))


def run(config, data):
    return run_research(config, lambda tickers, start, end: deepcopy(data))


class ResearchTests(unittest.TestCase):
    def test_level_one_130_30_seven_percent_and_matched_benchmark(self):
        c = configuration(1)
        c['positions'] = [dict(ticker='AAPL', side='long', shares=130),
                          dict(ticker='MSFT', side='short', shares=30)]
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [1, 1.1], 'MSFT': [1, 1.2], 'SPY': [1, 1.05]})
        r = run(c, d)
        s = r['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 107)
        self.assertAlmostEqual(s['benchmark_wealth'], 105)
        self.assertAlmostEqual(s['incremental_wealth'], 2)
        self.assertAlmostEqual(s['initial_net_exposure'], 1)
        self.assertAlmostEqual(s['initial_gross_exposure'], 1.6)
        self.assertAlmostEqual(s['return_pct'], 7)
        self.assertAlmostEqual(s['wealth_identity_error'], 0)

    def test_level_one_ignores_cost_tax_outside_gain_and_dividend_inputs(self):
        c = configuration(1)
        c.update(financing_pct=10, borrow_pct=10, manager_pct=10,
                 transaction_pct=5, outside_st_gain=100)
        d = history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 110], 'SPY': [100, 100]},
                    dividends={'AAPL': [0, 10]})
        s = run(c, d)['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 110)
        for key in ('costs', 'capital_tax', 'dividend_cash', 'dividend_tax', 'outside_gross_proceeds'):
            self.assertEqual(s[key], 0)

    def test_constant_quantities_do_not_silently_rebalance(self):
        c = configuration(1, end='2020-01-06')
        c['positions'] = [dict(ticker='AAPL', side='long', shares=1.3),
                          dict(ticker='MSFT', side='short', shares=.3)]
        d = history(['2020-01-02', '2020-01-03', '2020-01-06'],
                    {'AAPL': [100, 110, 100], 'MSFT': [100, 100, 50], 'SPY': [100, 100, 100]})
        r = run(c, d)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 115)
        self.assertEqual([t['event'] for t in r['trades']], ['open', 'open', 'exit', 'exit'])

    def test_short_sale_proceeds_are_not_extra_wealth(self):
        c = configuration(1)
        c['positions'] = [dict(ticker='AAPL', side='short', shares=1)]
        r = run(c, history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 100], 'SPY': [100, 100]}))
        self.assertEqual(r['daily'][0]['equity'], 100)
        self.assertEqual(r['daily'][0]['short_collateral'], 100)
        self.assertEqual(r['summary']['terminal_wealth'], 100)

    def test_short_gain_and_loss_direction(self):
        c = configuration(1)
        c['positions'] = [dict(ticker='AAPL', side='short', shares=1)]
        for end, expected in [(80, 120), (120, 80)]:
            with self.subTest(price=end):
                r = run(c, history(['2020-01-02', '2020-01-03'], {'AAPL': [100, end], 'SPY': [100, 100]}))
                self.assertAlmostEqual(r['summary']['terminal_wealth'], expected)

    def test_short_term_full_exit_tax_is_actual_dollars(self):
        c = configuration(2)
        s = run(c, history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 200], 'SPY': [100, 200]}))['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 160)
        self.assertAlmostEqual(s['capital_tax'], 40)
        self.assertAlmostEqual(s['exit_tax'], 40)
        self.assertAlmostEqual(s['incremental_wealth'], 0)

    def test_long_term_after_more_than_365_days(self):
        c = configuration(2, end='2021-01-04')
        s = run(c, history(['2020-01-02', '2021-01-04'], {'AAPL': [100, 200], 'SPY': [100, 100]}))['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 180)
        self.assertAlmostEqual(s['capital_tax'], 20)

    def test_exactly_365_days_remains_short_term(self):
        c = configuration(2, end='2021-01-01')
        s = run(c, history(['2020-01-02', '2021-01-01'], {'AAPL': [100, 200], 'SPY': [100, 100]}))['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 160)

    def test_short_sale_tax_is_conservatively_short_term(self):
        c = configuration(2, end='2021-01-04')
        c['positions'] = [dict(ticker='AAPL', side='short', shares=1)]
        r = run(c, history(['2020-01-02', '2021-01-04'], {'AAPL': [100, 50], 'SPY': [100, 100]}))
        self.assertAlmostEqual(r['summary']['capital_tax'], 20)
        self.assertEqual(r['trades'][-1]['character'], 'st')

    def test_long_dividends_taxed_and_short_dividends_paid(self):
        d = history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 100], 'SPY': [100, 100]},
                    dividends={'AAPL': [0, 2]})
        c = configuration(2)
        s = run(c, d)['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 101.5)
        self.assertAlmostEqual(s['dividend_cash'], 2)
        self.assertAlmostEqual(s['dividend_tax'], .5)
        c['positions'][0]['side'] = 'short'
        s = run(c, d)['summary']
        self.assertAlmostEqual(s['terminal_wealth'], 98)
        self.assertAlmostEqual(s['dividend_cash'], -2)
        self.assertEqual(s['dividend_tax'], 0)

    def test_split_changes_quantity_without_creating_profit(self):
        d = history(['2020-01-02', '2020-01-03', '2020-01-06'],
                    {'AAPL': [100, 50, 55], 'SPY': [100, 100, 100]}, splits={'AAPL': [0, 2, 0]})
        for side, expected in [('long', 110), ('short', 90)]:
            c = configuration(1, end='2020-01-06'); c['positions'][0]['side'] = side
            r = run(c, d)
            self.assertAlmostEqual(r['daily'][1]['equity'], 100)
            self.assertAlmostEqual(r['summary']['terminal_wealth'], expected)
            self.assertEqual(r['trades'][-1]['shares'], 2)

    def test_first_bar_dividend_and_split_precede_new_position(self):
        c = configuration(2)
        d = history(['2020-01-02', '2020-01-03'], {'AAPL': [50, 50], 'SPY': [100, 100]},
                    dividends={'AAPL': [2, 0]}, splits={'AAPL': [2, 0]})
        r = run(c, d)
        self.assertEqual(r['summary']['terminal_wealth'], 100)
        self.assertEqual(r['summary']['dividend_cash'], 0)
        self.assertEqual(r['trades'][-1]['shares'], 1)

    def test_short_rebate_income_is_taxed(self):
        c = configuration(2, start='2021-01-04', end='2022-01-04')
        c['positions'] = [dict(ticker='AAPL', side='short', shares=1)]
        c['rebate_pct'] = 10
        d = history(['2021-01-04', '2022-01-04'], {'AAPL': [100, 100], 'SPY': [100, 100]})
        r = run(c, d)['summary']
        self.assertAlmostEqual(r['rebate_tax'], 4)
        self.assertAlmostEqual(r['costs'], -10)
        self.assertAlmostEqual(r['terminal_wealth'], 106)
        self.assertAlmostEqual(r['wealth_identity_error'], 0)

    def test_actual_elapsed_day_costs(self):
        c = configuration(2)
        c.update(financing_pct=10, borrow_pct=20, rebate_pct=10, manager_pct=1,
                 tax_st_pct=0, tax_lt_pct=0)
        c['positions'] = [dict(ticker='AAPL', side='long', shares=130), dict(ticker='MSFT', side='short', shares=30)]
        d = history(['2020-01-02', '2020-01-03'], {'AAPL': [1, 1.1], 'MSFT': [1, 1.2], 'SPY': [1, 1]})
        s = run(c, d)['summary']
        cost = (30*.10 + 30*.20 + 100*.01 - 30*.10)/365
        self.assertAlmostEqual(s['costs'], cost)
        self.assertAlmostEqual(s['terminal_wealth'], 107-cost)

    def test_transaction_costs_charged_on_open_and_exit_and_not_tax_deducted(self):
        c = configuration(2); c['transaction_pct'] = 1
        s = run(c, history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 110], 'SPY': [100, 100]}))['summary']
        self.assertAlmostEqual(s['costs'], 2.1)
        self.assertAlmostEqual(s['capital_tax'], 4)
        self.assertAlmostEqual(s['terminal_wealth'], 103.9)

    def test_unrealized_drawdown_is_not_harvested_loss(self):
        c = configuration(2, end='2020-02-06')
        d = history(['2020-01-02', '2020-02-05', '2020-02-06'], {'AAPL': [100, 70, 100], 'SPY': [100, 100, 100]})
        r = run(c, d)
        self.assertEqual(r['summary']['harvested_loss'], 0)
        self.assertFalse(any(t['event'] == 'harvest' for t in r['trades']))
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 100)

    def test_level_three_next_close_and_cooldown(self):
        c = configuration(3, end='2020-03-10')
        d = history(['2020-01-02', '2020-02-05', '2020-02-06', '2020-03-06', '2020-03-09', '2020-03-10'],
                    {'AAPL': [100, 80, 82, 70, 90, 100], 'SPY': [100]*6})
        r = run(c, d)
        harvest = next(t for t in r['trades'] if t['event'] == 'harvest')
        reentry = next(t for t in r['trades'] if t['event'] == 'reentry')
        self.assertEqual(harvest['date'], '2020-02-06')
        self.assertEqual(harvest['price'], 82)
        self.assertAlmostEqual(harvest['pnl'], -18)
        self.assertGreater((date.fromisoformat(reentry['date'])-date.fromisoformat(harvest['date'])).days, 30)
        self.assertEqual(reentry['date'], '2020-03-09')
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 92)
        self.assertAlmostEqual(r['summary']['harvested_loss'], 18)
        self.assertAlmostEqual(r['summary']['remaining_carry_st'], 8)
        self.assertAlmostEqual(r['summary']['incremental_wealth_vs_no_harvest'], -8)

    def test_short_loss_trigger_uses_cover_price_not_signal_price(self):
        c = configuration(3, end='2020-03-06'); c['positions'][0]['side'] = 'short'
        d = history(['2020-01-02', '2020-02-05', '2020-02-06', '2020-03-06'],
                    {'AAPL': [100, 120, 118, 100], 'SPY': [100]*4})
        r = run(c, d)
        h = next(t for t in r['trades'] if t['event']=='harvest')
        self.assertEqual(h['date'], '2020-02-06')
        self.assertEqual(h['price'], 118)
        self.assertAlmostEqual(h['pnl'], -18)
        self.assertEqual(h['character'], 'st')
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 82)

    def test_no_harvest_within_thirty_days_of_purchase(self):
        c = configuration(3, end='2020-02-03')
        d = history(['2020-01-02','2020-01-20','2020-01-31','2020-02-03'],
                    {'AAPL':[100,80,80,100],'SPY':[100]*4})
        r = run(c,d)
        self.assertFalse(any(t['event']=='harvest' for t in r['trades']))
        self.assertEqual(r['summary']['harvested_loss'],0)

    def test_carryforward_used_next_year_and_joint_exit_settlement(self):
        c = configuration(3, end='2021-01-04')
        d = history(['2020-01-02','2020-02-05','2020-02-06','2020-03-09','2020-12-31','2021-01-04'],
                    {'AAPL':[100,80,80,80,80,100],'SPY':[100]*6})
        r = run(c,d)
        self.assertAlmostEqual(r['annual'][0]['carry_st'],20)
        self.assertAlmostEqual(r['annual'][1]['loss_used'],20)
        self.assertAlmostEqual(r['annual'][1]['carry_st'],0)
        self.assertAlmostEqual(r['summary']['capital_tax'],0)
        self.assertAlmostEqual(r['summary']['terminal_wealth'],100)

    def test_equal_rates_full_exit_no_free_tax_alpha(self):
        c = configuration(3, end='2021-01-04')
        c.update(outside_st_gain=100,tax_st_pct=40,tax_lt_pct=40)
        d = history(['2020-01-02','2020-02-05','2020-02-06','2020-03-09','2020-12-31','2021-01-04'],
                    {'AAPL':[100,80,80,80,80,100],'SPY':[100]*6})
        r=run(c,d);s=r['summary']
        self.assertAlmostEqual(s['terminal_wealth'],220)
        self.assertAlmostEqual(s['capital_tax'],80)
        self.assertAlmostEqual(s['outside_gross_proceeds'],200)
        self.assertAlmostEqual(s['incremental_wealth_vs_no_harvest'],0)
        self.assertAlmostEqual(s['tax_relief_before_exit_vs_no_harvest'],8)
        self.assertAlmostEqual(s['extra_exit_tax_vs_no_harvest'],8)
        self.assertAlmostEqual(s['wealth_identity_error'],0)

    def test_input_and_history_are_not_mutated(self):
        c=configuration(1);d=history(['2020-01-02','2020-01-03'],{'AAPL':[100,110],'SPY':[100,100]})
        before=deepcopy((c,d));run(c,d)
        self.assertEqual((c,d),before)

    def test_invalid_configuration_rejected_before_network(self):
        for field,value in [('level',True),('level',4),('initial_cash',0),('initial_cash',float('nan')),
                            ('cooldown_days',29),('harvest_threshold_pct',0),('start_date','invalid')]:
            c=configuration();c[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                run_research(c,lambda *args:self.fail('Validation must precede history download'))

    def test_invalid_history_rejected(self):
        d=history(['2020-01-02','2020-01-03'],{'AAPL':[100,110],'SPY':[100,100]})
        for change in ('date_order','missing_price','negative_price'):
            broken=deepcopy(d)
            if change=='date_order':broken['dates'].reverse()
            elif change=='missing_price':broken['prices']['AAPL'].pop()
            else:broken['prices']['AAPL'][1]=-1
            with self.subTest(change=change),self.assertRaises(ValueError):run(configuration(),broken)

    def test_insolvency_is_rejected_instead_of_fabricating_return(self):
        c=configuration(1);c['positions'][0]['side']='short'
        d=history(['2020-01-02','2020-01-03'],{'AAPL':[100,250],'SPY':[100,100]})
        with self.assertRaises(ValueError):run(c,d)


if __name__=='__main__':
    unittest.main()
