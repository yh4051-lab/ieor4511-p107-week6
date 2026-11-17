# Observed-price research results

Run on November 17, 2026, using 1,760 common trading sessions from January 2, 2019 through December 31, 2025. Prices, split events and dividends are observations; portfolio selection, trades, tax rates and financing terms are research assumptions. These are not actual client returns or manager performance.

## Files and checks

| File | Contents | Verification |
|---|---|---|
| `historical_summary.csv` | Core with harvesting, the same stocks without harvesting, SPY and a long-only harvesting basket | 4 rows; exact offline replay |
| `exits_summary.csv` | 7 exit policies across 3 strategies | 21 rows; exact offline replay |
| `one_time_summary.csv` | $0, $1M, $3M and $5M outside gains in 2021 across 3 strategies | 12 rows; exact offline replay |
| `cohort_summary.csv` | 100 random portfolios, seed 4511, with SPY and no-harvest controls | 100 requested, 100 completed, 0 failed; exact offline replay |
| `sensitivity.csv` | Financing, stock borrowing, tax rates and holding-period changes | 11 cases across 3 strategies |
| `*_verification.json` | Data and code hashes, assumptions, replay status and search details | Generated with the corresponding study |
| `figures/` | Exit-policy comparison and random-portfolio distribution, as PNG and SVG | Generated from the CSVs |

## Read the results carefully

All wealth figures include the same outside proceeds across compared strategies. For the default example, this is a one-time $1M short-term gain in 2021, in addition to the initial $1M portfolio. It is not correct to divide terminal wealth by $1M and call the result the portfolio return.

The default stock selection finishes ahead of SPY even without an outside gain. Neither the Core-versus-SPY nor the Core-versus-long-only comparison has a break-even crossing on the tested $0–$5M grid. The report records **no crossing in range**, not a zero-dollar threshold. A different portfolio, time period or cost assumption can change this result.

Of the 100 random portfolios, 40 finish ahead of SPY. This is a descriptive fraction for these draws, dates, rules and fixed 20-stock universe, not a forecast win probability. The universe contains currently identifiable stocks; random sampling does not remove survival, universe-selection or factor bias. It is not a point-in-time S&P 500 study.

The difference between harvesting and no harvesting includes replacement-security returns, transaction costs and tax-funding effects. It must not be presented as pure tax savings. Likewise, an exit-policy comparison includes differences in market exposure and cash withdrawal timing, as well as taxes.

## Reproduce

From the repository root:

```sh
python -m pip install -r requirements-observed.txt
python tools/fetch_market_study.py
python tools/run_observed_studies.py --mode all --samples 100
python tools/observed_sensitivity.py
python tools/plot_observed_results.py
python tools/verify_project.py
```

The frozen observations and full replay bundles remain local in ignored `data/raw/` and `private/observed_runs/`. A fresh download may differ if the vendor revises history. Each browser export includes its exact observations and request for offline replay. See [Observed research methodology](../docs/OBSERVED_RESEARCH.md) for the data hash, accounting order, controls and limitations.
