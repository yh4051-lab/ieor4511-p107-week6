# Input and output data dictionary

USD amounts are nominal. Rates and exposures are decimal fractions: `0.15=15%`, `1.3=130%`. Loss magnitudes are positive; signed realized P&L can be negative. `null` / blank means not applicable (for example terminal wealth before the final year), not zero. Public inputs are cataloged by relative path, classification, and SHA-256; restricted originals are stored separately.

## Inputs

| Field / group | Meaning |
|---|---|
| `initial_cash`, `horizon_years` | Starting after-tax cash/basis; integer annual horizon 1–10 |
| `market_price_returns` | Annual unlevered price-return scenario; excludes dividends; index and strategies share the path |
| `outside_st_gains`, `outside_lt_gains` | Nonnegative eligible external gains and corresponding incremental cash proceeds each year; same for every strategy |
| `tax_st`, `tax_lt`, `ordinary_tax_rate` | Flat effective scenario rates; no personal brackets or state calculation |
| `cash_return_after_tax` | Net return on side cash already accumulated at beginning of year |
| `long_exposure`, `short_exposure` | Long and positive absolute short MV divided by beginning net NAV; net must equal1 |
| `return_basis`, `alpha_pre_cost` | Gross price-return basis required; additional pre-cost scenario return, default0 |
| `manager_fee`, `advisor_fee`, `transaction_cost_rate` | Annual fractions of beginning NAV |
| `long_financing_rate` | Interest rate on `(long_exposure-1) × NAV` |
| `short_rebate_rate`, `short_borrow_rate` | Separate rates on short MV; the contract must specify whether quoted rebates already include borrow |
| `exit_transaction_rate` | Fraction of gross MV traded on full liquidation |
| `harvest_st_rates`, `harvest_lt_rates` | Exogenous realized loss magnitudes divided by annual beginning NAV |
| `realized_st_gain_rates`, `realized_lt_gain_rates` | Planned portfolio gain realizations divided by beginning NAV, before funding sales; baseline0 |
| `realization_st_fraction` | ST fraction for aggregate funding and exit P&L after Year1; Year1 override=1 |
| `interest_deduction_fraction` | Fraction of long interest allowed against rebate, capped so ordinary tax cannot become negative |

The public schedule records strategy, year, ST/LT loss rates, and the illustrative data classification. The input manifest records provenance and SHA-256 hashes; the JSON configuration supplies all numerical assumptions.

## Annual ledger

| Fields | Definition |
|---|---|
| `strategy`, `year`, `hypothetical` | Strategy id, one-based model year, scenario label (always true) |
| `nav_start`, `long_market_value`, `short_market_value_abs`, `net_exposure`, `gross_exposure` | Beginning capital and exposure checks; no extra wealth from short proceeds |
| `market_price_return`, `alpha_pre_cost`, `pre_cost_investment_pnl` | Gross scenario investment return, manager alpha assumption and resulting dollar P&L |
| `manager_fee`, `advisor_fee`, `long_financing_cost`, `short_borrow_cost`, `transaction_cost` | Positive cash expenses |
| `short_rebate`, `net_annual_cost`, `ordinary_interest_tax` | Positive rebate income; expenses less rebate; nonnegative modeled tax on unoffset rebate |
| `harvested_st_loss`, `harvested_lt_loss` | Positive exogenous harvesting events; separate from losses on funding/exit sales |
| `planned_realized_st_gain`, `planned_realized_lt_gain` | Explicit planned gain realizations; baseline zero |
| `expense_funding_realized_gain`, `tax_funding_sale`, `tax_funding_realized_gain` | Signed P&L from funding expenses; cash sale used for taxes; signed P&L on that sale |
| `portfolio_realized_st_gain_before_exit`, `portfolio_realized_lt_gain_before_exit` | All positive portfolio realizations by character before liquidation, including funding trades |
| `portfolio_realized_st_loss_before_exit`, `portfolio_realized_lt_loss_before_exit` | All positive portfolio loss magnitudes by character before liquidation, including funding trades |
| `outside_st_gain`, `outside_lt_gain` | Exogenous taxable gains/cash receipts outside strategy |
| `carry_st_start`, `carry_lt_start`, `carry_st_end`, `carry_lt_end` | Nonnegative tax carryforwards; final-year ends are AFTER full liquidation |
| `loss_used_st`, `loss_used_lt` | Losses used during this tax year, including carryforwards, against all eligible gains; not necessarily outside gains |
| `pre_exit_capital_tax`, `actual_capital_tax` | Counterfactual tax with no exit/additional tax-funding sale; actual joint annual liability. Final year is fully recomputed with liquidation |
| `current_outside_tax_relief_before_exit` | Reduction in marginal tax attributable to outside gains; diagnostic only, not added to wealth |
| `net_equity_basis_start`, `net_equity_basis_pre_exit` | Aggregate signed net basis before year / after annual activity; NOT tax-lot basis |
| `nav_after_costs_pre_exit` | Invested value after costs and ordinary-year tax funding; before final liquidation |
| `embedded_gain_pre_exit`, `embedded_gain_per_cumulative_harvest` | NAV minus net basis; ratio to cumulative exogenous harvested losses (blank when no harvesting) |
| `investor_cash_start`, `investor_cash_interest`, `investor_cash_pre_exit` | Separate investor cash ledger. Final-year pre-exit value deducts counterfactual tax and can be negative pending sale settlement |
| `realization_st_fraction` | Applied gain-character assumption for that year |
| `exit_transaction_cost`, `incremental_unwind_tax` | Full-exit trading cost; incremental final-year tax from exit, not a separate second tax bill |
| `exit_realized_st_gain`, `exit_realized_lt_gain`, `exit_realized_st_loss`, `exit_realized_lt_loss` | Final sale gain/loss magnitudes by scenario character, net of exit costs |
| `nav_after_exit`, `net_equity_basis_after_exit` | Zero after full liquidation; otherwise blank |
| `terminal_after_tax_wealth`, `capital_pnl_identity_error` | Actual modeled wealth in final year; residual of independent capital P&L accounting identity |

## Comparison and sensitivity outputs

`terminal_after_tax_wealth` includes common outside net gain proceeds; `wealth_net_of_common_outside_cash` subtracts their outside-only after-tax value. `incremental_wealth_vs_index` always compares matched inputs. `cumulative_net_costs` includes exit costs and deducts rebates. `cumulative_total_tax` includes annual capital and rebate taxes. `current_outside_relief_before_exit` in a summary is a sum of diagnostic annual reductions, including the final-year no-exit counterfactual; it must not be read as terminal savings.

`carry_st_after_exit` and `carry_lt_after_exit` are remaining tax attributes. Their `unused_carryforward_cash_value` is explicitly0. `max_capital_identity_error` is a numerical audit residual. `scenario`, `parameter`, `value` identify outside-gain schedules or one-at-a-time input changes. These rows are scenarios, not observations or independently sampled portfolio outcomes.

The break-even JSON contains the search interval, scan step, root(s), residuals, endpoints and whether the sampled curve was nondecreasing. An empty root list with `no_crossing_in_range` must not be interpreted as a verified global impossibility result.
