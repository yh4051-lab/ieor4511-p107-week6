import csv,json,unittest,io
from copy import deepcopy
from pathlib import Path
from p107.taxes import settle
from p107.model import simulate,compare,with_gains,validate
from p107.analysis import breakeven,difference
from p107.reporting import run

ROOT=Path(__file__).resolve().parents[1]


def config():
    return json.loads((ROOT/'configs/example_hypothetical.json').read_text(encoding='utf-8'))


def frictionless(c):
    for s in c['strategies']:
        for k in ['manager_fee','advisor_fee','long_financing_rate','short_rebate_rate',
                  'short_borrow_rate','transaction_cost_rate','exit_transaction_rate']:
            s[k]=0
    return c


class TaxTests(unittest.TestCase):
    def test_same_character_before_cross_character(self):
        t=settle(100,100,150,0,0,0,.4,.2)
        self.assertEqual(t.tax,10)
        self.assertEqual(t.loss_used_st,150)

    def test_long_losses_cross_to_short_gains(self):
        t=settle(100,50,0,120,0,0,.4,.2)
        self.assertEqual(t.tax,12)

    def test_carryforward_preserves_character(self):
        t=settle(0,20,70,10,0,0,.4,.2)
        self.assertEqual((t.carry_st,t.carry_lt),(60,0))
        u=settle(100,0,0,0,t.carry_st,t.carry_lt,.4,.2)
        self.assertEqual(u.tax,16)

    def test_unused_losses_have_no_cash_credit(self):
        t=settle(0,0,70,20,10,5,.4,.2)
        self.assertEqual(t.tax,0)
        self.assertEqual((t.carry_st,t.carry_lt),(80,25))
        self.assertEqual(t.loss_used_st+t.loss_used_lt,0)

    def test_loss_usage_capped_at_eligible_gains(self):
        t=settle(50,30,1000,1000,0,0,.4,.2)
        self.assertEqual(t.loss_used_st+t.loss_used_lt,80)

    def test_negative_or_nan_rejected(self):
        for value in [-1,float('nan')]:
            with self.assertRaises(ValueError): settle(value,0,0,0,0,0,.4,.2)


class AccountingTests(unittest.TestCase):
    def test_equal_initial_cash_and_exposure(self):
        c=config()
        for s in c['strategies']:
            _,r=simulate(c,s['name'])
            self.assertEqual(r[0]['nav_start'],1e6)
            self.assertAlmostEqual(r[0]['net_exposure'],1)
        _,r=simulate(c,'core_130_30')
        self.assertAlmostEqual(r[0]['gross_exposure'],1.6)
        self.assertAlmostEqual(r[0]['long_market_value'],1300000)
        self.assertAlmostEqual(r[0]['short_market_value_abs'],300000)

    def test_financing_rebate_and_borrow_signs(self):
        _,r=simulate(config(),'core_130_30')
        self.assertAlmostEqual(r[0]['long_financing_cost'],15000)
        self.assertAlmostEqual(r[0]['short_rebate'],12000)
        self.assertAlmostEqual(r[0]['short_borrow_cost'],600)
        self.assertAlmostEqual(r[0]['net_annual_cost'],9100)

    def test_no_outside_gains_no_outside_tax_relief(self):
        for s in config()['strategies']:
            _,r=simulate(with_gains(config(),0),s['name'])
            self.assertTrue(all(abs(x['current_outside_tax_relief_before_exit'])<1e-7 for x in r))

    def test_harvest_creates_equal_embedded_gain_increase(self):
        c=frictionless(config());c['horizon_years']=1
        a,ra=simulate(c,'core_130_30');b,rb=simulate(c,'index')
        self.assertAlmostEqual(ra[0]['embedded_gain_pre_exit']-rb[0]['embedded_gain_pre_exit'],150000)
        self.assertAlmostEqual(a['terminal_after_tax_wealth'],b['terminal_after_tax_wealth'])

    def test_one_year_manual_index_calculation(self):
        c=frictionless(with_gains(config(),0));c['horizon_years']=1
        summary,_=simulate(c,'index')
        self.assertAlmostEqual(summary['terminal_after_tax_wealth'],1000000+60000*(1-.40))

    def test_two_year_manual_index_calculation(self):
        c=frictionless(with_gains(config(),0));c['horizon_years']=2
        summary,_=simulate(c,'index')
        gross=1000000*1.06**2
        self.assertAlmostEqual(summary['terminal_after_tax_wealth'],gross-(gross-1000000)*.20)

    def test_one_year_manual_core_with_costs_and_exit(self):
        c=config()
        c['horizon_years']=1
        summary, rows=simulate(c, 'core_130_30')
        # Gross appreciation is 60,000; rebate is 12,000; expenses are 21,100.
        before_expenses=1072000.0
        basis_before_expenses=862000.0  # 1m + rebate - 150,000 harvested loss
        after_expenses=before_expenses-21100.0
        exit_cost=after_expenses*1.6*.0002
        # Harvest and later capital realization cancel in a full one-year exit.
        taxable_gain=100000.0+60000.0-exit_cost
        expected=after_expenses-exit_cost+100000.0-taxable_gain*.40
        self.assertAlmostEqual(summary['terminal_after_tax_wealth'], expected)
        self.assertAlmostEqual(rows[0]['net_equity_basis_pre_exit'],
                               basis_before_expenses*(1-21100.0/before_expenses))

    def test_same_rates_full_exit_eliminates_free_tax_alpha(self):
        c=frictionless(config());c['tax_st']=c['tax_lt']=.25;c['cash_return_after_tax']=0
        results,_=compare(c)
        for r in results:self.assertAlmostEqual(r['incremental_wealth_vs_index'],0,places=6)

    def test_final_year_netting_does_not_allocate_lt_losses_to_st_first(self):
        c=frictionless(with_gains(config(),0));c['horizon_years']=2
        c['market_price_returns']=[0,.06]+[0]*8
        c['outside_st_gains']=[0,50000]+[0]*8
        s=next(s for s in c['strategies'] if s['name']=='long_only_di')
        s['harvest_st_rates']=[0]*10;s['harvest_lt_rates']=[0,.10]+[0]*8;s['realization_st_fraction']=0
        r,_=simulate(c,'long_only_di')
        expected=1060000+50000-50000*.40-60000*.20
        self.assertAlmostEqual(r['terminal_after_tax_wealth'],expected)

    def test_expense_sales_generate_realizations(self):
        _,rows=simulate(config(),'index')
        self.assertGreater(rows[0]['expense_funding_realized_gain'],0)
        # Cost itself is not silently deducted from taxable capital appreciation.
        self.assertGreater(rows[0]['net_equity_basis_pre_exit'],0)

    def test_tax_sales_when_outside_cash_absent(self):
        _,rows=simulate(with_gains(config(),0),'index')
        self.assertGreater(rows[0]['tax_funding_sale'],0)
        self.assertGreaterEqual(rows[0]['investor_cash_pre_exit'],-1e-7)

    def test_carryforward_survives_until_exit(self):
        summary,rows=simulate(with_gains(config(),0),'core_130_30')
        self.assertGreater(rows[0]['carry_st_end'],0)
        self.assertLess(rows[-1]['carry_st_end'],rows[-1]['carry_st_start'])
        self.assertEqual(summary['unused_carryforward_cash_value'],0)

    def test_carryforward_has_no_cash_terminal_value_in_market_loss(self):
        c=with_gains(config(),0);c['market_price_returns']=[-.05]*10
        summary,_=simulate(c,'index')
        self.assertGreater(summary['carry_lt_after_exit'],0)
        self.assertEqual(summary['unused_carryforward_cash_value'],0)

    def test_terminal_bridge(self):
        for s in config()['strategies']:
            summary,rows=simulate(config(),s['name']);r=rows[-1]
            expected=r['nav_after_costs_pre_exit']+r['investor_cash_pre_exit']-r['exit_transaction_cost']-r['incremental_unwind_tax']
            self.assertAlmostEqual(expected,summary['terminal_after_tax_wealth'])

    def test_global_wealth_conservation(self):
        c=config()
        for s in c['strategies']:
            summary,rows=simulate(c,s['name'])
            expected=(c['initial_cash']+summary['outside_gross_gain_proceeds']+summary['cumulative_pre_cost_pnl']
                      -summary['cumulative_net_costs']-summary['cumulative_total_tax']
                      +sum(r['investor_cash_interest'] for r in rows))
            self.assertAlmostEqual(expected,summary['terminal_after_tax_wealth'],places=6)

    def test_capital_and_basis_identities(self):
        c=config()
        for s in c['strategies']:
            summary,rows=simulate(c,s['name'])
            self.assertLess(summary['max_capital_identity_error'],1e-7)
            for r in rows:
                self.assertAlmostEqual(r['embedded_gain_pre_exit'],r['nav_after_costs_pre_exit']-r['net_equity_basis_pre_exit'])

    def test_higher_borrow_cost_reduces_wealth(self):
        c=config();a,_=simulate(c,'core_130_30')
        next(s for s in c['strategies'] if s['name']=='core_130_30')['short_borrow_rate']=.03
        b,_=simulate(c,'core_130_30')
        self.assertLess(b['terminal_after_tax_wealth'],a['terminal_after_tax_wealth'])

    def test_rebate_ordinary_tax_switch(self):
        c=config();next(s for s in c['strategies'] if s['name']=='core_130_30')['interest_deduction_fraction']=0
        _,r=simulate(c,'core_130_30')
        self.assertAlmostEqual(r[0]['ordinary_interest_tax'],12000*.40)

    def test_long_term_harvesting_is_supported(self):
        c=config();s=next(s for s in c['strategies'] if s['name']=='long_only_di')
        s['harvest_lt_rates']=[.01]*10
        result,r=simulate(c,'long_only_di')
        self.assertEqual(r[0]['harvested_lt_loss'],10000)
        self.assertGreater(result['cumulative_harvested_lt_loss'],10000)

    def test_no_mutation_of_inputs(self):
        c=config();original=deepcopy(c);compare(c);self.assertEqual(c,original)

    def test_invalid_horizon_and_negative_basis_fail(self):
        c=config();c['horizon_years']=11
        with self.assertRaises(ValueError):validate(c)
        c=config();c['strategies'][0]['harvest_st_rates']=[2]*10
        with self.assertRaises(ValueError):simulate(c,'index')

    def test_provider_net_return_input_rejected(self):
        c=config();c['strategies'][0]['return_basis']='net_provider_return'
        with self.assertRaises(ValueError):validate(c)

    def test_full_loss_or_invalid_net_exposure_rejected(self):
        c=config();c['market_price_returns'][0]=-1
        with self.assertRaises(ValueError):validate(c)
        c=config();c['strategies'][2]['long_exposure']=1.2
        with self.assertRaises(ValueError):validate(c)


class SourceAndReproTests(unittest.TestCase):
    def test_public_schedule_matches_config_and_is_labeled(self):
        with (ROOT/'data/illustrative_loss_schedule.csv').open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        for s in config()['strategies']:
            selected=[r for r in rows if r['strategy']==s['name']]
            self.assertEqual([int(r['year']) for r in selected],list(range(1,11)))
            self.assertEqual([float(r['harvest_st_rate']) for r in selected],s['harvest_st_rates'])
        self.assertTrue(all(r['data_class']=='independent illustrative assumption' for r in rows))

    def test_public_input_manifest_hashes_and_classification(self):
        import hashlib
        with (ROOT/'data/input_manifest.csv').open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        for r in rows:
            self.assertEqual(r['classification'],'independent illustrative assumptions')
            self.assertEqual(hashlib.sha256((ROOT/r['file']).read_bytes()).hexdigest(),r['sha256'])

    def test_breakeven_bracket_and_residual(self):
        c=config();r,_=breakeven(c)
        self.assertEqual(len(r['roots_annual_usd']),1)
        x=r['roots_annual_usd'][0]
        self.assertLess(abs(difference(with_gains(c,x))),.01)
        self.assertLess(difference(with_gains(c,x-100)),0)
        self.assertGreater(difference(with_gains(c,x+100)),0)

    def test_no_root_is_reported_without_fabrication(self):
        c=config();c['tax_st']=c['tax_lt']=0;c['ordinary_tax_rate']=0
        r,_=breakeven(c)
        self.assertEqual(r['roots_annual_usd'],[])
        self.assertEqual(r['status'],'no_crossing_in_range')

    def test_breakeven_includes_partial_final_interval(self):
        c=config()
        result, points=breakeven(c, maximum=1000000, step=750000)
        self.assertEqual([p[0] for p in points], [0,750000,1000000])
        self.assertEqual(len(result['roots_annual_usd']),1)
        self.assertAlmostEqual(result['delta_at_max'], difference(with_gains(c,1000000)))

    def test_breakeven_rejects_invalid_search_parameters(self):
        for maximum, step in [(-1,5000),(1,float('inf')),(1,0),(1,-1),
                              (float('nan'),1),(float('inf'),1)]:
            with self.subTest(maximum=maximum,step=step):
                with self.assertRaises(ValueError):
                    breakeven(config(),maximum=maximum,step=step)

    def test_run_metadata_excludes_old_files_and_records_effective_inputs(self):
        out=ROOT/'work'/'test_metadata'
        out.mkdir(parents=True,exist_ok=True)
        (out/'old_output.txt').write_text('old output',encoding='utf-8')
        c=config()
        c['outside_st_gains']=[25000.0]*10
        run(c,out,ROOT/'configs/example_hypothetical.json',False)
        metadata=json.loads((out/'run_metadata.json').read_text(encoding='utf-8'))
        self.assertNotIn('old_output.txt',metadata['files_sha256'])
        self.assertEqual(len(metadata['files_sha256']),7)
        self.assertEqual(metadata['effective_config'],c)
        self.assertTrue((out/'old_output.txt').exists())

    def test_byte_identical_csv_and_json_reproduction(self):
        # Keep reproducibility checks in the project's work folder.
        td=ROOT/'work'/'test_repro'
        self.assertTrue(td.resolve().is_relative_to(ROOT.resolve()))
        a,b=td/'a',td/'b'
        p=ROOT/'configs/example_hypothetical.json'
        run(config(),a,p,False);run(config(),b,p,False)
        self.assertEqual(sorted(x.name for x in a.iterdir()), sorted(x.name for x in b.iterdir()))
        for p in a.iterdir():self.assertEqual(p.read_bytes(),(b/p.name).read_bytes(),p.name)


if __name__=='__main__':unittest.main()
