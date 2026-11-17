# P107: After-tax strategy comparison

IEOR E4511, P107 | Wedmont Private Capital

Team: Yaozhong Hu and Chun-An Ko

**Experimental branch:** the independent [Four-Strategy After-Tax Research prototype](TAX-AWARE-LAB.md) adds a four-strategy comparison, CVXPY allocation, tax-lot ledgers, cost sensitivity and block-bootstrap scenarios. On Windows, run `START-TAX-LAB.bat`; it opens its own local port, preferring 8777. The first example uses explicitly synthetic prices.

This Python project includes illustrative scenarios and historical tax-lot studies comparing a $1 million cash investment in an index strategy, long-only direct indexing, and a cash-funded Core 130/30 scenario. It tracks fees, financing, harvested losses, carryforwards, cost basis, and taxes through a full sale at the end of the holding period.

**The public example uses independent illustrative assumptions. It is not a historical backtest, provider performance, actual tax savings, or a completed final-project model.** The original source-based configuration and data are available separately to course reviewers through the [restricted data package](https://drive.google.com/file/d/1qM3_vRim7PjjDtkDC0bFYVb8deZpJyNk/view). See [reproduction instructions](docs/RESTRICTED_DATA.md).

## Observed-price studies · November 17

All four **Portfolio research** tabs now default to **Historical prices · tax lots**: 130/30 rebalancing/replacements, historical exit policies, one-time outside gains and random portfolios. The local 2019–2025 snapshot contains 41 securities and 1,760 sessions. These are observed prices with hypothetical trades, costs and client conditions; the fixed 20-stock universe is not point-in-time S&P 500 membership.

```sh
python -m pip install -r requirements-stock.txt
python tools/fetch_market_study.py
python tools/run_observed_studies.py --mode all --samples 100
python web/launch.py
```

Read [Observed-price research](docs/OBSERVED_RESEARCH.md) for algorithms, data provenance, replay instructions and remaining assumptions. `results_observed/` contains aggregate CSVs and verification reports. Raw price observations and full replay files stay in ignored local/private folders. Earlier calculations remain selectable for prior-export reproduction.

## Run the browser interface

**November 17 update:** choose **Portfolio research →** in the header.
The `/studies` page runs rebalancing with replacement
securities, exit comparisons, one-time outside gains, and seeded random
portfolios. It includes CSV exports and an exact offline replay package.
See [the study guide and coverage](docs/DOM_FEEDBACK_2026_11_10.md).
Choose **Assumptions & methodology** in either page header for the searchable
model reference at `/assumptions`: input defaults, loss calculations, trading
rules, taxes, exit policies, sampling algorithms and source-code links. It
describes starting settings; a completed run's export records the inputs used.
The earlier models retain their synthetic and annual examples. The new historical tax-lot default uses observed prices across all four tabs; select the calculation basis explicitly.

Download this repository using **Code > Download ZIP** and extract it into a new folder. On Windows with Python 3.12, double-click **START-STOCK.bat** to install the historical-data dependency and open the complete interface. To start from a terminal in the project folder, run:

```text
python web/launch.py
```

On Windows, use `py -3.12 web/launch.py` or `py -3.12 web/launch_stock.py`; both open the same integrated interface, preferring **http://127.0.0.1:8754**. If an older build or another app occupies that port, the launcher chooses another port through 8764; follow the actual URL it prints and opens. It reuses only a server whose build fingerprint matches this source and interface. On macOS or Linux, use `python3` if needed. The original illustrative scenario uses only the standard library. Historical stock research requires `python -m pip install -r requirements-stock.txt`, which `START-STOCK.bat` runs automatically. The historical stock form is open by default under **Portfolio → Custom Stock Research — After-Tax Loss Harvesting**. Complete it and press the single **Run comparison** button. **Analysis mode** defaults to **Historical stock research**; select **Illustrative scenario** to use the original model with the same button.

The three right-side tabs—**Summary**, **Annual ledger** and **Assumptions &
scope**—follow the selected **Analysis mode** and completed run. Historical
Summary shows after-tax wealth comparisons, an independent SPY pass/fail/tie
target, signed initial-exposure bars, equity curves and the harvesting bridge.
Annual ledger tracks the selected portfolio's taxes, trades and costs; the scope
tab records the exact settings and model notes. The original mode retains its
own break-even and holding-period comparisons. Downloads follow the mode:
**Download research JSON** for historical runs and **Download scenario ZIP** for
illustrative scenarios. This is a local Python application; GitHub does not host
its running interface.

## Reproduce the public results

```text
python -m pip install -r requirements.txt
python -m p107 --config configs/example_hypothetical.json --out results
python tools/verify_project.py
```

The requirements file pins optional figure dependencies. For CSVs without figures, run `python -m p107 --no-charts --out results_csv`. The verification command runs the model and web tests and compares all generated outputs from two complete runs. Verification records describe software checks, not investment validation.

## What to review

| File | Contents |
|---|---|
| `configs/example_hypothetical.json` | Complete public scenario and provenance |
| `data/input_manifest.csv` | Input classification and hashes |
| `results/baseline_comparison.csv` | Three-strategy comparison |
| `results/annual_ledger.csv` | Annual costs, tax losses, basis, and exit taxes |
| `results/breakeven.json` | Outside-gain threshold, search range, and residual |
| `results/sensitivity.csv` | Costs, taxes, horizons, and other assumptions |
| `docs/ASSUMPTIONS.md` | Meaning and limitations of the public inputs |
| `docs/METHODOLOGY.md` | Accounting order and conservation identities |
| `docs/LIMITATIONS.md` | Missing data and remaining sponsor scope |
| `docs/RESTRICTED_DATA.md` | Source-based reproduction for authorized reviewers |

The public default uses five years, 6% annual price appreciation, no dividends or alpha, $100,000 of annual outside ST gains, and illustrative 40% ST / 20% LT tax rates. Terminal wealth includes the same outside cash flows for every strategy; it is not the return on the $1 million investment alone. Current tax relief is not counted twice, and embedded gains are included in full-liquidation taxes.

The original illustrative model still requires review of its ST/LT loss and cost assumptions. The historical module below supports configurable exposures, including 150/50 and 200/100. The new sponsor workspace adds simplified exit and estate scenarios. Full wash-sale matching, authentic point-in-time data, calibrated tracking risk and client-specific tax treatment remain open work.

## Custom Stock Research — After-Tax Loss Harvesting

The English stock-research interface is embedded in Portfolio below Starting
cash. It combines historical positions, costs, dividends, taxes and loss
harvesting into one run, with full final liquidation. Manually select US tickers
and assign long/short budgets, such as 130/30, 150/50 or 200/100. You may choose
other exposures and split each leg across stocks using relative weights. The
engine converts initial budgets to fractional shares using historical entry
prices; optional Manual shares mode preserves direct quantity entry.

Using the single **Run comparison** button, the main **Summary** compares modeled after-tax wealth for the harvesting
strategy, the same initial portfolio without harvesting, and a 100%-long benchmark
funded with the same initial equity. The main **Annual ledger** lets you inspect
any of these three portfolios, including its taxes, trades, costs and holdings. The no-harvest comparison and exit-tax bridge help assess
harvesting separately from the effect of initial leverage and stock selection.
Target exposures apply at entry; the engine does not continuously rebalance.
The signed exposure chart uses initial equity rather than a misleading 100% pie.
A separate SPY target reports failure, success or a tie for the selected historical
period; it is not a forecast or client-suitability decision.

Run `START-STOCK.bat` on Windows. See [README-STOCK.md](README-STOCK.md) for startup,
allocation examples and offline replay, and [CODE-MAP.md](CODE-MAP.md) for changed
files. The original illustrative annual model remains separate. Tax rules are
simplified research assumptions; complete assumptions are retained in exported
JSON and the run-specific **Assumptions & scope** tab. Legacy research-level
API/CLI inputs remain supported for prior-run replay.


## Earlier implementation: November 10 sponsor feedback

The repository includes an **opt-in research extension** addressing Dominic
Corabi's four questions: 130/30 rebalancing and explicit temporary securities,
full/gradual/death/gift exits, one-time $1M/$3M/$5M external-gain break-even,
and reproducible multi-portfolio sampling from source-verified point-in-time
membership rows.

See **[Implementation and replication guide](docs/DOM_FEEDBACK_2026_11_10.md)**.

The new modules and CLI are research prototypes, not verified tax or portfolio
recommendations. The repository contains synthetic stock and membership
fixtures only. **It does not contain genuine point-in-time S&P 500 constituents,
complete historical borrow data, independently validated wash-sale substitutes,
or real client tax-lot histories.** Presenting the synthetic cohort as observed
S&P 500 performance would be incorrect.

Quick offline reproducibility check:

```sh
python -m unittest discover -s tests -v
python tools/dom_feedback.py scenario --config configs/example_hypothetical.json --event-year 2 --stepup-long-fraction 0.8 --out dom_scenario_results.json
python tools/dom_feedback.py historical --config configs/example_dom_historical.json --historical-data examples/dom_synthetic_history.json --out dom_historical_results.json
python tools/dom_feedback.py cohort --config configs/example_dom_historical.json --memberships examples/dom_synthetic_memberships.csv --historical-data examples/dom_synthetic_history.json --asof 2020-01-01 --long-count 3 --short-count 3 --samples 20 --seed 4511 --out dom_cohort_results.json
```

These commands use synthetic demonstration inputs and do not require network
access or changes to the existing browser interface. Historical
`/api/research/run` also accepts an opt-in
`engine_mode: "rebalanced_13030"` payload; the legacy browser form retains
its original input fields. Use the detailed guide for review safeguards.
