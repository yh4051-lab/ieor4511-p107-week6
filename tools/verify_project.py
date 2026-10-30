"""Run the delivered source audit, tests, CLI and complete byte-replay checks."""
import argparse,csv,hashlib,json,platform,re,subprocess,sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    if (ROOT/'tools/audit_sources.py').is_file():
        parser.add_argument('--source-root',type=Path)
    else:
        parser.set_defaults(source_root=None)
    args=parser.parse_args()
    out=ROOT/'verification';out.mkdir(exist_ok=True)
    report=dict(verification_time_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),python=platform.python_version(),commands=[])
    def execute(name,tail):
        command=[sys.executable,'-X','utf8',*tail]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        log=result.stdout+result.stderr
        (out/f'{name}.txt').write_text(log,encoding='utf-8')
        report['commands'].append(dict(name=name,command=['python','-X','utf8',*tail],exit_code=result.returncode))
        if result.returncode:
            (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            raise RuntimeError(f'{name} failed; see verification/{name}.txt')
        return log
    if args.source_root:
        execute('source_audit',['tools/audit_sources.py','--source-root',str(args.source_root)])
        report['source_audit_rerun']=True
    else:report['source_audit_rerun']=False
    test_log=execute('tests',['-m','unittest','discover','-s','tests','-v'])
    report['tests_run']=int(re.search(r'Ran (\d+) tests',test_log).group(1))
    report['tests_passed']=test_log.rstrip().endswith('OK')
    execute('example_run',['-m','p107','--config','configs/example_hypothetical.json','--out','results'])
    execute('replay_run',['-m','p107','--config','configs/example_hypothetical.json','--out','work/full_replay'])
    web_log=execute('web_tests',['-m','unittest','discover','-s','web/tests','-v'])
    report['web_tests_run']=int(re.search(r'Ran (\d+) tests',web_log).group(1))
    report['web_tests_passed']=web_log.rstrip().endswith('OK')
    comparisons=[]
    metadata=json.loads((ROOT/'results/run_metadata.json').read_text(encoding='utf-8'))
    generated=sorted([*metadata['files_sha256'],'run_metadata.json'])
    for filename in generated:
        rel=Path(filename)
        a=ROOT/'results'/rel
        b=ROOT/'work/full_replay'/rel
        comparisons.append(dict(file=rel.as_posix(),sha256=sha(a),byte_identical=b.is_file() and sha(a)==sha(b)))
    report['output_files_compared']=len(comparisons)
    report['all_outputs_byte_identical']=all(x['byte_identical'] for x in comparisons)
    report['output_checks']=comparisons
    for filename in ['baseline_comparison.csv','annual_ledger.csv','scenario_comparison.csv','scenario_ledgers.csv','sensitivity.csv','breakeven_curve.csv']:
        with (ROOT/'results'/filename).open(encoding='utf-8') as f:
            report[filename+'_rows']=sum(1 for _ in csv.DictReader(f))
    report['source_code_sha256']={p.relative_to(ROOT).as_posix():sha(p) for folder in ['p107','tests','tools'] for p in sorted((ROOT/folder).glob('*.py'))}
    report['requirements_sha256']=sha(ROOT/'requirements.txt')
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if not report['all_outputs_byte_identical'] or not report['tests_passed']:
        raise RuntimeError('Verification failed; inspect verification.json')
    print(f"PASS: {report['tests_run']} model tests and {report['web_tests_run']} web tests; {len(comparisons)} outputs byte-identical across two full runs.")


if __name__=='__main__':main()
