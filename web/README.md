# Local browser interface

From the repository root, run `python web/launch.py` with Python 3.12. On Windows, `py -3.12 web/launch.py` and `py -3.12 web/launch_stock.py` now open the same integrated interface at **http://127.0.0.1:8754**. The recommended Windows entry is **START-STOCK.bat**, which also installs `requirements-stock.txt` for Yahoo historical data. When starting manually, install those dependencies with `py -3.12 -m pip install -r requirements-stock.txt`. The original illustrative model uses only the standard library and starts from the independent public example in `configs/example_hypothetical.json`. For the restricted source-based run, use the command-line instructions in `docs/RESTRICTED_DATA.md`.

Expand **Portfolio → Custom Stock Research — After-Tax Loss Harvesting** for manually selected US stocks, adjustable long/short allocations and integrated after-tax harvesting research. See [README-STOCK.md](../README-STOCK.md) for its inputs, results and exports. The original illustrative scenario described below remains separate.

Use the inputs on the left and click **Run comparison**. The example menu resets every input before running; **Reset defaults** restores the baseline. Valid inputs are kept in the browser tab's session storage. Changed inputs are marked until rerun, and stale results cannot be downloaded.

- **Summary:** terminal after-tax wealth, differences from Index, an outside-gain break-even search, and holding-period comparisons.
- **Annual ledger:** returns and taxes, fees and financing, or basis and embedded gains. Select a strategy to inspect its annual rows.
- **Assumptions & scope:** source references, model limitations, and the sponsor requirements that still need further work.

Strategy colors stay consistent: slate for Index, blue for DI, and teal for Core. Signed numbers and text identify positive and negative comparisons alongside color.

**Download results** produces a ZIP containing the effective scenario, UI inputs, CSV outputs, code hashes, and reproduction instructions. It does not contain the private original source documents.

## Original illustrative model scope

The controls support 1-10 years, $10,000-$100 million in starting cash, and constant annual ST or LT outside gains. Mixed ST/LT schedules and irregular annual cash flows can be set through the original JSON configuration and command-line engine.

The UI scans 100 intervals from zero to the largest of starting cash, annual outside gains, and $100,000, then refines sign-changing break-even crossings. Its settings are included in the downloaded `breakeven.json`. The command-line default uses a $1 million maximum and $5,000 steps. A finite scan can miss tangencies or off-grid crossings.

Terminal wealth includes common outside gain proceeds and their taxes; it is not the return on starting cash alone. All results are hypothetical. The original illustrative scenario does not add historical prices, tax lots, manager alpha, or sponsor approval to its underlying model. Historical stock research uses its separate controls and accounting engine.

## Server and tests

The server binds only to `127.0.0.1` and serves a limited set of interface files. Closing the browser does not stop the background server started by either launcher. To run in the foreground instead:

```text
py -3.12 web/server.py --port 8755
```

Open `http://127.0.0.1:8755` and press Ctrl+C in the terminal when finished. You can choose another free port with `--port` and use that number in the browser URL. The automatic launchers use port 8754.

From the repository root, run:

```text
python -m unittest discover -s web/tests -v
```

The tests check input mapping, agreement with the baseline, download replay, and local HTTP access rules. Passing them does not validate the investment assumptions.
