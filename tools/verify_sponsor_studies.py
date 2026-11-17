"""Run all four sponsor studies and prove exact offline replay. No market claims."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p107.studies import defaults, run_study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'verification/sponsor_studies')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = defaults()
    checks = []
    for mode in ('exits', 'one_time', 'historical', 'cohort'):
        annual = mode in ('exits', 'one_time')
        request = dict(mode=mode, config=base['annual' if annual else 'historical'],
                       stepup_long_fraction=.8, event_year=2, data_source='synthetic',
                       samples=20, seed=4511, long_count=3, short_count=3)
        result = run_study(request)
        replay = run_study(result['request'],
                           history_provider=lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected network')))
        assert result == replay, mode + ': replay differs'
        assert len(result['rows']) == dict(exits=21, one_time=12, historical=3, cohort=20)[mode]
        if mode == 'historical':
            for run in result['results'].values():
                assert max(abs(row['wealth_identity_error']) for row in run['daily']) < .01
                assert max(abs(row['capital_identity_error']) for row in run['daily']) < .01
        csv_path = args.out/(mode + '_summary.csv')
        with csv_path.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=list(result['rows'][0]))
            writer.writeheader()
            writer.writerows(result['rows'])
        checks.append(dict(mode=mode, data_label=result['data_label'],
                           rows=len(result['rows']), exact_offline_replay=True,
                           run_id=result['run_id'], summary_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest()))
    report = dict(status='PASS', market_performance_claims=False, checks=checks,
                  source_sha256=result['metadata']['source_sha256'])
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS: all 4 studies, 56 comparison rows, exact offline replay; 20 seeded synthetic portfolios.')


if __name__ == '__main__':
    main()
