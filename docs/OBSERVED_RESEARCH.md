# Observed-price research: implementation and reproduction

Updated November 17, 2026. These are hypothetical strategies using observed prices, not manager returns or actual client tax savings.

## What changed

All four Portfolio research tabs now default to the same historical tax-lot engine. The original annual scenarios and earlier historical engines remain available to reproduce prior exports. Select the calculation basis explicitly; no scenario result silently inherits a historical price path.

| Employer question | Current implementation | Boundary |
|---|---|---|
| Rebalance to 130/30 and use replacements | Post-fee NAV targets, next-close harvest signals, explicit temporary securities, FIFO lots, quantity-matched same-ticker wash deferrals, daily maintenance liquidation | Household/IRA/options activity and historical locate/borrow terms are not supplied. Different-issuer substitutes are assumptions, not legal approval. |
| Death, gift, 3–5-year exit | Each policy follows observed prices and actual modeled lots. Proportional 3/4/5-year withdrawals, extension reduction, lot-level FMV adjustment, donor funding sales and recipient dual basis | Death/gift occur at the horizon. Eligibility is assumed for ordinary property. Estate/gift tax is a supplied dollar cost, default zero; no household exemption calculation. |
| One-time $1M/$3M/$5M gain | All three strategies, one selected calendar-year ST/LT gain, full final taxes, finite-grid break-even and residuals | Cash received equals incremental taxable gain. Real proceeds and original outside basis are separate client inputs. |
| Many random portfolios or PIT constituents | 100 seeded draws from a documented fixed stock universe, each with no-harvest and SPY controls; failed runs retained | This takes the random-portfolio branch of the request. It is not a historical S&P 500 membership backtest and does not remove survival or universe-selection bias. |

## Observed inputs and provenance

`configs/observed_study.json` specifies the study before results: 2019-01-02 through 2025-12-31, 20 candidate stocks, 20 different-issuer replacements and SPY. The retrieved snapshot has 1,760 common sessions and 41 securities. Its full numeric hash is `5e3130f66409e2216312c9c23273897fa268210a70ba0f843474819df2efa90d`. Individual study exports contain only the relevant symbols and therefore have their own hashes.

Yahoo Finance / yfinance supplies daily Close, Dividends and Stock Splits. The adapter retains retrieval/source metadata, normalizes split-adjusted observations to nominal units using later split events, and then applies each returned split once in the ledger. It rejects incomplete or mismatched trading calendars rather than filling prices or deleting failed stocks. Dividend cash follows the vendor ex-date, not a separate payment-date feed. The frozen snapshot is used for replay because the vendor can revise history.

The fixed universe is currently identifiable large US stocks chosen for sector variety before running results. This choice is not evidence of historical index membership. A random stock draw reduces individual portfolio picking but not selection, survival or factor bias. The replacement map is visible and configurable; substitutes preserve notional, not matching factor exposures.

Observed data stay in ignored `data/raw/` and private replay exports. The public repository contains the download command, configuration, aggregate CSVs, verification reports and code; it does not redistribute the raw price file or confidential provider inputs.

## Run and replay

```sh
python -m pip install -r requirements-observed.txt
python tools/fetch_market_study.py
python tools/run_observed_studies.py --mode all --samples 100
python tools/observed_sensitivity.py
python tools/plot_observed_results.py
python web/launch.py
```

Open Portfolio research and choose **Historical prices · tax lots**. Use the saved snapshot, fetch historical prices, or upload an authorized saved dataset. All four tabs share dates, portfolio rules and the historical engine. The random tab uses its listed positions as the universe/replacement map; long/short assignments are drawn from that list.

`results_observed/` contains summaries and verification reports. Complete observations, lots, wash matches and requests are stored locally in `private/observed_runs/`. Browser exports contain the exact request and result. For an exported request:

```sh
python tools/run_study.py --input request.json --out replay.json
```

The study runner repeats every study offline and compares the full result objects. Cohort reports retain all requested draws. Quantiles use completed draws; the win fraction uses all draws and counts failures as not winning. These are descriptive results, not confidence intervals.

## Daily accounting and execution

1. At entry, solve target NAV after transaction charges by bisection. Core targets 130% long and 30% short; controls target 100% long. Restricted short proceeds, free cash, debt and investor side cash remain separate.
2. Accrue management/advisor fees on prior account equity, financing on actual debt, borrow on prior short market value and rebates on restricted collateral, using elapsed calendar days / 365.
3. Apply split events before current valuation and cash dividends. A prior-close harvest signal executes at the next close. Rebalance every 21 observed sessions and after replacement switches; there is exposure drift between scheduled trades.
4. A loss-triggered original position is sold and a mapped substitute is opened. Return to the original only after more than 30 calendar days. Actual close execution is idealized; no bid/ask or intraday execution record is claimed.
5. Match tax losses as described below. Taxable ST/LT gains and carryforwards remain separate. Outside proceeds enter investor side cash at year-end. Capital tax is paid on the first observed session on/after February 1 of the next year, after the December wash window; all outstanding tax is settled at the horizon. This is an explicit research timing assumption, not the estimated-tax calendar.
6. Check equity / gross market exposure at the daily close. Below the default 30% maintenance ratio, liquidate and stop further trading. An insolvent liquidation is reported as a failed portfolio. Availability of stock borrow, the maintenance ratio and interest/borrow rates are assumed, not historical broker terms.
7. Reconcile every session: initial equity + outside proceeds + price P&L + net dividends − all cash costs − taxes paid = investor wealth. Separately, realized economic price P&L + remaining economic embedded gain = cumulative price P&L. Tax basis can differ from economic basis because of fees, wash adjustments, gifts or death.

## Tax-lot conventions

Each acquisition creates FIFO lots with economic basis, tax basis, acquisition date and holding-period credit. Opening and closing transaction fees affect tax basis/proceeds as well as cash expenses. Long gains are LT only after the calendar anniversary, with tacked holding time for wash replacements; stock shorts are ST under the stated no-identical-long-position convention.

Every loss sale, including ordinary rebalancing and substitute disposal, is tested against retained same-ticker acquisitions within the preceding 30 days. Subsequent acquisitions within 30 days match unmatched loss quantities in order. Partial matches split lots. The sale record is adjusted and the deferred loss is transferred to replacement long basis or reduced short proceeds. Split events also rescale pending share quantities. January matches update the prior sale year before its tax payment.

The account is stock-only, with unique disjoint original/replacement tickers and no simultaneous long/short holding in one security. It assumes no outside household, IRA, spouse, option or related-entity trades, and no new trades during 30 days after final liquidation. Consequently the matcher does not certify a real household's wash-sale treatment.

Positive dividends use the entered effective dividend rate. Short payments in lieu reduce cash; ordinary short positions closed within 45 days add those payments to closing basis. No automatic itemized-interest deduction is credited. Qualified-dividend holding tests, extraordinary distributions, state brackets, the ordinary-income capital-loss deduction and broker-specific reporting are outside this account model.

## Exit policies on historical lots

**Full sale:** close all positions, account for trading fees and settle all unpaid taxes.

**3/4/5-year withdrawal:** at each last session of the final N calendar years, sell 1 / remaining exit years of all positions and transfer net proceeds to side cash. The remaining account continues with smaller positions, costs and loss opportunities. Side cash earns 0%.

**Extension reduction:** over the final three calendar years, reduce short targets from 30% toward 0% and long targets from 130% toward 100%; retain the long core until final sale. This differs from withdrawing the whole investment.

**Death:** at the horizon, close shorts and settle donor tax, adjust each assumed eligible long lot to observed FMV (up or down), and sell as the beneficiary. The actual lot basis adjustment is recorded; no 80% aggregate gain proxy is used. Short liabilities receive no automatic adjustment. Ordinary-property eligibility is assumed; an optional estate-tax dollar cost is deducted, default zero.

**Gift:** at the horizon, cover shorts and sell sufficient long shares to repay account debt and donor taxes, including funding-sale gains. Transfer only unencumbered long shares. Recipient sale applies donor basis for gains, gift-date FMV for below-basis losses, and zero gain/loss in the basis interval. Donor outside gains and carryforwards stay with the donor. Report combined donor/recipient wealth. An optional gift-tax dollar cost is deducted, default zero; the model does not calculate exemptions or gift-tax basis adjustments.

## Controls and break-even

Core is compared with the same initial stocks and rebalancing schedule without loss harvesting. The reported harvesting-rule effect includes temporary-security returns, changed trading costs and tax-funding paths; it is not a pure tax-savings measure. The long-only control is an equal-weight harvesting basket of the selected names with a 0.25% management assumption, not a broad index-replication strategy. SPY uses observed fund prices, with no extra manager fee by default because fund expenses are already reflected in prices. All controls use the same initial equity, outside proceeds, dates and advisor rate.

The one-time study runs $0, $1M, $3M and $5M in the selected calendar year, for ST or LT character. It scans $0–$5M at $250k increments, then bisects sign-changing intervals and records residuals. Each evaluation re-runs the historical ledger because taxes can change financing and later wealth. A finite grid can miss a narrow crossing or tangent root; no crossing is not a zero-dollar threshold.

## Sources for the implemented conventions

- IRS Publication 550, **Wash Sales**, **Short Sales**, and **Payments in lieu of dividends**: https://www.irs.gov/publications/p550
- IRS Publication 551, **Property Received as a Gift** and **Inherited Property**: https://www.irs.gov/publications/p551
- yfinance history/download parameters: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html

Consulted November 17, 2026. The source rules have exceptions; only the bounded conventions stated above are implemented. Software tests establish accounting behavior, not tax-law signoff or investment suitability.
