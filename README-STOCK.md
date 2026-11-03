# Manual US Stock Research — Three Levels

The English research interface is embedded in **Portfolio**, immediately below
Starting cash. Expand **Custom Stock Research — Three Levels**. It is independent
of the original hypothetical scenario on the right.

## Start on Windows

1. Install Python 3.12 (recommended) with Python Launcher.
2. Extract the complete ZIP into a **new folder**. Keep your old project.
3. Double-click `START-STOCK.bat`. The first run installs `requirements-stock.txt`.
4. The launcher opens your local browser on port 8752.
5. Enter your initial equity, manual tickers, Long/Short directions, share counts,
   start/end dates and benchmark. Choose a research level and run.

If port 8752 is occupied by an older version, close its server first. The launcher
will not silently reuse an incompatible server or kill another process. An
alternative foreground command from the project root is:

```text
py -3 web/server.py --port 8753
```

Then open `http://127.0.0.1:8753` on your own computer. Logs for the background
launcher are `web/stock.stdout.log` and `web/stock.stderr.log`; its PID is saved
in `web/stock.pid`. Processes do not survive environment restarts.

## Research levels

| Level | Feature | Research value |
|---|---|---|
| 1 — Historical Position Validation | Manual tickers, shares and long/short directions; historical price P&L and equity path | Verify position arithmetic and demonstrate the workflow |
| 2 — After-Tax Lifecycle Comparison | Historical holdings, daily financing/borrow/management costs, dividends, annual tax settlement and full taxable exit | Compare modeled after-tax ending wealth across periods and horizons |
| 3 — Rule-Based Loss Harvesting | Actual modeled loss-triggered trades, next-close execution, delayed reentry, loss usage/carryforwards and exit-tax bridge | Evaluate harvesting, deferral, costs and final wealth under explicit rules |

All levels allow manual selection. There is no automatic stock-picking model.
Level 1 excludes dividends, costs, taxes and outside flows. Levels 2 and 3 include
those modeled components. Results should only be compared within the same level
and input assumptions.

## Historical data and position mechanics

- Use US USD equities or ETFs. AAPL, MSFT, SPY and BRK-B are examples, not recommendations.
- Select up to 20 distinct tickers. Combine duplicate holdings into one net position.
- Shares are initial **actual share quantities** at the first available session's
  close. The loader reconstructs nominal historical prices from Yahoo split-adjusted
  prices. Subsequent splits adjust quantity and per-share basis once.
- The engine keeps share quantities fixed, except splits and Level 3 trades. It
  does not assume cost-free daily rebalancing or multiply index returns by 1.3.
- Net/gross exposure is derived from the selected positions and investor equity.
  Short proceeds are restricted collateral, not extra investor wealth.
- History must exactly match the benchmark calendar. Missing bars, IPO gaps and
  unavailable securities fail visibly; no forward-filled or fabricated prices.
- End date must be before today in New York; incomplete current-day bars are excluded.
- Maximum requested interval is ten years. Yahoo corrections and present-day
  security selection can affect historical conclusions.

## Level 2 tax and cost assumptions

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

## Level 3 execution and attribution

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

The UI exports full JSON (inputs, nominal prices, actions, hashes, equity paths,
annual tax ledgers, trades, control runs and assumptions) and trades CSV.

Replay a downloaded JSON without network access:

```text
py -3 tools/replay_research.py path/to/p107-level-3-research.json
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
API remains for compatibility, but is not used by the three-level UI.

See `CODE-MAP.md` for the file/function map and implementation details.

```text
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s web/tests -v
```

Core tests use synthetic data and do not call Yahoo. Separately, all three levels
were exercised against live Yahoo AAPL/MSFT/SPY history, including a split, and
through the browser with exports and session restoration. The Python launcher
was tested in the cloud; the Windows batch wrapper was not executed on Windows.
