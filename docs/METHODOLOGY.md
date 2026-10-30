# Accounting methodology

This is a deterministic aggregate scenario model. It is reproducible financial accounting under stated assumptions, not an implementation of a broker's tax-lot ledger. All strategies start with the same cash, follow the same price-return path, and receive the same outside gain cash flows. No randomness, fitted alpha, simulated price records, or implied volatility estimate is used.

## State and annual order

Let V be strategy net equity, B its **aggregate signed net-equity basis proxy**, C investor side cash, Hs/Hl realized harvested losses, and Rs/Rl planned realized capital gains. A signed net basis for a long/short portfolio can be negative because it nets long cost against short proceeds; it is not the basis of an individual security. Negative long-only basis is rejected.

1. Beginning notionals: long = L×V; absolute short = S×V; net = L-S = 1; gross = L+S. Core has $1.3m long and $0.3m short on day one. Financing debit and restricted short proceeds are matched in this net-equity abstraction; short proceeds are not added to investor wealth. Notionals reset annually; tax consequences of actual rebalancing are not reconstructed.
2. Gross price P&L = V×(market price return + assumed alpha). Default alpha is zero. Rebate R = S×V×rebate rate. Before expenses, V* = V + P&L + R.
3. Loss/gain events leave value unchanged and change basis: B* = B + R - Hs - Hl + Rs + Rl. Reinvested rebate adds cost basis, preventing it from being taxed a second time as capital appreciation on exit.
4. Expenses E = manager + advisor + long interest + short borrow + trading proxy. Sell fraction E/V* of aggregate equity to fund E. Basis removed = E×B*/V*. Realized gain on this funding sale = E - basis removed. End value becomes V* - E. This is a transparent proportional-sale approximation, not optimal lot selection. Ongoing trading costs are treated conservatively as nondeductible cash expenses; execution-specific basis adjustments require tax-lot data.
5. Grow existing investor side cash at the configured **after-tax** cash rate, then receive common outside ST/LT gain proceeds. Calculate rebate tax separately. In ordinary years, net all portfolio realizations and outside gains with starting carryforwards. If side cash is insufficient to pay taxes, bisect the extra equity withdrawal w satisfying: `w + available cash = capital_tax(w) + rebate_tax`. Realizations on w are included. The algorithm rejects insolvency instead of allowing an unexplained negative funding account.
6. ST and LT losses first offset gains of the same character; only a residual loss offsets the other character. Remaining losses carry forward by character. All ST/LT rates are flat scenario parameters. This approximates the netting structure described by [IRS Topic 409](https://www.irs.gov/taxtopics/tc409) and [Publication 550 (2025)](https://www.irs.gov/publications/p550), consulted 2026-10-29. It does not reproduce a full Schedule D or the exceptions for short sales and wash sales.
7. For the final year, compute the counterfactual tax before exit, then **recompute the entire final-year tax settlement** using the same starting carryforwards plus all liquidation realizations. Do not consume carryforward sequentially as if outside gains and the exit were different tax years. Exit proceeds are net of explicit exit transaction costs. Both net equity and net basis are zero after full exit.

## Wealth and tax bridge

`terminal_after_tax_wealth = value_before_exit - exit_transaction_cost + available_side_cash - final_year_joint_capital_tax - rebate_tax`

Equivalently:

`terminal_after_tax_wealth = value_before_exit + side_cash_after_counterfactual_pre_exit_tax - exit_transaction_cost - incremental_unwind_tax`

Here `incremental_unwind_tax = final_year_joint_capital_tax - counterfactual_pre_exit_tax`. It can be negative in a loss-making liquidation. Pre-exit relief is a diagnostic counterfactual in the final year, **not a separate refund received and then counted again**.

`current_outside_tax_relief_before_exit` compares the marginal tax from adding outside gains to the portfolio's pre-exit tax computation against standalone outside tax. It is zero when outside gains are zero. It is not cumulative wealth added; earlier relief is already present as higher side cash. Carryforwards used internally at exit reduce the actual tax calculation, and unused carryforwards receive zero terminal cash value.

Two independently checked conservation identities are:

1. **Capital P&L:** cumulative realized capital P&L before exit + embedded gain before exit = cumulative price P&L. Financing/rebate are income/expenses, not capital P&L.
2. **Investor wealth:** initial cash + common gross outside gain proceeds + cumulative price P&L + side-cash earnings - cumulative net expenses (including exit, net of rebates) - all modeled taxes = terminal wealth.

The normalized `wealth_net_of_common_outside_cash` subtracts the outside-only cash account's hypothetical after-tax terminal value from each strategy. It is useful for comparison, but is not literally a standalone strategy account balance. For the default case the common amount is $300,000.

## Tax character is a material scenario assumption

All realizations through exactly Year 1 are ST. Later, an explicit fraction of each aggregate discretionary realization is ST (default Core 10%, DI 5%, index 0%); the remainder is LT. The same fraction applies to expense/tax funding sales and the aggregate exit gain or loss. This proxy cannot distinguish a short gain from a long loss inside the aggregate book. Real long/short tax lots are required before claiming legal holding-period classification, actual tax savings, or client suitability.

## Break-even and sensitivity design

For 5-year default inputs, solve Core terminal wealth minus index terminal wealth as a function of a constant nominal amount of outside ST gains **each year**. Scan $0–$1,000,000 in $5,000 increments and bisect every sign-changing interval. Record the range, endpoints, roots, residual and observed monotonicity; report `no_crossing_in_range` when none is found. A finite scan cannot rule out tangencies or off-grid roots for arbitrary future model designs. The LT-gain calculation is separate.

Sensitivity rows change one assumption at a time: horizon; ST/LT tax-rate pairs; Core management/advisor fees, long financing, rebate, borrow cost, gain character, interest deductibility and alpha; loss scale/mix; price path; side-cash return; and initial versus terminal outside-gain timing. The stress path keeps the exogenous loss curve fixed and is therefore an **accounting stress**, not a calibrated volatility/harvesting response. No probability or confidence interval is attached to these scenarios.

## Reproducibility

This public example uses independently specified illustrative assumptions. Restricted workbook extraction checks and source records are supplied separately in the course data package; they are not public input data.

The engine uses full binary floating-point precision internally and writes unrounded CSV values; narrative tables round to cents. No time stamps or random seeds affect numeric output. Tests check independent hand calculations, netting boundaries, funding and capital identities, full-exit neutrality under equal rates and zero costs, invalid inputs, source mapping, root residuals and repeat output bytes. The verification script additionally regenerates PNG/SVG figures twice and compares hashes in the actual local environment.
