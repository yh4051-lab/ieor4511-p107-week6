(() => {
  'use strict';
  const section = document.getElementById('stock-experiment');
  if (!section) return;
  const list = document.getElementById('stock-positions');
  const levelControl = document.getElementById('research-level');
  const status = document.getElementById('stock-status');
  const result = document.getElementById('stock-result');
  const button = document.getElementById('stock-calculate');
  const addButton = document.getElementById('stock-add');
  const initialCash = document.getElementById('initial_cash');
  const storageKey = 'p107-three-level-research-v1';
  const numberFields = {
    financing_pct: 'stock-finance', borrow_pct: 'stock-borrow', rebate_pct: 'stock-rebate',
    manager_pct: 'stock-manager', transaction_pct: 'stock-trade',
    tax_st_pct: 'research-tax-st', tax_lt_pct: 'research-tax-lt', dividend_tax_pct: 'research-tax-dividend',
    outside_st_gain: 'research-outside-st', outside_lt_gain: 'research-outside-lt',
    harvest_threshold_pct: 'research-threshold', cooldown_days: 'research-cooldown'
  };
  const descriptions = {
    1: {
      title: 'Level 1 — Historical Position Validation',
      value: 'Research value: verify long/short position arithmetic and demonstrate the research workflow.',
      scope: 'Follow your manually selected positions over historical prices. Results are before costs and taxes; no losses are harvested.'
    },
    2: {
      title: 'Level 2 — After-Tax Lifecycle Comparison',
      value: 'Research value: compare modeled after-tax wealth across market periods and holding horizons.',
      scope: 'Track historical holdings, dividends, financing, short costs, annual loss usage and a full taxable exit. The benchmark receives the same outside gains.'
    },
    3: {
      title: 'Level 3 — Rule-Based Loss Harvesting',
      value: 'Research value: examine how harvested losses, deferral, costs and the final exit affect investor wealth.',
      scope: 'Add an explicit loss trigger and delayed same-ticker reentry to Level 2. Compare harvested losses with actual loss usage and remaining tax liability under the stated rules.'
    }
  };
  let busy = false;
  let revision = 0;
  const rows = () => Array.from(list.querySelectorAll('.stock-position'));
  const field = (row, name) => row.querySelector('[data-field="' + name + '"]');
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const money = value => finite(value) ? new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 2}).format(value) : '—';
  const percent = value => finite(value) ? value.toFixed(2) + '%' : '—';
  const plain = value => value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);

  function readInputs() {
    const inputs = {
      level: Number(levelControl.value), initial_cash: Number(initialCash.value),
      start_date: document.getElementById('research-start').value,
      end_date: document.getElementById('research-end').value,
      benchmark: document.getElementById('research-benchmark').value.trim().toUpperCase(),
      positions: rows().map(row => ({
        ticker: field(row, 'ticker').value.trim().toUpperCase(),
        side: field(row, 'side').value,
        shares: Number(field(row, 'shares').value)
      }))
    };
    for (const [key, id] of Object.entries(numberFields)) inputs[key] = Number(document.getElementById(id).value);
    return inputs;
  }

  function save() {
    try {
      const inputs = readInputs();
      // Initial equity is owned by the original scenario form and is not restored here.
      delete inputs.initial_cash;
      sessionStorage.setItem(storageKey, JSON.stringify(inputs));
    } catch (_) {}
  }

  function changed() {
    revision++;
    result.classList.add('stock-stale');
    if (!result.hidden) status.textContent = 'Inputs changed. The displayed research result is from the previous run.';
    save();
  }

  function describeLevel() {
    const level = Number(levelControl.value);
    const description = descriptions[level];
    const target = document.getElementById('research-level-description');
    target.replaceChildren();
    const title = document.createElement('strong'); title.textContent = description.value;
    const text = document.createElement('span'); text.textContent = description.scope;
    target.append(title, text);
    for (const [id, minimum] of [['research-cost-fields', 2], ['research-tax-fields', 2], ['research-harvest-fields', 3]]) {
      const group = document.getElementById(id);
      group.hidden = level < minimum;
      group.disabled = level < minimum;
    }
    button.textContent = 'Run Level ' + level + ' Research';
  }

  function add(position = {}) {
    if (rows().length >= 20) {
      status.textContent = 'A research run supports at most 20 distinct tickers.';
      return;
    }
    const row = document.createElement('div'); row.className = 'stock-position';
    row.innerHTML = '<label>US ticker<input data-field="ticker" type="text" maxlength="15" placeholder="For example, AAPL or BRK-B" required pattern="[A-Za-z][A-Za-z0-9\\-]{0,14}" autocomplete="off" spellcheck="false"></label><label>Position direction<select data-field="side"><option value="long">Long</option><option value="short">Short</option></select></label><label>Shares at entry<input data-field="shares" type="number" min="0.000001" max="100000000" step="any" placeholder="For example, 100" required></label><button type="button" data-remove>Remove position</button>';
    for (const name of ['ticker', 'side', 'shares']) {
      if (position[name] !== undefined && position[name] !== null) field(row, name).value = String(position[name]);
    }
    if (!['long', 'short'].includes(field(row, 'side').value)) field(row, 'side').value = 'long';
    row.querySelector('[data-remove]').addEventListener('click', () => { row.remove(); changed(); });
    list.appendChild(row);
  }

  function paragraph(parent, text, className) {
    const element = document.createElement('p'); element.textContent = text;
    if (className) element.className = className;
    parent.appendChild(element); return element;
  }

  function heading(parent, text) {
    const element = document.createElement('h3'); element.className = 'research-result-heading'; element.textContent = text;
    parent.appendChild(element);
  }

  function table(parent, columns, records) {
    const scroll = document.createElement('div'); scroll.className = 'research-scroll';
    scroll.tabIndex = 0;
    const tableElement = document.createElement('table');
    const thead = document.createElement('thead'); const headerRow = document.createElement('tr');
    for (const [label] of columns) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; headerRow.appendChild(th); }
    thead.appendChild(headerRow); tableElement.appendChild(thead);
    const tbody = document.createElement('tbody');
    for (const record of records) {
      const tr = document.createElement('tr');
      for (const [, key, format] of columns) {
        const td = document.createElement('td'); td.textContent = format ? format(record[key]) : plain(record[key]); tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    tableElement.appendChild(tbody); scroll.appendChild(tableElement); parent.appendChild(scroll);
    if (!records.length) paragraph(parent, 'No records for this level and period.', 'research-empty');
  }

  function curve(parent, daily, benchmarkDaily = [], controlDaily = []) {
    const series = [
      {name: 'Strategy', color: '#315792', rows: daily},
      {name: 'Matched benchmark', color: '#6c7788', rows: benchmarkDaily, dash: '6 4'},
      {name: 'Same portfolio, no harvesting', color: '#16796c', rows: controlDaily, dash: '2 3'}
    ].map(item => ({...item, rows: item.rows.filter(row => finite(row.equity))})).filter(item => item.rows.length);
    if (!series.length) return;
    const dates = [...new Set(series.flatMap(item => item.rows.map(row => String(row.date))))].sort();
    const dateIndex = new Map(dates.map((date, index) => [date, index]));
    const width = 540, height = 260, left = 78, right = 16, top = 24, bottom = 44;
    const values = series.flatMap(item => item.rows.map(row => row.equity));
    const min = Math.min(...values), max = Math.max(...values);
    const pad = Math.max((max - min) * 0.1, Math.abs(max) * 0.01, 1);
    const lo = min - pad, hi = max + pad;
    const x = date => left + (width - left - right) * dateIndex.get(String(date)) / Math.max(1, dates.length - 1);
    const y = value => height - bottom - (height - top - bottom) * (value - lo) / (hi - lo);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.classList.add('research-curve'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Modeled historical equity in US dollars: ' + series.map(item => item.name).join(', '));
    const title = document.createElementNS(ns, 'title'); title.textContent = 'Historical equity with common external cash flows: ' + series.map(item => item.name).join(', '); svg.appendChild(title);
    for (let i = 0; i < 4; i++) {
      const value = lo + (hi - lo) * i / 3;
      const line = document.createElementNS(ns, 'line');
      for (const [key, v] of Object.entries({x1: left, x2: width - right, y1: y(value), y2: y(value), stroke: '#e0e8f2'})) line.setAttribute(key, String(v));
      svg.appendChild(line);
      const label = document.createElementNS(ns, 'text'); label.setAttribute('x', String(left - 7)); label.setAttribute('y', String(y(value) + 4)); label.setAttribute('text-anchor', 'end'); label.setAttribute('font-size', '11'); label.setAttribute('fill', '#526780'); label.textContent = Math.round(value).toLocaleString('en-US'); svg.appendChild(label);
    }
    for (const item of series) {
      const stride = Math.max(1, Math.ceil(item.rows.length / 600));
      const sampled = item.rows.filter((_, index) => index % stride === 0);
      if (sampled[sampled.length - 1] !== item.rows[item.rows.length - 1]) sampled.push(item.rows[item.rows.length - 1]);
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', sampled.map((row, index) => (index ? 'L' : 'M') + x(row.date).toFixed(2) + ',' + y(row.equity).toFixed(2)).join(' '));
      path.setAttribute('fill', 'none'); path.setAttribute('stroke', item.color); path.setAttribute('stroke-width', '2');
      if (item.dash) path.setAttribute('stroke-dasharray', item.dash);
      path.setAttribute('aria-label', item.name); svg.appendChild(path);
    }
    [[dates[0], left, 'start'], [dates[dates.length - 1], width - right, 'end']].forEach(([date, pos, anchor]) => {
      const label = document.createElementNS(ns, 'text'); label.setAttribute('x', String(pos)); label.setAttribute('y', String(height - 16)); label.setAttribute('text-anchor', anchor); label.setAttribute('font-size', '11'); label.setAttribute('fill', '#526780'); label.textContent = date; svg.appendChild(label);
    });
    parent.appendChild(svg);
    const legend = document.createElement('div'); legend.className = 'research-legend';
    for (const item of series) {
      const label = document.createElement('span'); label.style.display = 'block'; label.style.color = item.color;
      label.textContent = (item.dash ? '– – ' : '━━ ') + item.name; legend.appendChild(label);
    }
    parent.appendChild(legend);
    paragraph(parent, 'Common outside gain proceeds, when enabled, are included in every curve. The no-harvest control retains the same starting holdings without the harvesting rule.', 'research-legend');
  }

  function download(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function csv(records) {
    const columns = ['date', 'ticker', 'side', 'event', 'shares', 'price', 'pnl', 'character'];
    const cell = value => {
      let text = value === undefined || value === null ? '' : String(value);
      if (/^[=+@\t\r]/.test(text)) text = "'" + text;
      return '"' + text.replaceAll('"', '""') + '"';
    };
    return '\ufeff' + [columns.join(','), ...records.map(record => columns.map(key => cell(record[key])).join(','))].join('\r\n');
  }

  function render(data, inputs) {
    result.replaceChildren();
    const level = Number(data.level || inputs.level);
    const summary = data.summary || {};
    heading(result, descriptions[level].title);
    paragraph(result, level === 1 ? 'Historical price-only results — before costs and taxes.' : 'Historical results with modeled costs and taxes — full exit included.', 'research-table-note');
    const metrics = [
      ['Terminal investor wealth', summary.terminal_wealth, money],
      ['Matched benchmark ending wealth', summary.benchmark_wealth, money],
      ['Incremental wealth vs benchmark', summary.incremental_wealth, money],
      ['Simple gain / initial equity (outside cash removed; not CAGR)', summary.return_pct, percent]
    ];
    for (const [label, value, format] of metrics) {
      const metric = document.createElement('div'); metric.className = 'research-metric';
      const name = document.createElement('span'); name.textContent = label;
      const amount = document.createElement('strong'); amount.textContent = format(value); metric.append(name, amount); result.appendChild(metric);
    }
    if (level > 1 && (inputs.outside_st_gain || inputs.outside_lt_gain)) paragraph(result, 'Terminal wealth includes outside gain proceeds. The simple gain ratio removes gross outside proceeds and divides by initial equity; it is not TWR, IRR or CAGR.', 'research-warning');
    heading(result, 'Historical equity path'); curve(result, Array.isArray(data.daily) ? data.daily : [], Array.isArray(data.benchmark?.daily) ? data.benchmark.daily : [], Array.isArray(data.no_harvest_control?.daily) ? data.no_harvest_control.daily : []);
    heading(result, 'Accounting and exposure');
    const entries = [
      ['Initial equity', money(summary.initial_cash)],
      ['Initial net exposure', percent(finite(summary.initial_net_exposure) ? summary.initial_net_exposure * 100 : null)],
      ['Initial gross exposure', percent(finite(summary.initial_gross_exposure) ? summary.initial_gross_exposure * 100 : null)],
      ['Price P&L', money(summary.price_pnl)],
      ['Dividend cash flow', money(summary.dividend_cash)],
      ['Dividend tax', money(summary.dividend_tax)],
      ['Tax on short rebate (ST-rate proxy)', money(summary.rebate_tax)],
      ['Modeled costs', typeof summary.costs === 'object' ? plain(summary.costs) : money(summary.costs)],
      ['Capital-gains tax', money(summary.capital_tax)],
      ['Incremental exit tax', money(summary.exit_tax)],
      ['Unrealized P&L before exit', money(summary.unrealized_before_exit)]
    ];
    if (level === 3) entries.push(['Harvested loss', money(summary.harvested_loss)], ['Loss used against gains', money(summary.loss_used)], ['Remaining ST carryforward', money(summary.remaining_carry_st)], ['Remaining LT carryforward', money(summary.remaining_carry_lt)]);
    table(result, [['Measure', 'label'], ['Value', 'value']], entries.map(([label, value]) => ({label, value})));
    if (summary.cost_breakdown && typeof summary.cost_breakdown === 'object') {
      heading(result, 'Cost breakdown');
      table(result, [['Component', 'label'], ['Amount', 'value']], [
        ['Financing', 'financing'], ['Short borrow', 'borrow'], ['Management', 'management'],
        ['Trading', 'trading'], ['Short rebate received (reduces costs)', 'rebate']
      ].map(([label, key]) => ({label, value: money(summary.cost_breakdown[key])})));
    }
    if (level === 3 && finite(summary.incremental_wealth_vs_no_harvest)) {
      heading(result, 'Harvesting vs the same portfolio without harvesting');
      paragraph(result, 'This control uses the same manually selected starting holdings and assumptions, with harvesting disabled. It separates the harvesting decision from the choice of stocks.', 'research-table-note');
      table(result, [['Difference vs no-harvest control', 'label'], ['Amount', 'value']], [
        ['Incremental terminal wealth', 'incremental_wealth_vs_no_harvest'],
        ['Pre-exit capital-tax relief', 'tax_relief_before_exit_vs_no_harvest'],
        ['Extra exit tax', 'extra_exit_tax_vs_no_harvest'],
        ['Total modeled capital-tax saving', 'total_capital_tax_saving_vs_no_harvest'],
        ['Extra net costs', 'extra_cost_vs_no_harvest'],
        ['Price P&L difference', 'price_pnl_difference_vs_no_harvest']
      ].map(([label, key]) => ({label, value: money(summary[key])})));
      paragraph(result, 'Pre-exit capital-tax relief minus extra exit tax equals total modeled capital-tax saving. Relief before exit can reverse when positions are sold. Terminal wealth also changes with price exposure, dividends, costs and rebate taxes while positions are out of the market; the wealth difference is not pure tax alpha.', 'research-warning');
    }
    heading(result, 'Manual positions and historical prices');
    table(result, [['Ticker', 'ticker'], ['Direction', 'side'], ['Entry shares', 'shares'], ['Start price', 'start_price', money], ['End price', 'end_price', money]], Array.isArray(data.positions) ? data.positions : []);
    heading(result, 'Annual tax ledger');
    table(result, [['Year', 'year'], ['ST gain', 'gain_st', money], ['LT gain', 'gain_lt', money], ['ST loss', 'loss_st', money], ['LT loss', 'loss_lt', money], ['Tax', 'tax', money], ['Loss used', 'loss_used', money], ['ST carry', 'carry_st', money], ['LT carry', 'carry_lt', money], ['Outside proceeds', 'outside_proceeds', money], ['Exit tax', 'exit_tax', money]], Array.isArray(data.annual) ? data.annual : []);
    heading(result, 'Trade ledger');
    const trades = Array.isArray(data.trades) ? data.trades : [];
    table(result, [['Date', 'date'], ['Ticker', 'ticker'], ['Direction', 'side'], ['Event', 'event'], ['Shares', 'shares'], ['Price', 'price', money], ['Realized P&L', 'pnl', money], ['Tax character', 'character']], trades.slice(0, 300));
    if (trades.length > 300) paragraph(result, 'Showing the first 300 trades. Export includes all ' + trades.length + ' trades.', 'research-table-note');
    heading(result, 'Assumptions and research limits');
    const assumptions = document.createElement('ul'); assumptions.className = 'research-assumptions';
    for (const text of Array.isArray(data.assumptions) ? data.assumptions : []) { const li = document.createElement('li'); li.textContent = String(text); assumptions.appendChild(li); }
    result.appendChild(assumptions);
    const provenance = document.createElement('details'); const label = document.createElement('summary'); label.textContent = 'Data and reproducibility metadata';
    const pre = document.createElement('pre'); pre.style.whiteSpace = 'pre-wrap'; pre.textContent = JSON.stringify({metadata: data.metadata, data: data.data}, null, 2); provenance.append(label, pre); result.appendChild(provenance);
    const exports = document.createElement('div'); exports.className = 'research-export-buttons';
    const jsonButton = document.createElement('button'); jsonButton.type = 'button'; jsonButton.textContent = 'Download full research JSON';
    jsonButton.addEventListener('click', () => download('p107-level-' + level + '-research.json', JSON.stringify({inputs, result: data}, null, 2), 'application/json'));
    const csvButton = document.createElement('button'); csvButton.type = 'button'; csvButton.textContent = 'Download trades CSV';
    csvButton.addEventListener('click', () => download('p107-level-' + level + '-trades.csv', csv(trades), 'text/csv;charset=utf-8'));
    exports.append(jsonButton, csvButton); result.appendChild(exports); result.hidden = false;
  }

  async function run() {
    if (busy) return;
    for (const row of rows()) field(row, 'ticker').value = field(row, 'ticker').value.trim().toUpperCase();
    const benchmark = document.getElementById('research-benchmark'); benchmark.value = benchmark.value.trim().toUpperCase();
    if (!rows().length) { status.textContent = 'Add at least one manual position.'; return; }
    for (const control of [...section.querySelectorAll('input,select'), initialCash]) if (!control.disabled && !control.reportValidity()) return;
    const inputs = readInputs();
    if (inputs.end_date < inputs.start_date) { status.textContent = 'End date must be on or after start date.'; return; }
    const tickers = inputs.positions.map(position => position.ticker);
    if (new Set(tickers).size !== tickers.length) { status.textContent = 'Use each ticker once. Combine duplicate holdings into a single net position.'; return; }
    const stamp = revision;
    const previous = Array.from(section.querySelectorAll('input,select,button')).map(control => [control, control.disabled]);
    previous.forEach(([control]) => { control.disabled = true; });
    busy = true; result.classList.add('stock-stale'); status.textContent = 'Loading historical data and running Level ' + inputs.level + ' research. This may take a moment…';
    try {
      const response = await fetch('/api/research/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(inputs)});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('The server returned an invalid response. Check the server log and retry.'); }
      if (!response.ok) throw new Error(data.error || 'Historical data or research calculation is unavailable.');
      if (!data.summary) throw new Error('The server response is missing the research summary.');
      render(data, inputs);
      result.classList.toggle('stock-stale', revision !== stamp); save();
      status.textContent = revision === stamp ? 'Research complete. Review the data period, assumptions and ledgers before interpreting the result.' : 'Initial equity changed during this run. The displayed result uses the earlier input; run again to update.';
    } catch (error) {
      status.textContent = error.message === 'Failed to fetch' ? 'The Python server is unavailable. Restart START-STOCK.bat or web/launch_stock.py and try again.' : error.message;
    } finally {
      previous.forEach(([control, disabled]) => { control.disabled = disabled; });
      busy = false; describeLevel();
    }
  }

  addButton.addEventListener('click', () => { add(); changed(); });
  button.addEventListener('click', run);
  levelControl.addEventListener('change', describeLevel);
  section.addEventListener('input', changed); section.addEventListener('change', changed);
  initialCash.addEventListener('input', changed);
  section.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input')) { event.preventDefault(); run(); }
  });
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (saved && Array.isArray(saved.positions)) {
      if ([1, 2, 3].includes(saved.level)) levelControl.value = String(saved.level);
      for (const [key, id] of [['start_date', 'research-start'], ['end_date', 'research-end'], ['benchmark', 'research-benchmark']]) if (typeof saved[key] === 'string') document.getElementById(id).value = saved[key];
      for (const [key, id] of Object.entries(numberFields)) if (finite(saved[key])) document.getElementById(id).value = String(saved[key]);
      saved.positions.slice(0, 20).forEach(add);
    }
  } catch (_) {}
  if (!rows().length) add();
  describeLevel();
})();
