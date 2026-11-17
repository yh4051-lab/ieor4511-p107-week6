# Four-Strategy After-Tax Research: Experimental Branch

Branch: `codex/tax-aware-lab`. This feature was built in a separate Git worktree without changing, resetting or merging the original workspace or main. The earlier same-ticker long/short correction has been carried into this branch's original home page; the new batch engine still requires distinct original and replacement securities.

## Getting started

On Windows, extract the complete ZIP into a new folder and double-click `START-TAX-LAB.bat`. Python 3.12 and the Python Launcher are required. The first launch creates a virtual environment inside this folder and installs `requirements-lab.txt`, keeping package and TLS verification enabled.

The launcher prefers a separate local port, 8777. If another service already occupies that port, it selects an available port. Use the actual address opened by the launcher. Your existing application can continue running.

To launch from a terminal:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lab.txt
.venv\Scripts\python.exe web\launch_tax_lab.py
```

For the first run, keep the synthetic example and turn off cost sensitivity and scenario-path simulation. Run the four-strategy comparison first, then enable the 3 × 3 cost grid and 2–5 simulation paths. The interface displays elapsed calculation time; it does not present an invented progress estimate.

## How the four strategies differ

- A: A 100% long index ETF, without deliberate loss harvesting.
- B: The same candidate original securities, held as an equal-weight long-only basket with rule-based TLH. This is not a complete commercial direct-indexing product with calibrated tracking error.
- C: A 130/30 portfolio with fixed relative weights and scheduled rebalancing, without deliberate harvesting. Trades and actual model taxes are still recorded.
- D: A 130/30 portfolio with fixed long/short directions. CVXPY/CLARABEL selects weights and tax-lot sale priorities, alongside the same rule-based TLH, replacement securities and actual annual tax settlement.

The D–C difference includes optimized weights, lot selection, replacements and trading changes. It cannot all be described as pure tax alpha. D is not guaranteed to outperform the other strategies.

## Model and constraints

The local objective at each adjustment is: risk penalty + trading costs + estimated holding costs + a positive-realized-gain tax surrogate − expected return.

- The risk term is a benchmark-relative covariance quadratic. Estimates use only observations available before the decision date, with covariance shrinkage and numerical PSD regularization.
- Expected alpha defaults to zero. Future returns are not used to select weights.
- Long exposure must total 130% and short exposure 30%. A gross-exposure ceiling of 160% alone would not establish a 130/30 portfolio.
- Single-security caps constrain rebalance targets. Between trades, price changes can push actual concentration and gross exposure beyond those targets. If the candidate set cannot satisfy 130/30 under the selected caps, the model reports an explicit error.
- At fixed total exposures, uniform financing and borrow rates are generally constant with respect to weights. They remain in the recorded objective; the ledger separately charges actual financing debt and short market value.
- The optimizer conservatively penalizes positive realized gains and does not give an immediate cash credit for selling a loss. Actual loss use, carryforwards and wash-sale deferrals are settled in the accounting engine.
- The QP objective is not a global optimization of lifetime after-tax wealth. Cross-account wash sales, offsetting-position rules, securities-lending mechanics and intraday brokerage risk controls are not modeled in full.

This prototype follows the convex-optimization framework for trading off risk and costs. It does not claim to reproduce any particular tax-aware paper in full. For a general trading framework, see Boyd et al., *Multi-Period Trading via Convex Optimization*.

## Tax accounting and terminal wealth

Each lot retains its date, shares, economic basis and tax basis. Long unrealized profit is q × (P − B); the short-side sign is reversed. D can sell according to the optimizer's lot priorities. Existing studies retain FIFO when the allocator is not enabled.

The existing engine handles ST/LT netting, loss carryforwards, partial same-ticker wash-sale deferrals, dividends, financing, borrow and trading costs. Positions are closed at the end and outstanding model taxes are settled. Debt and costs already paid are reflected in net wealth and must not be deducted again; tax benefits must not be added twice.

The current case starts with cash. Importing a real client's existing tax lots is not available. Outside gains are accompanied by an equal cash inflow; this differs from modeling the full gross proceeds of an asset sale.

## How to interpret the four charts

1. **Wealth curves:** Interim values are book wealth after taxes actually paid, with unrealized tax liabilities still embedded. The final point is after full liquidation and tax settlement. Interim values are not all equivalent to immediate liquidation proceeds.
2. **Rule-triggered harvested losses and capital taxes paid:** A loss amount is not cash tax savings. Paid-tax differences also reflect different holdings, returns and trading paths. The annual ledger includes losses realized through other rebalancing and optimization trades.
3. **Potential tax on positive unrealized gains:** Each positive lot gain is multiplied by its model tax rate, before loss and carryforward offsets and without a complete estimate of closing costs. This is an explicitly labeled liability proxy, not an exact future tax bill.
4. **Cost-sensitivity heatmap:** Only financing and borrow rates change; all cells share the same frozen prices and other client conditions. Switch between D−A and D−C. Opposite signs at adjacent completed points identify a possible crossing interval, not an exact break-even threshold. Failed cells are not filled with zero.

The risk table uses price and dividend investment returns before current taxes and fees, excluding external cash flows and cash outside the investment account. Tracking error and volatility are annualized. Drawdown follows that investment-return path. Concentration is the largest single position's market value divided by investment-account NAV. ETFs are not decomposed into their underlying holdings. Undefined returns are reported as unknown, rather than converted into zero risk.

## Multiple periods, historical data and Monte Carlo

Research dates are editable. Observed-price studies require at least 20 return observations before the start date; a full lookback requires more warm-up data. The Yahoo source fetches an additional warm-up period. Insufficient data produces an explicit failure. Future observations are not used to complete the covariance estimate.

The local 2019–2025 snapshot is suitable for a study starting in 2020, using 2019 as warm-up. A ten-year study needs longer data. The synthetic example provides 2019 warm-up and a 2020–2022 evaluation period; it does not manufacture ten years of historical evidence.

Simulation jointly resamples 20-session blocks from pre-start observations, preserving common shocks across original securities, replacements and the benchmark. A–D are rerun on each simulated path. These are scenarios conditional on the block model, not real-world future probabilities. The ten-path limit is a usability limit for the prototype; small-sample quantiles do not establish robust statistical conclusions.

## Actual results from the synthetic example

Initial investment: $1,000,000. Period: January 2, 2020 through December 30, 2022. No outside gains. All prices in this example are artificial and are used only for operating and model checks.

| Strategy | Terminal after-tax wealth |
|---|---:|
| A Index | $1,159,503.48 |
| B Long-only basket + TLH | $1,183,624.28 |
| C 130/30 without harvesting | $896,513.74 |
| D QP + rule-based TLH | $970,613.53 |

D finishes $74,099.79 ahead of C, but $188,889.96 behind A. Its improvement cannot all be attributed to tax savings. B finishes higher on this synthetic path, but its rule-triggered harvested losses are zero; that outcome is not evidence that TLH caused its outperformance.

## Export and replay

The research ZIP contains `input.json` with the complete frozen observations and warm-up data, `result.json`, the four-strategy comparison CSV, each strategy's daily, annual, trade, realization, wash-sale and optimization ledgers, sensitivity and simulation CSVs, and file hashes.

```powershell
.venv\Scripts\python.exe -m p107.tax_lab --input input.json --out replay.json
```

Results record code hashes and the Python, NumPy, CVXPY and Clarabel versions. Different package versions or platforms may produce small floating-point differences.

If included in your package, `TAX-LAB-DEMO.html` opens the precomputed synthetic report without starting a server. To change conditions and recalculate, use `START-TAX-LAB.bat`. Changing any input marks the previous results as stale; rerun before downloading or printing.
