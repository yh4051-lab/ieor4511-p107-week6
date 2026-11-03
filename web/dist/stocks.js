'use strict';
const form = document.getElementById('stock-form');
const statusLine = document.getElementById('stock-status');
const errorLine = document.getElementById('stock-error');
const results = document.getElementById('stock-results');
const money = v => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:2}).format(v);
let lastResult = null;
for (const input of form.querySelectorAll('input[type=date]')) input.max = new Date().toLocaleDateString('en-CA');
form.addEventListener('input', () => { results.hidden=true; lastResult=null; statusLine.textContent='設定已變更，請重新計算。'; });
form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const values=Object.fromEntries(new FormData(form));
  for (const key of ['initial_cash','short_pct','financing_pct','borrow_pct','fee_pct']) values[key]=Number(values[key]);
  const button=document.getElementById('stock-run');
  button.disabled=true; errorLine.hidden=true; results.hidden=true; lastResult=null;
  // Lock inputs while downloading so displayed results always match visible inputs.
  for (const field of form.querySelectorAll('input,select')) field.disabled=true;
  statusLine.textContent='正在向 Yahoo 下載資料並計算，可能需要一段時間…';
  try {
    const response=await fetch('/api/stocks/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
    const data=await response.json();
    if (!response.ok) throw new Error(data.error || '計算失敗');
    render(data); lastResult=data; results.hidden=false; statusLine.textContent='計算完成。';
  } catch(error) { errorLine.textContent=error.message; errorLine.hidden=false; statusLine.textContent='未產生結果。'; }
  finally { button.disabled=false; for (const field of form.querySelectorAll('input,select')) field.disabled=false; }
});
function render(data) {
  document.getElementById('stock-period').textContent=`實際交易日期：${data.effective_start} 至 ${data.effective_end}；資料取得時間：${data.retrieved_at}`;
  const s=data.summary, summary=document.getElementById('stock-summary'); summary.replaceChildren();
  for (const [label,value] of [['期末淨資產',money(s.ending_equity)],['淨損益',money(s.net_pnl)],['累計報酬',s.net_return_pct.toFixed(2)+'%'],['最大回撤',s.max_drawdown_pct.toFixed(2)+'%'],['多頭損益',money(s.long_pnl)],['空頭損益',money(s.short_pnl)],['融資成本',money(s.financing_cost)],['借券成本',money(s.borrow_cost)],['管理費',money(s.management_fee)]]) {
    const card=document.createElement('div'), title=document.createElement('span'), valueNode=document.createElement('strong'); title.textContent=label; valueNode.textContent=value; card.append(title,valueNode); summary.append(card);
  }
  const tbody=document.getElementById('stock-positions'); tbody.replaceChildren();
  for(const p of data.positions){const tr=document.createElement('tr');for(const value of [p.ticker,p.side==='long'?'做多':'放空',money(p.initial_notional),p.total_return_pct.toFixed(2)+'%',money(p.pnl)]){const td=document.createElement('td');td.textContent=value;tr.append(td);}tbody.append(tr);}
  const notes=document.getElementById('stock-assumptions');notes.replaceChildren();for(const text of data.assumptions){const li=document.createElement('li');li.textContent=text;notes.append(li);}
  const svg=document.getElementById('stock-chart');svg.replaceChildren();const rows=data.ledger;
  let min=Infinity,max=-Infinity;for(const r of rows){min=Math.min(min,r.equity);max=Math.max(max,r.equity);}if(max===min){max+=1;min-=1;}
  const ns='http://www.w3.org/2000/svg';const line=document.createElementNS(ns,'polyline');
  const t0=Date.parse(rows[0].date),dt=Date.parse(rows.at(-1).date)-t0;
  line.setAttribute('points',rows.map(r=>`${105+770*(Date.parse(r.date)-t0)/dt},${220-190*(r.equity-min)/(max-min)}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#115e59');line.setAttribute('stroke-width','2');svg.append(line);
  for(const [text,x,y] of [[money(max),5,30],[money(min),5,225],[rows[0].date,105,250],[rows.at(-1).date,770,250]]){const label=document.createElementNS(ns,'text');label.setAttribute('x',x);label.setAttribute('y',y);label.setAttribute('font-size','12');label.textContent=text;svg.append(label);}
}
document.getElementById('stock-download').addEventListener('click',()=>{if(!lastResult)return;const url=URL.createObjectURL(new Blob([JSON.stringify(lastResult,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='P107_stock_experiment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
