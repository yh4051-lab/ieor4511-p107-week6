'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const source=path=>'https://github.com/yh4051-lab/ieor4511-p107-week6/blob/main/'+path.split('/').map(encodeURIComponent).join('/');
  let data,expanded=false,printState=[];
  function render(){
    const query=$('reference-search').value.trim().toLowerCase(),mode=$('reference-mode').value;
    const terms=query.split(/\s+/).filter(Boolean);
    const rows=data.entries.filter(e=>(mode==='all'||e.modes.includes(mode))&&terms.every(t=>[e.title,e.answer,e.method,e.limit,e.kind,...e.sources].join(' ').toLowerCase().includes(t)));
    const names=Object.fromEntries(data.modes.map(m=>[m.id,m.name]));
    $('engine-map').hidden=Boolean(query)||mode!=='all';
    $('starting-settings').hidden=Boolean(query);
    const nav=[['reference','Find a topic']];
    if(!$('engine-map').hidden)nav.push(['engine-map','Engine overview']);
    if(!$('starting-settings').hidden)nav.push(['starting-settings','Starting settings']);
    $('reference-sections').innerHTML=data.categories.map(category=>{
      const entries=rows.filter(e=>e.category===category.id);
      if(!entries.length)return '';
      nav.push(['category-'+category.id,category.name]);
      return `<section class="reference-section" id="category-${category.id}"><div class="category-head"><h2>${esc(category.name)}</h2><span>${entries.length} topics</span></div>`+entries.map(e=>`<article class="assumption" id="${e.id}"><div class="entry-top"><h3>${esc(e.title)}</h3><a href="#${e.id}" aria-label="Link to ${esc(e.title)}">Link ↗</a></div><p class="entry-scopes">${esc(e.modes.map(m=>names[m]).join(' · '))}</p><p class="entry-answer">${esc(e.answer)}</p><details class="method-detail"${expanded?' open':''}><summary>Method, assumptions and limits</summary><div class="method-body"><div><h4>${esc(e.kind==='Illustrative input'?'Input and calculation':'How it is calculated')}</h4><p>${esc(e.method)}</p></div><div><h4>What this leaves out</h4><p>${esc(e.limit)}</p></div><div class="entry-sources"><span>Implementation</span>${e.sources.map(p=>`<a href="${source(p)}" target="_blank" rel="noopener noreferrer">${esc(p)}</a>`).join('')}</div></div></details></article>`).join('')+'</section>';
    }).join('');
    nav.push(['glossary','Glossary']);
    $('section-nav').innerHTML=nav.map(([id,label])=>`<a href="#${id}">${esc(label)}</a>`).join('');
    $('reference-empty').hidden=rows.length>0;
    $('reference-count').textContent=`${rows.length} of ${data.entries.length} topics${mode==='all'?'':' · '+names[mode]}`;
    const columns=data.default_columns.map((c,i)=>({c,i})).filter(({c})=>mode==='all'||c.modes.includes(mode));
    $('defaults-table').innerHTML='<table><thead><tr><th scope="col">Input</th>'+columns.map(({c})=>'<th scope="col">'+esc(c.name)+'</th>').join('')+'</tr></thead><tbody>'+data.defaults.map(row=>'<tr><th scope="row">'+esc(row[0])+'</th>'+columns.map(({i})=>'<td>'+esc(row[i+1])+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
    $('defaults-table').querySelector('table').style.minWidth=columns.length===1?'350px':'780px';
    const d=data.exit_defaults,s=data.sampling_defaults;
    $('special-defaults').innerHTML=`<p><strong>Exit policy defaults:</strong> Core eligible long gain ${d.eligible_core_long_gain_pct}%; gift at the start of year ${d.gift_year}; recipient ST/LT ${d.recipient_st_pct}% / ${d.recipient_lt_pct}%; extension gain attribution ${d.extension_gain_share_pct}%.</p><p><strong>Sampling defaults:</strong> ${s.draws} draws, seed ${s.seed}, ${s.long_count} longs and ${s.short_count} shorts per draw.</p><p>Default values are read from the shipped configuration and form fields. Exact settings for a completed run are in its export.</p>`;
    $('expand-methods').textContent=expanded?'Collapse methods':'Expand methods';
  }
  function reveal(id){
    if(!data)return;
    if(data.entries.some(e=>e.id===id)){
      if(!$(id)){$('reference-search').value='';$('reference-mode').value='all';render();}
      const el=$(id);el.querySelector('details').open=true;el.scrollIntoView({block:'start',behavior:'auto'});
    }
  }
  $('reference-search').addEventListener('input',()=>data&&render());
  $('reference-mode').addEventListener('change',()=>data&&render());
  $('clear-filters').addEventListener('click',()=>{if(data){$('reference-search').value='';$('reference-mode').value='all';render();}});
  $('expand-methods').addEventListener('click',()=>{if(data){expanded=!expanded;document.querySelectorAll('.method-detail').forEach(el=>el.open=expanded);$('expand-methods').textContent=expanded?'Collapse methods':'Expand methods';}});
  document.addEventListener('click',event=>{const a=event.target.closest('a[href^="#"]');if(a&&data&&data.entries.some(e=>'#'+e.id===a.getAttribute('href'))){event.preventDefault();const id=a.getAttribute('href').slice(1);history.replaceState(null,'','#'+id);reveal(id);}});
  window.addEventListener('hashchange',()=>reveal(location.hash.slice(1)));
  window.addEventListener('beforeprint',()=>{printState=[...document.querySelectorAll('#reference details')].map(el=>[el,el.open]);printState.forEach(([el])=>el.open=true);});
  window.addEventListener('afterprint',()=>{printState.forEach(([el,open])=>el.open=open);printState=[];});
  $('print-reference').addEventListener('click',()=>window.print());
  fetch('/api/assumptions').then(r=>{if(!r.ok)throw Error('The reference could not load. Refresh the page or restart the local model.');return r.json();}).then(r=>{
    data=r;$('reference-mode').innerHTML='<option value="all">All calculations</option>'+data.modes.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');
    $('quick-links').innerHTML=data.quick_links.map(x=>`<a href="#${x.id}">${esc(x.title)} ↗</a>`).join('');
    $('glossary-list').innerHTML=data.glossary.map(([term,definition])=>`<dt>${esc(term)}</dt><dd>${esc(definition)}</dd>`).join('');
    $('review-date').textContent='Reviewed '+data.reviewed+'. Source links open the project repository.';
    render();reveal(location.hash.slice(1));
  }).catch(error=>{$('reference-error').hidden=false;$('reference-error').textContent=error.message;$('reference-count').textContent='Reference unavailable.';});
})();
