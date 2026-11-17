"""Independent accounting, paired scenarios, risk and replay tests for tax lab."""
from copy import deepcopy
from datetime import date, timedelta
import csv
import hashlib
import io
import json
from math import exp, sin, sqrt
from pathlib import Path
import random
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from p107.tax_lab import (tax_lab_defaults,run_tax_lab,tax_lab_zip,_risk,
                          _bootstrap_history,_small_run,_configuration,_prepare_history)


def fixture():
    c=tax_lab_defaults()['demo_config']
    c.update(initial_cash=10000,start_date='2020-01-02',end_date='2020-03-31',
             outside_gain_events=[],harvest_threshold_pct=20)
    names=[p['ticker'] for p in c['positions']]+c['replacement_tickers']+[c['benchmark']]
    dates=[];day=date(2019,10,1)
    while day<=date(2020,3,31):
        if day.weekday()<5:dates.append(day.isoformat())
        day+=timedelta(days=1)
    n=len(dates)
    prices={t:[100*exp((.0002+.00002*k)*i+.005*sin((i+k)*.3)) for i in range(n)] for k,t in enumerate(names)}
    d=dict(dates=dates,prices=prices,dividends={t:[0.]*n for t in names},
           splits={t:[0.]*n for t in names},metadata={'source':'Synthetic tax-lab test history','data_kind':'synthetic'})
    req=dict(config=c,data_source='uploaded',history=d,
             optimization=dict(risk_aversion=50,lookback=40,long_cap_pct=60,short_cap_pct=20),
             sensitivities=dict(enabled=False,financing_rates=[3,5,7],borrow_rates=[0,1,3]),
             monte_carlo=dict(enabled=False,paths=2,seed=4511))
    return req


class TaxLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request=fixture()
        cls.result=run_tax_lab(cls.request)

    def test_four_strategies_independent_accounting_and_optimizer_audit(self):
        result=self.result
        self.assertEqual(set(result['strategies']),set('ABCD'))
        self.assertEqual(result['data_kind'],'synthetic')
        self.assertEqual(set(result['runtime_versions']),{'python','numpy','cvxpy','clarabel'})
        self.assertTrue(all(isinstance(v,str) and v for v in result['runtime_versions'].values()))
        for key,run in result['strategies'].items():
            with self.subTest(strategy=key):
                s=run['summary']
                self.assertLess(s['max_wealth_identity_error'],.001)
                self.assertLess(s['max_capital_identity_error'],.001)
                self.assertAlmostEqual(s['initial_cash']+s['outside_gain_proceeds']+
                    s['cumulative_price_pnl']+s['cumulative_net_dividends']-
                    s['total_taxes']-s['total_financing_and_fees_net_rebate'],s['terminal_after_tax_wealth'],delta=1e-5)
                self.assertAlmostEqual(run['daily'][-1]['long_mv'],0)
                self.assertAlmostEqual(run['daily'][-1]['short_mv'],0)
                self.assertAlmostEqual(run['daily'][-1]['embedded_tax_liability_estimate'],0)
                self.assertIsNotNone(run['risk']['tracking_error'])
                self.assertGreaterEqual(run['risk']['max_drawdown'],0)
        self.assertEqual(result['strategies']['A']['summary']['cumulative_harvested_losses'],0)
        self.assertEqual(result['strategies']['C']['summary']['cumulative_harvested_losses'],0)
        decisions=result['strategies']['D']['optimizer_decisions']
        self.assertGreater(len(decisions),1)
        self.assertTrue(all(d['forecast_cutoff']<d['trade_date'] for d in decisions))
        self.assertTrue(all(abs(d['long_total']-1.3)<1e-7 and abs(d['short_total']-.3)<1e-7 for d in decisions))
        self.assertEqual(result['strategies']['A']['risk']['tracking_error'],0)

    def test_input_is_unchanged_and_replay_retains_exact_data(self):
        request=fixture();saved=deepcopy(request)
        first=run_tax_lab(request)
        self.assertEqual(request,saved)
        replay=run_tax_lab(first['request'],history_provider=lambda *a:self.fail('Replay must not use network'))
        self.assertEqual(replay['data_kind'],'synthetic')
        for key in 'ABCD':
            self.assertAlmostEqual(first['strategies'][key]['summary']['terminal_after_tax_wealth'],
                                   replay['strategies'][key]['summary']['terminal_after_tax_wealth'],places=7)
        self.assertEqual(first['request']['history'],replay['request']['history'])

    def test_live_history_is_fetched_once_and_source_metadata_cannot_launder_synthetic(self):
        request=fixture();data=request.pop('history');request['data_source']='live';calls=[]
        def provider(names,start,end):calls.append((names,start,end));return deepcopy(data)
        result=run_tax_lab(request,provider)
        self.assertEqual(len(calls),1)
        self.assertLess(calls[0][1],request['config']['start_date'])
        self.assertEqual(result['data_kind'],'synthetic')
        self.assertEqual(result['request']['data_source'],'uploaded')
        self.assertEqual(result['request']['source_kind'],'live')
        self.assertGreater(result['data_metadata']['warmup_sessions'],20)

    def test_large_live_universe_keeps_benchmark_last_in_every_batch(self):
        request=fixture();c=request['config'];d=request['history']
        originals=['STOCK'+chr(65+i) for i in range(20)]
        substitutes=['SUB'+chr(65+i) for i in range(20)]
        c['positions']=[dict(ticker=t,side='long' if i<10 else 'short',weight=1) for i,t in enumerate(originals)]
        c['substitutes']={t:dict(ticker=sub,reviewed_not_substantially_identical=True) for t,sub in zip(originals,substitutes)}
        all_names=originals+substitutes+['SPY'];prices=d['prices']['SPY']
        all_data=dict(dates=d['dates'],metadata=d['metadata'],
                      prices={t:prices[:] for t in all_names},
                      dividends={t:[0.]*len(prices) for t in all_names},
                      splits={t:[0.]*len(prices) for t in all_names})
        calls=[]
        def provider(names,start,end):
            calls.append(names)
            return dict(dates=all_data['dates'],metadata=all_data['metadata'],
                        **{g:{t:all_data[g][t] for t in names} for g in ('prices','dividends','splits')})
        config=_configuration(c,request['optimization'])
        raw,*_= _prepare_history(dict(data_source='live'),config,provider)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(names[-1]=='SPY' and len(names)<=22 for names in calls))
        self.assertEqual(set(raw['prices']),set(all_names))

    def test_risk_ignores_outside_cash_and_measures_investment_drawdown(self):
        returns=[None,-.1,.05,0.]
        run=dict(daily=[dict(investment_return=r,total_investor_wealth=w,external_flow=f,
                            max_concentration=.6,long_pct=130,short_pct=30)
                        for r,w,f in zip(returns,[100,10000090,10000100,20000100],[0,10000000,0,10000000])])
        benchmark=dict(daily=[dict(investment_return=r) for r in [None,0.,0.,0.]])
        risk=_risk(run,benchmark)
        self.assertAlmostEqual(risk['max_drawdown'],.1)
        self.assertAlmostEqual(risk['volatility'],float(np.std([-.1,.05,0],ddof=1)*sqrt(252)))
        self.assertAlmostEqual(risk['tracking_error'],risk['volatility'])
        self.assertEqual(risk['max_concentration'],.6)
        self.assertEqual(risk['max_gross_exposure'],1.6)
        run['daily'][2]['investment_return']=None
        self.assertIsNone(_risk(run,benchmark)['tracking_error'])

    def test_sensitivity_pairs_share_market_and_show_all_requested_rates(self):
        request=fixture();request['sensitivities']=dict(enabled=True,financing_rates=[3,5],borrow_rates=[1])
        result=run_tax_lab(request)
        self.assertEqual(result['sensitivity']['summary'],dict(completed=2,failed=0))
        anchor=result['comparison'][-1]
        row=next(r for r in result['sensitivity']['rows'] if r['financing_pct']==5)
        self.assertAlmostEqual(row['wealth_D'],anchor['terminal_wealth'])
        self.assertAlmostEqual(row['delta_D_A'],row['wealth_D']-row['wealth_A'])
        self.assertAlmostEqual(row['delta_D_C'],row['wealth_D']-row['wealth_C'])

    def test_bootstrap_uses_only_prestart_returns_and_preserves_joint_sampling(self):
        request=fixture();c=request['config'];data=request['history']
        first=_bootstrap_history(data,c,random.Random(88))
        changed=deepcopy(data)
        for t,values in changed['prices'].items():
            for i,d in enumerate(changed['dates']):
                if d>c['start_date']:values[i]*=1000+i
        second=_bootstrap_history(changed,c,random.Random(88))
        self.assertEqual(first,second)
        self.assertEqual(first['metadata']['data_kind'],'synthetic')
        self.assertLess(first['metadata']['training_last_date'],c['start_date'])
        self.assertEqual(len(first['dates']),len(data['dates']))
        self.assertTrue(all(v==0 for t,a in first['splits'].items() for d,v in zip(first['dates'],a) if d>=c['start_date']))
        # Identical input series must remain identical in every generated path.
        common=deepcopy(data);names=list(common['prices']);common['prices'][names[1]]=common['prices'][names[0]][:]
        generated=_bootstrap_history(common,c,random.Random(88))
        self.assertEqual(generated['prices'][names[0]],generated['prices'][names[1]])

    def test_seeded_monte_carlo_is_reproducible_and_keeps_failure_counts(self):
        request=fixture();request['monte_carlo']=dict(enabled=True,paths=2,seed=17)
        first=run_tax_lab(request);second=run_tax_lab(first['request'])
        self.assertEqual(first['monte_carlo'],second['monte_carlo'])
        self.assertEqual(first['monte_carlo']['summary']['completed'],2)
        self.assertEqual(first['monte_carlo']['summary']['failed'],0)
        self.assertEqual(len(first['monte_carlo']['rows']),2)
        self.assertIsNotNone(first['monte_carlo']['summary']['median_delta'])
        self.assertLess(first['monte_carlo']['training_last_date'],request['config']['start_date'])

    def test_zip_has_frozen_inputs_ledger_optimizer_records_and_hashes(self):
        with zipfile.ZipFile(io.BytesIO(tax_lab_zip(self.result))) as z:
            self.assertIsNone(z.testzip())
            self.assertIn('D/optimizer_decisions.csv',z.namelist())
            self.assertIn('D/realizations.csv',z.namelist())
            self.assertEqual(json.loads(z.read('input.json')),self.result['request'])
            for name,sha in json.loads(z.read('FILE_MANIFEST.json')).items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),sha)
            rows=list(csv.DictReader(io.StringIO(z.read('comparison.csv').decode('utf-8-sig'))))
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[-1]['strategy'],'D')
        for name,sha in self.result['engine_hashes'].items():
            self.assertEqual(hashlib.sha256((Path(__file__).resolve().parents[1]/'p107'/name).read_bytes()).hexdigest(),sha)

    def test_invalid_settings_and_missing_warmup_fail_before_optimization(self):
        cases=[]
        r=fixture();r['sensitivities']['financing_rates']=[3,3];cases.append(r)
        r=fixture();r['optimization']['long_cap_pct']=10;cases.append(r)
        r=fixture();r['monte_carlo']['paths']=True;cases.append(r)
        r=fixture();r['monte_carlo']['enabled']='true';cases.append(r)
        r=fixture();r['config']['positions'][0]['weight']=True;cases.append(r)
        for request in cases:
            request['data_source']='live';request.pop('history',None)
            with self.subTest(request=request),self.assertRaises(ValueError):
                run_tax_lab(request,lambda *a:self.fail('Validation must precede market download'))
        r=fixture();indices=[i for i,d in enumerate(r['history']['dates']) if d>=r['config']['start_date']]
        r['history']['dates']=[r['history']['dates'][i] for i in indices]
        for group in ('prices','splits','dividends'):
            r['history'][group]={t:[v[i] for i in indices] for t,v in r['history'][group].items()}
        with self.assertRaisesRegex(ValueError,'pre-start'):
            run_tax_lab(r)

    def test_economic_failure_retains_nulls_and_unknown_errors_propagate(self):
        with patch('p107.tax_lab._strategies',side_effect=ValueError('Insolvent margin liquidation')):
            row=_small_run({}, {}, {})
            self.assertEqual(row['status'],'failed');self.assertIsNone(row['wealth_D']);self.assertIsNone(row['delta_D_C'])
        for error in (ArithmeticError('Conservation failed'),ValueError('Missing required prices')):
            with self.subTest(error=str(error)),patch('p107.tax_lab._strategies',side_effect=error):
                with self.assertRaises(type(error)):_small_run({}, {}, {})


if __name__=='__main__':unittest.main()
