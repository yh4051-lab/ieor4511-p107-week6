# Code map — integrated, English, three-level research

| File | New/updated | Responsibility |
|---|---|---|
| `web/dist/index.html` | Updated | Portfolio details after Starting cash; level selector; manual rows; dates, benchmark, costs, tax inputs and harvesting rules. Outside this block the original scenario remains. |
| `web/dist/portfolio.js` | Replaced | Typed request construction, level-specific controls, `/api/research/run`, result/benchmark/control curves, tax bridge, ledgers, English assumptions, JSON/CSV export and session persistence. |
| `web/dist/portfolio.css` | Updated | Styles for embedded controls, charts, tables and stale results. |
| `web/dist/app.js` | Updated | Original scenario validation/draft/dirty handling skips custom research controls; neither form changes the other's results. |
| `web/server.py` | Updated | Adds research feature health marker and POST route; preserves original API and local-origin checks. |
| `p107/market_data.py` | Added/extended | `get_quote`, `load_history`, date/market validation, nominal split/dividend reconstruction, strict calendar matching, caching and data hashes. |
| `p107/research.py` | New | `run_research`: validated request -> dataset -> selected level -> matched benchmark -> optional no-harvest control. `_simulate` holds cash/debt/collateral, position basis, prices, splits, dividends, costs, annual netting, exit and trade rules. |
| `p107/taxes.py` | Reused unchanged | `settle` nets actual modeled realized ST/LT gains/losses and carryforwards. It does not itself decide trades or wash-sale eligibility. |
| `p107/model.py` | Preserved | Original annual illustrative accounting model; no historical research is secretly routed through exogenous harvested-loss curves. |
| `p107/portfolio.py` | Retained | Earlier snapshot API compatibility only. The three-level UI uses `research.py`. |
| `tools/run_research.py` | New | Run user JSON configuration and export JSON plus daily/annual/trade/position CSVs. |
| `tools/replay_research.py` | New | Offline replay using downloaded data and hash checks. |
| `configs/example_stock_research.json` | New | Example manually selected AAPL long/MSFT short with SPY benchmark; illustrative configuration, not a recommendation. |
| `examples/research-level3-synthetic.json` | New | Fully replayable synthetic loss/reentry/exit example, not market evidence. |
| `tests/test_market_history.py` | New | Splits, reverse splits, dividends, missing/pre-IPO sessions, cache isolation and dataset identity. |
| `tests/test_research.py` | New | Independent accounting controls: leverage, signs, taxes, dividends, short rebate tax, next-close execution, cooldown, carryforwards, insolvency and no-free-tax-alpha. |
| `web/tests/test_web.py` | Extended | Original tests retained; new APIs validated with deterministic fixtures and foreign-origin rejection. |
| `requirements-stock.txt` | Added | Optional `yfinance==1.7.0`; original scenario still uses standard library. |
| `web/launch_stock.py` / `START-STOCK.bat` | Added/updated | Install optional dependencies, start/reuse only compatible research server on port 8752, and open the browser. |

No database, brokerage account or automatic trade execution is required. No
GitHub push or external deployment is performed by this bundle.
