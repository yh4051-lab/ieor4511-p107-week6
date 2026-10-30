"""Write scenario results to CSV and standalone charts."""
import csv, hashlib, json, platform
from importlib.metadata import version
from pathlib import Path
from . import __version__
from .model import compare, with_gains
from .analysis import breakeven, sensitivity_configs


def write_csv(path, rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def charts(out, baseline, curve, sensitivity, config):
    import math
    from reportlab import rl_config
    from reportlab.graphics.shapes import Drawing, String, Line, Rect
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics import renderSVG,renderPDF
    from reportlab.lib.colors import HexColor,white
    import pypdfium2 as pdfium
    rl_config.invariant=1
    colors=[HexColor(x) for x in ['#375577','#b47d32','#16796c']]
    (out/'figures').mkdir(exist_ok=True)
    def base(title,subtitle):
        d=Drawing(780,430)
        d.add(Rect(0,0,780,430,fillColor=white,strokeColor=None))
        d.add(String(32,393,title,fontName='Helvetica-Bold',fontSize=18,fillColor=HexColor('#17324d')))
        d.add(String(32,370,subtitle,fontSize=10,fillColor=HexColor('#526575')))
        d.add(String(32,18,'HYPOTHETICAL | P107 Week 6 | Full liquidation | See configs and methodology',fontSize=9,fillColor=HexColor('#526575')))
        return d
    def save(d,name):
        renderSVG.drawToFile(d,str(out/'figures'/f'{name}.svg'))
        pdf=pdfium.PdfDocument(renderPDF.drawToString(d))
        page=pdf[0]; bitmap=page.render(scale=2)
        bitmap.to_pil().save(out/'figures'/f'{name}.png')
        bitmap.close();page.close();pdf.close()
    n=config['horizon_years']
    d=base('Terminal wealth after all modeled taxes',
           f'{n}-year scenario; starting cash ${config["initial_cash"]:,.0f}; identical outside cash flows; values in $ thousands')
    b=HorizontalBarChart();b.x=160;b.y=100;b.width=545;b.height=235
    b.data=[[r['terminal_after_tax_wealth']/1000 for r in baseline]]
    b.categoryAxis.categoryNames=[{'index':'Index','long_only_di':'Long-only DI','core_130_30':'Core 130/30'}.get(r['strategy'],r['strategy']) for r in baseline]
    vmax=max(r['terminal_after_tax_wealth']/1000 for r in baseline)*1.15
    step=10**math.floor(math.log10(max(vmax/5,1)))
    step=math.ceil(vmax/(5*step))*step
    b.valueAxis.valueMin=0;b.valueAxis.valueMax=step*5;b.valueAxis.valueStep=step
    b.bars[0].fillColor=colors[0];b.bars.strokeColor=None;b.barWidth=34
    b.categoryAxis.labels.fontSize=12;b.valueAxis.labels.fontSize=10
    b.barLabelFormat='%.1f';b.barLabels.nudge=8;b.barLabels.fontSize=11
    d.add(b);d.add(String(160,60,'Includes the same outside gain proceeds for every strategy; this is not a portfolio return.',fontSize=10))
    save(d,'terminal_wealth')
    d=base('Outside gains and the break-even condition',
           f'Core 130/30 minus index; {n}-year scenario; annual outside ST gains; both axes in $ thousands')
    lp=LinePlot();lp.x=85;lp.y=90;lp.width=620;lp.height=245
    lp.data=[[(r['annual_outside_st_gain']/1000,r['core_minus_index']/1000) for r in curve if r['annual_outside_st_gain']<=300000]]
    lp.lines[0].strokeColor=colors[2];lp.lines[0].strokeWidth=2.5
    lp.xValueAxis.valueMin=0;lp.xValueAxis.valueMax=300;lp.xValueAxis.valueStep=50
    ys=[p[1] for p in lp.data[0]]
    lo=math.floor(min(ys)/20)*20;hi=max(20,math.ceil(max(ys)/20)*20)
    lp.yValueAxis.valueMin=lo;lp.yValueAxis.valueMax=hi;lp.yValueAxis.valueStep=20
    lp.xValueAxis.labels.fontSize=10;lp.yValueAxis.labels.fontSize=10
    d.add(lp)
    y0=90+245*(0-lo)/(hi-lo)
    d.add(Line(85,y0,705,y0,strokeColor=HexColor('#9aa8b2'),strokeDashArray=[4,3]))
    d.add(String(260,49,'Annual outside short-term gains ($k)',fontSize=11))
    save(d,'outside_gains_breakeven')
    rows=[r for r in sensitivity if r['parameter']=='core_long_financing_rate' and r['strategy']=='core_130_30']
    d=base('Financing cost can reverse the comparison',
           f'Core 130/30 minus index; {n}-year scenario; other inputs fixed at the supplied configuration')
    lp=LinePlot();lp.x=85;lp.y=90;lp.width=620;lp.height=245
    lp.data=[[(float(r['value'])*100,r['incremental_wealth_vs_index']/1000) for r in rows]]
    lp.lines[0].strokeColor=colors[1];lp.lines[0].strokeWidth=2.5
    lp.xValueAxis.valueMin=3;lp.xValueAxis.valueMax=9;lp.xValueAxis.valueStep=1
    ys=[p[1] for p in lp.data[0]];lo=math.floor(min(ys)/20)*20;hi=max(20,math.ceil(max(ys)/20)*20)
    lp.yValueAxis.valueMin=lo;lp.yValueAxis.valueMax=hi;lp.yValueAxis.valueStep=20
    d.add(lp);d.add(Line(85,90+245*(-lo)/(hi-lo),705,90+245*(-lo)/(hi-lo),strokeColor=HexColor('#9aa8b2'),strokeDashArray=[4,3]))
    d.add(String(255,49,'Annual long financing rate (%)',fontSize=11))
    save(d,'financing_sensitivity')


def run(config, out, config_path, make_charts=True):
    out.mkdir(parents=True,exist_ok=True)
    summaries,ledger=compare(config)
    write_csv(out/'baseline_comparison.csv',summaries)
    write_csv(out/'annual_ledger.csv',ledger)
    scenarios=[];scenario_ledgers=[]
    for character in ['st','lt']:
        for amount in [0,25000,50000,100000,250000,500000]:
            c=with_gains(config,amount,character)
            sr,sl=compare(c)
            name=f'annual_{character}_{amount}'
            for r in sr: scenarios.append(dict(scenario=name,**r))
            for r in sl: scenario_ledgers.append(dict(scenario=name,**r))
    write_csv(out/'scenario_comparison.csv',scenarios)
    write_csv(out/'scenario_ledgers.csv',scenario_ledgers)
    sensitivity=[]
    for parameter,value,c in sensitivity_configs(config):
        sr,_=compare(c)
        for r in sr: sensitivity.append(dict(parameter=parameter,value=value,**r))
    write_csv(out/'sensitivity.csv',sensitivity)
    be,points=breakeven(config)
    blt,_=breakeven(config,'lt')
    (out/'breakeven.json').write_text(json.dumps({'st':be,'lt':blt},indent=2)+'\n',encoding='utf-8')
    curve=[dict(annual_outside_st_gain=x,core_minus_index=y,hypothetical=True) for x,y in points]
    write_csv(out/'breakeven_curve.csv',curve)
    if make_charts: charts(out,summaries,curve,sensitivity,config)
    generated_files = [
        'baseline_comparison.csv', 'annual_ledger.csv',
        'scenario_comparison.csv', 'scenario_ledgers.csv',
        'sensitivity.csv', 'breakeven.json', 'breakeven_curve.csv',
    ]
    if make_charts:
        generated_files.extend(
            f'figures/{name}.{extension}'
            for name in ['terminal_wealth', 'outside_gains_breakeven', 'financing_sensitivity']
            for extension in ['png', 'svg']
        )
    effective_config = json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False)
    metadata=dict(python_version=platform.python_version(),
                  config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
                  effective_config=config,
                  effective_config_sha256=hashlib.sha256(effective_config.encode('utf-8')).hexdigest(),
                  model_version=__version__,randomness='none',source=config.get('label', 'hypothetical scenario; consult input provenance'),
                  source_code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
                  files_sha256={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
                                for name in sorted(generated_files)})
    if make_charts:
        metadata['chart_dependencies']={name:version(name) for name in ['reportlab','pypdfium2','pillow']}
    (out/'run_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return summaries,be
