"""Read the public method reference and defaults from the shipped inputs."""
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InputDefaults(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.values = {}
        self.feed(path.read_text(encoding='utf-8'))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and 'id' in attrs and 'value' in attrs:
            self.values[attrs['id']] = attrs['value']


def reference(root=ROOT):
    """Only read allowlisted public files; this endpoint does not accept paths."""
    root = Path(root)
    data = json.loads((root/'web/dist/assumptions.json').read_text(encoding='utf-8'))
    annual = json.loads((root/'configs/example_hypothetical.json').read_text(encoding='utf-8'))
    stock = InputDefaults(root/'web/dist/index.html').values
    study = InputDefaults(root/'web/dist/studies.html').values
    core = next(s for s in annual['strategies'] if s['name']=='core_130_30')
    pct = lambda v: f'{float(v):g}%'
    dollars = lambda v: f'${float(v):,.0f}'
    a = lambda key: pct(core[key]*100)
    h = lambda key: pct(stock[key])
    s = lambda key: pct(study[key])
    data['default_columns'] = [
        {'name':'Illustrative scenario', 'modes':['scenario']},
        {'name':'Historical stock research', 'modes':['history']},
        {'name':'Exit planning / Liquidity events', 'modes':['exits','one_time']},
        {'name':'Rebalancing / Portfolio sampling', 'modes':['rebalance','sampling']},
    ]
    data['defaults'] = [
        ['Starting equity', dollars(annual['initial_cash']), dollars(stock['initial_cash']), dollars(study['cash']), dollars(study['cash'])],
        ['Period', str(annual['horizon_years'])+' years', stock['research-start']+' to '+stock['research-end'], study['horizon']+' years', study['start']+' to '+study['end']],
        ['Price return', pct(annual['market_price_returns'][0]*100)+' per year', 'Observed closing prices', s('return')+' per year', 'Synthetic example; market data optional'],
        ['Long / short exposure', '130% / 30% for Core; 100% / 0% for Index and DI', h('research-long-exposure')+' / '+h('research-short-exposure')+' at entry', 'Same annual strategy exposures', '130% / 30% targets'],
        ['Management fee', a('manager_fee')+' Core; 0.03% Index; 0.25% DI', h('stock-manager')+' portfolio; none added to ETF benchmark', s('manager')+' Core; 0.03% Index; 0.25% DI', s('manager')+' portfolio; 0.03% benchmark'],
        ['Advisor fee', a('advisor_fee'), 'No separate advisor-fee field', s('advisor'), s('advisor')],
        ['Financing rate', a('long_financing_rate'), h('stock-finance'), s('finance'), s('finance')],
        ['Short borrow rate', a('short_borrow_rate'), h('stock-borrow'), s('borrow'), s('borrow')],
        ['Short rebate rate', a('short_rebate_rate'), h('stock-rebate'), s('rebate'), s('rebate')],
        ['Trading costs', 'Annual NAV: 0% Index / 0.03% DI / 0.05% Core; separate exit costs', h('stock-trade')+' of each trade', 'Same annual proxies and exit rates', s('trade')+' of each trade'],
        ['ST / LT tax rates', pct(annual['tax_st']*100)+' / '+pct(annual['tax_lt']*100), h('research-tax-st')+' / '+h('research-tax-lt'), s('tax-st')+' / '+s('tax-lt'), s('tax-st')+' / '+s('tax-lt')],
        ['Outside gain schedule', dollars(annual['outside_st_gains'][0])+' ST each year', dollars(stock['research-outside-st'])+' ST + '+dollars(stock['research-outside-lt'])+' LT per calendar year', dollars(study['annual-gain'])+' ST/year for exits; $0/$1M/$3M/$5M once in year '+study['event-year']+' for liquidity events', dollars(study['historical-gain'])+' ST once in calendar '+study['outside-year']],
        ['Loss rule', 'Assumed annual loss curve', h('research-threshold')+' loss trigger', 'Same assumed annual loss curves', s('threshold')+' loss trigger'],
        ['Rebalance / reentry', 'Annual aggregate notionals; no trade reconstruction', 'No target rebalancing; reentry after >'+stock['research-cooldown']+' calendar days', 'Annual aggregate notionals, adjusted for exit policy', 'Every '+study['rebalance']+' sessions and after switches; original reentry after >30 calendar days'],
    ]
    data['loss_curves'] = [dict(strategy=s['name'], rates=[x*100 for x in s['harvest_st_rates']], lt_rates=[x*100 for x in s['harvest_lt_rates']]) for s in annual['strategies']]
    data['exit_defaults'] = dict(eligible_core_long_gain_pct=float(study['stepup']), gift_year=int(study['gift-year']), recipient_st_pct=float(study['recipient-st']), recipient_lt_pct=float(study['recipient-lt']), extension_gain_share_pct=50)
    data['sampling_defaults'] = dict(draws=int(study['samples']), seed=int(study['seed']), long_count=int(study['n-long']), short_count=int(study['n-short']))
    data['default_sources'] = ['configs/example_hypothetical.json','web/dist/index.html','web/dist/studies.html','web/dist/portfolio.js','web/dist/studies.js']
    observed=json.loads((root/'configs/observed_study.json').read_text(encoding='utf-8'))
    data['default_columns'][2]['name']='Earlier annual studies'
    data['default_columns'][3]['name']='Earlier rebalancing / sampling'
    data['default_columns'].append({'name':'Historical tax lots · current studies','modes':['observed']})
    current=[dollars(observed['initial_cash']),observed['start_date']+' to '+observed['end_date'],
             'Observed nominal daily closes', '130% / 30% Core; 100% / 0% long-only controls',
             pct(observed['manager_pct'])+' Core; '+pct(observed['di_manager_pct'])+' long-only basket; '+pct(observed['benchmark_manager_pct'])+' additional SPY fee',
             pct(observed['advisor_pct']),pct(observed['financing_pct']),pct(observed['borrow_pct']),pct(observed['rebate_pct']),
             pct(observed['transaction_pct'])+' of each trade; included in basis/proceeds',
             pct(observed['tax_st_pct'])+' / '+pct(observed['tax_lt_pct']),
             '$1M ST once in '+str(observed['event_year'])+'; liquidity comparison varies amount',
             pct(observed['harvest_threshold_pct'])+' trigger on tax-lot basis; wash deferrals matched',
             'Every '+str(observed['rebalance_every_sessions'])+' sessions and after switches; reentry after >30 days']
    for row,value in zip(data['defaults'],current):row.append(value)
    data['observed_defaults']=dict(draws=observed['samples'],seed=observed['seed'],long_count=observed['long_count'],short_count=observed['short_count'],maintenance=observed['maintenance_equity_to_gross_pct'])
    data['default_sources'].append('configs/observed_study.json')
    return data
