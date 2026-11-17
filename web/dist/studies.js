'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n);
  const number = n => new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(n);
  const n = id => Number($(id).value);
  const clone = obj => JSON.parse(JSON.stringify(obj));
  const labels = {index:'Index',long_only_di:'Direct Indexing',core_130_30:'Core 130/30',harvest:'Harvest + rebalance',no_harvest:'Rebalance, no harvest',benchmark:'Index benchmark'};
  const descriptions = {
    exits:['Compare the exit choices','Compare a full sale, 3–5-year sales, extension reduction, holding until death and gifting. All use the same annual assumptions.'],
    one_time:['Find the one-time gain threshold','Test one taxable event and compare Core with both Index and Direct Indexing.'],
    historical:['Keep 130/30 while harvesting','Compare periodic rebalancing with and without harvesting, plus a passive benchmark. Inspect replacement trades and exposure drift.'],
    cohort:['Test more than hand-picked stocks','Run seeded random portfolios from the supplied formation-date universe. Compare every draw with its no-harvest case and benchmark.']
  };
  let mode='exits', base, lastResult, busy=false;
  function section(id,visible) {
    $(id).hidden=!visible;
    $(id).querySelectorAll('input,select,textarea').forEach(el => {el.disabled=!visible;});
  }
  function markDirty() {
    if (!lastResult) return;
    $('download').disabled=true;
    $('output').classList.add('dirty');
    $('status').textContent='Inputs changed. Run again to update the results.';
  }
  function sourceFields() {
    const synthetic=$('data-source').value==='synthetic';
    const historical=['historical','cohort'].includes(mode);
    section('history-upload-label',historical && $('data-source').value==='uploaded');
    section('review-label',historical && !synthetic);
    $('data-note').textContent=synthetic ? 'Synthetic prices and membership rows test the software. They are not actual stocks or S&P 500 history.' : 'Use documented prices and reviewed replacement mappings. Missing securities cause an error; the model will not silently drop them.';
  }
  function setMode(next) {
    mode=next;lastResult=null;$('download').disabled=true;
    document.querySelectorAll('[data-mode]').forEach(el => {
      if(el.dataset.mode===mode)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');
    });
    const annual=['exits','one_time'].includes(mode);
    section('annual-fields',annual);section('historical-fields',!annual);
    section('exit-fields',mode==='exits');section('gain-fields',mode==='one_time');
    section('cohort-fields',mode==='cohort');sourceFields();
    if(base && $('data-source').value==='synthetic') {
      $('positions').value=mode==='cohort' ? Object.entries(base.historical.substitutes).map(([t,v],i) => `${t},${i%2?'short':'long'},1,${v.ticker}`).join('\n') : 'T1,long,1,S1\nT2,short,1,S2';
    }
    $('result-title').textContent=descriptions[mode][0];
    $('study-description').textContent=descriptions[mode][1];
    $('result-label').textContent=annual?'ILLUSTRATIVE ANNUAL MODEL':'HISTORICAL ENGINE · DATA SOURCE MATTERS';
    $('error').hidden=true;$('output').classList.remove('dirty');
    $('output').innerHTML='<div class="empty panel"><h3>Review the inputs, then run</h3><p>'+esc(descriptions[mode][1])+'</p><p>Every export includes inputs, results, source hashes and an offline replay command.</p></div>';
    $('status').textContent='Ready. Results are calculated only when you run.';
  }
  function reset() {
    $('study-form').reset();
    setMode(mode);
  }
  async function fileJson(id) {
    const file=$(id).files[0];
    if(!file)throw Error('Select the price observations JSON file.');
    if(file.size>4500000)throw Error('Use a price file smaller than 4.5 MB for this browser study.');
    return JSON.parse(await file.text());
  }
  function parseMembership(text) {
    // Standard CSV with quoted cells and escaped quotes; no silent row skipping.
    const rows=[];let row=[],cell='',quoted=false;
    for(let i=0;i<text.length;i++) {
      const c=text[i];
      if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
      else if(c===','&&!quoted){row.push(cell);cell='';}
      else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(s=>s.trim()))rows.push(row);row=[];cell='';}
      else cell+=c;
    }
    if(quoted)throw Error('Membership CSV contains an unclosed quote.');
    row.push(cell);if(row.some(s=>s.trim()))rows.push(row);
    const keys=(rows.shift()||[]).map(s=>s.replace(/^\uFEFF/,'').trim());
    return rows.map(values=>{
      if(values.length!==keys.length)throw Error('Membership CSV has inconsistent columns.');
      const r=Object.fromEntries(keys.map((k,i)=>[k,values[i].trim()]));
      r.point_in_time_verified=String(r.point_in_time_verified||'').toLowerCase()==='true';return r;
    });
  }
  async function request() {
    if(['exits','one_time'].includes(mode)) {
      const c=clone(base.annual);
      c.initial_cash=n('cash');c.horizon_years=n('horizon');c.market_price_returns=Array(10).fill(n('return')/100);
      c.tax_st=n('tax-st')/100;c.tax_lt=n('tax-lt')/100;c.ordinary_tax_rate=c.tax_st;
      c.outside_st_gains=Array(10).fill(n('annual-gain'));c.outside_lt_gains=Array(10).fill(0);
      for(const s of c.strategies) {
        s.advisor_fee=n('advisor')/100;
        if(s.name==='core_130_30')Object.assign(s,{manager_fee:n('manager')/100,long_financing_rate:n('finance')/100,short_borrow_rate:n('borrow')/100,short_rebate_rate:n('rebate')/100});
      }
      return {mode,config:c,event_year:n('event-year'),character:$('gain-character').value,
        stepup_long_fraction:n('stepup')/100,gift_year:n('gift-year'),recipient_tax_st:n('recipient-st')/100,recipient_tax_lt:n('recipient-lt')/100};
    }
    const c=clone(base.historical),source=$('data-source').value;
    if(source!=='synthetic'&&!$('replacement-reviewed').checked)throw Error('Review the replacement-security assumptions and check the box before running.');
    c.initial_cash=n('cash');c.start_date=$('start').value;c.end_date=$('end').value;c.benchmark=$('benchmark').value.trim().toUpperCase();
    c.positions=[];c.substitutes={};
    for(const line of $('positions').value.trim().split(/\r?\n/)) {
      const parts=line.split(',').map(x=>x.trim());
      if(parts.length!==4||!['long','short'].includes(parts[1])||!Number.isFinite(Number(parts[2]))||Number(parts[2])<=0)throw Error('Each position must be: ticker, long/short, positive weight, replacement ticker.');
      const ticker=parts[0].toUpperCase();
      c.positions.push({ticker,side:parts[1],weight:Number(parts[2])});
      c.substitutes[ticker]={ticker:parts[3].toUpperCase(),reviewed_not_substantially_identical:true};
    }
    Object.assign(c,{rebalance_every_sessions:n('rebalance'),harvest_threshold_pct:n('threshold'),
      financing_pct:n('finance'),borrow_pct:n('borrow'),rebate_pct:n('rebate'),manager_pct:n('manager'),advisor_pct:n('advisor'),
      transaction_pct:n('trade'),tax_st_pct:n('tax-st'),tax_lt_pct:n('tax-lt'),ordinary_tax_pct:n('tax-st'),dividend_tax_pct:n('tax-lt'),
      outside_gain_events:[{year:n('outside-year'),amount:n('historical-gain'),character:'st'}]});
    const r={mode,config:c,data_source:source,samples:n('samples'),seed:n('seed'),long_count:n('n-long'),short_count:n('n-short'),as_of:c.start_date};
    if(source==='uploaded')r.history=await fileJson('history-file');
    if(mode==='cohort') {
      if($('members-file').files[0])r.memberships=parseMembership(await $('members-file').files[0].text());
      else if(source!=='synthetic')throw Error('Upload the documented historical membership CSV for a non-synthetic cohort.');
    }
    return r;
  }
  function table(title,rows,cols,note='') {
    return `<div class="panel table-panel"><h3>${esc(title)}</h3><p>${esc(note)}</p><div class="table-scroll"><table><thead><tr>${cols.map(c=>'<th>'+esc(c[1])+'</th>').join('')}</tr></thead><tbody>${rows.map(row=>'<tr>'+cols.map(([key,label,fmt])=>'<td>'+esc(fmt?fmt(row[key],row):row[key])+'</td>').join('')+'</tr>').join('')}</tbody></table></div></div>`;
  }
  function cards(items){return '<div class="cards">'+items.map(([label,value,note])=>`<div class="card"><small>${esc(label)}</small><strong>${esc(value)}</strong><p>${esc(note)}</p></div>`).join('')+'</div>';}
  function chart(lines) {
    const colors=['#355c9b','#187a73','#bc8246'];
    const vals=lines.flatMap(l=>l.values),lo=Math.min(...vals),hi=Math.max(...vals),range=hi-lo||1;
    return '<div class="panel"><h3>Investor wealth over time</h3><svg class="chart" viewBox="0 0 650 160" role="img" aria-label="Daily investor wealth for three matched comparisons">'+lines.map((l,j)=>'<polyline fill="none" stroke="'+colors[j]+'" stroke-width="2" points="'+l.values.map((v,i)=>`${10+i/Math.max(1,l.values.length-1)*630},${140-(v-lo)/range*125}`).join(' ')+'"/>').join('')+'</svg><div class="legend">'+lines.map((l,i)=>`<span style="--ink:${colors[i]}">${esc(l.name)}</span>`).join('')+'</div><p class="note">The final point includes liquidation and taxes. Outside proceeds are included on the same schedule for all portfolios.</p></div>';
  }
  function render(r) {
    $('result-label').textContent=r.data_label;
    let html='';
    if(mode==='exits') {
      const core=r.rows.filter(x=>x.strategy==='core_130_30'),full=core.find(x=>x.policy==='Full sale'),staged=core.find(x=>x.policy==='3-year full-portfolio exit'),death=core.find(x=>x.policy==='Hold until death');
      html+=cards([['Core · full sale',money(full.terminal_after_tax_wealth),'Includes outside cash and final taxes'],['Core · 3-year exit',staged?money(staged.terminal_after_tax_wealth):'Unavailable','Proceeds remain in side cash'],['Core · hold until death',money(death.terminal_after_tax_wealth),'Conditional basis-adjustment scenario']]);
      html+=table('Exit comparison',r.rows,[['policy','Exit policy'],['strategy','Strategy',x=>labels[x]],['terminal_after_tax_wealth','After-tax wealth',money],['difference_vs_full_sale','Vs same strategy, full sale',money],['incremental_wealth_vs_index','Vs Index, same policy',money],['cumulative_total_tax','Total taxes',money],['cumulative_net_costs','Net costs',money]],'Compare both columns: the policy effect and the strategy effect answer different questions.');
      html+='<details><summary>Annual exit ledger</summary>'+table('Cash, basis and taxes',r.annual,[['policy','Policy'],['strategy','Strategy',x=>labels[x]],['year','Year'],['nav_start','Starting NAV',money],['partial_exit_proceeds','Sale proceeds to cash',money],['net_equity_basis_pre_exit','Remaining basis',money],['actual_capital_tax','Capital tax',money]])+'</details>';
    } else if(mode==='one_time') {
      html+=cards(r.searches.map(s=>['Core vs '+labels[s.comparator],s.roots_usd.length?s.roots_usd.map(money).join(', '):'No crossing',`One-time ${s.character.toUpperCase()} gain in year ${s.event_year}; search $0–$5M`]).concat([['Gain frequency','Once','Other years receive zero outside gains']]));
      html+=table('One-time gain scenarios',r.rows,[['outside_gain','Outside gain',money],['strategy','Strategy',x=>labels[x]],['terminal_after_tax_wealth','After-tax wealth',money],['incremental_wealth_vs_index','Difference vs Index',money],['cumulative_total_tax','Total taxes',money]],'Identical gain proceeds are included in every strategy. A larger ending balance by itself is not evidence of better investment returns.');
      html+='<details><summary>Break-even search diagnostics</summary><pre class="scope-json">'+esc(JSON.stringify(r.searches.map(({curve,...s})=>s),null,2))+'</pre></details>';
    } else if(mode==='historical') {
      const h=r.results.harvest.summary;
      html+=cards([['Harvest + rebalance',money(h.terminal_after_tax_wealth),'Terminal wealth after all modeled taxes'],['Harvesting benefit',money(r.harvesting_benefit),'Vs same portfolio without harvesting'],['Difference vs benchmark',money(h.incremental_wealth_vs_benchmark),'Stock selection and leverage also contribute']]);
      html+=table('Matched comparisons',r.rows,[['strategy','Strategy',x=>labels[x]],['terminal_after_tax_wealth','After-tax wealth',money],['total_taxes','All taxes',money],['total_financing_and_fees_net_rebate','Net costs',money],['cumulative_harvested_losses','Harvested losses',money],['remaining_carry_st','Unused ST carry',money]]);
      html+=chart(Object.entries(r.results).map(([name,run])=>({name:labels[name],values:run.daily.map(x=>x.total_investor_wealth)})));
      html+='<details open><summary>Harvest portfolio · annual ledger</summary>'+table('Tax utilization',r.results.harvest.annual,[['year','Year'],['realized_st_loss','Realized ST losses',money],['realized_lt_loss','Realized LT losses',money],['loss_used_st','ST losses used',money],['loss_used_lt','LT losses used',money],['tax','Capital tax',money]])+'</details>';
      html+='<details><summary>Trades and replacement events</summary>'+table('Trade ledger',r.results.harvest.trades,[['date','Date'],['ticker','Ticker'],['side','Side'],['reason','Reason'],['shares','Shares',number],['fee','Fee',money]])+'</details>';
      html+='<details><summary>Exposure, financing and cash</summary>'+table('Daily ledger',r.results.harvest.daily,[['date','Date'],['long_pct','Long %',number],['short_pct','Short %',number],['debt','Financing debt',money],['investor_side_cash','Outside / investor cash',money],['active_substitutes','Temporary positions',v=>v.join(', ')]])+'</details>';
    } else {
      html+=cards([['Median difference',money(r.median_delta),'Harvest portfolio minus benchmark'],['Benchmark win fraction',number(r.benchmark_win_fraction*100)+'%',`${r.draws} seeded draws; not a probability forecast`],['5th–95th percentile',money(r.p05_delta)+' to '+money(r.p95_delta),'Distribution of benchmark differences']]);
      html+=table('Every sampled portfolio',r.rows,[['sample_id','Draw'],['long_names','Long stocks',v=>v.join(', ')],['short_names','Short stocks',v=>v.join(', ')],['after_tax_terminal_wealth','After-tax wealth',money],['incremental_wealth_vs_benchmark','Vs benchmark',money],['harvesting_benefit','Vs no harvest',money]],`Seed ${r.seed}; formation ${r.formation_date}. No failing portfolio is silently removed.`);
    }
    html+='<div class="panel limits"><h3>How to interpret this run</h3><ul>'+r.warnings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></div>';
    html+='<details><summary>Exact assumptions and source metadata</summary><pre class="scope-json">'+esc(JSON.stringify({config:r.request.config,data:r.data_metadata,metadata:r.metadata},null,2))+'</pre></details>';
    $('output').innerHTML=html;$('output').classList.remove('dirty');
    $('download').disabled=false;$('status').textContent='Study complete. Review results and export the replay package.';
  }
  $('study-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!base)return;busy=true;$('run').disabled=true;$('download').disabled=true;$('error').hidden=true;
    const enabled=[...$('study-form').querySelectorAll('input,select,textarea')].filter(el=>!el.disabled);
    enabled.forEach(el=>el.disabled=true);
    $('status').textContent='Running calculations…';
    try {
      const payload=await request();
      const response=await fetch('/api/studies/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const r=await response.json();if(!response.ok)throw Error(r.error||'The study could not finish.');
      lastResult=r;render(r);
    } catch(error) {$('error').textContent=error.message;$('error').hidden=false;$('status').textContent='Please check the inputs and try again.';}
    finally {enabled.forEach(el=>el.disabled=false);busy=false;$('run').disabled=false;}
  });
  $('study-form').addEventListener('input',markDirty);$('study-form').addEventListener('change',markDirty);
  $('data-source').addEventListener('change',sourceFields);
  document.querySelectorAll('[data-mode]').forEach(el=>el.addEventListener('click',()=>{if(!busy)setMode(el.dataset.mode);}));
  $('reset').addEventListener('click',()=>{if(!busy)reset();});
  $('download').addEventListener('click',()=>{if(lastResult)window.location.href='/api/studies/download/'+lastResult.run_id;});
  fetch('/api/studies/defaults').then(r=>{if(!r.ok)throw Error('Could not load the examples.');return r.json();}).then(r=>{base=r;setMode(mode);$('run').disabled=false;}).catch(e=>{$('error').hidden=false;$('error').textContent=e.message;});
})();
