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

The original illustrative model still requires review of its source-based ST/LT estimates and cost assumptions. The historical module below supports configurable exposures, including 150/50 and 200/100. Full wash-sale rules, calibrated tracking risk, gradual exits and estate scenarios remain further research work.

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
