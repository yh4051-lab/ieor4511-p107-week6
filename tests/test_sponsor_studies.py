"""Independent accounting and end-to-end regressions for sponsor studies."""
from copy import deepcopy
import json
import unittest

from p107.studies import ROOT, defaults, run_study
from p107.model import compare, simulate, with_gains
from p107.dom_historical import historical_13030, historical_comparison
from p107.dom_sampling import sample_portfolios, evaluate_portfolio_cohort
from test_dom_feedback import history, historical_config


def clean_annual():
    c=defaults()['annual']
    c['market_price_returns']=[0.]*10
    c['outside_st_gains']=c['outside_lt_gains']=[0.]*10
    for s in c['strategies']:
        for k in ('manager_fee','advisor_fee','long_financing_rate','short_rebate_rate',
                  'short_borrow_rate','transaction_cost_rate','exit_transaction_rate'):
            s[k]=0.
        for k in ('harvest_st_rates','harvest_lt_rates','realized_st_gain_rates','realized_lt_gain_rates'):
            s[k]=[0.]*10
    return c


class ExitAccounting(unittest.TestCase):
    def test_full_portfolio_exit_releases_equal_cash_in_flat_market(self):
        c=clean_annual();c['exit_policy']=dict(mode='gradual_liquidation',years=3)
        s,rows=simulate(c,'core_130_30')
        self.assertAlmostEqual(s['terminal_after_tax_wealth'],1000000)
        self.assertAlmostEqual(rows[2]['partial_exit_proceeds'],1000000/3)
        self.assertAlmostEqual(rows[3]['partial_exit_proceeds'],1000000/3)
        self.assertAlmostEqual(rows[4]['nav_start'],1000000/3)
        self.assertAlmostEqual(rows[4]['investor_cash_start'],2000000/3)

    def test_staged_wealth_reconciles_with_returns_costs_and_taxes(self):
        c=defaults()['annual'];c['exit_policy']=dict(mode='gradual_liquidation',years=4)
        for s in compare(c)[0]:
            expected=c['initial_cash']+s['outside_gross_gain_proceeds']+s['cumulative_pre_cost_pnl']-s['cumulative_net_costs']-s['cumulative_total_tax']
            self.assertAlmostEqual(s['terminal_after_tax_wealth'],expected,places=6)

    def test_extension_only_does_not_artificially_reduce_long_only_harvesting(self):
        c=defaults()['annual'];base=simulate(c,'long_only_di')[0]
        c['exit_policy']=dict(mode='gradual',years=3,extension_embedded_gain_share=.5)
        new=simulate(c,'long_only_di')[0]
        self.assertAlmostEqual(base['terminal_after_tax_wealth'],new['terminal_after_tax_wealth'])

    def test_ledger_notionals_follow_extension_reduction(self):
        c=defaults()['annual'];c['exit_policy']=dict(mode='gradual',years=3,extension_embedded_gain_share=.5)
        _,rows=simulate(c,'core_130_30')
        self.assertAlmostEqual(rows[-1]['short_market_value_abs']/rows[-1]['nav_start'],.1)
        self.assertAlmostEqual(rows[-1]['long_market_value']/rows[-1]['nav_start'],1.1)

    def test_long_only_death_uses_full_fmv_adjustment(self):
        c=clean_annual();c['market_price_returns']=[.1]*10
        c['exit_policy']=dict(mode='death',step_up_long_embedded_fraction=.8)
        result,rows=simulate(c,'index')
        self.assertAlmostEqual(result['terminal_after_tax_wealth'],1000000*1.1**5)
        self.assertAlmostEqual(rows[-1]['exit_realized_lt_gain'],0.)

    def test_gift_does_not_tax_donor_external_gains_at_recipient_zero_rate(self):
        c=with_gains(clean_annual(),1000000,'st','year',4)
        c['exit_policy']=dict(mode='gift',gift_year=3,recipient_tax_st=0.,recipient_tax_lt=0.)
        result,rows=simulate(c,'index')
        self.assertAlmostEqual(result['terminal_after_tax_wealth'],1600000)
        self.assertAlmostEqual(rows[3]['donor_outside_capital_tax'],400000)

    def test_donor_keeps_loss_carry_after_gift(self):
        c=with_gains(clean_annual(),1000000,'st','year',4)
        core=next(s for s in c['strategies'] if s['name']=='core_130_30')
        core['harvest_st_rates'][0]=.1
        c['exit_policy']=dict(mode='gift',gift_year=3,recipient_tax_st=0.,recipient_tax_lt=0.)
        _,rows=simulate(c,'core_130_30')
        self.assertAlmostEqual(rows[2]['donor_carry_st_end'],100000)
        self.assertEqual(rows[2]['carry_st_start'],0.)
        self.assertAlmostEqual(rows[3]['donor_outside_capital_tax'],360000)

    def test_below_basis_gift_is_not_silently_credited_as_donor_loss(self):
        c=clean_annual();c['market_price_returns']=[-.1]*10
        c['exit_policy']=dict(mode='gift',gift_year=3)
        with self.assertRaisesRegex(ValueError,'dual-basis'):
            simulate(c,'index')


class HistoricalAccounting(unittest.TestCase):
    def flat(self):
        c=historical_config();c['outside_gain_events']=[]
        data=history();data['prices']={k:[100.]*len(data['dates']) for k in data['prices']}
        return c,data

    def test_post_fee_rebalance_reaches_exact_target(self):
        c,d=self.flat();c['transaction_pct']=.1
        r=historical_13030(c,d)
        self.assertAlmostEqual(r['daily'][0]['long_pct'],130,places=7)
        self.assertAlmostEqual(r['daily'][0]['short_pct'],30,places=7)
        self.assertGreater(r['daily'][0]['cost_this_session'],0)

    def test_dividend_tax_and_wealth_bridge_independent_calculation(self):
        c,d=self.flat();d['dividends']['ALFA'][10]=1.;d['dividends']['CHAR'][10]=1.
        c['rebalance_every_sessions']=10000
        r=historical_13030(c,d)['summary']
        self.assertAlmostEqual(r['cumulative_net_dividends'],10000)
        self.assertAlmostEqual(r['dividend_taxes'],2600)
        self.assertAlmostEqual(r['terminal_after_tax_wealth'],1007400)
        self.assertAlmostEqual(r['total_taxes'],2600)

    def test_split_preserves_wealth_and_capital_identity(self):
        c,d=self.flat();d['splits']['ALFA'][10]=2
        d['prices']['ALFA'][10:]=[50.]*(len(d['dates'])-10)
        s=historical_13030(c,d)['summary']
        self.assertAlmostEqual(s['terminal_after_tax_wealth'],1000000)
        self.assertAlmostEqual(s['cumulative_price_pnl'],0.)

    def test_outside_gain_is_not_reinvested_into_strategy(self):
        c,d=self.flat()
        d['dates']=['2020-12-30','2020-12-31','2021-01-04','2021-01-05']
        for kind in ('prices','splits','dividends'):
            for key in d[kind]: d[kind][key]=[100. if kind=='prices' else 0.]*4
        c.update(start_date=d['dates'][0],end_date=d['dates'][-1],rebalance_every_sessions=1,
                 outside_gain_events=[dict(year=2020,amount=1000000,character='st')])
        r=historical_13030(c,d)
        self.assertAlmostEqual(r['daily'][2]['equity'],1000000)
        self.assertAlmostEqual(r['daily'][2]['long_mv'],1300000)
        self.assertAlmostEqual(r['daily'][2]['investor_side_cash'],600000)
        self.assertAlmostEqual(r['summary']['terminal_after_tax_wealth'],1600000)

    def test_comparisons_receive_identical_outside_cash(self):
        c=historical_config();r=historical_comparison(c,history())
        self.assertEqual({v['summary']['outside_gain_proceeds'] for v in r['results'].values()},{100000})
        self.assertEqual(r['results']['no_harvest']['summary']['substitute_switches'],0)
        self.assertAlmostEqual(r['harvesting_benefit'],r['results']['harvest']['summary']['terminal_after_tax_wealth']-r['results']['no_harvest']['summary']['terminal_after_tax_wealth'])

    def test_no_unrequested_history_extension(self):
        c=historical_config();c['end_date']='2020-01-10'
        with self.assertRaisesRegex(ValueError,'start/end'):
            historical_13030(c,history())


class StudyIntegration(unittest.TestCase):
    def test_cohort_fetches_whole_universe_in_bounded_batches(self):
        from p107.studies import membership_rows
        base=defaults()
        data=json.loads((ROOT/'examples/dom_synthetic_history.json').read_text(encoding='utf-8'))
        calls=[]
        def provider(names,start,end):
            self.assertLessEqual(len(names),22)
            calls.append(names)
            return dict(dates=data['dates'],metadata=data['metadata'],
                        **{kind:{name:data[kind][name] for name in names}
                           for kind in ('prices','splits','dividends')})
        r=run_study(dict(mode='cohort',data_source='live',config=base['historical'],
                        memberships=membership_rows(base['memberships_csv']),samples=2),provider)
        self.assertEqual([len(x) for x in calls],[22,3])
        self.assertEqual(len(r['rows']),2)
        self.assertEqual(r,run_study(r['request']))

    def test_incomplete_requested_period_is_not_silently_shortened(self):
        c=defaults()['historical'];c['end_date']='2025-01-01'
        with self.assertRaisesRegex(ValueError,'does not cover'):
            run_study(dict(mode='historical',config=c))

    def test_all_four_studies_have_exact_offline_replay(self):
        b=defaults()
        for mode in ('exits','one_time','historical','cohort'):
            with self.subTest(mode=mode):
                r=run_study(dict(mode=mode,config=b['annual' if mode in ('exits','one_time') else 'historical'],
                                 stepup_long_fraction=.8,event_year=2,gift_year=3,samples=8))
                replay=run_study(r['request'],lambda *args:self.fail('Offline replay attempted network access'))
                self.assertEqual(r,replay)
                self.assertTrue(r['rows'])

    def test_one_time_results_cover_all_strategies_and_both_comparators(self):
        r=run_study(dict(mode='one_time',config=defaults()['annual'],event_year=2))
        self.assertEqual({s['comparator'] for s in r['searches']},{'index','long_only_di'})
        self.assertEqual(len(r['rows']),12)
        for row in r['rows']:
            self.assertEqual(row['outside_gain'],row['outside_gross_gain_proceeds'])
        for search in r['searches']:
            self.assertTrue(all(abs(x)<.01 for x in search['residuals_usd']))

    def test_cohort_comparisons_are_reproducible_not_sp_history(self):
        r=run_study(dict(mode='cohort',config=defaults()['historical'],samples=8,seed=1234))
        self.assertEqual(len(r['results']),8)
        self.assertIn('SYNTHETIC',r['data_label'])
        self.assertGreaterEqual(r['benchmark_win_fraction'],0.)
        self.assertLessEqual(r['benchmark_win_fraction'],1.)
        for row in r['results']:
            self.assertFalse(set(row['long_names']) & set(row['short_names']))

    def test_cohort_rejects_lookahead_formation(self):
        c=defaults()['historical']
        with self.assertRaisesRegex(ValueError,'formation date'):
            evaluate_portfolio_cohort(c,[],'2021-01-01',1,1,lambda c:None)

    def test_membership_invalid_effective_interval(self):
        rows=[dict(ticker='A',source_id='synthetic',point_in_time_verified=True,
                   member_from='2021-01-01',member_to='2020-01-01')]
        with self.assertRaisesRegex(ValueError,'end must be after'):
            sample_portfolios(rows,'2022-01-01',1,1)


if __name__=='__main__':unittest.main()
