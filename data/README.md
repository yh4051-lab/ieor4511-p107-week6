# Public example inputs

The numerical inputs in this repository are independent illustrative assumptions. They contain no original provider workbook, extracted provider loss schedule, historical prices, tax lots, or actual trading records.

- `configs/example_hypothetical.json` is the complete runnable configuration.
- `data/illustrative_loss_schedule.csv` lists the assumed loss magnitudes for each strategy and year.
- `data/input_manifest.csv` records classifications, provenance, and file hashes.

The curves only exercise the accounting: larger early losses decline over time as a simple illustrative shape. Their levels are not empirically calibrated, and the assumed price path does not establish that the harvesting opportunities are achievable. See `docs/ASSUMPTIONS.md`.

Course reviewers can obtain the original source workbook, source-based configuration, source notes, and reference results from the restricted Drive package linked in `docs/RESTRICTED_DATA.md`. Keep that package in the ignored `private/` directory; do not commit its files or outputs.
