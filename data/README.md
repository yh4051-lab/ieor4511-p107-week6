# Public example inputs

The public configurations contain independent research assumptions. The repository also contains explicitly synthetic software fixtures and aggregate results generated using observed market data. Original provider workbooks, extracted provider loss schedules, raw observed prices and actual client trading records are not included.

- `configs/example_hypothetical.json` is the complete runnable configuration.
- `data/illustrative_loss_schedule.csv` lists the assumed loss magnitudes for each strategy and year.
- `data/input_manifest.csv` records classifications, provenance, and file hashes.
- `configs/observed_study.json` specifies the historical study's dates, fixed universe, replacements and assumed costs/taxes.
- `data/observed_source_manifest.json` records the separate local observed-price snapshot, its source and hashes. It is not a bundled data file. Download it with `python tools/fetch_market_study.py`; the output stays in ignored `data/raw/`.

The curves only exercise the accounting: larger early losses decline over time as a simple illustrative shape. Their levels are not empirically calibrated, and the assumed price path does not establish that the harvesting opportunities are achievable. See `docs/ASSUMPTIONS.md`.

Course reviewers can obtain the original source workbook, source-based configuration, source notes, and reference results from the restricted Drive package linked in `docs/RESTRICTED_DATA.md`. Keep that package in the ignored `private/` directory; do not commit its files or outputs.
