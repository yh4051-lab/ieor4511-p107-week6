# Local browser interface

From the repository root, run `python web/launch.py` with Python 3.12. On Windows, `py -3.12 web/launch.py` and `py -3.12 web/launch_stock.py` open the same integrated interface, preferring **http://127.0.0.1:8754**. The launcher reuses only a matching source/interface/configuration build; if the port holds an older build or another app it tries ports through 8764. Use the actual URL printed/opened by the launcher. The recommended Windows entry is **START-STOCK.bat**, which also installs `requirements-stock.txt` for Yahoo historical data. When starting manually, install those dependencies with `py -3.12 -m pip install -r requirements-stock.txt`. The original illustrative model uses only the standard library and starts from the independent public example in `configs/example_hypothetical.json`. For the restricted source-based run, use the command-line instructions in `docs/RESTRICTED_DATA.md`.

Expand **Portfolio → Custom Stock Research — After-Tax Loss Harvesting** for manually selected US stocks, adjustable long/short allocations and integrated after-tax harvesting research. Click **Run After-Tax Research** to populate the main **Summary** and **Annual ledger** on the right. **Results source** switches between completed historical research and the original illustrative scenario without rerunning either. See [README-STOCK.md](../README-STOCK.md) for inputs, results and exports.

The main result views follow **Results source**:

| View | Historical stock research | Illustrative scenario |
|---|---|---|
| **Summary** | Harvesting/no-harvest/benchmark wealth cards, three equity paths and harvesting tax/cost bridge. | Index/DI/Core wealth cards, outside-gain break-even search and holding-period comparisons. |
| **Annual ledger** | Select strategy, no-harvest control or benchmark; inspect annual taxes, trades, accounting/exposure, costs and initial holdings. | Select Index, DI or Core and returns/taxes, fees/financing or basis/embedded gains. |
| Toolbar download | **Download research JSON**, containing the full research inputs, prices, results and assumptions. | **Download scenario ZIP**, containing scenario/UI inputs, CSV outputs, code hashes and reproduction instructions. |

The historical Annual ledger also offers **Download trades CSV** for its selected
portfolio. The compact **View research results** sidebar button returns to its
Summary. **Scenario method** describes only the original illustrative model and
selects that source. Break-even and holding-period charts are not historical
research outputs.

**Run comparison** selects and recalculates the illustrative scenario. Its
example menu resets the original inputs before running; **Reset defaults**
restores that baseline without clearing custom stock selections. Starting cash
is shared and changes mark both models stale; other inputs affect only their
own model. Stale results are marked and their downloads are disabled. Input
drafts survive a same-tab refresh through session storage; completed historical
results must be rerun after refresh. The original scenario retains slate Index,
blue DI and teal Core colors; signed text identifies comparison direction.

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
