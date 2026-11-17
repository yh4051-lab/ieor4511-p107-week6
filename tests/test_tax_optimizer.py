"""Independent selected-lot, causal forecast and engine accounting controls."""
from copy import deepcopy
from datetime import date, timedelta
from math import exp, sin
import unittest

import numpy as np

from p107.lot_accounting import LotBook
from p107.observed_engine import simulate_observed
from p107.tax_optimizer import build_tax_allocator, lot_gain_tax_coefficient


def forecast_history():
    dates=[];day=date(2020,9,1)
    while day<=date(2021,3,31):
        if day.weekday()<5:dates.append(day.isoformat())
        day+=timedelta(days=1)
    symbols=['AAA','BBB','CCC','DDD','EEE','FFF','SPY']
    return dict(dates=dates,
        prices={t:[100*exp(.0002*i+.02*sin(.17*i+k)) for i in range(len(dates))] for k,t in enumerate(symbols)},
        splits={t:[0.]*len(dates) for t in symbols},
        dividends={t:[0.]*len(dates) for t in symbols},
        metadata={'source':'Synthetic optimizer controls'})


def config():
    return dict(start_date='2021-01-04',end_date='2021-02-01',initial_cash=1000,
        benchmark='SPY',positions=[{'ticker':'AAA','side':'long','weight':1},
            {'ticker':'BBB','side':'long','weight':1},{'ticker':'CCC','side':'short','weight':1}],
        substitutes={a:{'ticker':b,'reviewed_not_substantially_identical':True}
                     for a,b in [('AAA','DDD'),('BBB','EEE'),('CCC','FFF')]},
        long_exposure_pct=130,short_exposure_pct=30,rebalance_every_sessions=5,
        cooldown_days=30,manager_pct=0,advisor_pct=0,financing_pct=0,borrow_pct=0,
        rebate_pct=0,transaction_pct=0,tax_st_pct=40,tax_lt_pct=20,
        ordinary_tax_pct=40,dividend_tax_pct=20,harvest_threshold_pct=50,
        maintenance_equity_to_gross_pct=0,outside_gain_events=[],
        optimizer={'max_long_weight':.8,'max_short_weight':.3,'risk_aversion':20})


def selected_state():
    c=config();c['optimizer']['risk_aversion']=0
    book=LotBook()
    book.open('AAA','long',5,40,date(2020,11,1))
    expensive=book.open('AAA','long',5,90,date(2020,12,1))
    book.open('BBB','long',5,100,date(2020,12,1))
    book.open('CCC','short',2,100,date(2020,12,1))
    roots={p['ticker']:dict(side=p['side'],active=p['ticker']) for p in c['positions']}
    state=dict(config=c,data={},dates=[date(2021,1,4)],index=0,roots=roots,book=book,
        prices={'AAA':100,'BBB':100,'CCC':100},nav=1000,
        current_notionals={'AAA':1000,'BBB':500,'CCC':200},reason='scheduled_rebalance',
        targets={'long':1.3,'short':.3})
    return c,state,expensive['id']


class TaxOptimizerTests(unittest.TestCase):
    def test_selected_lot_close_reduces_realized_gain_vs_fifo(self):
        book=LotBook()
        book.open('AAA','long',5,40,date(2020,11,1))
        second=book.open('AAA','long',5,90,date(2020,12,1))
        fifo=deepcopy(book)
        selected=book.close('AAA','long',2,100,date(2021,1,4),'rebalance',lot_order=[second['id']])
        default=fifo.close('AAA','long',2,100,date(2021,1,4),'rebalance')
        self.assertEqual(sum(r['tax_pnl'] for r in selected),20)
        self.assertEqual(sum(r['tax_pnl'] for r in default),120)
        self.assertEqual(selected[0]['lot_id'],second['id'])
        self.assertEqual(book.quantity('AAA','long'),8)
        for order in ([999], [second['id'],second['id']], ['2']):
            before=deepcopy(book.lots)
            with self.subTest(order=order),self.assertRaises(ValueError):
                book.close('AAA','long',1,100,date(2021,1,4),'rebalance',lot_order=order)
            self.assertEqual(book.lots,before)

    def test_qp_selects_lower_tax_lot_and_exact_book_targets(self):
        c,state,cheaper=selected_state()
        allocator=build_tax_allocator(c,forecast_history())
        plan=allocator(state)
        self.assertAlmostEqual(plan['weights']['AAA'],.8,places=6)
        self.assertAlmostEqual(plan['weights']['BBB'],.5,places=6)
        self.assertAlmostEqual(plan['weights']['CCC'],.3,places=6)
        self.assertEqual(plan['lot_orders']['AAA'][0],cheaper)
        self.assertAlmostEqual(plan['record']['long_total'],1.3,places=9)
        self.assertAlmostEqual(plan['record']['short_total'],.3,places=9)
        self.assertAlmostEqual(plan['record']['estimated_positive_gain_tax_usd'],8,places=4)
        sales=plan['record']['planned_lot_sales']
        self.assertTrue(any(r['lot_id']==cheaper and abs(r['planned_sale_shares']-2)<1e-4 for r in sales))
        self.assertEqual(plan['record']['loss_credit_in_objective'],0)
        selected=state['book'].close('AAA','long',2,100,date(2021,1,4),'rebalance',lot_order=plan['lot_orders']['AAA'])
        self.assertAlmostEqual(sum(r['tax_pnl'] for r in selected)*.4,8)

    def test_future_prices_do_not_change_forecasts_or_trades(self):
        c,state,_=selected_state();c['optimizer'].update(return_model='trailing_mean',risk_aversion=20)
        first=forecast_history();future=deepcopy(first)
        for ticker,values in future['prices'].items():
            future['prices'][ticker]=[v if day<'2021-01-04' else v*1000 for day,v in zip(future['dates'],values)]
        a=build_tax_allocator(c,first)(state)
        b=build_tax_allocator(c,future)(state)
        np.testing.assert_allclose(list(a['weights'].values()),list(b['weights'].values()),rtol=0,atol=1e-10)
        self.assertEqual(a['record']['forecast_cutoff'],b['record']['forecast_cutoff'])
        self.assertLess(a['record']['forecast_cutoff'],'2021-01-04')
        self.assertEqual(a['record']['planned_lot_sales'],b['record']['planned_lot_sales'])

    def test_missing_warmup_and_infeasible_caps_fail_without_fallback(self):
        c,state,_=selected_state();history=forecast_history()
        short=deepcopy(history)
        short['dates']=history['dates'][-5:]
        for group in ('prices','splits','dividends'):
            short[group]={t:v[-5:] for t,v in history[group].items()}
        with self.assertRaisesRegex(ValueError,'past returns'):
            build_tax_allocator(c,short)(state)
        c['optimizer']['max_long_weight']=.1
        with self.assertRaisesRegex(ValueError,'infeasible'):
            build_tax_allocator(c,history)(state)
        c=config();c['optimizer']['return_model']='future-alpha'
        with self.assertRaisesRegex(ValueError,'return_model'):
            build_tax_allocator(c,history)

    def test_loss_sales_have_no_immediate_credit_in_planning_proxy(self):
        c=config();lot=dict(side='long',tax_basis=120,opened=date(2020,1,1),holding_credit=0)
        self.assertEqual(lot_gain_tax_coefficient(lot,100,date(2021,1,4),c),0)
        lot.update(side='short',tax_basis=80)
        self.assertEqual(lot_gain_tax_coefficient(lot,100,date(2021,1,4),c),0)

    def test_engine_hook_has_exact_post_fee_exposures_and_accounting(self):
        c=config();c.update(transaction_pct=.05,lab_diagnostics=True)
        full=forecast_history();indices=[i for i,d in enumerate(full['dates']) if c['start_date']<=d<=c['end_date']]
        data={'dates':[full['dates'][i] for i in indices],'metadata':full['metadata']}
        for group in ('prices','splits','dividends'):
            data[group]={t:[values[i] for i in indices] for t,values in full[group].items()}
        allocator=build_tax_allocator(c,full)
        result=simulate_observed(c,data,allocator=allocator)
        self.assertGreater(len(result['optimization_records']),1)
        initial=result['daily'][0]
        self.assertAlmostEqual(initial['long_pct'],130,places=7)
        self.assertAlmostEqual(initial['short_pct'],30,places=7)
        self.assertAlmostEqual(result['summary']['max_wealth_identity_error'],0,places=5)
        self.assertEqual(result['daily'][-1]['embedded_tax_liability_estimate'],0)
        self.assertEqual(result['daily'][-1]['max_concentration'],0)
        self.assertTrue(all(r['forecast_cutoff']<r['trade_date'] for r in result['optimization_records']))
        self.assertTrue(all(r['status']=='optimal' for r in result['optimization_records']))
        self.assertAlmostEqual(sum(t['fee'] for t in result['trades']),result['summary']['cost_breakdown']['transactions'])

    def test_diagnostics_remove_external_cash_and_preserve_existing_engine_outputs(self):
        c=config();c.update(start_date='2021-01-04',end_date='2021-01-05',rebalance_every_sessions=21)
        prices={t:[100,110 if t=='AAA' else 100] for t in ['AAA','BBB','CCC','DDD','EEE','FFF','SPY']}
        data=dict(dates=[c['start_date'],c['end_date']],prices=prices,
                  splits={t:[0,0] for t in prices},dividends={t:[0,0] for t in prices})
        base=simulate_observed(c,data)
        diag=simulate_observed({**c,'lab_diagnostics':True},data)
        for key in ('trades','annual','realizations','events','wash_matches'):
            self.assertEqual(base[key],diag[key])
        for key,value in base['summary'].items():self.assertEqual(value,diag['summary'][key])
        external=simulate_observed({**c,'lab_diagnostics':True,'outside_gain_events':[dict(year=2021,amount=1000,character='st')]},data)
        self.assertAlmostEqual(diag['daily'][-1]['investment_return'],.065)
        self.assertEqual(external['daily'][-1]['investment_return'],diag['daily'][-1]['investment_return'])
        self.assertEqual(external['daily'][-1]['external_flow'],1000)
        self.assertEqual(diag['daily'][-1]['external_flow'],0)
        self.assertAlmostEqual(diag['summary']['pre_exit_embedded_tax_liability_estimate'],26)
        self.assertNotIn('diagnostic_notes',base)
        self.assertNotIn('optimization_records',base)


if __name__=='__main__':unittest.main()
