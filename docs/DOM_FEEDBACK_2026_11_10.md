# Dominic Corabi feedback — November 10, 2026

Status: **research extension, not production tax advice or real-client backtest**.
All outputs in `examples/dom_synthetic_*` are deliberately fabricated test
fixtures, never S&P 500 history or actual manager performance. The public GitHub
repository must not contain restricted Quantinno/AQR/client input files.

This branch implements four follow-ups in separate, inspectable components.
Existing `p107/model.py` and `p107/research.py` retain their old behavior
without the new opt-in options.

## 1. Maintain 130/30 and substitute while harvesting

- `p107/dom_historical.py::historical_13030` implements dollar-target
  rebalancing to gross 130% long and 30% short exposure, using NAV each
  `rebalance_every_sessions` (default 21); it also rebalances immediately
  after a harvest/replacement swap.
- On a prior-session eligible loss signal, the next session closes the original
  tax lots and opens an explicitly mapped temporary replacement with the
  **same dollar market exposure**, rather than holding that slice in idle cash.
  It waits **more than 30 calendar days** after the sale before repurchasing
  the original, with a configurable cooldown >=30 and minimum holding >=31.
- FIFO lots, annual capital-gain netting/carryforwards, cash, restricted short
  collateral, debt, interest, short rebates, fees, rebalancing trades and end
  liquidation are tracked. See `trades`, `daily` and `annual` ledgers.
- Start/end rebalancing uses the available daily close as an idealized
  execution convention. Exact exposure will deviate slightly due to fees.
- A replacement **must** carry a user-supplied
  `reviewed_not_substantially_identical=true`. That is an assumption
  requiring independent professional verification. This code **does not**
  certify wash-sale compliance across household accounts, affiliates,
  options, replacement ETFs or short-sale constructive-sale rules. Real
  borrowing availability, spreads and margin calls are not modeled.
- Opt-in routing: `run_research({"engine_mode":"rebalanced_13030",...})`.
  Existing no-opt-in research stays intact. Browser's existing
  `/api/research/run` accepts this opt-in payload; the legacy form does not
  expose all of the new knobs.

**Reproduce without external data:**

```sh
python tools/dom_feedback.py historical \
  --config configs/example_dom_historical.json \
  --historical-data examples/dom_synthetic_history.json \
  --out /tmp/dom_history.json
```

This fixture uses synthetic `T1..T12` / `S1..S12` tickers, not real prices.
For genuine historical analysis, supply documented daily nominal split/dividend
data and valid separately reviewed replacement mappings. A generated
historical run is only as reliable as those observations and assumptions.

## 2. Lifetime full sale, gradual 3–5-year exit, gift, death

- `p107/model.py` accepts an optional `exit_policy`, with default
  `{"mode":"full_liquidation"}` preserving the original calculation.
- `{"mode":"gradual","years":3|4|5,
  "extension_embedded_gain_share":0.5}` phases down **extensions** over
  multiple years, scales financing, short rebate and harvested loss rates,
  and recognizes an explicit share of embedded gains each year.
  The embedded-gain allocation is user-assumed, **not inferred from lots**.
- `{"mode":"death","step_up_long_embedded_fraction":0.8}`
  estimates how much gain could be excluded when qualifying **long-book**
  basis is adjusted at death. The residual fraction remains exposed to tax,
  including short-related liabilities. The fraction must be supplied; no
  exact security-level attribution is available in the aggregate model.
- `{"mode":"gift","recipient_liquidates":true}` passes the original basis
  to the gift recipient and models a **same-day recipient sale** for an
  apples-to-apples after-tax comparison. Without immediate liquidation,
  gifted property is not equivalent to spendable after-tax wealth.
- None of these calculate estate or gift tax, state-specific nuances,
  special dual-basis loss rules for gifts, inheritance exceptions,
  dividend timing, detailed short character, or full household tax returns.
  A death step-up is not assumed on unclosed short positions.

**Reproduce exit differences under explicitly assumed fractions:**

```sh
python tools/dom_feedback.py scenario \
  --config configs/example_hypothetical.json \
  --event-year 2 --stepup-long-fraction 0.8 \
  --out /tmp/dom_scenarios.json
```

This generates comparable after-tax terminal wealth for each of the index,
long-only DI and core 130/30 strategies under the respective **modelled**
exit policies. Do **not** extrapolate the results as legal advice.

## 3. One-time outside capital gains and break-even

- `p107/model.py::with_gains(...,timing='year',event_year=2)`
  places the outside gain **only in that year** rather than in every year.
- `p107/analysis.py::one_time_gain_comparison` evaluates $1M, $3M,
  and $5M as distinct one-time outside ST or LT capital gains.
- `one_time_gain_breakeven` computes numeric crossing(s) in incremental
  terminal after-tax wealth against another strategy. It does not
  falsely call a no-crossing result a zero break-even. Finite grid may
  miss a tangency or extremely narrow crossing.
- The inherited toy model assumes outside cash proceeds equal the gain.
  Real clients have a separate tax basis, gross proceeds and cash flows;
  this proxy must be replaced before treating results as a recommendation.

The `scenario` command above writes per-gain differences and break-even
diagnostics, with the event year recorded.

## 4. Multiple random portfolios, with point-in-time selection

- `p107/dom_sampling.py` samples disjoint long and short portfolios
  using a fixed seed, with reproducible quantiles across outcomes.
- It requires user-supplied membership rows with a historical effective
  interval, source ID, point-in-time verification attestation and, when
  supplied, a source publication date no later than the formation date.
- It **never downloads today's S&P 500 constituents and calls them
  historical**. True survivorship-free point-in-time S&P 500 membership
  has **not been provided**. No authentic S&P results are claimed.
- To generate configurations only, run `sample`. To actually run multiple
  portfolios using an audited price input and the rebalance engine, run
  `cohort`.

```sh
python tools/dom_feedback.py cohort \
  --config configs/example_dom_historical.json \
  --memberships examples/dom_synthetic_memberships.csv \
  --historical-data examples/dom_synthetic_history.json \
  --asof 2020-01-01 --long-count 3 --short-count 3 \
  --samples 20 --seed 4511 --out /tmp/dom_cohort.json
```

The 20-sample example is a **synthetic system test**, not a market result.
For defensible PIT US equity portfolios, obtain an audited membership
dataset (e.g. authorized CRSP/Compustat or historical index constituency),
historical prices with delisted securities, splits, dividends, and
borrow/replacement availability. Explicitly evaluate data leakage.

## Verification

CI workflow: `.github/workflows/verify-dom-feedback.yml`.

```sh
python -m compileall -q p107 tests tools
python -m unittest discover -s tests -v
```

GitHub Actions also runs all three synthetic CLI examples and checks the
number of one-time gain scenarios, the exit-scenario count, 130/30 target
and reproducible 20-portfolio cohort.

## Review required before sponsor use

1. Obtain and document actual point-in-time security membership history,
   clean price and corporate action records, tradability, borrow and short
   availability, and credible replacement-security mapping.
2. Obtain client-specific capital gain timing, basis, marginal rates and
   planned exit pathways. Disentangle external taxable gain from gross
   sale proceeds.
3. Validate the tax character and wash-sale treatment with a qualified
   tax professional (especially shorts, loss lots, gifts and estate).
4. Run sensitivity on manager fees, collateral/financing, spreads,
   stressed market regimes and liquidation-trigger probabilities.
5. Compare costs and returns of index/long-only/13030 under equal
   investor cash flows, and distinguish *deferral* from permanent tax
   savings. Do not present synthetic results as actual historical evidence.

**Public repo security:** only synthetic code/config/test data in this PR.
Do not push restricted provider PDFs or real investor records.
