# Local browser interface

From the repository root, run `python web/launch.py` with Python 3.12. On Windows, `py -3.12 web/launch.py` and `py -3.12 web/launch_stock.py` open the same integrated interface, preferring **http://127.0.0.1:8754**. The launcher reuses only a matching source/interface/configuration build; if the port holds an older build or another app it tries ports through 8764. Use the actual URL printed/opened by the launcher. The recommended Windows entry is **START-STOCK.bat**, which also installs `requirements-stock.txt` for Yahoo historical data. When starting manually, install those dependencies with `py -3.12 -m pip install -r requirements-stock.txt`. The original illustrative model uses only the standard library and starts from the independent public example in `configs/example_hypothetical.json`. For the restricted source-based run, use the command-line instructions in `docs/RESTRICTED_DATA.md`.

The complete **Portfolio → Custom Stock Research — After-Tax Loss Harvesting**
form is open by default. Enter your manually selected US stocks, allocation,
dates, costs, taxes and harvesting rules, then press the single **Run comparison**
button. There is no separate research run button. **Analysis mode** defaults to
**Historical stock research**; choose **Illustrative scenario** for the original
model. The initial page does not run either model automatically or pick stocks.
See [README-STOCK.md](../README-STOCK.md) for the full workflow.

All three result tabs follow the active mode and its completed run:

| View | Historical stock research | Illustrative scenario |
|---|---|---|
| **Summary** | Independent SPY pass/fail/tie target, harvesting/no-harvest/selected-benchmark wealth cards, signed initial-exposure bars, three equity paths and harvesting tax/cost bridge. | Index/DI/Core wealth cards, outside-gain break-even search and holding-period comparisons. |
| **Annual ledger** | Select strategy, no-harvest control, selected benchmark or additional SPY target when needed; inspect annual taxes, trades, accounting/exposure, costs and holdings. | Select Index, DI or Core and returns/taxes, fees/financing or basis/embedded gains. |
| **Assumptions & scope** | Exact run settings, actual dates, rates, trade rules, SPY evaluation and model notes. | Original illustrative methodology, fixed assumptions and coverage. |
| Toolbar download | **Download research JSON** with inputs, prices, results, comparisons and assumptions. | **Download scenario ZIP** with scenario/UI inputs, CSV outputs, hashes and reproduction instructions. |

**Strategy failed — below SPY** means ending wealth after costs, taxes and full
liquidation is below the independently simulated 100%-long SPY target, with
matched initial equity and outside cash flows. The selected benchmark may be
QQQ or another supported ticker; it is never mislabeled as SPY. Pass/fail/tie
uses each ending wealth rounded to USD cents. It describes this historical
period, not risk-adjusted alpha, future performance or client suitability.
Positive harvesting value versus the no-harvest control can coexist with a SPY
failure.

The initial-exposure chart uses signed bars and initial equity before opening
fees, so 130% long / 30% short remains gross 160% and net 100%. A pie would hide
that denominator; final holdings are fully liquidated in this model.

The historical Annual ledger offers **Download trades CSV** for its selected
portfolio. The compact **View research results** link returns to Summary.
Switching **Analysis mode** preserves completed results without rerunning either
engine; the single button runs only the active engine. Starting cash is shared.
Changing it marks both models stale; other inputs affect only their own model.
All historical views mark stale results and disable exports until rerun.

**Reset defaults** in research mode restores the historical defaults and blank
Long/Short ticker rows. In illustrative mode, the example menu and reset restore
that model's inputs. Inactive model fields are hidden and disabled so their
validation cannot block the active form. Enter in a research input follows the
same single-submit path. Input drafts survive a same-tab refresh through session
storage; completed results must be rerun after refresh.

## Original illustrative model scope

The controls support 1-10 years, $10,000-$100 million in starting cash, and constant annual ST or LT outside gains. Mixed ST/LT schedules and irregular annual cash flows can be set through the original JSON configuration and command-line engine.

The UI scans 100 intervals from zero to the largest of starting cash, annual outside gains, and $100,000, then refines sign-changing break-even crossings. Its settings are included in the downloaded `breakeven.json`. The command-line default uses a $1 million maximum and $5,000 steps. A finite scan can miss tangencies or off-grid crossings.

Terminal wealth includes common outside gain proceeds and their taxes; it is not the return on starting cash alone. All results are hypothetical. The original illustrative scenario does not add historical prices, tax lots, manager alpha, or sponsor approval to its underlying model. Historical stock research uses its separate controls and accounting engine.

## Server and tests

The server binds only to `127.0.0.1` and serves a limited set of interface files. Closing the browser does not stop the background server started by either launcher. To run in the foreground instead:

```text
py -3.12 web/server.py --port 8755
```

Open `http://127.0.0.1:8755` and press Ctrl+C in the terminal when finished. You can choose another free port with `--port` and use that number in the browser URL. The automatic launchers prefer port 8754 and can select another port through 8764 when a matching server is unavailable there.

From the repository root, run:

```text
python -m unittest discover -s web/tests -v
```

The tests check input mapping, agreement with the baseline, download replay, and local HTTP access rules. Passing them does not validate the investment assumptions.
