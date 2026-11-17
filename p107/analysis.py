from copy import deepcopy
from math import isfinite
from .model import compare, with_gains


def difference(config, target='core_130_30'):
    summaries,_ = compare(config)
    return next(r['incremental_wealth_vs_index'] for r in summaries if r['strategy']==target)


def breakeven(config, character='st', maximum=1000000.0, step=5000.0):
    """Find break-even points by scanning and bisecting sign changes."""
    if not isfinite(maximum) or maximum < 0:
        raise ValueError('Search maximum must be finite and nonnegative')
    if not isfinite(step) or step <= 0:
        raise ValueError('Scan step must be finite and positive')
    if not isfinite(maximum / step) or maximum / step > 100000:
        raise ValueError('Search grid must contain at most 100001 regular points')
    def f(x): return difference(with_gains(config,x,character))
    points=[(i*step,f(i*step)) for i in range(int(maximum/step)+1)]
    # Include the upper bound even when it is not a multiple of the step.
    if points[-1][0] < maximum:
        points.append((maximum, f(maximum)))
    roots=[]
    for (a,fa),(b,fb) in zip(points,points[1:]):
        if fa == 0: roots.append(a)
        elif fa*fb < 0:
            for _ in range(60):
                mid=(a+b)/2
                fm=f(mid)
                if abs(fm) < 1e-7: a=b=mid; break
                if fa*fm<=0: b=mid
                else: a,fa=mid,fm
            roots.append((a+b)/2)
    if points[-1][1]==0: roots.append(points[-1][0])
    roots=sorted(set(round(x,6) for x in roots))
    return dict(horizon_years=config['horizon_years'],outside_character=character,
                schedule='same_nominal_amount_each_year',search_min=0,search_max=maximum,scan_step=step,
                status='crossing_found' if roots else 'no_crossing_in_range',
                roots_annual_usd=roots,root_residual_usd=[f(x) for x in roots],
                delta_at_zero=points[0][1],delta_at_max=points[-1][1],
                nondecreasing_on_scan=all(b[1]>=a[1]-1e-7 for a,b in zip(points,points[1:])),
                limitation='Finite grid detects sign-changing roots; does not prove monotonicity or exclude tangencies.'),points


def sensitivity_configs(config):
    result=[]
    def add(name,c,value): result.append((name,value,c))
    for n in [1,3,5,10]:
        c=deepcopy(config);c['horizon_years']=n;add('horizon_years',c,n)
    for st,lt in [(0,0),(.30,.15),(config['tax_st'],config['tax_lt']),(.45,.30),(config['tax_st'],config['tax_st'])]:
        c=deepcopy(config);c['tax_st']=st;c['tax_lt']=lt;c['ordinary_tax_rate']=st
        add('tax_rates_st_lt',c,f'{st}/{lt}')
    core=next(s for s in config['strategies'] if s['name']=='core_130_30')
    finance_grid=[round(max(0,core['long_financing_rate']+d),8) for d in [-.01,0,.02,.04]]
    rebate_grid=[0,round(max(0,core['short_rebate_rate']-.01),8),core['short_rebate_rate']]
    for key,values in [('manager_fee',[.002,.004,.008]),('advisor_fee',[0,.001,.005]),
                       ('long_financing_rate',finance_grid),
                       ('short_rebate_rate',rebate_grid),('short_borrow_rate',[0,.002,.01,.03]),
                       ('realization_st_fraction',[0,.1,.5,1]),
                       ('interest_deduction_fraction',[0,1]),('alpha_pre_cost',[-.01,0,.01])]:
        for value in values:
            c=deepcopy(config);next(s for s in c['strategies'] if s['name']=='core_130_30')[key]=value
            add('core_'+key,c,value)
    for scale in [0,.5,1]:
        c=deepcopy(config);s=next(s for s in c['strategies'] if s['name']=='core_130_30')
        s['harvest_st_rates']=[x*scale for x in s['harvest_st_rates']]
        add('core_loss_scale',c,scale)
    c=deepcopy(config);s=next(s for s in c['strategies'] if s['name']=='core_130_30')
    s['harvest_lt_rates']=[.2*x for x in s['harvest_st_rates']]
    s['harvest_st_rates']=[.8*x for x in s['harvest_st_rates']]
    add('core_loss_character',c,'80% ST / 20% LT')
    for ret in [0,.03,.06,.09]:
        c=deepcopy(config);c['market_price_returns']=[ret]*10;add('market_price_return',c,ret)
    c=deepcopy(config);c['market_price_returns']=[-.20,.10,.08,.06,.06,.06,.06,.06,.06,.06]
    add('market_path',c,'hypothetical_stress_fixed_loss_curve')
    for ret in [0,.02,.04]:
        c=deepcopy(config);c['cash_return_after_tax']=ret;add('cash_return_after_tax',c,ret)
    for character in ['st','lt']:
        for timing in ['initial','terminal']:
            add('outside_gains_timing',with_gains(config,500000,character,timing),f'{character}_{timing}_500000')
    return result


def one_time_gain_comparison(config, amounts=(0, 1000000, 3000000, 5000000),
                             event_year=1, character='st', target='core_130_30',
                             comparator='long_only_di'):
    """Evaluate a one-time outside gain, not a recurring annual gain.

    IMPORTANT: the scenario prototype assumes gross proceeds of the outside
    sale equal the modeled gain; real client proceeds must be supplied separately.
    Compare *incremental* wealth, because both strategies receive the same
    outside cash flow.
    """
    if target == comparator:
        raise ValueError('Target and comparator must differ')
    if type(event_year) is not int or not 1 <= event_year <= config['horizon_years']:
        raise ValueError('event_year outside investment horizon')
    rows = []
    for amount in amounts:
        c = with_gains(config, float(amount), character, 'year', event_year)
        summary, _ = compare(c)
        mapped = {x['strategy']: x for x in summary}
        if target not in mapped or comparator not in mapped:
            raise ValueError('Strategy name not found in model')
        a, b = mapped[target], mapped[comparator]
        rows.append(dict(outside_gain_usd=float(amount), event_year=event_year,
                         character=character, target=target, comparator=comparator,
                         target_terminal_wealth=a['terminal_after_tax_wealth'],
                         comparator_terminal_wealth=b['terminal_after_tax_wealth'],
                         incremental_after_tax_wealth=a['terminal_after_tax_wealth'] -
                                                      b['terminal_after_tax_wealth'],
                         target_harvested_losses=a['cumulative_harvested_st_loss'] +
                                                 a['cumulative_harvested_lt_loss'],
                         hypothetical=True))
    return rows


def one_time_gain_breakeven(config, event_year=1, character='st',
                            target='core_130_30', comparator='long_only_di',
                            maximum=5000000, step=25000):
    """Find crossing(s) against *one* outside gain event with bounded grid.

    Non-monotone outcomes can cross more than once. No root is not zero
    breakeven; return an explicit not-found status and grid diagnostics.
    """
    if not isfinite(maximum) or maximum <= 0 or not isfinite(step) or step <= 0:
        raise ValueError('Invalid positive finite search range or step')
    if maximum / step > 10000:
        raise ValueError('Grid too large; choose a larger step')
    if type(event_year) is not int or not 1 <= event_year <= config['horizon_years']:
        raise ValueError('Invalid event year')
    def delta(x):
        return one_time_gain_comparison(config, (x,), event_year, character,
                                        target, comparator)[0]['incremental_after_tax_wealth']
    points = [(0., delta(0.))]
    count = int(maximum / step)
    points += [(i * step, delta(i * step)) for i in range(1, count + 1)]
    if points[-1][0] < maximum:
        points.append((maximum, delta(maximum)))
    roots = []
    for (a, fa), (b, fb) in zip(points, points[1:]):
        if abs(fa) < 1e-7:
            roots.append(a)
        if fa * fb < 0:
            lo, hi, fl = a, b, fa
            for _ in range(55):
                mid = (lo + hi) / 2
                fm = delta(mid)
                if fl * fm <= 0:
                    hi = mid
                else:
                    lo, fl = mid, fm
            roots.append((lo + hi) / 2)
    if abs(points[-1][1]) < 1e-7:
        roots.append(points[-1][0])
    roots = sorted(set(round(x, 4) for x in roots))
    return dict(status='crossing_found' if roots else 'no_crossing_in_range',
                event_year=event_year, character=character,
                schedule='one_time_only', target=target, comparator=comparator,
                roots_usd=roots, residuals_usd=[delta(x) for x in roots],
                search_max=maximum, scan_step=step,
                delta_at_zero_usd=points[0][1],
                delta_at_max_usd=points[-1][1],
                caveat='Finite-grid search detects sign-change roots, not tangencies; '
                       'no crossing is not proof a strategy is always superior.'), points
