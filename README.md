# P107: After-tax strategy comparison

IEOR E4511, Week 6 | Wedmont Private Capital

Team: Yaozhong Hu and Chun-An Ko

This is our initial Python model comparing a $1 million cash investment in an index strategy, long-only direct indexing, and a cash-funded Core 130/30 scenario. It tracks fees, financing, harvested losses, carryforwards, cost basis, and taxes through a full sale at the end of the holding period.

**The public example uses independent illustrative assumptions. It is not a historical backtest, provider performance, actual tax savings, or a completed final-project model.** The original source-based configuration and data are available separately to course reviewers through the [restricted data package](https://drive.google.com/file/d/1qM3_vRim7PjjDtkDC0bFYVb8deZpJyNk/view). See [reproduction instructions](docs/RESTRICTED_DATA.md).

## Run the browser interface

Download this repository using **Code > Download ZIP** and extract it into a new folder. On Windows with Python 3.12, double-click **START-STOCK.bat** to install the historical-data dependency and open the complete interface. To start from a terminal in the project folder, run:

```text
python web/launch.py
```

On Windows, use `py -3.12 web/launch.py` or `py -3.12 web/launch_stock.py`; both now open the same integrated interface at **http://127.0.0.1:8754**. On macOS or Linux, use `python3` if needed. The original illustrative scenario uses only the standard library. Historical stock research requires `python -m pip install -r requirements-stock.txt`, which `START-STOCK.bat` runs automatically. Expand **Portfolio → Custom Stock Research — After-Tax Loss Harvesting** to configure historical positions; use **Run comparison** for the separate original illustrative scenario.

Use **Summary** for wealth and break-even comparisons, **Annual ledger** for costs and tax calculations, and **Assumptions & scope** for current coverage. **Download results** saves the effective inputs and outputs. This is a local Python application; GitHub does not host its running interface.

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

We still need to review the assumptions with Dom, clarify the source-based annual ST/LT estimates, confirm costs, and obtain security-level data. Individual tax lots, wash-sale controls, calibrated tracking risk, gradual exits, estate scenarios, 150/50, and 200/100 require further work.

## Custom Stock Research — After-Tax Loss Harvesting

The English stock-research interface is embedded in Portfolio below Starting
cash. It combines historical positions, costs, dividends, taxes and loss
harvesting into one run, with full final liquidation. Manually select US tickers
and assign long/short budgets, such as 130/30, 150/50 or 200/100. You may choose
other exposures and split each leg across stocks using relative weights. The
engine converts initial budgets to fractional shares using historical entry
prices; optional Manual shares mode preserves direct quantity entry.

Results compare modeled after-tax wealth for the harvesting strategy, the same
initial portfolio without harvesting, and a 100%-long benchmark funded with the
same initial equity. The no-harvest comparison and exit-tax bridge help assess
harvesting separately from the effect of initial leverage and stock selection.
Target exposures apply at entry; the engine does not continuously rebalance.

Run `START-STOCK.bat` on Windows. See [README-STOCK.md](README-STOCK.md) for startup,
allocation examples and offline replay, and [CODE-MAP.md](CODE-MAP.md) for changed
files. The original illustrative annual model remains separate. Tax rules are
simplified research assumptions; complete assumptions are retained in exported
JSON after removal of the long visible assumptions panel. Legacy research-level
API/CLI inputs remain supported for prior-run replay.
