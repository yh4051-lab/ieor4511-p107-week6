# Code map — integrated after-tax stock research

| File | New/updated | Responsibility |
|---|---|---|
| `web/dist/index.html` | Updated | Default-open historical form, one Run comparison submit button, Analysis mode selector, inactive-model fieldsets and matching Summary/Annual ledger/Assumptions & scope panels. |
| `web/dist/portfolio.js` | Replaced | Exposes `P107Research.run/reset/isBusy` to the shared submit route; requests level 3 and `evaluate_spy`, renders SPY verdict, signed initial exposure, Summary cards/curves/tax bridge, selectable ledgers, run-specific scope, exports and stale state. |
| `web/dist/portfolio.css` | Updated | Styles for full-width research results, pass/fail/tie banners, signed exposure bars, mode selector, responsive charts/tables and model-specific stale results. |
| `web/dist/app.js` | Updated | Routes the single Run comparison button to the active engine; defaults to historical mode without an automatic legacy run. Coordinates all three tabs, cached outputs, inactive-field validation, reset and shared initial equity through `P107Results`. |
| `web/server.py` | Updated | Adds research feature and startup build-fingerprint health markers and POST route; preserves original API and local-origin checks. |
| `p107/market_data.py` | Added/extended | `get_quote`, `load_history`, date/market validation, nominal split/dividend reconstruction, strict calendar matching, caching and data hashes; supports 20 positions plus the selected benchmark and SPY. |
| `p107/research.py` | New | `run_research`: validated request -> dataset -> resolve target budgets to initial shares -> simulation -> matched benchmark -> same-portfolio no-harvest control -> optional independent SPY verdict. `evaluate_spy` preserves the legacy output contract when absent; the verdict uses separately cent-rounded wealth and a display difference. Legacy level 1/2 requests remain supported. `_simulate` holds cash/debt/collateral, position basis, prices, splits, dividends, costs, annual netting, exit and trade rules. |
| `p107/taxes.py` | Reused unchanged | `settle` nets actual modeled realized ST/LT gains/losses and carryforwards. It does not itself decide trades or wash-sale eligibility. |
| `p107/model.py` | Preserved | Original annual illustrative accounting model; no historical research is secretly routed through exogenous harvested-loss curves. |
| `p107/portfolio.py` | Retained | Earlier snapshot API compatibility only. The integrated UI uses `research.py`. |
| `tools/run_research.py` | New | Run user JSON configuration and export JSON plus daily/annual/trade/position CSVs. |
| `tools/replay_research.py` | New | Offline replay using downloaded data and hash checks. |
| `configs/example_stock_research.json` | New | Integrated 130/30 target-exposure example with $1 million equity, AAPL long/MSFT short, per-leg weights and SPY benchmark; illustrative configuration, not a recommendation. |
| `examples/research-level3-synthetic.json` | New | Fully replayable synthetic loss/reentry/exit example, not market evidence. |
| `tests/test_market_history.py` | New | Splits, reverse splits, dividends, missing/pre-IPO sessions, cache isolation and dataset identity. |
| `tests/test_research.py` | New | Independent controls: target 130/30 and higher exposure, per-leg weights, manual-share compatibility, leverage, taxes, dividends, rebate tax, next-close execution, cooldown, carryforwards, insolvency, no-free-tax-alpha, SPY pass/fail/tie rounding, independent custom benchmarks and legacy replay compatibility. |
| `web/tests/test_web.py` | Extended | Original tests retained; new APIs validated with deterministic fixtures and foreign-origin rejection. |
| `requirements-stock.txt` | Added | Optional `yfinance==1.7.0`; original scenario still uses standard library. |
| `web/build_info.py` | New | Fingerprints current source, interface and baseline configuration so a new download cannot silently reuse an older running build. |
| `web/launch.py` / `web/launch_stock.py` / `START-STOCK.bat` | Updated | Both Python launchers reuse only the matching integrated build; prefer port 8754 and try alternatives through 8764 without killing old processes. Print/open the actual URL. The Windows batch entry also installs historical-data dependencies. |

No database, brokerage account or automatic trade execution is required. No
GitHub push or external deployment is performed by this bundle.
