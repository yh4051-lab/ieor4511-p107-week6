# Current limitations and next steps

Scope: this document describes the original annual scenario model in `p107/model.py`. The newer three-level historical research engine is documented in `../README-STOCK.md` and `../CODE-MAP.md`; its assumptions and limits are separate.

This version checks the portfolio and tax accounting under stated assumptions. It is ready to review as an initial model, but it does not establish whether a real client's account would achieve these results.

- Returns and harvested losses are scenario inputs. There is no historical price dataset or evidence that the assumed losses can be generated along each return path.
- Cost basis is tracked for the aggregate portfolio. There are no individual tax lots, wash-sale checks, holding-period records, or actual rebalancing trades.
- Both public loss curves are independent illustrative assumptions. Neither curve is calibrated to provider or market data.
- Fees and financing terms need confirmation. Margin calls, short recalls, borrow availability, dividend-in-lieu payments, and tracking error are not modeled.
- Taxes use flat scenario rates. State residency, tax brackets, ordinary-income loss deductions, interest carryforwards, and special short-sale rules are omitted.
- All strategies receive the same outside gain proceeds. The model excludes the common original principal of those outside investments and is not a full household balance sheet.
- Full sale remains the baseline. The sponsor workspace now includes proportional 3–5-year sales, extension reduction, gift/recipient sale, and a conditional death-basis adjustment. These are aggregate annual scenarios, not historical lot-level estate or gift planning. Historical studies still end in a full sale.

The new rebalanced historical engine adds FIFO lots, scheduled target exposures,
replacement trades and seeded cohort comparisons. It does not implement all
wash-sale matching, short-sale tax rules, margin calls or borrow recalls. In
particular, losses from ordinary rebalancing and disposal of replacement shares
need further matching. No authentic point-in-time S&P 500 dataset has been
provided; included cohort results use labeled synthetic fixtures. Read
[the coverage table](DOM_FEEDBACK_2026_11_10.md) before presenting results.

Before expanding the model, we need to review a small example by hand, confirm the annual ST/LT loss and gain estimates with Dom, and check representative management, financing, rebate, and borrow costs. A historical backtest will also require authorized security prices, corporate actions, holdings, and tax-lot data.

Passing the tests verifies the implemented accounting and specified examples. It does not validate the economic assumptions, guarantee tax savings, or establish a client recommendation.
