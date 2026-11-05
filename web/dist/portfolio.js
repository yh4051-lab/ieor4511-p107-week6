(() => {
  'use strict';
  const section = document.getElementById('stock-experiment');
  if (!section) return;
  const list = document.getElementById('stock-positions');
  const allocationMode = document.getElementById('research-allocation-mode');
  const longExposure = document.getElementById('research-long-exposure');
  const shortExposure = document.getElementById('research-short-exposure');
  const status = document.getElementById('stock-status');
  const result = document.getElementById('stock-result');
  const summaryPanel = document.getElementById('research-summary-panel');
  const ledgerPanel = document.getElementById('research-ledger-panel');
  const researchDownload = document.getElementById('research-download');
  const pending = document.getElementById('research-pending');
  const scopePanel = document.getElementById('research-scope-panel');
  const sharedStatus = document.getElementById('status');
  const addButton = document.getElementById('stock-add');
  const initialCash = document.getElementById('initial_cash');
  const storageKey = 'p107-integrated-research-v2';
  const legacyStorageKey = 'p107-three-level-research-v1';
  const numberFields = {
    financing_pct: 'stock-finance', borrow_pct: 'stock-borrow', rebate_pct: 'stock-rebate',
    manager_pct: 'stock-manager', transaction_pct: 'stock-trade',
    tax_st_pct: 'research-tax-st', tax_lt_pct: 'research-tax-lt', dividend_tax_pct: 'research-tax-dividend',
    outside_st_gain: 'research-outside-st', outside_lt_gain: 'research-outside-lt',
    harvest_threshold_pct: 'research-threshold', cooldown_days: 'research-cooldown'
  };
  let busy = false;
  let revision = 0;
  let lastRun = null;
  let resultRevision = -1;
  let ledgerStrategy = 'strategy';
  let lastStatus = 'Select your stocks and press Run comparison.';
  const rows = () => Array.from(list.querySelectorAll('.stock-position'));
  const field = (row, name) => row.querySelector('[data-field="' + name + '"]');
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const money = value => finite(value) ? new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 2}).format(value) : '—';
  const percent = value => finite(value) ? value.toFixed(2) + '%' : '—';
  const plain = value => value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);

  function readInputs() {
    const inputs = {
      level: 3, evaluate_spy: true, initial_cash: Number(initialCash.value),
      allocation_mode: allocationMode.value,
      long_exposure_pct: Number(longExposure.value),
      short_exposure_pct: Number(shortExposure.value),
      start_date: document.getElementById('research-start').value,
      end_date: document.getElementById('research-end').value,
      benchmark: document.getElementById('research-benchmark').value.trim().toUpperCase(),
      positions: rows().map(row => ({
        ticker: field(row, 'ticker').value.trim().toUpperCase(),
        side: field(row, 'side').value,
        ...(allocationMode.value === 'shares' ? {shares: Number(field(row, 'shares').value)} : {weight: Number(field(row, 'weight').value)})
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

  function setStatus(message) {
    lastStatus = message;
    status.textContent = message;
    if (window.P107Results?.currentMode() === 'research' && sharedStatus) sharedStatus.textContent = message;
  }

  function changed() {
    revision++;
    updateAllocation();
    if (lastRun) setStatus('Inputs changed. Run comparison to update the right-side results.');
    syncResultState();
    save();
  }

  function syncResultState() {
    const stale = !!lastRun && revision !== resultRevision;
    result.classList.toggle('stock-stale', stale || busy);
    summaryPanel?.classList.toggle('stock-stale', stale || busy);
    ledgerPanel?.classList.toggle('stock-stale', stale || busy);
    scopePanel?.classList.toggle('stock-stale', stale || busy);
    if (researchDownload) researchDownload.disabled = !lastRun || stale || busy;
    for (const control of document.querySelectorAll('[data-research-export]')) control.disabled = !lastRun || stale || busy;
    if (pending) {
      pending.hidden = window.P107Results?.currentMode() !== 'research' || !lastRun || !(stale || busy);
      pending.textContent = busy ? 'Historical research is running. The displayed results are from the previous completed run.' : 'Research inputs changed. These results are from the previous run; press Run comparison to update.';
    }
  }

  function showResearch(view = 'summary') {
    window.P107Results?.show('research', view);
    document.querySelector('.results-column')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  function downloadJson() {
    if (!lastRun || busy || revision !== resultRevision) return;
    download('p107-after-tax-research.json', JSON.stringify(lastRun, null, 2), 'application/json');
  }

  function updateAllocation() {
    const manual = allocationMode.value === 'shares';
    document.getElementById('research-exposure-fields').hidden = manual;
    longExposure.disabled = manual || busy;
    shortExposure.disabled = manual || busy;
    for (const row of rows()) {
      for (const name of ['shares', 'weight']) {
        const control = field(row, name);
        const active = name === (manual ? 'shares' : 'weight');
        control.closest('label').hidden = !active;
        control.disabled = busy || !active;
      }
    }
    const target = document.getElementById('research-allocation-summary');
    if (manual) {
      target.textContent = 'Manual shares: actual long, short, gross and net exposures are shown after historical prices are loaded.';
      return;
    }
    const equity = Number(initialCash.value), long = Number(longExposure.value), short = Number(shortExposure.value);
    if (![equity, long, short].every(finite) || equity <= 0 || long < 0 || short < 0) {
      target.textContent = 'Enter initial equity and nonnegative allocation percentages.';
      return;
    }
    target.textContent = 'Initial equity ' + money(equity) + ' → Long ' + money(equity * long / 100) + ' / Short ' + money(equity * short / 100) + '. Gross exposure ' + percent(long + short) + '; net exposure ' + percent(long - short) + '. Targets use initial equity before opening fees. Short proceeds stay restricted; financing and borrow costs are included.';
  }

  function add(position = {}) {
    if (rows().length >= 20) {
      setStatus('A research run supports at most 20 distinct tickers.');
      return;
    }
    const row = document.createElement('div'); row.className = 'stock-position';
    row.innerHTML = '<label>US ticker<input data-field="ticker" type="text" maxlength="15" placeholder="For example, AAPL or BRK-B" required pattern="[A-Za-z][A-Za-z0-9\\-]{0,14}" autocomplete="off" spellcheck="false"></label><label>Position direction<select data-field="side"><option value="long">Long</option><option value="short">Short</option></select></label><label>Relative weight within this direction<input data-field="weight" type="number" min="0.000001" max="1000000" step="any" value="1" required><span class="field-note">For two longs, weights 3 and 1 split the long allocation 75% / 25%. Each direction is sized separately.</span></label><label hidden>Shares at entry<input data-field="shares" type="number" min="0.000001" max="100000000" step="any" placeholder="For example, 100" required disabled></label><button type="button" data-remove>Remove position</button>';
    for (const name of ['ticker', 'side', 'shares', 'weight']) {
      if (position[name] !== undefined && position[name] !== null) field(row, name).value = String(position[name]);
    }
    if (!['long', 'short'].includes(field(row, 'side').value)) field(row, 'side').value = 'long';
    row.querySelector('[data-remove]').addEventListener('click', () => { row.remove(); changed(); });
    list.appendChild(row);
    updateAllocation();
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
    if (!records.length) paragraph(parent, 'No records for this period.', 'research-empty');
  }

  function curve(parent, daily, benchmarkDaily = [], controlDaily = []) {
    const series = [
      {name: 'After-tax harvesting strategy', color: '#315792', rows: daily},
      {name: '100% long benchmark', color: '#6c7788', rows: benchmarkDaily, dash: '6 4'},
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

  function card(parent, title, value, description, kind) {
    const article = document.createElement('article');
    article.className = 'strategy-card research-wealth-card research-card-' + kind;
    paragraph(article, title, 'card-name');
    paragraph(article, description, 'card-desc');
    paragraph(article, money(value), 'wealth-value');
    parent.appendChild(article);
  }

  function renderVerdict(parent, data) {
    const summary = data.summary || {};
    const spyWealth = summary.spy_benchmark_wealth;
    const difference = finite(summary.spy_display_difference) ? summary.spy_display_difference : summary.incremental_wealth_vs_spy;
    const statusCode = ['pass', 'fail', 'tie'].includes(summary.spy_status) ? summary.spy_status : null;
    const panel = document.createElement('section'); panel.id = 'research-verdict';
    panel.className = 'research-verdict research-verdict-' + (statusCode || 'unavailable');
    panel.setAttribute('role', 'status');
    const title = document.createElement('h2');
    title.textContent = statusCode === 'fail' ? 'Strategy failed — below SPY' : statusCode === 'pass' ? 'Strategy passed — above SPY' : statusCode === 'tie' ? 'Strategy matched SPY' : 'SPY comparison unavailable';
    panel.appendChild(title);
    if (statusCode) paragraph(panel, 'After-tax wealth: strategy ' + money(summary.terminal_wealth) + ' · SPY ' + money(spyWealth) + ' · Difference ' + money(difference) + '.');
    paragraph(panel, 'This target compares full-liquidation after-tax wealth for this historical period, with the same initial equity and outside cash flows. It is separate from the effect of harvesting versus your own no-harvest control.', 'research-table-note');
    parent.appendChild(panel);
  }

  function renderInitialExposure(parent, data) {
    const summary = data.summary || {};
    const equity = summary.initial_cash;
    if (!finite(equity) || equity <= 0) return;
    const positions = Array.isArray(data.positions) ? data.positions : [];
    const total = side => positions.filter(position => position.side === side).reduce((sum, position) => sum + position.shares * position.start_price, 0);
    const longValue = total('long'), shortValue = total('short');
    const longPct = longValue / equity * 100, shortPct = shortValue / equity * 100;
    const section = document.createElement('section'); section.className = 'panel research-initial-exposure';
    heading(section, 'Initial capital and long / short exposure');
    paragraph(section, 'Initial equity ' + money(equity) + ' · Gross exposure ' + percent(longPct + shortPct) + ' · Net exposure ' + percent(longPct - shortPct) + '.', 'research-table-note');
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const width = 660, height = 230, left = 128, right = 542, top = 38, bottom = 190;
    const limit = Math.max(100, longPct, shortPct) * 1.08;
    const x = value => left + (value + limit) / (2 * limit) * (right - left);
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Initial exposure relative to starting equity: long ' + percent(longPct) + ', short minus ' + percent(shortPct) + ', equity reference 100%.');
    const title = document.createElementNS(ns, 'title'); title.textContent = 'Signed initial exposure before opening fees. Short exposure extends below zero; positions do not form slices of a 100% capital pie.'; svg.appendChild(title);
    function text(value, px, py, anchor = 'start') {
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', String(px)); label.setAttribute('y', String(py)); label.setAttribute('text-anchor', anchor); label.setAttribute('font-size', '13'); label.setAttribute('fill', '#405670'); label.textContent = value; svg.appendChild(label);
    }
    const line = document.createElementNS(ns, 'line');
    for (const [key, value] of Object.entries({x1: x(0), x2: x(0), y1: top, y2: bottom, stroke: '#708099', 'stroke-width': 1.5})) line.setAttribute(key, String(value));
    svg.appendChild(line);
    for (const [label, value, y, color] of [['Long', longPct, 62, '#315792'], ['Short', -shortPct, 112, '#b3603d'], ['Equity reference', 100, 162, '#93a3b7']]) {
      const rect = document.createElementNS(ns, 'rect');
      const start = Math.min(x(0), x(value));
      for (const [key, v] of Object.entries({x: start, y: y - 18, width: Math.max(0, Math.abs(x(value) - x(0))), height: 28, rx: 3, fill: color})) rect.setAttribute(key, String(v));
      svg.appendChild(rect); text(label, 8, y + 1); text((value > 0 ? '+' : '') + percent(value), width - 8, y + 1, 'end');
    }
    text('−' + Math.round(limit) + '%', left, 218); text('0%', x(0), 218, 'middle'); text('+' + Math.round(limit) + '%', right, 218, 'end');
    section.appendChild(svg);
    const amounts = document.createElement('div'); amounts.className = 'research-exposure-amounts';
    for (const [label, value, allocation] of [['Long positions', longValue, longPct], ['Short positions', shortValue, shortPct]]) {
      const item = document.createElement('div'); paragraph(item, label); const amount = document.createElement('strong'); amount.textContent = money(value); item.appendChild(amount);
      paragraph(item, percent(allocation) + ' of initial equity', 'research-table-note'); amounts.appendChild(item);
    }
    section.appendChild(amounts);
    paragraph(section, 'Bars use initial investor equity as the denominator, before opening fees. Long and short positions may exceed 100%; they are not a 100% pie. Final holdings are fully liquidated, so the initial allocation is the useful exposure view. Short proceeds remain restricted collateral.', 'research-table-note');
    parent.appendChild(section);
  }

  function renderResearchScope(data, inputs) {
    if (!scopePanel) return;
    scopePanel.replaceChildren(); scopePanel.classList.add('research-main', 'panel', 'research-scope-panel');
    const title = document.createElement('h2'); title.textContent = 'Assumptions & scope — this historical run'; scopePanel.appendChild(title);
    paragraph(scopePanel, 'These settings belong to the same completed run shown in Summary and Annual ledger. Input changes require Run comparison to update all three views.', 'research-table-note');
    heading(scopePanel, 'Run configuration');
    const configuration = [
      ['Initial equity', money(inputs.initial_cash)],
      ['Requested period', inputs.start_date + ' to ' + inputs.end_date],
      ['Actual trading period', (data.metadata?.actual_start || inputs.start_date) + ' to ' + (data.metadata?.actual_end || inputs.end_date)],
      ['Position sizing', inputs.allocation_mode === 'target_exposure' ? 'Initial long / short budgets with weights normalized within each direction' : 'Manually entered initial share quantities'],
      ['Selected benchmark', inputs.benchmark + ' · 100% long initial exposure'],
      ['Pass / fail target', '100% long SPY after-tax final wealth, matched initial equity and outside cash flows'],
      ['Financing / borrow / rebate', percent(inputs.financing_pct) + ' / ' + percent(inputs.borrow_pct) + ' / ' + percent(inputs.rebate_pct) + ' per year'],
      ['Management / trading', percent(inputs.manager_pct) + ' per year / ' + percent(inputs.transaction_pct) + ' per trade'],
      ['ST / LT / dividend tax', percent(inputs.tax_st_pct) + ' / ' + percent(inputs.tax_lt_pct) + ' / ' + percent(inputs.dividend_tax_pct)],
      ['Annual outside ST / LT gains', money(inputs.outside_st_gain) + ' / ' + money(inputs.outside_lt_gain)],
      ['Harvest signal', percent(inputs.harvest_threshold_pct) + ' closing-price loss, after holding more than 30 calendar days; execution at the next available close'],
      ['Same-ticker reentry', 'Only after more than ' + inputs.cooldown_days + ' calendar days following a close'],
      ['Final exit', 'All remaining positions fully liquidated at the final available session']
    ];
    table(scopePanel, [['Setting', 'label'], ['Value', 'value']], configuration.map(([label, value]) => ({label, value})));
    heading(scopePanel, 'Interpret the comparisons');
    paragraph(scopePanel, 'SPY pass / fail is the chosen historical target, not a conclusion about every client or future period. The selected benchmark may differ from SPY. The no-harvest control starts with exactly the same stocks and quantities; its wealth difference also reflects time out of the market, dividends and trading costs. Initial exposures drift rather than being continuously rebalanced.');
    heading(scopePanel, 'Model scope');
    const notes = Array.isArray(data.assumptions) ? data.assumptions.filter(note => !/^Level [123]|^All levels/.test(note)) : [];
    if (notes.length) {
      const list = document.createElement('ul');
      for (const note of notes) { const item = document.createElement('li'); item.textContent = note; list.appendChild(item); }
      scopePanel.appendChild(list);
    } else paragraph(scopePanel, 'The model uses historical closing prices, simplified flat tax rates, annual netting, carryforwards and full final liquidation. It does not enforce broker margin requirements or complete household wash-sale rules.');
    paragraph(scopePanel, 'Historical data and all model notes are included in the research JSON export. Borrow availability and modeled cost/tax rates are user-supplied assumptions, not quotes from Yahoo.', 'research-table-note');
    const metadata = document.createElement('details'); metadata.className = 'research-provenance';
    const label = document.createElement('summary'); label.textContent = 'Data and reproducibility metadata';
    const pre = document.createElement('pre'); pre.textContent = JSON.stringify({metadata: data.metadata, data: data.data}, null, 2); metadata.append(label, pre); scopePanel.appendChild(metadata);
  }

  function researchEntries(simulation) {
    const summary = simulation.summary || {};
    const positions = (Array.isArray(simulation.positions) ? simulation.positions : []).map(position => ({...position, initial_value: position.shares * position.start_price, initial_allocation_pct: position.shares * position.start_price / summary.initial_cash * 100}));
    const initialValue = side => positions.filter(position => position.side === side).reduce((sum, position) => sum + position.initial_value, 0);
    return {positions, entries: [
      ['Initial equity', money(summary.initial_cash)],
      ['Terminal after-tax wealth', money(summary.terminal_wealth)],
      ['Initial long position value', money(initialValue('long')) + ' (' + percent(initialValue('long') / summary.initial_cash * 100) + ')'],
      ['Initial short position value', money(initialValue('short')) + ' (' + percent(initialValue('short') / summary.initial_cash * 100) + ')'],
      ['Initial net exposure', percent(finite(summary.initial_net_exposure) ? summary.initial_net_exposure * 100 : null)],
      ['Initial gross exposure', percent(finite(summary.initial_gross_exposure) ? summary.initial_gross_exposure * 100 : null)],
      ['Price P&L', money(summary.price_pnl)],
      ['Dividend cash flow', money(summary.dividend_cash)],
      ['Dividend tax', money(summary.dividend_tax)],
      ['Tax on short rebate (ST-rate proxy)', money(summary.rebate_tax)],
      ['Modeled net costs', money(summary.costs)],
      ['Capital-gains tax, including final liquidation', money(summary.capital_tax)],
      ['Incremental exit tax', money(summary.exit_tax)],
      ['Unrealized P&L immediately before final exit', money(summary.unrealized_before_exit)],
      ['Harvested loss', money(summary.harvested_loss)],
      ['Loss used against gains', money(summary.loss_used)],
      ['Remaining ST carryforward', money(summary.remaining_carry_st)],
      ['Remaining LT carryforward', money(summary.remaining_carry_lt)]
    ].map(([label, value]) => ({label, value}))};
  }

  function selectedSimulation() {
    if (!lastRun) return null;
    return ledgerStrategy === 'strategy' ? lastRun.result : lastRun.result[ledgerStrategy];
  }

  function renderResearchLedger() {
    const content = document.getElementById('research-ledger-content');
    const simulation = selectedSimulation();
    if (!content || !simulation) return;
    content.replaceChildren();
    const summary = simulation.summary || {};
    const {positions, entries} = researchEntries(simulation);
    heading(content, 'Annual tax ledger');
    paragraph(content, 'Actual modeled realized gains, losses, annual tax settlement and full final liquidation. Unused loss carryforwards are not cash.', 'research-table-note');
    table(content, [['Year', 'year'], ['ST gain', 'gain_st', money], ['LT gain', 'gain_lt', money], ['ST loss', 'loss_st', money], ['LT loss', 'loss_lt', money], ['Tax', 'tax', money], ['Loss used', 'loss_used', money], ['ST carry', 'carry_st', money], ['LT carry', 'carry_lt', money], ['Outside proceeds', 'outside_proceeds', money], ['Exit tax', 'exit_tax', money]], Array.isArray(simulation.annual) ? simulation.annual : []);
    heading(content, 'Trade ledger');
    const trades = Array.isArray(simulation.trades) ? simulation.trades : [];
    table(content, [['Date', 'date'], ['Ticker', 'ticker'], ['Direction', 'side'], ['Event', 'event'], ['Shares', 'shares', value => finite(value) ? value.toLocaleString('en-US', {maximumFractionDigits: 6}) : '—'], ['Price', 'price', money], ['Realized P&L', 'pnl', money], ['Tax character', 'character']], trades.slice(0, 300));
    if (trades.length > 300) paragraph(content, 'Showing the first 300 trades. The selected portfolio CSV includes all ' + trades.length + ' trades.', 'research-table-note');
    heading(content, 'Accounting and exposure');
    table(content, [['Measure', 'label'], ['Value', 'value']], entries);
    if (summary.cost_breakdown && typeof summary.cost_breakdown === 'object') {
      heading(content, 'Cost breakdown');
      table(content, [['Component', 'label'], ['Amount', 'value']], [
        ['Financing', 'financing'], ['Short borrow', 'borrow'], ['Management', 'management'],
        ['Trading', 'trading'], ['Short rebate received (reduces costs)', 'rebate']
      ].map(([label, key]) => ({label, value: money(summary.cost_breakdown[key])})));
    }
    heading(content, 'Starting positions and historical prices');
    table(content, [['Ticker', 'ticker'], ['Direction', 'side'], ['Entry shares', 'shares', value => finite(value) ? value.toLocaleString('en-US', {maximumFractionDigits: 6}) : '—'], ['Initial position value', 'initial_value', money], ['% of initial equity', 'initial_allocation_pct', percent], ['Start price', 'start_price', money], ['End price', 'end_price', money]], positions);
  }

  function render(data, inputs, stamp) {
    lastRun = {inputs, result: data};
    resultRevision = stamp;
    result.replaceChildren();
    paragraph(result, 'Results are displayed in Summary, Annual ledger and Assumptions & scope on the right.', 'research-table-note');
    const viewButton = document.createElement('button'); viewButton.type = 'button'; viewButton.textContent = 'View research results';
    viewButton.addEventListener('click', () => showResearch()); result.appendChild(viewButton); result.hidden = false;

    summaryPanel.replaceChildren(); summaryPanel.classList.add('research-main');
    const summary = data.summary || {};
    const actualStart = data.metadata?.actual_start || inputs.start_date;
    const actualEnd = data.metadata?.actual_end || inputs.end_date;
    const runReference = document.getElementById('research-run-reference');
    if (runReference) runReference.textContent = 'Historical research · ' + actualStart + ' to ' + actualEnd + (data.metadata?.run_id ? ' · Run ' + data.metadata.run_id.slice(0, 8) : '');
    const introduction = document.createElement('div'); introduction.className = 'takeaway research-takeaway';
    paragraph(introduction, 'HISTORICAL RESEARCH · AFTER FULL LIQUIDATION', 'eyebrow');
    const title = document.createElement('h2'); title.textContent = 'After-tax loss-harvesting results'; introduction.appendChild(title);
    paragraph(introduction, actualStart + ' to ' + actualEnd + ' · Initial equity ' + money(summary.initial_cash) + ' · Benchmark ' + inputs.benchmark);
    summaryPanel.appendChild(introduction);
    renderVerdict(summaryPanel, data);
    const cards = document.createElement('div'); cards.className = 'strategy-cards research-wealth-cards';
    card(cards, 'With harvesting', summary.terminal_wealth, 'Your selected stocks and harvesting rule', 'strategy');
    card(cards, 'Same portfolio, no harvesting', data.no_harvest_control?.summary?.terminal_wealth, 'Same initial positions, costs and tax settings', 'control');
    card(cards, '100% long benchmark', summary.benchmark_wealth, inputs.benchmark + ' · Same equity and outside cash flows', 'benchmark');
    summaryPanel.appendChild(cards);
    const metrics = document.createElement('div'); metrics.className = 'research-summary-metrics';
    for (const [label, value, format] of [
      ['Incremental wealth vs benchmark', summary.incremental_wealth, money],
      ['Incremental wealth from harvesting', summary.incremental_wealth_vs_no_harvest, money],
      ['Simple gain / initial equity (not CAGR)', summary.return_pct, percent]
    ]) {
      const metric = document.createElement('div'); metric.className = 'research-metric';
      const name = document.createElement('span'); name.textContent = label;
      const amount = document.createElement('strong'); amount.textContent = format(value); metric.append(name, amount); metrics.appendChild(metric);
    }
    summaryPanel.appendChild(metrics);
    renderInitialExposure(summaryPanel, data);
    paragraph(summaryPanel, 'Historical prices, dividends, financing, trading, annual taxes and full liquidation are included. The benchmark starts 100% long; its leverage differs from your selected portfolio. The no-harvest control uses your exact initial holdings. Initial exposure targets are not continuously rebalanced.', 'research-table-note');
    if (inputs.outside_st_gain || inputs.outside_lt_gain) paragraph(summaryPanel, 'Every curve includes the same outside gain proceeds. The simple gain ratio removes gross outside proceeds from wealth change and divides by initial equity; it is not TWR, IRR or CAGR.', 'research-warning');
    const analysis = document.createElement('div'); analysis.className = 'research-analysis-grid';
    const chartPanel = document.createElement('section'); chartPanel.className = 'panel research-chart-panel';
    heading(chartPanel, 'Historical equity path');
    curve(chartPanel, Array.isArray(data.daily) ? data.daily : [], Array.isArray(data.benchmark?.daily) ? data.benchmark.daily : [], Array.isArray(data.no_harvest_control?.daily) ? data.no_harvest_control.daily : []);
    analysis.appendChild(chartPanel);
    const bridge = document.createElement('section'); bridge.className = 'panel research-bridge-panel';
    heading(bridge, 'Harvesting vs the same portfolio without harvesting');
    table(bridge, [['Difference vs no-harvest control', 'label'], ['Amount', 'value']], [
      ['Incremental terminal wealth', 'incremental_wealth_vs_no_harvest'],
      ['Pre-exit capital-tax relief', 'tax_relief_before_exit_vs_no_harvest'],
      ['Extra exit tax', 'extra_exit_tax_vs_no_harvest'],
      ['Total modeled capital-tax saving', 'total_capital_tax_saving_vs_no_harvest'],
      ['Extra net costs', 'extra_cost_vs_no_harvest'],
      ['Price P&L difference', 'price_pnl_difference_vs_no_harvest']
    ].map(([label, key]) => ({label, value: money(summary[key])})));
    paragraph(bridge, 'Pre-exit capital-tax relief minus extra exit tax equals total modeled capital-tax saving. Terminal wealth also changes with time out of the market, dividends and costs; this difference is not pure tax alpha.', 'research-table-note');
    analysis.appendChild(bridge); summaryPanel.appendChild(analysis);
    const ledgerButton = document.createElement('button'); ledgerButton.type = 'button'; ledgerButton.className = 'secondary-button research-view-ledger'; ledgerButton.textContent = 'View annual tax and trade ledgers'; ledgerButton.addEventListener('click', () => showResearch('ledger')); summaryPanel.appendChild(ledgerButton);
    paragraph(summaryPanel, 'Modeled tax results use simplified rules, a same-ticker cooldown and no broker margin enforcement. Complete model notes and historical data are included in the JSON export.', 'research-table-note');

    ledgerPanel.replaceChildren(); ledgerPanel.classList.add('research-main', 'panel', 'research-ledger-panel');
    const ledgerTitle = document.createElement('h2'); ledgerTitle.textContent = 'Historical research ledgers'; ledgerPanel.appendChild(ledgerTitle);
    const selectorLabel = document.createElement('label'); selectorLabel.htmlFor = 'research-ledger-strategy'; selectorLabel.textContent = 'Portfolio';
    const selector = document.createElement('select'); selector.id = 'research-ledger-strategy';
    const choices = [['strategy', 'Harvesting strategy'], ['no_harvest_control', 'Same portfolio, no harvesting'], ['benchmark', inputs.benchmark + ' · Selected benchmark']];
    if (data.spy_benchmark && inputs.benchmark !== 'SPY') choices.push(['spy_benchmark', 'SPY · Pass / fail target']);
    if (!choices.some(([value]) => value === ledgerStrategy)) ledgerStrategy = 'strategy';
    for (const [value, label] of choices) {
      const option = document.createElement('option'); option.value = value; option.textContent = label; selector.appendChild(option);
    }
    selector.value = ledgerStrategy;
    selector.addEventListener('change', () => { ledgerStrategy = selector.value; renderResearchLedger(); });
    const filter = document.createElement('div'); filter.className = 'research-ledger-filter'; filter.append(selectorLabel, selector); ledgerPanel.appendChild(filter);
    const content = document.createElement('div'); content.id = 'research-ledger-content'; ledgerPanel.appendChild(content);
    renderResearchLedger();
    const exports = document.createElement('div'); exports.className = 'research-export-buttons';
    const jsonButton = document.createElement('button'); jsonButton.type = 'button'; jsonButton.textContent = 'Download full research JSON'; jsonButton.dataset.researchExport = '';
    jsonButton.addEventListener('click', downloadJson);
    const csvButton = document.createElement('button'); csvButton.type = 'button'; csvButton.textContent = 'Download trades CSV'; csvButton.dataset.researchExport = '';
    csvButton.addEventListener('click', () => {
      if (!lastRun || busy || revision !== resultRevision) return;
      const suffix = ledgerStrategy === 'strategy' ? '' : '-' + ledgerStrategy.replaceAll('_', '-');
      download('p107-after-tax-trades' + suffix + '.csv', csv(selectedSimulation()?.trades || []), 'text/csv;charset=utf-8');
    });
    exports.append(jsonButton, csvButton); ledgerPanel.appendChild(exports);
    const provenance = document.createElement('details'); provenance.className = 'research-provenance';
    const label = document.createElement('summary'); label.textContent = 'Data and reproducibility metadata';
    const pre = document.createElement('pre'); pre.textContent = JSON.stringify({metadata: data.metadata, data: data.data}, null, 2); provenance.append(label, pre); ledgerPanel.appendChild(provenance);
    renderResearchScope(data, inputs);
    window.P107Results?.setResearchAvailable(true);
    showResearch();
    syncResultState();
  }

  async function run() {
    if (busy) return false;
    for (const row of rows()) field(row, 'ticker').value = field(row, 'ticker').value.trim().toUpperCase();
    const benchmark = document.getElementById('research-benchmark'); benchmark.value = benchmark.value.trim().toUpperCase();
    if (!rows().length) { setStatus('Add at least one manual position.'); return false; }
    for (const control of [...section.querySelectorAll('input,select'), initialCash]) if (!control.disabled && !control.reportValidity()) { setStatus('Check the highlighted research input before running.'); return false; }
    const inputs = readInputs();
    if (inputs.end_date <= inputs.start_date) { setStatus('End date must be after start date.'); return false; }
    const tickers = inputs.positions.map(position => position.ticker);
    if (new Set(tickers).size !== tickers.length) { setStatus('Use each ticker once. Combine duplicate holdings into a single net position.'); return false; }
    if (inputs.allocation_mode === 'target_exposure') {
      if (inputs.long_exposure_pct + inputs.short_exposure_pct <= 0) { setStatus('Set at least one positive long or short allocation.'); return false; }
      for (const side of ['long', 'short']) {
        const exposure = inputs[side + '_exposure_pct'];
        const count = inputs.positions.filter(position => position.side === side).length;
        if (exposure > 0 && !count) { setStatus('Add at least one ' + side + ' ticker for your ' + exposure + '% ' + side + ' allocation.'); return false; }
        if (exposure === 0 && count) { setStatus('Remove ' + side + ' positions or set a positive ' + side + ' allocation.'); return false; }
      }
    }
    const stamp = revision;
    const previous = Array.from(section.querySelectorAll('input,select,button')).map(control => [control, control.disabled]);
    previous.forEach(([control]) => { control.disabled = true; });
    busy = true; syncResultState(); document.dispatchEvent(new CustomEvent('p107:research-busy', {detail: {busy: true}})); setStatus('Loading historical prices and comparing after-tax wealth with harvesting, without harvesting, SPY and your selected benchmark. This may take a moment…');
    try {
      const response = await fetch('/api/research/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(inputs)});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('The server returned an invalid response. Check the server log and retry.'); }
      if (!response.ok) throw new Error(data.error || 'Historical data or research calculation is unavailable.');
      if (!data.summary) throw new Error('The server response is missing the research summary.');
      render(data, inputs, stamp);
      syncResultState(); save();
      setStatus(revision === stamp ? 'Comparison complete. Summary, Annual ledger and Assumptions & scope show this historical run.' : 'Inputs changed during this run. The displayed result uses the earlier input; run again to update.');
      return true;
    } catch (error) {
      setStatus(error.message === 'Failed to fetch' ? 'The Python server is unavailable. Restart START-STOCK.bat or web/launch_stock.py and try again.' : error.message);
      return false;
    } finally {
      previous.forEach(([control, disabled]) => { control.disabled = disabled; });
      busy = false; updateAllocation(); syncResultState(); document.dispatchEvent(new CustomEvent('p107:research-busy', {detail: {busy: false}}));
    }
  }

  function reset() {
    if (busy) return;
    allocationMode.value = 'target_exposure'; longExposure.value = '130'; shortExposure.value = '30';
    document.getElementById('research-start').value = '2020-01-02';
    document.getElementById('research-end').value = '2024-12-31';
    document.getElementById('research-benchmark').value = 'SPY';
    const defaults = {financing_pct: 5, borrow_pct: 1, rebate_pct: 0, manager_pct: 0, transaction_pct: 0.05, tax_st_pct: 40, tax_lt_pct: 20, dividend_tax_pct: 20, outside_st_gain: 0, outside_lt_gain: 0, harvest_threshold_pct: 5, cooldown_days: 30};
    for (const [key, id] of Object.entries(numberFields)) document.getElementById(id).value = String(defaults[key]);
    list.replaceChildren(); add({side: 'long'}); add({side: 'short'});
    changed(); setStatus('Research defaults restored. Select your stocks and press Run comparison.');
  }

  window.P107Research = {run, reset, isBusy: () => busy};

  researchDownload?.addEventListener('click', downloadJson);
  document.addEventListener('p107:result-mode', () => {
    syncResultState();
    if (window.P107Results?.currentMode() === 'research') setStatus(lastStatus);
  });
  addButton.addEventListener('click', () => { add({side: rows().length === 1 && field(rows()[0], 'side').value === 'long' ? 'short' : 'long'}); changed(); });
  section.addEventListener('input', changed); section.addEventListener('change', changed);
  section.addEventListener('toggle', updateAllocation);
  initialCash.addEventListener('input', changed); initialCash.addEventListener('change', changed);
  document.getElementById('example-picker')?.addEventListener('change', changed);
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || sessionStorage.getItem(legacyStorageKey));
    if (saved && Array.isArray(saved.positions)) {
      allocationMode.value = saved.allocation_mode === 'target_exposure' ? 'target_exposure' : 'shares';
      if (finite(saved.long_exposure_pct)) longExposure.value = String(saved.long_exposure_pct);
      if (finite(saved.short_exposure_pct)) shortExposure.value = String(saved.short_exposure_pct);
      for (const [key, id] of [['start_date', 'research-start'], ['end_date', 'research-end'], ['benchmark', 'research-benchmark']]) if (typeof saved[key] === 'string') document.getElementById(id).value = saved[key];
      for (const [key, id] of Object.entries(numberFields)) if (finite(saved[key])) document.getElementById(id).value = String(saved[key]);
      saved.positions.slice(0, 20).forEach(add);
    }
  } catch (_) {}
  if (!rows().length) { add({side: 'long'}); add({side: 'short'}); }
  updateAllocation();
})();
