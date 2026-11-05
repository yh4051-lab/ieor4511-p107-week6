# Custom Stock Research — After-Tax Loss Harvesting

The English research form is open by default in **Portfolio**, below Starting
cash. Complete **Custom Stock Research — After-Tax Loss Harvesting**, then use
the single **Run comparison** button at the bottom of the input panel. The same
completed historical run appears in **Summary**, **Annual ledger** and
**Assumptions & scope** on the right. **Analysis mode** defaults to **Historical
stock research**; the original **Illustrative scenario** remains optional.

## Start on Windows

1. Install Python 3.12 (recommended) with Python Launcher.
2. Extract the complete ZIP into a **new folder**. Keep your old project.
3. Double-click `START-STOCK.bat`. The first run installs `requirements-stock.txt`.
4. The launcher opens the current build in your local browser. Its preferred URL
   is **http://127.0.0.1:8754**; use the actual URL printed by the launcher.
5. Enter your initial equity, manual tickers, Long/Short directions, allocation,
   start/end dates and benchmark. Review costs, tax rates and harvesting rules,
   then click **Run comparison**. The right-side **Summary** displays this run;
   inspect its records in **Annual ledger** and its settings in **Assumptions & scope**.

Both terminal commands below open the same integrated interface:

```text
py -3.12 web/launch.py
py -3.12 web/launch_stock.py
```

Run either command, not both. If you skip `START-STOCK.bat`, install historical-data dependencies first with `py -3.12 -m pip install -r requirements-stock.txt`. The original illustrative model needs no extra packages.

The launcher reuses a server only when its build fingerprint matches the current
source, interface and configuration. If port 8754 is occupied by an older build
or another app, it tries ports 8755 through 8764 and prints/opens the chosen URL.
It does not stop other processes. An alternative foreground command from the
project root is:

```text
py -3.12 web/server.py --port 8755
```

Then open `http://127.0.0.1:8755` on your own computer. Logs for the background
launcher are `web/stock.stdout.log` and `web/stock.stderr.log`; its PID is saved
in `web/stock.pid`. Processes do not survive environment restarts.

## One integrated after-tax workflow

The browser combines historical positions, costs, taxes and rule-based loss
harvesting in one run. There is no level selector. Every run includes:

- Historical nominal prices, split-adjusted share counts and dividend cash flows.
- Daily financing, short borrow, rebate and management costs; trading costs.
- Annual capital-gains tax, loss usage, carryforwards and final taxable liquidation.
- Loss-triggered trades, delayed reentry and an exit-tax attribution bridge.
- Matched outside cash flows for three ending-wealth comparisons: the strategy
  with harvesting, the same initial portfolio without harvesting, and a long-only
  benchmark funded with the same initial equity.

You manually select every stock. The app does not choose stocks for you. The
benchmark retains 100% initial long exposure; changing the strategy's leverage
changes its market risk, so a positive difference versus the benchmark is not by
itself a measure of risk-adjusted alpha. The no-harvest control uses exactly the
same starting positions as the harvesting strategy and helps isolate the effect
of the harvesting rule.

## One button and three matching result views

**Run comparison** executes only the engine selected in **Analysis mode**. In
the default **Historical stock research** mode, the complete stock form supplies
prices, positions, costs, taxes and harvesting settings. There is no separate
Run After-Tax Research button. Pressing Enter in a research input uses the same
submit path. The initial page does not automatically run the illustrative model
or choose stocks for you.

| Control or view | Historical research behavior |
|---|---|
| **Summary** | SPY pass/fail/tie status, three after-tax wealth cards, differences, simple gain ratio, signed initial-exposure bars, three equity curves and harvesting tax/cost bridge. |
| **Annual ledger** | Select harvesting strategy, no-harvest control or selected benchmark; inspect annual taxes, trades, accounting/exposure, costs and initial holdings/prices. When the selected benchmark differs from SPY, the SPY target is also available as a ledger choice. |
| **Assumptions & scope** | Exact settings, requested/actual dates, tax and cost rates, harvesting rules, SPY evaluation, model limits and provenance for the same completed run. |
| **Analysis mode** | Select historical research or the original illustrative model. Each retains its completed results while the page is open; switching mode does not run either engine. |
| **View research results** | Compact sidebar link that returns to the historical Summary. |
| **Download research JSON** | Main toolbar download for the full historical run. |
| **Download trades CSV** | Historical Annual ledger export for the currently selected portfolio. |

The original model uses its own visible inputs in **Illustrative scenario** mode
and the same **Run comparison** button. Its break-even graph and 1/3/5/10-year
sensitivity table remain exclusive to that mode. The historical form is disabled
when inactive, and inactive illustrative fields do not block research validation.
Only Starting cash is shared. Changing shared equity marks both results stale;
other model-specific edits mark only their own results stale. Stale historical
results are visibly marked across all three views and cannot be exported until
rerun. Session storage restores input drafts, not completed research datasets
after a page reload.

**Reset defaults** in research mode restores 130/30, the historical settings and
two blank Long/Short rows. You still select the tickers yourself. In illustrative
mode, reset restores that model's baseline.

## SPY target and initial-exposure chart

Each new browser run requests an independent, 100%-long SPY comparison with the
same initial equity and outside cash flows. The configured benchmark remains
available; choosing QQQ, for example, does not relabel QQQ as SPY.

The Summary status compares strategy and SPY ending wealth **after modeled costs,
taxes and full liquidation**:

- **Strategy failed — below SPY**: strategy ending wealth is lower.
- **Strategy passed — above SPY**: strategy ending wealth is higher.
- **Strategy matched SPY**: the displayed ending wealths are equal.

The verdict compares each wealth rounded to USD cents; its displayed difference
uses those rounded wealths. This is a target for the selected historical period,
not a risk-adjusted alpha estimate, forecast or client-suitability classification.
Harvesting can improve the selected portfolio relative to its no-harvest control
while the strategy still fails the SPY target.

Signed initial-exposure bars show Long, Short and a 100% equity reference using
initial investor equity **before opening fees** as the denominator. They preserve
130% long / 30% short, gross 160% and net 100% rather than forcing exposures into
a 100% pie chart. A final-holdings pie is omitted because the model fully
liquidates all holdings at the end.

## Choose your initial allocation

The default **Allocate by long / short exposure** mode converts your budgets to fractional shares
using the first available historical closing price. Long and short exposures are
separate percentages of initial investor equity; they do not need to sum to 100%.

For $1,000,000 of initial equity:

| Long / short exposure | Initial long budget | Initial short budget | Net exposure | Gross exposure |
|---|---:|---:|---:|---:|
| 130% / 30% | $1,300,000 | $300,000 | 100% | 160% |
| 150% / 50% | $1,500,000 | $500,000 | 100% | 200% |
| 200% / 100% | $2,000,000 | $1,000,000 | 100% | 300% |
| 200% / 50% | $2,000,000 | $500,000 | 150% | 250% |

You may enter exposures from 0% to 1,000% per leg. At least one leg must be
positive. A positive leg requires at least one selected stock; a zero-budget leg
must have no positions. Higher values increase modeled risk and financing costs;
they are inputs to the scenario, not evidence that a broker would allow it.

Each stock has a **relative weight within its long or short leg**. The app
normalizes weights separately within each leg. Two long stocks with weights
3 and 1 receive 75% and 25% of the long budget. Two short stocks with weights
1 and 1 each receive half the short budget. A single stock receives its entire
leg's budget regardless of its positive relative weight.

```text
Initial shares = initial equity × leg exposure / 100
                 × stock weight / sum of weights in that leg
                 ÷ first historical price
```

The optional **Enter shares manually** mode keeps directly entered share quantities;
it derives net and gross exposures from those holdings. It does not apply the
target budget inputs.

These are **initial** allocations. Shares remain fixed except for corporate
actions and harvesting trades; there is no daily rebalance to maintain 130/30.
Reentry restores the original split-adjusted share count. Prices, costs, taxes
and time out of the market can cause later exposures to drift.

## Historical data and position mechanics

- Use US USD equities or ETFs. AAPL, MSFT, SPY and BRK-B are examples, not recommendations.
- Select up to 20 distinct position tickers. Combine duplicate holdings into one net position. The data request can additionally include the selected benchmark and SPY.
- Target budgets are resolved to fractional shares at the first available session's
  close; the manual mode uses your entered initial share quantities. The loader
  reconstructs nominal historical prices from Yahoo split-adjusted prices. Subsequent splits adjust quantity and per-share basis once.
- The engine keeps share quantities fixed, except splits and harvesting trades. It
  does not assume cost-free daily rebalancing or multiply index returns by 1.3.
- Net/gross exposure is derived from the selected positions and investor equity.
  Short proceeds are restricted collateral, not extra investor wealth.
- History within the research window must exactly match the benchmark calendar. Missing bars, IPO gaps and
  unavailable securities fail visibly; no forward-filled or fabricated prices.
- Later observations are used only to recover split factors. Missing prices after
  the selected end date are excluded from calculations and recorded in audit
  metadata; invalid in-window prices and invalid split actions still fail.
- End date must be before today in New York; incomplete current-day bars are excluded.
- Maximum requested interval is ten years. Yahoo corrections and present-day
  security selection can affect historical conclusions.

## Tax and cost accounting

Daily costs use actual calendar days / 365. Financing accrues on actual debit
balance; borrow costs on prior short market value; rebates on restricted short
cash. Management fees apply to prior total account equity including cash. Fees
and taxes are funded from free cash, then debt. Positive cash repays debt.

Long dividends are paid and taxed on the ex-date using one flat input rate.
Short dividends are paid as cash expenses without a tax deduction. There is no
reinvestment. Short rebate is taxed at the ST rate as an ordinary-income proxy.
Management, financing, borrow and trading costs are nondeductible expenses in
this simplified model. A benchmark ETF's fund fees are already reflected in
observed prices; custom strategy management fees are not charged again to it.

Long capital realizations held more than 365 days use the LT rate; shorter
holdings and all short-cover realizations use the ST rate. Annual netting and
character-preserving carryforwards reuse `p107/taxes.py`. Final-year outside
gains, carryforwards and all exit realizations are jointly settled. Exit tax is
the difference from a counterfactual settlement without liquidation, so it can
be negative. Unused carryforwards have no terminal cash value or cash refund.

Outside ST/LT gains and equal gross cash proceeds are added at each modeled
calendar year end, including partial first/last years, without proration. They
are matched for strategy, benchmark and no-harvest control. Ending wealth includes
these flows. The reported simple gain ratio removes gross outside proceeds and
divides by initial equity; it is **not TWR, IRR or CAGR** and includes outside-gain
tax burden.

## Harvesting execution and attribution

After a position has been held more than 30 calendar days, a close-to-basis loss
at or beyond the configured threshold generates a signal. The sale/cover executes
at the **next available close**, not at the already observed signal price. Actual
execution can produce a smaller loss or even a gain. Only realized losses from
those trades count as harvested losses.

The same ticker reopens only after **more than** the configured cooldown calendar
days (minimum 30). A cooldown of 30 permits reentry on day 31 or the next available
session. There are no replacement securities or optimizer; equity is uninvested
while a position is out. Reentry restores the original split-adjusted share count,
not the original weight, and may require financing. Splits adjust pending reentry
quantities even while the position is closed.

Results include both a passive benchmark and the **same manual starting portfolio
without harvesting**. The tax bridge is:

```text
Pre-exit capital-tax relief - extra exit tax = total modeled capital-tax saving
```

Terminal wealth can still differ because of time out of the market, dividends,
financing and transaction costs. That difference is not pure tax alpha. Harvesting
can make the client worse off despite producing more realized losses.

## Export and reproduce

The **Download research JSON** toolbar button and **Download full research JSON**
in the historical Annual ledger export inputs, nominal prices, actions, hashes,
equity paths, annual tax ledgers, trades, control runs, resolved allocations and
assumptions. **Download trades CSV** exports the currently selected portfolio
(strategy, no-harvest control, selected benchmark or separate SPY target when available). The original scenario has its own
**Download scenario ZIP** button in illustrative mode.

Replay a downloaded JSON without network access:

```text
py -3 tools/replay_research.py path/to/p107-after-tax-research.json
```

The replay checks the saved numeric-data SHA-256 and reproduces summary, daily,
annual, trade and position records. A synthetic example is included at
`examples/research-level3-synthetic.json`; it is clearly not real market evidence.

Run a JSON configuration from the command line and export all ledgers:

```text
py -3 tools/run_research.py configs/example_stock_research.json --out work/my-research
```

Choose a new output directory for each run. The full configuration and data are
stored with results; transient in-memory history caching is not your audit record.

## Important scope limits

Summary keeps the model note short. The dedicated **Assumptions & scope** tab
shows the settings and modeling notes for the same completed historical run;
complete notes also remain in exported JSON and this document.

The tax system is an educational proxy, not a complete US return. The waiting
rule checks only this modeled account and does not adjudicate substantially
identical securities, household accounts, options, straddles or special short-sale
rules. State taxes are represented only if you choose suitable effective input
rates; there is no jurisdiction-specific calculation. Dividend qualifications
are not inferred. Borrow availability, margin calls, short recalls, market impact,
gradual exits, liquidity shocks, death and basis step-up are not modeled.
Nonpositive equity stops a run rather than inventing a valid continuation.

These features support the sponsor's research questions under explicit assumptions.
They do not by themselves finish the research paper, client decision matrix or
empirical calibration requested in the project brief.

## Tests and changes

Do not delete `tests/test_model.py` or the original tests. The earlier one-stock
label-only UI is replaced by the embedded research interface. The old snapshot
API remains for compatibility, but is not used by the integrated UI. Historical
level 1/2/3 API and CLI configurations also remain supported for replay of prior
research; new browser requests always use the full harvesting engine (level 3).
They also send `evaluate_spy: true`. This opt-in adds `spy_benchmark`, SPY wealth,
raw and display-rounded differences, and `spy_status` to the result. Saved legacy
API/CLI configurations without that flag retain their previous output contract.

See `CODE-MAP.md` for the file/function map and implementation details.

```text
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s web/tests -v
```

Core tests use synthetic data and do not call Yahoo. They include hand-calculated
130/30 and higher-exposure allocation examples, taxes, costs and harvesting
controls. Live Yahoo history and browser checks are separate from those tests. The Python launcher
was tested in the cloud; the Windows batch wrapper was not executed on Windows.
