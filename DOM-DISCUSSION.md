# Questions for Dom: From Research Comparisons to Client Decisions

Suggested opening:

> We want the platform to explain when long–short direct indexing is worthwhile for a specific client after taxes, fees, financing and a realistic exit. Before adding more models, we would like to confirm the decision the platform should support and the evidence needed to support it.

1. **Final deliverable:** Should the primary output be a client decision matrix or report that recommends an eligible strategy, explains why, and identifies the conditions under which that conclusion changes? What would make that output useful in an actual client conversation?

2. **Meaning of “optimal”:** Should the platform choose among an index ETF, long-only direct indexing and long–short structures such as 130/30, 150/50 and 200/100, including an exit plan? Or should building an optimizer that selects individual weights and tax-lot trades also be a core deliverable?

3. **Objective and risk limits:** Is the principal objective terminal after-tax, after-fee wealth, subject to explicit tracking-error, drawdown, concentration and liquidity limits? How should we compare strategies with different risk, and what minimum economic improvement would justify their additional complexity?

4. **Client inputs:** Which observable client conditions should drive the decision: existing holdings and tax basis, ST/LT tax rates, loss carryforwards, expected outside gains and their timing, investment horizon, liquidity needs and intended disposition? Should the first version focus on a cash-funded investor or a client with concentrated low-basis assets?

5. **Sensitivity priorities:** Which uncertainties should we test first, and what ranges are realistic: financing and borrow costs, tax rates, holding period, gain timing and character, leverage and market regime? Would a heatmap and break-even thresholds be more useful than a large collection of separate runs?

6. **Exit comparison:** Which exits must be in the core study: full liquidation, a 3–5-year glide path, an unexpected liquidity need, gifts, or death with applicable basis treatment? When comparing them, what common horizon, cash-flow treatment and valuation assumptions would you want us to use? For gifts and death, should the outcome measure be investor, beneficiary or total family after-tax wealth?

7. **Controls and attribution:** Would you support four comparison arms—index ETF, long-only + TLH, 130/30 without tax management, and tax-aware 130/30? Should we also hold portfolio construction as closely matched as possible to distinguish tax management from stock selection, leverage and changes in risk?

8. **Robustness and data:** Is the priority paired random portfolios, rolling historical start dates, point-in-time index membership, or a combination? Is the purpose to establish that the conclusion survives different stock selections and market periods, rather than finding a portfolio that happens to win? Can you help us identify appropriate point-in-time data?

9. **Tax-model fidelity:** Which tax details need to be implemented for a credible first conclusion, and which can remain explicit assumptions? In particular, how should we handle wash sales, loss utilization and carryforwards, existing tax lots, short-side treatment, gifts and estate scenarios? Should we separately quantify temporary deferral and permanent tax savings using matched cash flows and a stated discount rate?

10. **Next milestone and acceptance:** Given limited time, should we first complete a reproducible historical comparison with risk metrics, realistic exits and cost sensitivity, then add trade-level optimization and broader simulation? Which two or three results would convince you that the platform has answered the project’s main research question?

If time is short, prioritize Questions 1, 2, 3, 5 and 10.

Suggested decision to leave the meeting with: an agreed primary output, eligible strategy set, minimum client inputs, risk constraints, required exit scenarios and the next validation milestone.
