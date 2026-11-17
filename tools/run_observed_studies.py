"""Run and replay observed-price studies; retain observations in local private files."""
import argparse,csv,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from p107.observed_studies import observed_defaults,run_observed_study


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['historical','exits','one_time','cohort','all'],default='all')
    p.add_argument('--samples',type=int,default=100)
    p.add_argument('--skip-replay',action='store_true')
    args=p.parse_args()
    out=ROOT/'results_observed';private=ROOT/'private/observed_runs'
    out.mkdir(exist_ok=True);private.mkdir(parents=True,exist_ok=True)
    modes=['historical','exits','one_time','cohort'] if args.mode=='all' else [args.mode]
    for mode in modes:
        start=time.perf_counter();c=observed_defaults()
        request=dict(mode=mode,engine='historical_lots',config=c,data_source='local_cache',
                     samples=args.samples,seed=4511,long_count=3,short_count=3,event_year=2021,character='st')
        result=run_observed_study(request,progress=lambda text:print(mode+': '+text,flush=True))
        (private/(mode+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        replay_equal=None
        if not args.skip_replay:
            print(mode+': offline replay',flush=True)
            replay=run_observed_study(result['request'],history_provider=lambda *a:(_ for _ in ()).throw(AssertionError('Network during replay')))
            replay_equal=result==replay
            if not replay_equal:raise AssertionError(mode+' exact replay failed')
        keys=list(dict.fromkeys(k for row in result['rows'] for k in row))
        path=out/(mode+'_summary.csv')
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
            for row in result['rows']:writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
        report=dict(mode=mode,status='PASS',observed_data_sha256=result['data_metadata']['data_sha256'],
                    actual_start=result['data_metadata']['actual_start'],actual_end=result['data_metadata']['actual_end'],
                    sessions=result['data_metadata']['sessions'],row_count=len(result['rows']),
                    exact_offline_replay=replay_equal,summary_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    source_sha256=result['metadata']['source_sha256'],assumptions=result['warnings'])
        if mode=='cohort':report.update(draws=result['draws'],failed_count=result['failed_count'],seed=result['seed'],
                                       benchmark_win_fraction=result['benchmark_win_fraction'])
        if mode=='one_time':report['searches']=result['searches']
        (out/(mode+'_verification.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(mode+': PASS; '+str(len(result['rows']))+' rows; '+str(round(time.perf_counter()-start,1))+' seconds',flush=True)


if __name__=='__main__':main()
