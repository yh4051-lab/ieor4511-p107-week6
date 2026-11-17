"""Hand-calculated controls for historical taxes and employer comparisons."""
from copy import deepcopy
from datetime import date,timedelta
import unittest

from p107.lot_accounting import LotBook,gift_sale_gain,held_more_than_year
from p107.observed_engine import simulate_observed
from p107.observed_studies import search_crossings,strategy_config,run_observed_study


class WashLots(unittest.TestCase):
    def test_leap_year_anniversary_is_st_until_next_day(self):
        self.assertFalse(held_more_than_year(date(2020,1,1),date(2021,1,1)))
        self.assertTrue(held_more_than_year(date(2020,1,1),date(2021,1,2)))
    def test_forward_long_match_defers_loss_and_recovers_on_sale(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1))
        b.close('X','long',100,7.5,date(2020,3,1),'harvest')
        b.open('X','long',100,8,date(2020,3,20))
        self.assertAlmostEqual(b.realizations[0]['tax_pnl'],0)
        self.assertAlmostEqual(b.lots[0]['tax_basis'],10.5)
        b.close('X','long',100,11,date(2021,5,1),'exit')
        self.assertAlmostEqual(b.realizations[-1]['tax_pnl'],50)
        self.assertAlmostEqual(sum(r['economic_pnl'] for r in b.realizations),50)

    def test_partial_prior_purchase_matches_held_shares_only(self):
        b=LotBook();b.open('X','long',100,50,date(2020,9,20))
        b.open('X','long',50,55,date(2020,12,13));b.open('X','long',25,45,date(2020,12,20))
        b.close('X','long',100,40,date(2021,1,3),'rebalance')
        self.assertAlmostEqual(b.realizations[0]['tax_pnl'],-250)
        self.assertAlmostEqual(sum(l['qty']*l['tax_basis'] for l in b.lots),4625)
        self.assertEqual(sum(m['shares'] for m in b.matches),75)

    def test_partial_future_purchase_does_not_duplicate_match(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1))
        b.close('X','long',100,8,date(2020,3,1),'rebalance')
        b.open('X','long',150,9,date(2020,3,20))
        self.assertAlmostEqual(sum(l['qty']*l['tax_basis'] for l in b.lots),1550)
        self.assertEqual(sum(m['shares'] for m in b.matches),100)

    def test_multiple_losses_match_one_acquisition_in_order(self):
        b=LotBook();b.open('X','long',50,10,date(2020,1,1));b.open('X','long',50,12,date(2020,1,2))
        b.close('X','long',100,8,date(2020,3,1),'rebalance');b.open('X','long',75,9,date(2020,3,10))
        self.assertAlmostEqual(sum(r['tax_pnl'] for r in b.realizations),-100)
        self.assertAlmostEqual(sum(l['qty']*l['tax_basis'] for l in b.lots),875)

    def test_thirty_day_boundary_and_day_31(self):
        for lag,expected in [(30,0),(31,-200)]:
            b=LotBook();b.open('X','long',100,10,date(2020,1,1));b.close('X','long',100,8,date(2020,3,1),'harvest')
            b.open('X','long',100,9,date(2020,3,1)+timedelta(days=lag))
            self.assertAlmostEqual(b.realizations[0]['tax_pnl'],expected)

    def test_short_reopening_adjusts_short_proceeds(self):
        b=LotBook();b.open('X','short',100,10,date(2020,1,1));b.close('X','short',100,12,date(2020,3,1),'rebalance')
        b.open('X','short',100,11,date(2020,3,10))
        self.assertAlmostEqual(b.lots[0]['tax_basis'],9)
        b.close('X','short',100,8,date(2020,5,1),'exit')
        self.assertAlmostEqual(sum(r['tax_pnl'] for r in b.realizations),100)

    def test_cross_year_wash_changes_sale_year(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1));b.close('X','long',100,8,date(2020,12,20),'rebalance')
        b.open('X','long',100,9,date(2021,1,10))
        self.assertEqual(b.buckets(2020)['loss_st'],0)
        self.assertEqual(b.buckets(2021)['loss_st'],0)

    def test_split_during_window_preserves_dollar_loss(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1));b.close('X','long',100,8,date(2020,3,1),'harvest')
        b.split('X',2);b.open('X','long',200,4,date(2020,3,10))
        self.assertAlmostEqual(b.realizations[0]['tax_pnl'],0)
        self.assertAlmostEqual(sum(l['qty']*l['tax_basis'] for l in b.lots),1000)

    def test_replacement_disposal_uses_same_matching_rules(self):
        b=LotBook();b.open('SUB','long',10,20,date(2020,1,1));b.close('SUB','long',10,15,date(2020,3,1),'replacement_exit')
        b.open('SUB','long',10,16,date(2020,3,10))
        self.assertEqual(b.realizations[0]['wash_disallowed'],50)

    def test_different_ticker_is_not_matched(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1));b.close('X','long',100,8,date(2020,3,1),'harvest')
        b.open('Y','long',100,9,date(2020,3,10));self.assertEqual(len(b.matches),0)

    def test_fees_enter_basis_and_net_proceeds(self):
        b=LotBook();b.open('X','long',100,10,date(2020,1,1),.1);b.close('X','long',100,11,date(2021,3,1),'exit',.1)
        self.assertAlmostEqual(b.realizations[0]['tax_pnl'],80)
        self.assertEqual(b.realizations[0]['character'],'lt')

    def test_short_payment_in_lieu_basis_for_short_holding(self):
        b=LotBook();b.open('X','short',100,10,date(2020,1,1));b.in_lieu('X',.2)
        b.close('X','short',100,9,date(2020,2,1),'exit');self.assertAlmostEqual(b.realizations[0]['tax_pnl'],80)

    def test_gift_dual_basis_gain_loss_and_middle(self):
        self.assertEqual(gift_sale_gain(100,80,120),20)
        self.assertEqual(gift_sale_gain(100,80,70),-10)
        self.assertEqual(gift_sale_gain(100,80,90),0)


def flat_case():
    days=['2019-01-02','2019-12-31','2020-02-03','2020-12-31','2021-02-01','2021-12-31',
          '2022-02-01','2022-12-30','2023-02-01','2023-12-29']
    symbols=['AAA','BBB','CCC','DDD','SPY']
    d=dict(dates=days,prices={t:[100.]*len(days) for t in symbols},
           splits={t:[0.]*len(days) for t in symbols},dividends={t:[0.]*len(days) for t in symbols},metadata={'source':'synthetic unit test'})
    c=dict(start_date=days[0],end_date=days[-1],initial_cash=1000000,positions=[dict(ticker='AAA',side='long',weight=1),dict(ticker='CCC',side='short',weight=1)],
           substitutes={'AAA':dict(ticker='BBB',reviewed_not_substantially_identical=True),'CCC':dict(ticker='DDD',reviewed_not_substantially_identical=True)},
           long_exposure_pct=130,short_exposure_pct=30,rebalance_every_sessions=1000,
           manager_pct=0,advisor_pct=0,financing_pct=0,borrow_pct=0,transaction_pct=0,rebate_pct=0,
           tax_st_pct=40,tax_lt_pct=20,ordinary_tax_pct=40,dividend_tax_pct=20,maintenance_equity_to_gross_pct=0,
           benchmark='SPY',benchmark_manager_pct=0,di_manager_pct=0,outside_gain_events=[])
    return c,d


class ObservedEngine(unittest.TestCase):
    def test_flat_all_exit_policies_preserve_wealth(self):
        c,d=flat_case()
        for p in [dict(mode='full_sale'),dict(mode='death'),dict(mode='gift'),dict(mode='extension',years=3)]+[dict(mode='gradual',years=y) for y in (3,4,5)]:
            with self.subTest(policy=p):self.assertAlmostEqual(simulate_observed(c,d,p)['summary']['terminal_after_tax_wealth'],1000000)

    def test_tax_on_known_long_gain(self):
        c,d=flat_case();c=strategy_config(c,'index');d['prices']['SPY'][-1]=110
        s=simulate_observed(c,d)['summary'];self.assertAlmostEqual(s['terminal_after_tax_wealth'],1080000)

    def test_death_adjusts_actual_long_lot_and_keeps_short_tax(self):
        c,d=flat_case();d['prices']['AAA'][-1]=110;d['prices']['CCC'][-1]=90
        r=simulate_observed(c,d,dict(mode='death'))
        self.assertAlmostEqual(r['summary']['basis_adjustment'],130000)
        self.assertAlmostEqual(r['summary']['total_taxes'],12000)
        self.assertAlmostEqual(r['summary']['terminal_after_tax_wealth'],1148000)

    def test_below_basis_death_adjusts_down(self):
        c,d=flat_case();c=strategy_config(c,'index');d['prices']['SPY'][-1]=90
        s=simulate_observed(c,d,dict(mode='death'))['summary']
        self.assertAlmostEqual(s['basis_adjustment'],-100000)
        self.assertEqual(s['total_taxes'],0)

    def test_gift_donor_outside_gain_not_at_recipient_zero_rate(self):
        c,d=flat_case();c=strategy_config(c,'index');c['outside_gain_events']=[dict(year=2023,amount=1000000,character='st')]
        d['prices']['SPY'][-1]=110
        s=simulate_observed(c,d,dict(mode='gift',recipient_tax_st_pct=0,recipient_tax_lt_pct=0))['summary']
        self.assertAlmostEqual(s['total_taxes'],400000)
        self.assertAlmostEqual(s['terminal_after_tax_wealth'],1700000)

    def test_gift_closes_debt_before_transfer(self):
        c,d=flat_case();r=simulate_observed(c,d,dict(mode='gift'))
        self.assertTrue(any(t['reason']=='gift_funding_sale' for t in r['trades']))
        self.assertAlmostEqual(r['daily'][-1]['debt'],0)

    def test_gradual_releases_equal_thirds_in_flat_case(self):
        c,d=flat_case();r=simulate_observed(c,d,dict(mode='gradual',years=3))
        self.assertEqual(len(r['events']),2)
        for e in r['events']:self.assertAlmostEqual(e['net_withdrawal'],1000000/3)
        self.assertAlmostEqual(r['summary']['terminal_after_tax_wealth'],1000000)

    def test_post_fee_target_is_130_30(self):
        c,d=flat_case();c['transaction_pct']=.1;r=simulate_observed(c,d)
        self.assertAlmostEqual(r['daily'][0]['long_pct'],130,places=7)
        self.assertAlmostEqual(r['daily'][0]['short_pct'],30,places=7)

    def test_wealth_identity_with_costs_splits_dividends(self):
        c,d=flat_case();c.update(manager_pct=.4,advisor_pct=.1,financing_pct=5,borrow_pct=1,rebate_pct=.2,transaction_pct=.05)
        d['splits']['AAA'][2]=2;d['prices']['AAA'][2:]=[50.]*(len(d['dates'])-2);d['dividends']['AAA'][4]=1
        r=simulate_observed(c,d)
        self.assertLess(r['summary']['max_wealth_identity_error'],.001)
        self.assertLess(r['summary']['max_capital_identity_error'],.001)

    def test_margin_breach_liquidates_and_does_not_restart(self):
        c,d=flat_case();c['maintenance_equity_to_gross_pct']=50;d['prices']['CCC'][3:]=[200.]*(len(d['dates'])-3)
        r=simulate_observed(c,d)
        self.assertEqual(r['summary']['margin_liquidations'],1)
        self.assertEqual(r['daily'][-1]['long_mv'],0)

    def test_outside_gain_only_once_and_tax_next_february(self):
        c,d=flat_case();c['outside_gain_events']=[dict(year=2019,amount=1000000,character='st')]
        r=simulate_observed(c,d)
        self.assertEqual(r['summary']['outside_gain_proceeds'],1000000)
        self.assertEqual(r['annual'][0]['payment_date'],'2020-02-03')
        self.assertAlmostEqual(r['summary']['terminal_after_tax_wealth'],1600000)

    def test_shared_ticker_rejected(self):
        c,d=flat_case();c['substitutes']['AAA']['ticker']='CCC'
        with self.assertRaisesRegex(ValueError,'disjoint'):simulate_observed(c,d)

    def test_break_even_matches_known_root_and_no_crossing(self):
        r=search_crossings(lambda x:x-123456,maximum=1000000,step=250000)
        self.assertAlmostEqual(r['roots_usd'][0],123456,places=1)
        self.assertLess(abs(r['residuals_usd'][0]),.01)
        self.assertEqual(search_crossings(lambda x:50,1000,250)['status'],'no_crossing_in_range')

    def test_observed_study_exact_offline_replay(self):
        c,d=flat_case();req=dict(mode='historical',engine='historical_lots',config=c,data_source='uploaded',history=d)
        r=run_observed_study(req);self.assertEqual(r,run_observed_study(r['request']))
        self.assertEqual(len(r['rows']),4)


if __name__=='__main__':unittest.main()
