"""Regression controls for Dominic's four Nov 10 research requests.

No invented market history. Synthetic observations exercise accounting only.
"""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from p107.analysis import one_time_gain_comparison, one_time_gain_breakeven
from p107.model import simulate, with_gains
from p107.dom_historical import historical_13030
from p107.dom_sampling import sample_portfolios, evaluate_portfolio_cohort
from p107.research import run_research

ROOT=Path(__file__).resolve().parents[1]


def illustrative():
    return json.loads((ROOT/'configs/example_hypothetical.json').read_text(encoding='utf-8'))


def history():
    dates=[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(75)]
    prices={s:[100.]*75 for s in ['ALFA','BETA','CHAR','DELT','SPY']}
    prices['ALFA']=[100. if i<33 else 80. if i<60 else 82. for i in range(75)]
    return {'dates':dates,'prices':prices,
            'dividends':{s:[0.]*75 for s in prices},
            'splits':{s:[0.]*75 for s in prices},
            'metadata':{'source':'unit-test synthetic'}}


def historical_config():
    return dict(engine_mode='rebalanced_13030',start_date='2020-01-01',
                end_date='2020-03-15',initial_cash=1000000,
                positions=[dict(ticker='ALFA',side='long',weight=1),
                           dict(ticker='CHAR',side='short',weight=1)],
                substitutes={'ALFA':{'ticker':'BETA','reviewed_not_substantially_identical':True},
                             'CHAR':{'ticker':'DELT','reviewed_not_substantially_identical':True}},
                benchmark='SPY',rebalance_every_sessions=50,cooldown_days=30,
                harvest_threshold_pct=10,manager_pct=0,transaction_pct=0,
                financing_pct=0,borrow_pct=0,rebate_pct=0,
                tax_st_pct=40,tax_lt_pct=20,ordinary_tax_pct=40,
                outside_gain_events=[dict(year=2020,amount=100000,character='st')])


class OneTimeGains(unittest.TestCase):
    def test_exactly_one_gain_year(self):
        c=with_gains(illustrative(),3000000,'st','year',3)
        self.assertEqual(c['outside_st_gains'][:5],[0,0,3000000,0,0])
        self.assertEqual(c['outside_lt_gains'][:5],[0]*5)
        with self.assertRaises(ValueError):
            with_gains(illustrative(),1000,'st','year',6)

    def test_one_m_three_m_five_m(self):
        rows=one_time_gain_comparison(illustrative(),amounts=(1000000,3000000,5000000),
                                      event_year=2)
        self.assertEqual([x['outside_gain_usd'] for x in rows],[1000000,3000000,5000000])
        self.assertTrue(all(x['event_year']==2 and x['hypothetical'] for x in rows))
        for x in rows:
            self.assertAlmostEqual(x['target_terminal_wealth']-x['comparator_terminal_wealth'],
                                   x['incremental_after_tax_wealth'])

    def test_breakeven_is_one_time_not_annual(self):
        result,points=one_time_gain_breakeven(illustrative(),event_year=1,
                                              maximum=50000,step=25000)
        self.assertEqual(result['schedule'],'one_time_only')
        self.assertEqual([x[0] for x in points],[0,25000,50000])


class ExitScenarios(unittest.TestCase):
    def test_full_liquidation_default_is_unchanged(self):
        base=illustrative()
        s0,_=simulate(base,'core_130_30')
        explicit=deepcopy(base);explicit['exit_policy']={'mode':'full_liquidation'}
        s1,_=simulate(explicit,'core_130_30')
        self.assertAlmostEqual(s0['terminal_after_tax_wealth'],s1['terminal_after_tax_wealth'])

    def test_death_stepup_requires_user_assumption(self):
        c=illustrative();c['exit_policy']={'mode':'death'}
        with self.assertRaises(ValueError):simulate(c,'index')
        c['exit_policy']['step_up_long_embedded_fraction']=1.
        summary,rows=simulate(c,'index')
        regular,_=simulate(illustrative(),'index')
        self.assertEqual(summary['exit_mode'],'death')
        self.assertGreaterEqual(summary['terminal_after_tax_wealth'],
                                regular['terminal_after_tax_wealth']-1e-7)
        self.assertNotEqual(rows[-1]['step_up_exempt_embedded_gain'],0)

    def test_gift_carries_basis_and_immediate_recipient_sale(self):
        c=illustrative();c['exit_policy']={'mode':'gift','recipient_liquidates':True}
        gift,_=simulate(c,'core_130_30')
        sold,_=simulate(illustrative(),'core_130_30')
        self.assertAlmostEqual(gift['terminal_after_tax_wealth'],
                               sold['terminal_after_tax_wealth'])
        self.assertEqual(gift['exit_mode'],'gift')

    def test_three_four_five_year_unwind(self):
        for years in [3,4,5]:
            c=illustrative()
            c['exit_policy']={'mode':'gradual','years':years,'extension_embedded_gain_share':.5}
            summary,rows=simulate(c,'core_130_30')
            self.assertEqual(summary['exit_mode'],'gradual')
            self.assertGreater(summary['terminal_after_tax_wealth'],0)
            self.assertGreater(sum(abs(x['transition_realized_gain']) for x in rows),0)
            self.assertLess(rows[-1]['gross_exposure'],rows[0]['gross_exposure'])
            self.assertTrue(all(abs(x['capital_pnl_identity_error'])<1e-4 for x in rows))

    def test_invalid_exit_policy_rejected(self):
        c=illustrative();c['exit_policy']={'mode':'gradual','years':2,'extension_embedded_gain_share':.5}
        with self.assertRaises(ValueError):simulate(c,'core_130_30')


class HistoricalRebalance(unittest.TestCase):
    def test_13030_substitute_harvest_and_reentry(self):
        c=historical_config()
        r=historical_13030(c,history())
        self.assertEqual(r['summary']['target_long_pct'],130)
        self.assertEqual(r['summary']['target_short_pct'],30)
        self.assertGreater(r['summary']['cumulative_harvested_losses'],0)
        self.assertGreaterEqual(r['summary']['substitute_switches'],1)
        self.assertIn('BETA',r['daily'][34]['active_substitutes'])
        self.assertGreater(r['summary']['terminal_after_tax_wealth'],0)
        self.assertTrue(any(t['reason']=='cooldown_expired' for t in r['trades']))
        self.assertAlmostEqual(r['daily'][0]['long_pct'],130,places=5)
        self.assertAlmostEqual(r['daily'][0]['short_pct'],30,places=5)

    def test_integrated_opt_in_route(self):
        c=historical_config()
        r=run_research(c,lambda names,start,end:history())
        self.assertEqual(r['metadata']['mode'],'rebalance_with_substitution')
        self.assertEqual(len(r['positions']),2)

    def test_no_unreviewed_substitute(self):
        c=historical_config()
        c['substitutes']['ALFA']['reviewed_not_substantially_identical']=False
        with self.assertRaises(ValueError):historical_13030(c,history())


class RandomPortfolios(unittest.TestCase):
    def members(self):
        return [dict(ticker='T'+str(i),member_from='2010-01-01',member_to=None,
                     published_as_of='2010-01-01',source_id='archived_source',
                     point_in_time_verified=True) for i in range(20)]

    def test_reproducible_disjoint_portfolios(self):
        a=sample_portfolios(self.members(),'2020-01-01',4,4,draws=20,seed=4511)
        b=sample_portfolios(self.members(),'2020-01-01',4,4,draws=20,seed=4511)
        self.assertEqual(a,b)
        self.assertEqual(len(a),20)
        for item in a:
            ls={x['ticker'] for x in item['positions'] if x['side']=='long'}
            ss={x['ticker'] for x in item['positions'] if x['side']=='short'}
            self.assertFalse(ls & ss)

    def test_point_in_time_provenance_is_required(self):
        members=self.members();members[0].pop('point_in_time_verified')
        with self.assertRaises(ValueError):
            sample_portfolios(members,'2020-01-01',4,4)
        members=self.members();members[0]['published_as_of']='2022-01-01'
        with self.assertRaises(ValueError):
            sample_portfolios(members,'2020-01-01',4,4)

    def test_cohort_summary(self):
        result=evaluate_portfolio_cohort({},self.members(),'2020-01-01',2,2,
                lambda c:{'summary':{'terminal_after_tax_wealth':100+len(c['positions'])}},
                draws=8,seed=12)
        self.assertEqual(result['draws'],8)
        self.assertEqual(result['median_wealth'],104)


if __name__=='__main__':
    unittest.main()
