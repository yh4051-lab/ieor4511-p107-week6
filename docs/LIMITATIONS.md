# Current limitations and next steps

This version checks the portfolio and tax accounting under stated assumptions. It is ready to review as an initial model, but it does not establish whether a real client's account would achieve these results.

- Returns and harvested losses are scenario inputs. There is no historical price dataset or evidence that the assumed losses can be generated along each return path.
- Cost basis is tracked for the aggregate portfolio. There are no individual tax lots, wash-sale checks, holding-period records, or actual rebalancing trades.
- Both public loss curves are independent illustrative assumptions. Neither curve is calibrated to provider or market data.
- Fees and financing terms need confirmation. Margin calls, short recalls, borrow availability, dividend-in-lieu payments, and tracking error are not modeled.
- Taxes use flat scenario rates. State residency, tax brackets, ordinary-income loss deductions, interest carryforwards, and special short-sale rules are omitted.
- All strategies receive the same outside gain proceeds. The model excludes the common original principal of those outside investments and is not a full household balance sheet.
- The current exit sells everything at once. Gradual exits, liquidity events, estate treatment, 150/50, and 200/100 remain part of the broader project.

Before expanding the model, we need to review a small example by hand, confirm the annual ST/LT loss and gain estimates with Dom, and check representative management, financing, rebate, and borrow costs. A historical backtest will also require authorized security prices, corporate actions, holdings, and tax-lot data.

Passing the tests verifies the implemented accounting and specified examples. It does not validate the economic assumptions, guarantee tax savings, or establish a client recommendation.
