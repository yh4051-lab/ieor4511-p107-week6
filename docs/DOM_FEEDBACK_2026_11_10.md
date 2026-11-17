# Portfolio research: current status

The November 17 observed-price update supersedes the implementation described below. All four tabs now use historical tax lots by default. See [current coverage, algorithms, real-data provenance and reproduction](OBSERVED_RESEARCH.md). Earlier model exports remain reproducible.

## Earlier implementation record

# Portfolio research: November 10 feedback

Updated November 17, 2026. This is a research model with explicit assumptions.
Software tests do not establish investment performance or tax compliance.

## Open and use the studies

Start `python web/launch.py`, then choose **Portfolio research →** in the header.
The page is `/studies` on the local address printed by the launcher.

1. Choose **Rebalancing**, **Exit planning**, **Liquidity events** or
   **Portfolio sampling**.
2. Review inputs and expand **Fees, financing and taxes**. These rates are
   illustrative and can be changed. Select **Run analysis** after changing inputs.
3. Read the comparison and run-specific assumptions below it. The same outside
   proceeds are included across strategies: total wealth is not just the return
   on starting capital.
4. In Exit planning, select a strategy to compare its policies, or select
   **All strategies**. Liquidity events displays all three strategies side by side.
   Expand the ledgers and **Assumptions and limitations** for detail. The visible
   **Model coverage** table separates available functions from remaining work.
5. Choose **Export results** for a ZIP with CSVs, complete results, exact inputs, source
   hashes and an offline replay command:

```sh
python tools/run_study.py --input request.json --out replay.json
```

Observed prices stay in the downloaded package. Do not commit private data or
restricted provider files to the public repository.

## Coverage of the four questions

| Question | Implemented and exposed in the UI | Remaining limits |
|---|---|---|
| Rebalance 130/30 and replace during the wash-sale window | Scheduled post-fee NAV targets; next-session harvesting; mapped temporary securities; return after more than 30 calendar days; trade, daily and annual ledgers | Replacement suitability is an input, not a legal determination. Full wash-sale matching and margin/borrow constraints remain open. |
| Hold until death, gift, exit over 3–5 years | Seven annual-scenario policies: full sale, whole-portfolio sales over 3/4/5 years, extension reduction, death, gift with recipient sale | Annual aggregate proxies, not historical lot-level exit simulations. No gift/estate tax or legal transfer of short liabilities. |
| One-time outside gain of $1M/$3M/$5M | Zero-gain control plus all three amounts, event year and ST/LT character; Core break-even versus Index and Direct Indexing | Assumed return/loss schedules; finite-grid root search; gain cash is an incremental cash-flow proxy. |
| Random portfolios or PIT S&P 500 | Seeded disjoint long/short draws, each run with harvesting, no-harvest and benchmark comparisons; membership/provenance CSV input | Authentic PIT index data has not been supplied. The included 20-draw verification is synthetic, not an S&P 500 backtest. |

### 1. Rebalance and replace

`p107/dom_historical.py` solves targets on NAV after transaction fees. Market
moves cause exposure drift between scheduled trades. A prior-close loss signal
executes at the following close. Before harvesting an original ticker, all its
open lots must be older than 30 days. Its explicitly mapped substitute is held
during the cooldown instead of leaving that slice in cash.

Costs include manager/advisor fees, financing debt, short borrow, taxable rebates
and trading charges. Cash, restricted short collateral and debt are separate.
Outside gain proceeds go to investor side cash, not into the leveraged account.
Taxes use side cash first; a shortfall is funded by account cash/debt. Outside
events are settled at calendar year-end in this engine.

Controls are the same portfolio without harvesting and a passive 100%-long
benchmark with its own manager rate (default 0.03%). Prices, dates, initial
equity and outside gains match. Harvesting benefit isolates the rule comparison;
benchmark differences also include stock selection and leverage. The final
wealth point includes liquidation taxes.

Daily checks reconcile total wealth to initial equity, outside proceeds, price
P&L, net long/short dividends, costs and all taxes. They also reconcile realized
plus embedded price gains to cumulative price P&L.

This is not a full wash-sale engine. Rebalance losses, substitute-disposal
losses, household accounts, substantially identical exposures and special short
rules need further matching. FIFO and ST treatment of shorts are research
conventions. Close execution, borrow availability and no margin calls are
assumptions. Nonpositive account equity stops the run.

### 2. Exit choices

These comparisons use `p107/model.py`, with annual assumed returns and losses.
They do not use historical prices from the other study.

- **Full sale:** final liquidation with exit costs and taxes.
- **3/4/5-year full-portfolio exit:** sell 1 / remaining exit years of the
  remaining portfolio each year, remove proportional basis, and move proceeds
  after trading costs to side cash. Exposure, costs and future loss amounts
  decline as assets leave. The final year sells the remainder.
- **Extension reduction:** reduce long/short extensions over three years, retain
  the long-only core, then sell it. This differs from full withdrawal. Realized
  extension gain is an explicit aggregate assumption.
- **Hold until death:** eligible long-only assets adjust to FMV; Core uses the
  entered eligible share of net embedded gain as a proxy. This does not establish
  lot-level eligible gains or grant an adjustment to short liabilities. Losses
  also adjust in a below-basis death scenario.
- **Gift with recipient sale:** carry donor basis into the recipient account,
  keep donor carryforwards with donor outside gains, and apply recipient rates
  only to the recipient portfolio. Compare combined donor/recipient family
  wealth. The recipient sells at the same horizon; no automatic tax-free gift
  wealth is credited. Below-aggregate-basis gifts are rejected because dual-basis
  tax lots are not implemented. Individual mixed gain/loss lots need review too.

No estate/gift taxes, exceptions to inherited basis or legal transfer of shorts
are simulated. These are research questions, not actual account tax advice.

### 3. One-time gain threshold

One event occurs only in the selected year. The page compares $0/$1M/$3M/$5M and
searches $0–$5M in $25,000 intervals, refining sign changes by bisection. Root
residuals are retained. **No crossing** is not a zero-dollar threshold. A finite
grid can miss a tangency or a very narrow crossing.

Common original principal of outside investments is excluded; incremental cash
equals taxable gain. Actual client analysis needs proceeds and basis separately.
Compare strategy differences, not balances increased by larger outside deposits.

### 4. Random portfolios and data

The browser accepts 1–200 draws and a reproducible seed. Long and short names do
not overlap within a draw. Formation, costs, rates, horizon and outside flows
match across portfolios. Median, 5th/95th percentile and benchmark win fraction
describe the supplied universe; they are not forecasts or confidence intervals.

Non-synthetic studies require membership CSV fields `ticker`, `member_from`,
`member_to` (exclusive; blank if ongoing), `source_id`, and
`point_in_time_verified`. Optional `published_as_of` cannot be later than
formation. The data owner must substantiate this attestation; the program cannot
authenticate it. Formation must equal history start. Enter replacement mappings
for every eligible name. Today's S&P 500 list is not historical membership.

Prices can come from the existing Yahoo adapter or uploaded JSON with `dates`,
`prices`, `splits`, `dividends`, and `metadata`. Missing series fail the run;
failed portfolios are not silently removed. True PIT research still needs
membership and delisted-security records, corporate-action coverage and
historical borrow/replacement availability. Yahoo alone does not supply these.

Bundled `dom_synthetic_*` files contain invented test symbols and prices labeled
**SYNTHETIC SOFTWARE TEST — NOT MARKET HISTORY**. They exercise software without
claiming a historical record or manager performance.

## Reproduce verification

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python tools/verify_sponsor_studies.py
python tools/verify_project.py
```

The study verifier writes 56 comparison rows: 21 exits, 12 one-time gains,
3 historical controls and 20 random draws. Each study is replayed with its exact
exported observations and compared for equality. Historical ledgers also check
daily capital P&L and wealth. Current verification reports record counts and
source hashes. CI runs model/web tests, four-study replay and legacy command-line
examples without external prices.

## Tax source references

- [IRS Publication 550](https://www.irs.gov/publications/p550): the 30-day
  before/after wash-sale window and special short/account rules; a cooldown
  alone does not establish compliance.
- [IRS Publication 551](https://www.irs.gov/publications/p551): inherited basis
  differs from gift basis; below-basis gifts can require dual bases.

Reviewed November 17, 2026. Only the documented research conventions above are
implemented.
