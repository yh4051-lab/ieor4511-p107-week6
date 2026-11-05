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
    def test_opt_in_spy_target_pass_fail_and_tie_after_tax(self):
        c = configuration(3)
        c['evaluate_spy'] = True
        for price, expected in [(120, 'pass'), (100, 'fail'), (110, 'tie')]:
            with self.subTest(end_price=price):
                r = run(c, history(['2020-01-02', '2020-01-03'],
                                   {'AAPL': [100, price], 'SPY': [100, 110]}))
                self.assertEqual(r['summary']['spy_status'], expected)
                self.assertAlmostEqual(r['summary']['spy_benchmark_wealth'], 106)
                self.assertAlmostEqual(r['summary']['incremental_wealth_vs_spy'],
                                       r['summary']['terminal_wealth'] - 106)
                self.assertIs(r['spy_benchmark'], r['benchmark'])

    def test_spy_target_is_independent_of_selected_benchmark_and_keeps_calendar_order(self):
        c = configuration(3)
        c.update(evaluate_spy=True, benchmark='QQQ')
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [100, 110], 'SPY': [100, 120], 'QQQ': [100, 105]})
        calls = []
        def provider(tickers, start, end):
            calls.append((tickers, start, end))
            return deepcopy(d)
        r = run_research(c, provider)
        self.assertEqual(calls, [(['AAPL', 'SPY', 'QQQ'], '2020-01-02', '2020-01-03')])
        self.assertAlmostEqual(r['summary']['benchmark_wealth'], 103)
        self.assertAlmostEqual(r['summary']['incremental_wealth'], 3)
        self.assertAlmostEqual(r['summary']['spy_benchmark_wealth'], 112)
        self.assertAlmostEqual(r['summary']['incremental_wealth_vs_spy'], -6)
        self.assertEqual(r['summary']['spy_status'], 'fail')
        self.assertEqual(r['spy_benchmark']['positions'][0]['ticker'], 'SPY')
        self.assertEqual(r['benchmark']['positions'][0]['ticker'], 'QQQ')

    def test_spy_in_selected_positions_is_fetched_once(self):
        c = configuration(3)
        c.update(evaluate_spy=True, benchmark='QQQ',
                 positions=[dict(ticker='SPY', side='long', shares=1)])
        d = history(['2020-01-02', '2020-01-03'],
                    {'SPY': [100, 110], 'QQQ': [100, 100]})
        calls = []
        def provider(tickers, *args):
            calls.append(tickers)
            return deepcopy(d)
        r = run_research(c, provider)
        self.assertEqual(calls, [['SPY', 'QQQ']])
        self.assertEqual(r['summary']['spy_status'], 'tie')

    def test_twenty_positions_and_two_benchmarks_require_twenty_two_symbols(self):
        c = configuration(3)
        symbols = ['STOCK' + chr(ord('A') + i) for i in range(20)]
        c.update(evaluate_spy=True, benchmark='QQQ',
                 positions=[dict(ticker=s, side='long', shares=1) for s in symbols])
        d = history(['2020-01-02', '2020-01-03'], {s: [1, 1] for s in symbols + ['SPY', 'QQQ']})
        calls = []
        def provider(tickers, *args):
            calls.append(tickers)
            return deepcopy(d)
        r = run_research(c, provider)
        self.assertEqual(calls, [symbols + ['SPY', 'QQQ']])
        self.assertEqual(r['summary']['spy_status'], 'tie')

    def test_spy_status_compares_separately_rounded_ending_wealth(self):
        c = configuration(3)
        c.update(evaluate_spy=True, tax_st_pct=0, tax_lt_pct=0)
        for actual, target, expected, display_difference in [
            (100.003, 100.004, 'tie', 0),
            (100.004, 100.003, 'tie', 0),
            (100.005, 100.004, 'pass', .01),
            (100.004, 100.005, 'fail', -.01),
        ]:
            with self.subTest(actual=actual, target=target):
                r = run(c, history(['2020-01-02', '2020-01-03'],
                                   {'AAPL': [100, actual], 'SPY': [100, target]}))
                self.assertEqual(r['summary']['spy_status'], expected)
                self.assertAlmostEqual(r['summary']['spy_display_difference'], display_difference)
                self.assertAlmostEqual(r['summary']['incremental_wealth_vs_spy'], actual-target)

    def test_harvesting_can_add_value_but_still_fail_spy_target(self):
        c = configuration(3, end='2021-03-10')
        c.update(evaluate_spy=True, outside_st_gain=100)
        d = history(['2020-01-02', '2020-02-05', '2020-02-06', '2020-03-09', '2020-12-31', '2021-03-10'],
                    {'AAPL': [100, 80, 80, 80, 80, 100], 'SPY': [100, 100, 100, 100, 100, 200]})
        r = run(c, d)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 224)
        self.assertAlmostEqual(r['summary']['incremental_wealth_vs_no_harvest'], 4)
        self.assertAlmostEqual(r['summary']['spy_benchmark_wealth'], 300)
        self.assertEqual(r['summary']['spy_status'], 'fail')

    def test_spy_control_matches_flows_and_trading_costs_but_not_custom_management(self):
        c = configuration(3)
        c.update(evaluate_spy=True, benchmark='QQQ', outside_st_gain=100,
                 outside_lt_gain=50, transaction_pct=.5, manager_pct=10)
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [100, 100], 'SPY': [100, 100], 'QQQ': [100, 100]})
        r = run(c, d)
        spy = r['spy_benchmark']['summary']
        self.assertEqual(spy['outside_gross_proceeds'], 150)
        self.assertAlmostEqual(spy['capital_tax'], 50)
        self.assertAlmostEqual(spy['cost_breakdown']['trading'], 1)
        self.assertEqual(spy['cost_breakdown']['management'], 0)
        self.assertGreater(r['summary']['cost_breakdown']['management'], 0)
        self.assertAlmostEqual(spy['terminal_wealth'], 199)

    def test_spy_evaluation_rejects_non_boolean_before_history_fetch(self):
        for value in (0, 1, None, 'true', [], {}):
            c = configuration(3)
            c['evaluate_spy'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'evaluate_spy'):
                run_research(c, lambda *args: self.fail('Validation must precede history download'))

    def test_spy_evaluation_is_opt_in_for_prior_export_compatibility(self):
        c = configuration(3)
        c['benchmark'] = 'QQQ'
        d = history(['2020-01-02', '2020-01-03'], {'AAPL': [100, 110], 'QQQ': [100, 100]})
        previous = run(c, d)
        self.assertNotIn('spy_benchmark', previous)
        self.assertNotIn('spy_status', previous['summary'])
        self.assertNotIn('spy_evaluation', previous['metadata'])
        c['evaluate_spy'] = False
        disabled = run(c, d)
        for field in ('summary', 'daily', 'annual', 'trades', 'positions', 'benchmark', 'no_harvest_control', 'data'):
            self.assertEqual(previous[field], disabled[field])

    def test_target_130_30_sizes_from_initial_equity_then_runs_after_tax(self):
        c = configuration(3)
        c.update(initial_cash=1_000_000, allocation_mode='target_exposure',
                 long_exposure_pct=130, short_exposure_pct=30,
                 positions=[dict(ticker='AAPL', side='long', weight=1),
                            dict(ticker='MSFT', side='short', weight=1)])
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [100, 110], 'MSFT': [200, 240], 'SPY': [100, 105]})
        r = run(c, d)
        opened = {t['ticker']: t for t in r['trades'] if t['event'] == 'open'}
        self.assertAlmostEqual(opened['AAPL']['shares'], 13_000)
        self.assertAlmostEqual(opened['MSFT']['shares'], 1_500)
        self.assertAlmostEqual(opened['AAPL']['shares'] * opened['AAPL']['price'], 1_300_000)
        self.assertAlmostEqual(opened['MSFT']['shares'] * opened['MSFT']['price'], 300_000)
        self.assertAlmostEqual(r['summary']['initial_net_exposure'], 1)
        self.assertAlmostEqual(r['summary']['initial_gross_exposure'], 1.6)
        self.assertAlmostEqual(r['daily'][0]['debt'], 300_000)
        self.assertAlmostEqual(r['daily'][0]['short_collateral'], 300_000)
        self.assertAlmostEqual(r['summary']['price_pnl'], 70_000)
        self.assertAlmostEqual(r['summary']['capital_tax'], 28_000)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 1_042_000)
        self.assertAlmostEqual(r['summary']['benchmark_wealth'], 1_030_000)
        self.assertAlmostEqual(r['no_harvest_control']['summary']['terminal_wealth'], 1_042_000)

    def test_target_exposure_can_exceed_130_30_without_changing_investor_equity(self):
        c = configuration(3)
        c.update(initial_cash=1_000_000, allocation_mode='target_exposure',
                 long_exposure_pct=200, short_exposure_pct=50,
                 positions=[dict(ticker='AAPL', side='long', weight=1),
                            dict(ticker='MSFT', side='short', weight=1)])
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [100, 100], 'MSFT': [200, 200], 'SPY': [100, 100]})
        r = run(c, d)
        self.assertAlmostEqual(r['positions'][0]['shares'], 20_000)
        self.assertAlmostEqual(r['positions'][1]['shares'], 2_500)
        self.assertAlmostEqual(r['summary']['initial_net_exposure'], 1.5)
        self.assertAlmostEqual(r['summary']['initial_gross_exposure'], 2.5)
        self.assertAlmostEqual(r['daily'][0]['equity'], 1_000_000)
        self.assertAlmostEqual(r['daily'][0]['debt'], 1_000_000)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 1_000_000)

    def test_relative_weights_are_normalized_separately_for_each_leg(self):
        c = configuration(3)
        c.update(initial_cash=1_000_000, allocation_mode='target_exposure',
                 long_exposure_pct=130, short_exposure_pct=30,
                 positions=[dict(ticker='AAPL', side='long', weight=3),
                            dict(ticker='MSFT', side='long', weight=1),
                            dict(ticker='NVDA', side='short', weight=2),
                            dict(ticker='TSLA', side='short', weight=1)])
        d = history(['2020-01-02', '2020-01-03'],
                    {'AAPL': [100, 100], 'MSFT': [200, 200], 'NVDA': [50, 50],
                     'TSLA': [250, 250], 'SPY': [100, 100]})
        original = deepcopy(c)
        r = run(c, d)
        amounts = {p['ticker']: p['shares'] * p['start_price'] for p in r['positions']}
        self.assertAlmostEqual(amounts['AAPL'], 975_000)
        self.assertAlmostEqual(amounts['MSFT'], 325_000)
        self.assertAlmostEqual(amounts['NVDA'], 200_000)
        self.assertAlmostEqual(amounts['TSLA'], 100_000)
        self.assertEqual(c, original)

    def test_target_sizing_supports_a_long_only_zero_short_budget(self):
        c = configuration(3)
        c.update(allocation_mode='target_exposure', long_exposure_pct=100,
                 short_exposure_pct=0,
                 positions=[dict(ticker='AAPL', side='long', weight=1)])
        r = run(c, history(['2020-01-02', '2020-01-03'],
                           {'AAPL': [100, 110], 'SPY': [100, 100]}))
        self.assertAlmostEqual(r['summary']['initial_gross_exposure'], 1)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 106)

    def test_invalid_target_allocation_rejected_before_history_download(self):
        valid = configuration(3)
        valid.update(allocation_mode='target_exposure', long_exposure_pct=130,
                     short_exposure_pct=30,
                     positions=[dict(ticker='AAPL', side='long', weight=1),
                                dict(ticker='MSFT', side='short', weight=1)])
        changes = [dict(allocation_mode='unknown'), dict(long_exposure_pct=-1),
                   dict(short_exposure_pct=float('nan')), dict(long_exposure_pct=1001),
                   dict(long_exposure_pct=True), dict(long_exposure_pct=0, short_exposure_pct=0),
                   dict(short_exposure_pct=0),
                   dict(positions=[dict(ticker='AAPL', side='long', weight=1)]),
                   dict(positions=[dict(ticker='AAPL', side='long', weight=0),
                                   dict(ticker='MSFT', side='short', weight=1)]),
                   dict(positions=[dict(ticker='AAPL', side='long', weight=float('inf')),
                                   dict(ticker='MSFT', side='short', weight=1)])]
        for change in changes:
            c = deepcopy(valid)
            c.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                run_research(c, lambda *args: self.fail('Allocation validation must precede download'))

    def test_explicit_manual_shares_mode_preserves_existing_position_quantities(self):
        c = configuration(3)
        c.update(allocation_mode='shares', long_exposure_pct=200, short_exposure_pct=50)
        r = run(c, history(['2020-01-02', '2020-01-03'],
                           {'AAPL': [100, 110], 'SPY': [100, 100]}))
        self.assertEqual(r['positions'][0]['shares'], 1)
        self.assertAlmostEqual(r['summary']['terminal_wealth'], 106)
        self.assertAlmostEqual(r['summary']['initial_gross_exposure'], 1)

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
