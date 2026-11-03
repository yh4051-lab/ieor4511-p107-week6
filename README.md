# P107: After-tax strategy comparison

IEOR E4511, Week 6 | Wedmont Private Capital

Team: Yaozhong Hu and Chun-An Ko

This is our initial Python model comparing a $1 million cash investment in an index strategy, long-only direct indexing, and a cash-funded Core 130/30 scenario. It tracks fees, financing, harvested losses, carryforwards, cost basis, and taxes through a full sale at the end of the holding period.

**The public example uses independent illustrative assumptions. It is not a historical backtest, provider performance, actual tax savings, or a completed final-project model.** The original source-based configuration and data are available separately to course reviewers through the [restricted data package](https://drive.google.com/file/d/1qM3_vRim7PjjDtkDC0bFYVb8deZpJyNk/view). See [reproduction instructions](docs/RESTRICTED_DATA.md).

## Run the browser interface

Download this repository using **Code > Download ZIP**, extract it, and open a terminal in its folder. With Python 3.12 installed, run:

```text
python web/launch.py
```

On Windows, `py -3.12 web/launch.py` also works. On macOS or Linux, use `python3` if needed. The interface opens locally at `http://127.0.0.1:8751`. Change the assumptions and click **Run comparison**. The engine and browser interface need no extra packages.

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


## Manual Yahoo stock experiment

Install the optional dependency with `py -3.12 -m pip install -r requirements-stocks.txt`
(on other systems use `python -m pip`). Start the server from the repository root:

```text
py -3.12 web/server.py
```

Open http://127.0.0.1:8751/stocks, or follow the stock link from the main page.
If the old launcher is already running a background server, close that server first;
on Windows its PID is in `web/server.pid` (PowerShell: `Stop-Process -Id (Get-Content web/server.pid)`).
Keep the new foreground terminal running; Ctrl+C stops it.

Enter comma-separated long and short Yahoo symbols, past dates, starting USD cash,
130/30, 150/50 or 200/100 initial exposure, and explicit annual cost assumptions.
Each side starts equally allocated. Fixed adjusted-price units are held without
rebalancing, so gross/net exposures drift. Results show pre-tax equity, drawdown,
position contributions and accrued costs; download JSON contains inputs, adjusted
prices, daily ledger, retrieval time and assumptions.

Only confirmed USD series are accepted. Empty downloads, unverified currencies,
missing sessions, incompatible coverage and nonpositive equity fail explicitly.
No synthetic data is substituted. Yahoo access requires internet and may be rate-limited.

This is a historical total-return proxy using Yahoo dividend/split-adjusted Close,
not executable stock prices, tax basis, tax-loss harvesting or an index replication.
Financing is an assumed charge on initial extension; borrowing uses prior-session
short value; fees use prior-session equity, ACT/365. Short adjusted returns approximate
dividend compensation. No short rebate, margin/availability model, taxes, transaction
fees or slippage is included. Do not use adjusted prices as tax-lot cost basis or feed
these results into the existing illustrative loss schedule as measured tax alpha.
Tests use deterministic fixtures; a live Yahoo download must also be checked locally.

Dependency reference: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
