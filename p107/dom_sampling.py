"""Deterministic portfolio cohorts from USER-SUPPLIED point-in-time membership.

This deliberately refuses to infer historical S&P 500 composition from today's
constituents. Constituent source provenance must be independently audited.
"""
from copy import deepcopy
from datetime import date
from math import isfinite
import random

from .market_data import normalize_ticker


def _members_at_date(memberships, as_of):
    when=date.fromisoformat(as_of)
    selected=set()
    if not isinstance(memberships,list):
        raise ValueError('Supply membership records from a point-in-time source')
    for record in memberships:
        if not isinstance(record,dict):
            raise ValueError('Invalid membership record')
        ticker=normalize_ticker(record['ticker'])
        if not record.get('source_id') or record.get('point_in_time_verified') is not True:
            raise ValueError('Every membership requires source ID and independent PIT verification')
        start=date.fromisoformat(record['member_from'])
        end=date.fromisoformat(record['member_to']) if record.get('member_to') else None
        published=record.get('published_as_of')
        if published and date.fromisoformat(published)>when:
            raise ValueError('Membership source not known at formation date (lookahead)')
        if start<=when and (end is None or when<end):
            selected.add(ticker)
    return sorted(selected)


def sample_portfolios(memberships, as_of, n_long, n_short, draws=100, seed=4511,
                      replacements=None):
    """Sample non-overlapping long and short sets at one historical formation date.

    A PIT source and historical availability are required for real backtests.
    Returns configs only; no prices are invented.
    """
    if (type(n_long) is not int or type(n_short) is not int or
        n_long<1 or n_short<1 or type(draws) is not int or not 1<=draws<=10000 or
        type(seed) is not int):
        raise ValueError('Positive portfolio counts and integer seed required')
    universe=_members_at_date(memberships,as_of)
    if len(universe)<n_long+n_short:
        raise ValueError('Insufficient verified historical constituents for disjoint books')
    rng=random.Random(seed)
    samples=[]
    for i in range(draws):
        names=rng.sample(universe,n_long+n_short)
        longs=sorted(names[:n_long]);shorts=sorted(names[n_long:])
        positions=([dict(ticker=t,side='long',weight=1/n_long) for t in longs]+
                   [dict(ticker=t,side='short',weight=1/n_short) for t in shorts])
        if replacements is not None:
            missing=[t for t in names if t not in replacements]
            if missing:
                raise ValueError('Missing independently reviewed replacements: '+','.join(missing[:5]))
        samples.append(dict(portfolio_number=i+1,formation_date=as_of,seed=seed,
                            point_in_time_membership_source='user_supplied_verified',
                            positions=positions,
                            substitutes={t:replacements[t] for t in names} if replacements else None))
    return samples


def evaluate_portfolio_cohort(base_config, memberships, as_of, n_long, n_short,
                              run_one, draws=100, seed=4511):
    """Run all synthetic selections through a caller-supplied, tested engine.

    run_one(config) must return a dict with summary. No Yahoo API calls or PIT
    membership data are fabricated by this wrapper.
    """
    if not callable(run_one):
        raise ValueError('Supply a callable research engine')
    samples=sample_portfolios(memberships,as_of,n_long,n_short,draws,seed,
                              base_config.get('substitutes'))
    results=[]
    for sample in samples:
        c=deepcopy(base_config)
        c['positions']=sample['positions']
        if sample['substitutes'] is not None:c['substitutes']=sample['substitutes']
        outcome=run_one(c)
        summary=outcome['summary']
        ending=float(summary['terminal_after_tax_wealth'])
        if not isfinite(ending):
            raise ValueError('Portfolio result not finite')
        results.append(dict(sample_id=sample['portfolio_number'],seed=seed,
                            formation_date=as_of,long_names=[p['ticker'] for p in c['positions'] if p['side']=='long'],
                            short_names=[p['ticker'] for p in c['positions'] if p['side']=='short'],
                            after_tax_terminal_wealth=ending,
                            harvested_losses=summary.get('cumulative_harvested_losses'),
                            provenance='user_supplied_PIT_membership'))
    ordered=sorted(x['after_tax_terminal_wealth'] for x in results)
    def quantile(p):
        k=(len(ordered)-1)*p;i=int(k);j=min(len(ordered)-1,i+1)
        return ordered[i]*(1-(k-i))+ordered[j]*(k-i)
    return dict(draws=draws,seed=seed,formation_date=as_of,
                p05_wealth=quantile(.05),median_wealth=quantile(.5),p95_wealth=quantile(.95),
                results=results,
                limitations=['No PIT membership, no defensible historical-universe claim.',
                             'Random selection removes manual stock picking but not data selection or factor bias.',
                             'Constituent delistings, missing prices, borrow feasibility and transaction cost need verification.'])
