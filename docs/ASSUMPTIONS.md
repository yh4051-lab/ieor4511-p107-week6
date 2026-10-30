# Model assumptions

The public example uses independent illustrative inputs. It is not historical performance, a provider estimate, or a client recommendation. All strategies start with $1 million cash and end with full liquidation.

| Input | Public default | Interpretation |
|---|---|---|
| Holding period | 5 years | Also test 1, 3, and 10 years |
| Price appreciation | 6% each year | Educational path; zero dividends and zero alpha |
| Outside gains | $100,000 ST per year | Same incremental cash flows for all strategies |
| ST / LT / ordinary tax rates | 40% / 20% / 40% | Round effective scenario rates, not statutory or personal rates |
| Index / DI / Core manager fees | 0.03% / 0.25% / 0.40% of beginning NAV | Illustrative |
| Advisor fee | 0.10% of beginning NAV | Same for all strategies; not an employer quote |
| Core long financing / short rebate | 5% / 4% | Applied to the separate 30% extension / short notionals |
| Additional short borrow fee | 0.20% of short notional | Illustrative; real contracts must clarify overlap with rebate |
| Annual trading costs, Index / DI / Core | 0 / 0.03% / 0.05% of beginning NAV | Expense proxies, not reconstructed trades |
| Exit costs, Index / DI / Core | 0.01% / 0.01% / 0.02% of gross exposure | Deducted before the final tax settlement |
| Side cash return | 0% after tax | Separate from the investment account |

Core ST loss rates are 15%, 10%, 7%, 4%, and then 2% for Years 5-10. DI ST rates are 5%, 3%, 2%, 1%, 0.5%, and then 0.3% for Years 6-10. Index has no intentional harvesting. Both curves are chosen educational examples, not extracted, fitted, or scaled versions of a provider curve. They use beginning-of-year NAV. Baseline LT loss rates and planned gain realization rates are zero; separate LT losses are supported in the engine and sensitivity analysis.

Harvesting changes realized losses and embedded gains without creating cash. Expense-funding and tax-funding sales also create realizations. Exactly-one-year realizations are all ST; later aggregate realization ST fractions are 0%, 5%, and 10% for Index, DI, and Core. This approximates tax character without claiming individual tax-lot accuracy.

Losses offset same-character gains before cross-character netting, and unused losses carry forward. Unused carryforwards receive no terminal cash value. Ordinary-income capital-loss deductions, personal brackets, state taxes, and special short-sale rules are not modeled. Interest deductibility is capped at rebate income; no automatic refund is credited for net financing expenses or fees.

Terminal wealth includes the common outside gain cash flows. Current tax relief is never added again as a separate asset, and embedded gains are taxed in the final-year settlement. The Core and DI curves must be varied in sensitivities; these inputs cannot support a ranking of real investment products.

The restricted source-based run uses a different configuration. Its numeric results are intentionally not included in this public repository. Use the separate access and reproduction instructions in `RESTRICTED_DATA.md`.
