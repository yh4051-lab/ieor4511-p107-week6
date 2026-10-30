'use strict';
const $ = id => document.getElementById(id);
const form = $('scenario-form');
const names = {index:'Index', long_only_di:'Long-only DI', core_130_30:'Core 130/30'};
const kinds = {index:'index', long_only_di:'di', core_130_30:'core'};
const descriptions = {index:'Index portfolio · Benchmark', long_only_di:'Long-only · Illustrative loss curve', core_130_30:'Long-short · Illustrative loss curve'};
const money = value => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(Math.abs(value)<.5?0:value);
const number = value => new Intl.NumberFormat('en-US', {maximumFractionDigits:0}).format(value);
const signed = value => Math.abs(value)<.5 ? '$0' : (value >= 0 ? '+' : '−') + money(Math.abs(value));
const direction = value => value >= 0 ? 'positive' : 'negative';
let defaultInputs, lastResult, busy = false, dirty = false;
const draftKey = 'p107-public-inputs-v1';

function setView(view, focus = false) {
  document.querySelectorAll('[role="tab"]').forEach(tab => {
    const selected = tab.dataset.view === view;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });
  document.querySelectorAll('.tab-view').forEach(panel => {panel.hidden = panel.id !== 'view-' + view;});
  $('results-section').hidden = view === 'scope';
}

function clearInputError() {
  $('input-error').hidden = true;
  form.querySelectorAll('[aria-invalid]').forEach(input => {
    input.removeAttribute('aria-invalid');
    input.removeAttribute('aria-describedby');
  });
}

function inputsValid() {
  clearInputError();
  const invalid = Array.from($('input-fields').querySelectorAll('input, select')).find(input => !input.validity.valid);
  if (!invalid) return true;
  const label = invalid.labels?.[0]?.textContent.trim() || 'This field';
  $('input-error').textContent = `${label}: enter ${invalid.id === 'horizon_years' ? 'a whole number' : 'a number'} between ${number(Number(invalid.min))} and ${number(Number(invalid.max))}.`;
  $('input-error').hidden = false;
  invalid.setAttribute('aria-invalid', 'true');
  invalid.setAttribute('aria-describedby', 'input-error');
  const details = invalid.closest('details');
  if (details) details.open = true;
  invalid.focus({preventScroll:true});
  invalid.scrollIntoView({block:'nearest'});
  $('status').textContent = 'Check the highlighted input before running.';
  return false;
}

function saveDraft() {
  if (!Array.from($('input-fields').querySelectorAll('input, select')).every(input => input.validity.valid)) return;
  try {sessionStorage.setItem(draftKey, JSON.stringify(readInputs()));} catch (_) {}
}

function setInputs(inputs) {
  for (const [key, value] of Object.entries(inputs)) $(key).value = value;
}
function readInputs() {
  return Object.fromEntries(Object.keys(defaultInputs).map(key => [key, key === 'outside_character' ? $(key).value : Number($(key).value)]));
}
function markDirty() {
  if (busy || !defaultInputs) return;
  clearInputError();
  $('example-picker').value = 'custom';
  const values = readInputs();
  dirty = !lastResult || Object.keys(defaultInputs).some(key => values[key] !== lastResult.inputs[key]);
  $('pending').hidden = !dirty || !lastResult;
  $('results-section').classList.toggle('is-stale', dirty);
  $('download').disabled = dirty || !lastResult;
  $('status').textContent = dirty ? 'Inputs changed. Run comparison to update.' : 'Results match the current inputs.';
  saveDraft();
}
function setBusy(value) {
  busy = value;
  $('input-fields').disabled = value;
  $('run').disabled = value;
  $('reset').disabled = value;
  $('example-picker').disabled = value;
  $('download').disabled = value || !lastResult || dirty;
  $('run').textContent = value ? 'Calculating…' : 'Run comparison →';
  $('results-section').setAttribute('aria-busy', String(value));
}

function renderChart(data) {
  const full = data.curve;
  const roots = data.breakeven.roots_annual_usd;
  const focus = Math.min(data.breakeven.search_max, Math.max(data.config.initial_cash * .3, data.inputs.outside_gains * 1.2, (roots[0] || 0) * 2));
  let points = full.filter(p => p.annual_outside_gain <= focus);
  const next = full.find(p => p.annual_outside_gain > focus);
  if (next) points.push(next);
  if (points.length < 2) points = full.slice(0, 2);
  const W=500, H=235, L=70, R=20, T=20, B=42;
  const xmax = points[points.length-1].annual_outside_gain;
  const ys=points.map(p=>p.core_minus_index);
  const lo0=Math.min(...ys,0), hi0=Math.max(...ys,0), pad=Math.max((hi0-lo0)*.15,1);
  const lo=lo0-pad,hi=hi0+pad;
  const x = v => L+(W-L-R)*v/xmax;
  const y = v => H-B-(H-T-B)*(v-lo)/(hi-lo);
  const compact = v => Math.abs(v)>=1e6 ? (v/1e6).toFixed(1)+'m' : Math.abs(v)>=1000 ? (v/1000).toFixed(0)+'k' : v.toFixed(0);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Core minus Index terminal after-tax wealth at different levels of annual outside gains"><title>Positive values favor Core; negative values favor Index. Both include full exit taxes.</title>`;
  for(let i=0;i<=3;i++) {
    const val=lo+(hi-lo)*i/3,py=y(val);
    svg+=`<line class="chart-gridline" x1="${L}" x2="${W-R}" y1="${py}" y2="${py}"/><text class="chart-label" x="${L-10}" y="${py+4}" text-anchor="end" font-size="11">${compact(val)}</text>`;
  }
  const curvePoints=points.map(p=>`${x(p.annual_outside_gain)},${y(p.core_minus_index)}`).join(' ');
  svg+=`<polygon class="curve-fill" points="${x(points[0].annual_outside_gain)},${y(0)} ${curvePoints} ${x(xmax)},${y(0)}"/>`;
  svg+=`<line class="zero-line" x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}" stroke-dasharray="4 4"/>`;
  for(let i=0;i<=3;i++) svg+=`<text class="chart-label" x="${x(xmax*i/3)}" y="${H-14}" text-anchor="middle" font-size="11">${compact(xmax*i/3)}</text>`;
  svg+=`<polyline class="curve-line" points="${curvePoints}" stroke-width="2.5" fill="none" stroke-linejoin="round"/>`;
  for(const root of roots.filter(v=>v<=xmax).slice(0,5)) svg+=`<circle class="root-dot" cx="${x(root)}" cy="${y(0)}" r="4.5" stroke-width="2"><title>Crossing: ${money(root)} per year</title></circle>`;
  for(const point of points) svg+=`<circle cx="${x(point.annual_outside_gain)}" cy="${y(point.core_minus_index)}" r="5" fill="transparent"><title>Outside gains ${money(point.annual_outside_gain)}; Core minus Index ${signed(point.core_minus_index)}</title></circle>`;
  $('breakeven-chart').innerHTML=svg+'</svg>';
}

function renderLedger() {
  if (!lastResult) return;
  const strategy=$('ledger-strategy').value;
  const rows=lastResult.ledger.filter(r=>r.strategy===strategy);
  const views = {
    tax: {
      note:'Price P&L is before costs and taxes. Final-year tax includes full liquidation. Loss carryforwards are unused losses, not cash.',
      columns:[['Starting NAV',r=>r.nav_start],['Pre-tax price P&L',r=>r.pre_cost_investment_pnl],['ST losses harvested',r=>r.harvested_st_loss],['LT losses harvested',r=>r.harvested_lt_loss],['Tax paid',r=>r.actual_capital_tax+r.ordinary_interest_tax],['Ending loss carryforward',r=>r.carry_st_end+r.carry_lt_end]]
    },
    costs: {
      note:'Rebates offset annual costs. Financing, rebate, and borrow rates apply to their respective notionals. Exit trading costs are shown separately.',
      columns:[['Management fee',r=>r.manager_fee],['Advisor fee',r=>r.advisor_fee],['Long financing',r=>r.long_financing_cost],['Short rebate',r=>r.short_rebate],['Short borrow',r=>r.short_borrow_cost],['Annual trading',r=>r.transaction_cost],['Net annual costs',r=>r.net_annual_cost],['Exit trading',r=>r.exit_transaction_cost]]
    },
    basis: {
      note:'Portfolio value, basis, and embedded gains are after costs and before the final sale. Carryforwards are after tax settlement, including exit in the last year. Basis is an aggregate proxy, not individual tax lots.',
      columns:[['Portfolio value before exit',r=>r.nav_after_costs_pre_exit],['Net-equity basis proxy',r=>r.net_equity_basis_pre_exit],['Embedded gain',r=>r.embedded_gain_pre_exit],['Embedded gain per $1 harvested',r=>r.embedded_gain_per_cumulative_harvest,v=>v===null?'—':v.toFixed(2)+'×'],['ST carryforward',r=>r.carry_st_end],['LT carryforward',r=>r.carry_lt_end],['Incremental exit tax',r=>r.incremental_unwind_tax]]
    }
  };
  const view=views[$('ledger-view').value];
  $('ledger-note').textContent=view.note;
  $('ledger-table').innerHTML=`<table><thead><tr><th scope="col">Year</th>${view.columns.map(([label])=>`<th scope="col">${label}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr><td>Year ${r.year}${r.terminal_after_tax_wealth!==null?' · Exit':''}</td>${view.columns.map(([,value,format])=>`<td>${(format||money)(value(r))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

function render(data) {
  lastResult=data;
  const core=data.summaries.find(r=>r.strategy==='core_130_30');
  const delta=core.incremental_wealth_vs_index;
  $('takeaway-title').innerHTML=`After ${data.config.horizon_years} ${data.config.horizon_years===1?'year':'years'}, Core ${Math.abs(delta)<.5 ? 'roughly matches Index' : 'finishes <strong class="'+direction(delta)+'">'+money(Math.abs(delta))+'</strong> '+(delta>=0?'ahead of':'behind')+' Index'}`;
  const char=data.inputs.outside_character==='st'?'short-term':'long-term';
  $('scenario-caption').textContent=`Starting cash ${money(data.config.initial_cash)} · Annual price return ${data.inputs.price_return_pct}% · Annual outside ${char} gains ${money(data.inputs.outside_gains)}`;
  $('strategy-cards').innerHTML=data.summaries.map(r=>`<article class="strategy-card ${kinds[r.strategy]}"><div class="card-name">${names[r.strategy]}</div><p class="card-desc">${descriptions[r.strategy]}</p><div class="wealth-value">${money(r.terminal_after_tax_wealth)}</div><div class="card-comparison"><strong class="${r.strategy==='index'?'':direction(r.incremental_wealth_vs_index)}">${r.strategy==='index'?'Benchmark':signed(r.incremental_wealth_vs_index)}</strong><span>${r.strategy==='index'?'Reference strategy':'vs. Index'}</span></div></article>`).join('');
  $('wealth-note').textContent=`Wealth is after costs and full exit taxes. It includes ${money(core.outside_gross_gain_proceeds)} of common outside gain proceeds over the holding period and the associated taxes, so it is not a return on starting cash alone. All strategies receive the same outside gains. Displayed amounts are rounded to dollars.`;
  const be=data.breakeven;
  const allFlat=data.curve.every(p=>Math.abs(p.core_minus_index)<.01);
  const root=be.roots_annual_usd[0];
  if(allFlat) {
    $('breakeven-number').textContent='Similar at sampled points';
    $('breakeven-description').textContent='Core and Index differ by less than one cent at every sampled point in this search.';
  } else if(root!==undefined) {
    $('breakeven-number').innerHTML=`${money(root)}<small>/ year</small>`;
    $('breakeven-description').textContent=be.roots_annual_usd.length>1 ? `${be.roots_annual_usd.length} crossings found; the smallest is shown. Use the curve to see which strategy is ahead at each level.` : `At about this level of annual outside ${char} gains, the two strategies finish with equal wealth. All other inputs stay fixed.`;
  } else {
    $('breakeven-number').textContent='No crossing found';
    $('breakeven-description').textContent=`No sign-changing crossing was found from ${money(be.search_min)} to ${money(be.search_max)} per year. This does not rule out a crossing outside that range.`;
  }
  $('search-note').textContent=`Constant annual ${char} gains are scanned from ${money(be.search_min)} to ${money(be.search_max)} in ${money(be.scan_step)} steps, then sign-changing intervals are refined. Outside gains of the other type are zero. The finite grid can miss tangencies or crossings between points. The chart may show a shorter range; the download includes the full curve.`;
  renderChart(data);
  $('horizon-table').innerHTML=`<table><thead><tr><th>Years</th><th class="strategy-heading di">Long-only DI</th><th class="strategy-heading core">Core 130/30</th></tr></thead><tbody>${[1,3,5,10].map(n=>{
    const rows=data.horizons.filter(r=>r.horizon===n);
    if(rows.some(r=>r.strategy==='unavailable')) return `<tr><td>${n}</td><td colspan="2">Scenario not feasible</td></tr>`;
    const di=rows.find(r=>r.strategy==='long_only_di'), coreRow=rows.find(r=>r.strategy==='core_130_30');
    return `<tr class="${data.config.horizon_years===n?'selected-row':''}"><td>${n}</td><td class="${direction(di.incremental_wealth_vs_index)}">${signed(di.incremental_wealth_vs_index)}</td><td class="${direction(coreRow.incremental_wealth_vs_index)}">${signed(coreRow.incremental_wealth_vs_index)}</td></tr>`;
  }).join('')}</tbody></table>`;
  const metrics=[['Cumulative pre-tax price P&L','cumulative_pre_cost_pnl'],['Cumulative net costs, including exit trading','cumulative_net_costs'],['Cumulative pre-exit outside tax relief','current_outside_relief_before_exit'],['Incremental exit tax in the final year','incremental_unwind_tax'],['Cumulative tax paid, including exit','cumulative_total_tax'],['Embedded gain before exit','embedded_gain_before_exit'],['Net-equity basis proxy before exit','net_equity_basis_before_exit'],['ST loss carryforward after exit','carry_st_after_exit'],['LT loss carryforward after exit','carry_lt_after_exit']];
  $('tax-table').innerHTML=`<table><thead><tr><th>Metric</th>${data.summaries.map(r=>`<th class="strategy-heading ${kinds[r.strategy]}">${names[r.strategy]}</th>`).join('')}</tr></thead><tbody>${metrics.map(([label,key])=>`<tr><td>${label}</td>${data.summaries.map(r=>`<td>${money(r[key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  renderLedger();
  $('result-content').hidden=false;
  $('loading').hidden=true;
  $('run-reference').textContent=`Model ${data.metadata.model_version} · Run ${data.run_id.slice(0,8)}`;
}

async function run() {
  if(busy || !inputsValid()) return;
  setView('summary');
  $('error').hidden=true;
  setBusy(true);
  $('status').textContent='Calculating returns, costs, loss offsets, and exit taxes…';
  try {
    const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readInputs())});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error || 'Calculation failed. Please try again.');
    render(data);
    dirty=false;
    $('pending').hidden=true;
    $('results-section').classList.remove('is-stale');
    $('status').textContent='Updated · Results reflect the current inputs';
    saveDraft();
  } catch(error) {
    $('error').textContent=error.message==='Failed to fetch'?'The local server is not responding. Run python web/launch.py from the repository folder, then refresh this page.':error.message;
    $('error').hidden=false;
    $('loading').hidden=true;
    $('status').textContent='Not completed. See the message above.';
    dirty=true;
  } finally {setBusy(false);}
}

form.addEventListener('submit',event=>{event.preventDefault();run();});
form.addEventListener('input',event=>{if(event.target.id!=='example-picker')markDirty();});
form.addEventListener('change',event=>{if(event.target.id!=='example-picker')markDirty();});
function loadExample(value) {
  const inputs={...defaultInputs};
  if(value==='no-gains')inputs.outside_gains=0;
  if(value==='high-financing')inputs.financing_pct=6.5;
  setInputs(inputs);markDirty();$('example-picker').value=value;run();
}
$('reset').addEventListener('click',()=>loadExample('default'));
$('example-picker').addEventListener('change',event=>loadExample(event.target.value));
$('ledger-strategy').addEventListener('change',renderLedger);
$('ledger-view').addEventListener('change',renderLedger);
document.querySelectorAll('[role="tab"]').forEach(tab=>{
  tab.addEventListener('click',()=>setView(tab.dataset.view));
  tab.addEventListener('keydown',event=>{
    const views=['summary','ledger','scope'], index=views.indexOf(tab.dataset.view);
    let next;
    if(event.key==='ArrowRight') next=views[(index+1)%views.length];
    if(event.key==='ArrowLeft') next=views[(index+views.length-1)%views.length];
    if(event.key==='Home')next=views[0];
    if(event.key==='End')next=views[views.length-1];
    if(next){event.preventDefault();setView(next,true);}
  });
});
document.querySelectorAll('[data-go-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.goView,true)));
$('download').addEventListener('click',async()=>{
  if(!lastResult || dirty) return;
  $('download').disabled=true;
  try {
    const response=await fetch('/api/download/'+lastResult.run_id);
    if(!response.ok) throw new Error('This result has expired. Run the comparison again before downloading.');
    const blob=await response.blob(), url=URL.createObjectURL(blob), link=document.createElement('a');
    link.href=url;link.download='P107_scenario_'+lastResult.run_id.slice(0,8)+'.zip';
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    $('status').textContent='Download ready: inputs, CSV files, source hashes, and reproduction instructions.';
  } catch(error) {$('error').textContent=error.message;$('error').hidden=false;}
  finally {$('download').disabled=busy||dirty;}
});

(async()=>{
  try {
    const response=await fetch('/api/defaults');
    if(!response.ok) throw new Error('Could not load the model inputs.');
    defaultInputs=(await response.json()).inputs;
    let initial={...defaultInputs}, restored=false;
    try {
      const draft=JSON.parse(sessionStorage.getItem(draftKey));
      if(draft && Object.keys(defaultInputs).every(key=>key in draft)) {
        initial=Object.fromEntries(Object.keys(defaultInputs).map(key=>[key,draft[key]]));
        restored=Object.keys(defaultInputs).some(key=>initial[key]!==defaultInputs[key]);
      }
    } catch (_) {}
    setInputs(initial);
    $('example-picker').value=restored?'custom':'default';
    setBusy(false);
    await run();
  } catch(error) {
    $('loading').hidden=true;
    $('error').textContent='Could not connect to the local model. Run python web/launch.py from the repository folder, then refresh this page.';
    $('error').hidden=false;
    $('status').textContent='Local server disconnected.';
    $('input-fields').disabled=true;$('run').disabled=true;$('reset').disabled=true;
    $('example-picker').disabled=true;
  }
})();
