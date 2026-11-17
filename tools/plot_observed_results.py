"""Plot aggregate study outputs; raw security observations are not redistributed."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_observed'

def read(name):
    with (OUT/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))

def finish(fig,name):
    fig.text(.01,.015,'Observed 2019–2025 prices · hypothetical rules/costs · fixed stock universe, not PIT S&P 500',fontsize=8,color='#617187')
    fig.tight_layout(rect=(0,.045,1,1))
    (OUT/'figures').mkdir(exist_ok=True)
    fig.savefig(OUT/'figures'/(name+'.svg'),metadata={'Date':None})
    fig.savefig(OUT/'figures'/(name+'.png'),dpi=160,metadata={'Software':'P107 research'})
    plt.close(fig)

def main():
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    rows=[r for r in read('exits_summary.csv') if r['strategy']=='core_130_30']
    fig,ax=plt.subplots(figsize=(9,5))
    names=[r['policy'].replace(' full-portfolio exit',' exit').replace('3-year extension reduction + final sale','Extension reduction').replace('Gift with recipient sale','Gift → recipient sale') for r in rows]
    values=[float(r['terminal_after_tax_wealth'])/1e6 for r in rows]
    bars=ax.barh(names,values,color=['#65748b']+['#4465b2']*4+['#14786e']*2);ax.invert_yaxis()
    ax.set_xlabel('Terminal family wealth ($ millions, including common outside proceeds)');ax.set_title('Core 130/30 · historical exit policies',loc='left',pad=15)
    ax.bar_label(bars,fmt='%.2f',padding=4);ax.set_xlim(0,max(values)*1.13)
    finish(fig,'historical_exits')
    rows=read('cohort_summary.csv');completed=[r for r in rows if r['status']=='completed']
    delta=[float(r['incremental_wealth_vs_benchmark'])/1e6 for r in completed]
    fig,ax=plt.subplots(figsize=(9,4.8));ax.hist(delta,bins=15,color='#4465b2',edgecolor='white');ax.axvline(0,color='#14786e',lw=1.4)
    ax.set_title(f'{len(rows)} seeded random portfolios · {len(rows)-len(completed)} failed runs',loc='left',pad=15)
    ax.set_xlabel('After-tax wealth difference versus SPY ($ millions)');ax.set_ylabel('Completed portfolios')
    finish(fig,'random_portfolio_distribution')
    print('Saved two figures as PNG and SVG.')

if __name__=='__main__':main()
