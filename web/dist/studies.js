'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => n===null||n===undefined?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Math.abs(n)<.5?0:n);
  const number = n => new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(n);
  const n = id => Number($(id).value);
  const clone = obj => JSON.parse(JSON.stringify(obj));
  const labels = {index:'Index',long_only_di:'Long-only harvesting',core_130_30:'Core 130/30',harvest:'Harvest + rebalance',no_harvest:'Rebalance, no harvest',benchmark:'Index benchmark'};
  const descriptions = {
    exits:['Exit strategy comparison','Set a common horizon and return assumption for each exit policy.','Annual return and loss assumptions. Historical tax-lot exits and estate/gift taxes are not included.'],
    one_time:['One-time capital gains','Choose the year and tax character of a single outside gain.','One event at $0, $1M, $3M or $5M. Break-even uses the annual scenario model, not a historical backtest.'],
    historical:['Rebalancing and loss harvesting','Set the portfolio, replacement securities and trading rules.','Scheduled 130/30 targets with replacement positions. Full wash-sale matching and borrow constraints remain outside this model.'],
    cohort:['Portfolio sampling results','Set the universe, portfolio size and number of draws.','Random portfolios use the supplied universe. The included example is synthetic; verified historical index membership is not supplied.']
  };
  let mode='exits', base, lastResult, busy=false, strategyView='core_130_30';
  const positionDrafts={}; let lastModeKey=null;
  const observed=()=>$('model-basis').value==='observed';
  function section(id,visible) {
    $(id).hidden=!visible;
    $(id).querySelectorAll('input,select,textarea').forEach(el => {el.disabled=!visible;});
  }
  function markDirty() {
    if (!lastResult) return;
    $('download').disabled=true;
    if($('strategy-view'))$('strategy-view').disabled=true;
    $('output').classList.add('dirty');
    $('status').textContent='Parameters changed. Run again to update results.';
  }
  function sourceFields() {
    const historical=observed()||['historical','cohort'].includes(mode);
    const synthetic=$('data-source').value==='synthetic';
    section('history-upload-label',historical&&$('data-source').value==='uploaded');
    section('review-label',historical&&!synthetic);
    $('data-note').textContent=synthetic?'Synthetic test observations, not market history.':$('data-source').value==='local_cache'?'Saved Yahoo daily prices, splits and dividends. This local snapshot is retained for exact replay.':'Fetch complete observed prices. Missing securities or sessions stop the run; no invented prices replace them.';
  }
  function applyPreset() {
    if(!base)return;
    const c=observed()?base.observed:base.historical;
    const fields={cash:'initial_cash',start:'start_date',end:'end_date',benchmark:'benchmark',rebalance:'rebalance_every_sessions',threshold:'harvest_threshold_pct',manager:'manager_pct',advisor:'advisor_pct',finance:'financing_pct',borrow:'borrow_pct',rebate:'rebate_pct',trade:'transaction_pct','tax-st':'tax_st_pct','tax-lt':'tax_lt_pct',maintenance:'maintenance_equity_to_gross_pct'};
    for(const [id,key] of Object.entries(fields))if(c[key]!==undefined)$(id).value=c[key];
    $('outside-year').value=observed()?2021:2020;$('samples').value=observed()?100:20;
    $('data-source').value=observed()?(base.observed_cache_available?'local_cache':'live'):'synthetic';
    $('replacement-reviewed').checked=observed();
    lastModeKey=null;
  }
  function setMode(next) {
    if(lastModeKey)positionDrafts[lastModeKey]=$('positions').value;
    mode=next;lastResult=null;$('download').disabled=true;
    document.querySelectorAll('[data-mode]').forEach(el=>{if(el.dataset.mode===mode)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    const annual=!observed()&&['exits','one_time'].includes(mode);
    section('annual-fields',annual);section('historical-fields',!annual);
    section('exit-fields',annual&&mode==='exits');section('gain-fields',annual&&mode==='one_time');
    section('cohort-fields',mode==='cohort');section('membership-input',mode==='cohort'&&!observed());
    $('fixed-universe-note').hidden=mode!=='cohort'||!observed();
    section('observed-exit-fields',observed()&&mode==='exits');section('observed-gain-fields',observed()&&mode==='one_time');
    section('maintenance-label',observed());sourceFields();
    $('positions-note').textContent=observed()&&mode==='cohort'?'One row per universe stock: ticker, side placeholder, weight placeholder, replacement. Random draws assign the long/short books; the displayed map stays fixed.':'One row per position: ticker, long/short, relative weight, replacement ticker.';
    $('data-source').querySelector('option[value=synthetic]').disabled=observed();
    $('data-source').querySelector('option[value=local_cache]').disabled=!observed();
    const key=$('model-basis').value+'-'+mode;
    if(base&&!annual){
      const c=observed()?base.observed:base.historical;
      const rows=mode==='cohort'?Object.entries(c.substitutes).map(([t,v],i)=>`${t},${i%2?'short':'long'},1,${v.ticker}`).join('\n'):c.positions.map(p=>`${p.ticker},${p.side},${p.weight},${c.substitutes[p.ticker].ticker}`).join('\n');
      $('positions').value=positionDrafts[key]||rows;
    }
    lastModeKey=!annual?key:null;
    $('result-title').textContent=descriptions[mode][0];
    $('study-description').textContent=observed()?'Use the same observed prices and tax-lot rules across comparisons.':descriptions[mode][1];
    $('result-label').textContent=observed()?'Historical tax lots':annual?'Annual scenario':'Earlier historical model';
    $('result-label').classList.remove('synthetic');
    $('basis-note').textContent=observed()?'Observed prices; hypothetical holdings and costs. The same lot engine supports all four analyses.':'Earlier models remain available to reproduce previous exports. Their rules and defaults differ from the historical lot engine.';
    $('scope-note').textContent=observed()?({historical:'Rebalancing, temporary securities, wash deferrals and matched controls. Final wealth includes all modeled taxes.',exits:'Compare full sale, 3–5-year withdrawals, extension reduction, death and gifts using the same historical tax lots.',one_time:'One calendar-year outside gain. Compare Index, a long-only harvesting basket and Core 130/30 after costs and final taxes.',cohort:'Random portfolios from a fixed documented stock pool. This is not a point-in-time S&P 500 backtest.'}[mode]):descriptions[mode][2];
    $('error').hidden=true;$('output').classList.remove('dirty');
    $('output').innerHTML='<div class="empty panel"><h3>Ready for a comparison</h3><p>Review the dates, holdings and assumptions, then select Run analysis.</p><p class="note">Exports include exact inputs, observations, tax-lot ledgers and replay instructions. A 100-portfolio batch can take a few minutes.</p></div>';
    $('status').textContent='Ready to calculate.';
  }
  function reset() {
    HTMLFormElement.prototype.reset.call($('study-form'));strategyView='core_130_30';
    for(const key of Object.keys(positionDrafts))delete positionDrafts[key];
    applyPreset();setMode(mode);
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
    if(!observed()&&['exits','one_time'].includes(mode)) {
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
    const c=clone(observed()?base.observed:base.historical),source=$('data-source').value;
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
    if(observed()){
      r.engine='historical_lots';r.event_year=n('outside-year');r.character=$('observed-character').value;
      r.recipient_tax_st_pct=n('observed-recipient-st');r.recipient_tax_lt_pct=n('observed-recipient-lt');r.estate_tax_cost=n('estate-cost');r.gift_tax_cost=n('gift-cost');
      c.maintenance_equity_to_gross_pct=n('maintenance');
      if(mode==='cohort'){c.universe=c.positions.map(p=>p.ticker);c.universe_kind='fixed_research_universe';}
    }
    if(mode==='cohort'&&!observed()) {
      if($('members-file').files[0])r.memberships=parseMembership(await $('members-file').files[0].text());
      else if(source!=='synthetic')throw Error('Upload the documented historical membership CSV for a non-synthetic cohort.');
    }
    return r;
  }
  function table(title,rows,cols,note='') {
    const colors={index:'var(--index)',long_only_di:'var(--di)',core_130_30:'var(--core)',harvest:'var(--core)',no_harvest:'var(--di)',benchmark:'var(--index)'};
    return `<div class="panel table-panel"><h3>${esc(title)}</h3><p>${esc(note)}</p><div class="table-scroll"><table><thead><tr>${cols.map(c=>'<th scope="col">'+esc(c[1])+'</th>').join('')}</tr></thead><tbody>${rows.map(row=>'<tr>'+cols.map(([key,label,fmt])=>{
      const value=esc(fmt?fmt(row[key],row):row[key]);
      return '<td>'+(key==='strategy'?`<span class="strategy-name" style="--strategy:${colors[row[key]]||'var(--ink)'}">${value}</span>`:value)+'</td>';
    }).join('')+'</tr>').join('')}</tbody></table></div></div>`;
  }
  function cards(items){return '<div class="cards">'+items.map(([label,value,note])=>`<div class="card"><small>${esc(label)}</small><strong>${esc(value)}</strong><p>${esc(note)}</p></div>`).join('')+'</div>';}
  function details(title,body){return '<details class="result-details"><summary>'+esc(title)+'</summary>'+body+'</details>';}
  function policyLabel(value){return value.replace(' full-portfolio exit',' portfolio exit').replace('3-year extension reduction + final sale','Reduce extension, then sell');}
  function chart(lines) {
    const colors={harvest:'#14786e',no_harvest:'#8b7298',benchmark:'#65748b',long_only_di:'#4465b2'};
    const vals=lines.flatMap(l=>l.values),lo=Math.min(...vals),hi=Math.max(...vals),range=hi-lo||1;
    const ticks=Array.from({length:5},(_,i)=>lo+range*i/4);
    const dates=lines[0].dates,times=dates.map(d=>Date.parse(d+'T00:00:00Z')),start=times[0],span=times.at(-1)-start||1;
    const x=i=>82+(times[i]-start)/span*614,y=v=>196-(v-lo)/range*166;
    const tickLabel=v=>Math.abs(v)>=1000000?'$'+number(v/1000000)+'M':'$'+number(v/1000)+'k';
    return '<div class="panel chart-panel"><h3>Investor wealth over time</h3><svg class="chart" viewBox="0 0 720 238" role="img" aria-label="Daily investor wealth for matched comparisons; dates on the horizontal axis, USD on the vertical axis">'+
      ticks.map(v=>`<line x1="82" y1="${y(v)}" x2="696" y2="${y(v)}" stroke="#e8edf3"/><text x="70" y="${y(v)+4}" text-anchor="end">${esc(tickLabel(v))}</text>`).join('')+
      lines.map(l=>'<polyline fill="none" stroke="'+colors[l.key]+'" stroke-width="2" points="'+l.values.map((v,i)=>`${x(i)},${y(v)}`).join(' ')+'"/>').join('')+
      [0,Math.floor((dates.length-1)/2),dates.length-1].map((i,j)=>`<text x="${x(i)}" y="224" text-anchor="${['start','middle','end'][j]}">${esc(dates[i])}</text>`).join('')+
      '</svg><div class="legend">'+lines.map(l=>`<span style="--ink:${colors[l.key]}">${esc(l.name)}</span>`).join('')+'</div><p class="note">The final point includes liquidation and taxes. Outside proceeds follow the same schedule in all matched comparisons.</p></div>';
  }
  function render(r) {
    const synthetic=r.data_label.toLowerCase().includes('synthetic');
    $('result-label').textContent=r.engine==='historical_lots'?r.data_label:['exits','one_time'].includes(mode)?'Annual scenario':synthetic?'Synthetic data · not market history':'Historical input · review provenance';
    $('result-label').classList.toggle('synthetic',synthetic);
    let html='';
    if(mode==='exits') {
      const selected=strategyView==='all'?'core_130_30':strategyView;
      const selectedRows=r.rows.filter(x=>x.strategy===selected),rows=strategyView==='all'?r.rows:selectedRows;
      const full=selectedRows.find(x=>x.policy==='Full sale'),staged=selectedRows.find(x=>x.policy==='3-year full-portfolio exit'),death=selectedRows.find(x=>x.policy==='Hold until death');
      html+='<div class="result-controls"><label>Strategy<select id="strategy-view">'+['core_130_30','index','long_only_di','all'].map(s=>`<option value="${s}"${s===strategyView?' selected':''}>${labels[s]||'All strategies'}</option>`).join('')+'</select></label><span>'+esc(labels[selected])+' · after-tax wealth at the same horizon</span></div>';
      html+=cards([['Full sale',money(full.terminal_after_tax_wealth),'Includes outside cash and final taxes'],['3-year portfolio exit',staged?money(staged.terminal_after_tax_wealth):'Unavailable','Sale proceeds remain in cash'],['Hold until death',money(death.terminal_after_tax_wealth),'Uses the stated basis adjustment']]);
      const columns=[['policy','Exit policy',policyLabel]];
      if(strategyView==='all')columns.push(['strategy','Strategy',x=>labels[x]]);
      columns.push(['terminal_after_tax_wealth','After-tax wealth',money],['difference_vs_full_sale','Vs full sale',money],['incremental_wealth_vs_index','Vs Index',money]);
      html+=table('Exit policies',rows,columns,'Vs full sale compares the same strategy. Vs Index compares the same exit policy. Gift rows show combined donor and recipient wealth.');
      html+=details('Taxes and costs',table('Cumulative amounts',rows,[['policy','Exit policy',policyLabel],['strategy','Strategy',x=>labels[x]],['cumulative_total_tax','Total taxes',money],['cumulative_net_costs','Net costs',money]]));
      html+=details('Annual ledger',table('Tax settlements',r.annual.filter(x=>strategyView==='all'||x.strategy===selected),r.engine==='historical_lots'?[['policy','Policy',policyLabel],['strategy','Strategy',x=>labels[x]],['year','Tax year'],['payment_date','Payment'],['realized_st_loss','ST losses after wash adjustments',money],['realized_lt_loss','LT losses after wash adjustments',money],['tax','Donor capital tax',money]]:[['policy','Policy',policyLabel],['strategy','Strategy',x=>labels[x]],['year','Year'],['nav_start','Starting NAV',money],['partial_exit_proceeds','Sale proceeds to cash',money],['net_equity_basis_pre_exit','Remaining basis',money],['actual_capital_tax','Capital tax',money]]));
    } else if(mode==='one_time') {
      const million=r.rows.find(x=>x.strategy==='core_130_30'&&x.outside_gain===1000000);
      html+=cards(r.searches.map(s=>['Break-even · Core vs '+labels[s.comparator],s.roots_usd.length?s.roots_usd.map(money).join(', '):'No crossing',`One ${s.character.toUpperCase()} gain in year ${s.event_year}; search $0–$5M`]).concat([['Core vs Index · $1M gain',money(million.incremental_wealth_vs_index),'Difference in terminal after-tax wealth']]));
      const amounts=[...new Set(r.rows.map(x=>x.outside_gain))];
      const rows=amounts.map(amount=>{
        const by=Object.fromEntries(r.rows.filter(x=>x.outside_gain===amount).map(x=>[x.strategy,x.terminal_after_tax_wealth]));
        return {outside_gain:amount,...by,vs_index:by.core_130_30-by.index,vs_di:by.core_130_30-by.long_only_di};
      });
      html+=table('Wealth by outside gain',rows,[['outside_gain','One-time gain',money],['index','Index',money],['long_only_di','Long-only basket',money],['core_130_30','Core 130/30',money],['vs_index','Core vs Index',money],['vs_di','Core vs basket',money]],'The same gain proceeds enter each strategy. Compare the differences between strategies, not balances across different gain amounts.');
      html+=details('Tax totals',table('Taxes by scenario',r.rows,[['outside_gain','Outside gain',money],['strategy','Strategy',x=>labels[x]],['cumulative_total_tax','Total taxes',money]]));
      html+=details('Break-even search details','<pre class="scope-json">'+esc(JSON.stringify(r.searches.map(({curve,...s})=>s),null,2))+'</pre>');
    } else if(mode==='historical') {
      const h=r.results.harvest.summary;
      html+=cards([['Harvest + rebalance',money(h.terminal_after_tax_wealth),'Terminal wealth after all modeled taxes'],['Harvesting benefit',money(r.harvesting_benefit),'Rule + replacement effect vs no harvest'],['Difference vs benchmark',money(h.incremental_wealth_vs_benchmark),'Stock selection and leverage also contribute']]);
      html+=table('Matched comparisons',r.rows,[['strategy','Strategy',x=>labels[x]],['terminal_after_tax_wealth','After-tax wealth',money],['total_taxes','All taxes',money],['total_financing_and_fees_net_rebate','Net costs',money],['cumulative_harvested_losses','Harvested losses',money],['remaining_carry_st','Unused ST carry',money]]);
      html+=chart(Object.entries(r.results).map(([name,run])=>({key:name,name:labels[name],dates:run.daily.map(x=>x.date),values:run.daily.map(x=>x.total_investor_wealth)})));
      html+=details('Annual tax ledger',table('Tax utilization',r.results.harvest.annual,[['year','Year'],['realized_st_loss','Realized ST losses',money],['realized_lt_loss','Realized LT losses',money],['loss_used_st','ST losses used',money],['loss_used_lt','LT losses used',money],['tax','Capital tax',money]]));
      if(r.engine==='historical_lots')html+=details('Wash-sale deferrals',table('Quantity-matched losses',r.results.harvest.wash_matches,[['sale_date','Loss sale'],['replacement_date','Replacement acquisition'],['ticker','Ticker'],['side','Side'],['shares','Matched shares',number],['loss_deferred','Loss added to replacement basis',money]]));
      html+=details('Trades and replacements',table('Trade ledger',r.results.harvest.trades,[['date','Date'],['ticker','Ticker'],['side','Side'],['reason','Reason',v=>v.replaceAll('_',' ')],['shares','Shares',number],['fee','Fee',money]]));
      html+=details('Exposure, financing and cash',table('Daily ledger',r.results.harvest.daily,[['date','Date'],['long_pct','Long %',number],['short_pct','Short %',number],['debt','Financing debt',money],['investor_side_cash','Outside / investor cash',money],['active_substitutes','Temporary positions',v=>v.join(', ')] ]));
    } else {
      html+=cards([['Median vs benchmark',money(r.median_delta),'Difference in after-tax wealth'],['Portfolios ahead of benchmark',number(r.benchmark_win_fraction*100)+'%',`${r.draws} seeded draws; not a probability forecast`],['5th–95th percentile',money(r.p05_delta)+' to '+money(r.p95_delta),'Distribution of completed-run benchmark differences']]);
      html+=table('Every sampled portfolio',r.rows,[['sample_id','Draw'],['status','Status',v=>v||'completed'],['long_names','Long stocks',v=>v.join(', ')],['short_names','Short stocks',v=>v.join(', ')],['after_tax_terminal_wealth','After-tax wealth',money],['incremental_wealth_vs_benchmark','Vs benchmark',money],['harvesting_benefit','Vs no harvest',money]],`Seed ${r.seed}; formation ${r.formation_date}. Failed draws: ${r.failed_count||0}. Failures stay in the report and count as not winning.`);
    }
    html+=details('Assumptions and limitations','<ul class="limits">'+r.warnings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>');
    html+=details('Run details','<pre class="scope-json">'+esc(JSON.stringify({config:r.request.config,data:r.data_metadata,metadata:r.metadata},null,2))+'</pre>');
    $('output').innerHTML=html;$('output').classList.remove('dirty');
    $('download').disabled=false;$('status').textContent='Results updated. Ready to export.';
    if($('strategy-view'))$('strategy-view').addEventListener('change',event=>{if(!busy){strategyView=event.target.value;render(lastResult);}});
  }
  $('study-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!base)return;busy=true;$('run').disabled=true;$('download').disabled=true;$('error').hidden=true;
    if($('strategy-view'))$('strategy-view').disabled=true;
    if(lastResult)$('output').classList.add('dirty');
    const enabled=[...$('study-form').querySelectorAll('input,select,textarea')].filter(el=>!el.disabled);
    enabled.forEach(el=>el.disabled=true);
    $('status').textContent='Running calculations…';
    try {
      const payload=await request();
      const response=await fetch('/api/studies/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const r=await response.json();if(!response.ok)throw Error(r.error||'The study could not finish.');
      lastResult=r;render(r);
      if(window.matchMedia('(max-width:700px)').matches)$('results').scrollIntoView({behavior:'auto',block:'start'});
    } catch(error) {$('error').textContent=error.message;$('error').hidden=false;$('status').textContent='Please check the inputs and try again.';}
    finally {enabled.forEach(el=>el.disabled=false);busy=false;$('run').disabled=false;}
  });
  $('study-form').addEventListener('input',markDirty);$('study-form').addEventListener('change',markDirty);
  $('data-source').addEventListener('change',sourceFields);
  $('model-basis').addEventListener('change',()=>{if(!busy){applyPreset();setMode(mode);}});
  document.querySelectorAll('[data-mode]').forEach(el=>el.addEventListener('click',()=>{if(!busy&&mode!==el.dataset.mode)setMode(el.dataset.mode);}));
  $('reset').addEventListener('click',()=>{if(!busy)reset();});
  $('download').addEventListener('click',()=>{if(lastResult)window.location.href='/api/studies/download/'+lastResult.run_id;});
  fetch('/api/studies/defaults').then(r=>{if(!r.ok)throw Error('Could not load the examples.');return r.json();}).then(r=>{base=r;applyPreset();setMode(mode);$('run').disabled=false;}).catch(e=>{$('error').hidden=false;$('error').textContent=e.message;});
})();
