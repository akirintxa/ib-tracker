const COLORS = ['#2c5f8a','#3a7d44','#c4622d','#b5456b','#6b4bbf','#1a7a62','#c47d0e','#3a6aa8','#5a8a32','#a83228','#4a3a8a'];
let charts = {}, portfolioData = null;

const f = (n,d=2) => n.toLocaleString('es-VE',{minimumFractionDigits:d,maximumFractionDigits:d});
const fu = n => '$'+f(Math.abs(n));
const sg = n => n>=0?'+':'-';

function showTab(t) {
  ['holdings','vs','divs','trades'].forEach(id => document.getElementById('tab-'+id).style.display = id===t?'':'none');
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active',['holdings','vs','divs','trades'][i]===t));
  if (t==='divs' && portfolioData) buildDivTab();
  if (t==='vs' && portfolioData) buildVsTab();
  if (t==='trades' && portfolioData) buildTradesTab();
}

async function loadPortfolio() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spinning');
  document.getElementById('err').style.display = 'none';
  document.getElementById('tbody').innerHTML = '<tr class="loading-row"><td colspan="7"><span class="spinner"></span>Obteniendo datos del portafolio...</td></tr>';
  document.getElementById('m-total').innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch('/api/portfolio');
    
    if (res.status === 401) {
      document.getElementById('login-overlay').style.display = 'flex';
      return;
    }
    
    if (!res.ok) throw new Error('El servidor no respondió correctamente (HTTP '+res.status+')');
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    portfolioData = data;
    const prices = data.prices;
    const rows = data.holdings.map(h => ({...h, price: prices[h.ticker] ?? null})).filter(h => h.price);
    if (!rows.length) throw new Error('No se recibieron precios.');
    rows.sort((a,b) => (b.qty*b.price)-(a.qty*a.price));
    portfolioData.rows = rows;

    renderTable(rows);
    renderMetrics(rows, data.dividends);
    if (document.getElementById('tab-vs').style.display !== 'none') buildVsTab();
    if (document.getElementById('tab-divs').style.display !== 'none') buildDivTab();
    if (document.getElementById('tab-trades').style.display !== 'none') buildTradesTab();

    const now = new Date();
    document.getElementById('stamp').textContent = 'Actualizado: '+now.toLocaleDateString('es-VE')+' '+now.toLocaleTimeString('es-VE',{hour:'2-digit',minute:'2-digit'});
  } catch(e) {
    const el = document.getElementById('err');
    el.style.display = 'block';
    el.innerHTML = `<strong>No se pudo conectar al servidor.</strong><br>
      Asegúrate de haber ejecutado <code>python app.py</code> en la misma carpeta.<br>
      Luego haz clic en Actualizar o recarga la página.<br><br>
      Detalle: ${e.message}`;
    document.getElementById('tbody').innerHTML = '<tr class="loading-row"><td colspan="7">Sin datos — inicia el servidor primero.</td></tr>';
    document.getElementById('m-total').textContent = '—';
  }
  btn.classList.remove('spinning');
}

function renderTable(rows) {
  const tb = document.getElementById('tbody');
  tb.innerHTML = '';
  rows.forEach(h => {
    const val=h.qty*h.price, cost=h.qty*h.avgPrice, pnl=val-cost, ret=(h.price-h.avgPrice)/h.avgPrice*100;
    const dir=ret>=0?'up':'down', bw=Math.min(Math.abs(ret)*2.5,100);
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><div class="tk-n">${h.ticker}</div><div class="tk-f">${h.name}</div></td>
      <td class="r">${f(h.qty,4)}</td><td class="r">${fu(h.avgPrice)}</td><td class="r">${fu(h.price)}</td>
      <td class="r">${fu(val)}</td>
      <td class="r" style="color:${pnl>=0?'var(--green)':'var(--red)'}">${sg(pnl)}${fu(pnl)}</td>
      <td class="r"><span class="badge ${dir}">${sg(ret)}${f(Math.abs(ret))}%</span>
        <div class="bar-t"><div class="bar-f" style="width:${bw}%;background:${ret>=0?'#3a7d44':'#c4322d'}"></div></div>
      </td>`;
    tb.appendChild(tr);
  });
}

function renderMetrics(rows, dividends) {
  let tv=0, tc=0;
  rows.forEach(h=>{tv+=h.qty*h.price; tc+=h.qty*h.avgPrice;});
  const totalDiv = dividends.totalNet;
  const pnl=tv-tc, pp=(pnl/tc)*100, tr=((pnl+totalDiv)/tc)*100, dir=pnl>=0?'up':'down';
  document.getElementById('m-total').textContent=fu(tv);
  document.getElementById('m-inv').textContent=fu(tc);
  document.getElementById('m-pnl').className='m-val '+dir;
  document.getElementById('m-pnl').textContent=sg(pnl)+fu(pnl);
  document.getElementById('m-pnl-pct').textContent=sg(pp)+f(Math.abs(pp))+'%';
  document.getElementById('m-div').textContent='$'+f(totalDiv);
  document.getElementById('m-div-sub').textContent='desde '+( portfolioData.firstDate ? portfolioData.firstDate.substring(0,7) : '—');
  document.getElementById('m-ret').className='m-val '+(tr>=0?'up':'down');
  document.getElementById('m-ret').textContent=sg(tr)+f(Math.abs(tr))+'%';
}

function buildVsTab() {
  const rows = portfolioData.rows;
  const dividends = portfolioData.dividends;
  const vooBase = portfolioData.vooBase;
  let tv=0,tc=0; rows.forEach(h=>{tv+=h.qty*h.price;tc+=h.qty*h.avgPrice;});
  const pnl=tv-tc, portRet=((pnl+dividends.totalNet)/tc)*100;
  const voo=rows.find(r=>r.ticker==='VOO');
  const spRet=voo && vooBase?((voo.price-vooBase)/vooBase)*100:null;

  const pv=document.getElementById('vs-port');
  pv.className='vs-val '+(portRet>=0?'up':'down');
  pv.textContent=sg(portRet)+f(Math.abs(portRet))+'%';

  if(spRet!==null){
    const sv=document.getElementById('vs-sp');
    sv.className='vs-val '+(spRet>=0?'up':'down');
    sv.textContent=sg(spRet)+f(Math.abs(spRet))+'%';
    const pw=portRet>spRet;
    document.getElementById('vc-port').classList.toggle('winner',pw);
    document.getElementById('vc-sp').classList.toggle('winner',!pw);
    ['vc-port','vc-sp'].forEach(id=>{const el=document.getElementById(id);const old=el.querySelector('.winner-tag');if(old)old.remove();});
    const tag=document.createElement('div');tag.className='winner-tag';tag.textContent='ganador';
    document.getElementById(pw?'vc-port':'vc-sp').appendChild(tag);
    document.getElementById('vs-sp-sub').textContent='desde primera compra ('+( portfolioData.firstDate ? portfolioData.firstDate.substring(0,7) : '')+ ')';
  }

  const tickers=rows.map(r=>r.ticker), rets=rows.map(r=>parseFloat(((r.price-r.avgPrice)/r.avgPrice*100).toFixed(2)));
  const spRef=spRet?parseFloat(spRet.toFixed(2)):null;

  if(charts.vs) charts.vs.destroy();
  charts.vs=new Chart(document.getElementById('vsChart'),{
    type:'bar',
    data:{labels:tickers,datasets:[
      {label:'Tu posición',data:rets,backgroundColor:rets.map(r=>r>=0?'rgba(58,125,68,.75)':'rgba(196,50,45,.75)'),borderRadius:4,order:2},
      {label:'S&P 500 ref.',data:tickers.map(()=>spRef),type:'line',borderColor:'#c47d0e',backgroundColor:'transparent',borderWidth:2,pointRadius:0,borderDash:[5,4],order:1}
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.raw}%`}}},
      scales:{x:{ticks:{color:'#a09d97',font:{size:11}},grid:{display:false}},
              y:{ticks:{color:'#a09d97',font:{size:11},callback:v=>v+'%'},grid:{color:'rgba(0,0,0,0.05)'}}}}
  });

  const leg=document.getElementById('alloc-leg'); leg.innerHTML='';
  rows.forEach((r,i)=>{const d=document.createElement('div');d.className='leg-i';d.innerHTML=`<span class="leg-d" style="background:${COLORS[i%COLORS.length]}"></span>${r.ticker}`;leg.appendChild(d);});
  const vals=rows.map(r=>parseFloat((r.qty*r.price).toFixed(2)));
  if(charts.alloc) charts.alloc.destroy();
  charts.alloc=new Chart(document.getElementById('allocChart'),{
    type:'doughnut',
    data:{labels:tickers,datasets:[{data:vals,backgroundColor:COLORS.slice(0,rows.length),borderWidth:3,borderColor:'#f7f6f2'}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>` ${ctx.label}: ${fu(ctx.raw)}`}}},
      cutout:'62%'}
  });
}

function buildDivTab() {
  const divs = portfolioData.dividends;

  // Cards por ticker
  const g=document.getElementById('div-grid'); g.innerHTML='';
  divs.byTicker.filter(d=>d.net>0).forEach(d=>{
    const card=document.createElement('div');card.className='div-card';
    card.innerHTML=`<div class="div-tk">${d.ticker}</div><div class="div-net">$${f(d.net)}</div><div class="div-gross">bruto $${f(d.gross)}</div>`;
    g.appendChild(card);
  });

  // Gráfico por trimestre
  const QS = divs.byQuarter.map(q=>q.quarter);
  const DN = divs.byQuarter.map(q=>q.net);
  const DT = divs.byQuarter.map(q=>q.tax);

  if(charts.div) charts.div.destroy();
  charts.div=new Chart(document.getElementById('divChart'),{
    type:'bar',
    data:{labels:QS,datasets:[
      {label:'Neto',data:DN,backgroundColor:'rgba(58,125,68,.8)',borderRadius:4,stack:'s'},
      {label:'Retención',data:DT,backgroundColor:'rgba(196,50,45,.6)',borderRadius:4,stack:'s'}
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>` ${ctx.dataset.label}: $${ctx.raw.toFixed(2)}`}}},
      scales:{x:{stacked:true,ticks:{color:'#a09d97',font:{size:11}},grid:{display:false}},
              y:{stacked:true,ticks:{color:'#a09d97',font:{size:11},callback:v=>'$'+v},grid:{color:'rgba(0,0,0,0.05)'}}}}
  });

  // Tabla resumen por trimestre
  const tb=document.getElementById('div-tbody'); tb.innerHTML='';
  divs.byQuarter.forEach(q=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${q.quarter}</td><td class="r">$${f(q.gross)}</td><td class="r" style="color:var(--red)">-$${f(q.tax)}</td><td class="r" style="color:var(--green);font-weight:500">$${f(q.net)}</td>`;
    tb.appendChild(tr);
  });
  // Fila total
  const totTr=document.createElement('tr');
  totTr.style.fontWeight='600';
  totTr.style.borderTop='2px solid var(--border)';
  totTr.innerHTML=`<td>Total</td><td class="r">$${f(divs.totalGross)}</td><td class="r" style="color:var(--red)">-$${f(divs.totalTax)}</td><td class="r" style="color:var(--green)">$${f(divs.totalNet)}</td>`;
  tb.appendChild(totTr);

  // Tabla detalle por ticker
  const tb2=document.getElementById('div-ticker-tbody'); tb2.innerHTML='';
  divs.byTicker.filter(d=>d.net>0).forEach(d=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><div class="tk-n">${d.ticker}</div><div class="tk-f">${d.name}</div></td><td class="r">$${f(d.gross)}</td><td class="r" style="color:var(--red)">-$${f(d.tax)}</td><td class="r" style="color:var(--green);font-weight:500">$${f(d.net)}</td>`;
    tb2.appendChild(tr);
  });
}

function buildTradesTab() {
  const trades = portfolioData.trades;
  const tb = document.getElementById('trades-tbody');
  tb.innerHTML = '';
  
  trades.forEach(t => {
    const tr = document.createElement('tr');
    const typeColor = t.type === 'Buy' ? 'var(--green)' : 'var(--amber)';
    const typeLabel = t.type === 'Buy' ? 'Compra' : 'Venta';
    const netColor = t.net < 0 ? 'var(--text)' : 'var(--green)'; 
    const netSign = t.net < 0 ? '-' : '+';
    
    tr.innerHTML = `
      <td>${t.date}</td>
      <td style="color:${typeColor}; font-weight:500;">${typeLabel}</td>
      <td><div class="tk-n">${t.symbol}</div><div class="tk-f">${portfolioData.tickerNames[t.symbol] || t.symbol}</div></td>
      <td class="r">${f(t.qty, 4)}</td>
      <td class="r">${fu(t.price)}</td>
      <td class="r" style="color:var(--red)">-$${f(Math.abs(t.commission))}</td>
      <td class="r" style="color:${netColor}">${netSign}$${f(Math.abs(t.net))}</td>
    `;
    tb.appendChild(tr);
  });
}

async function uploadCSV(input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  
  const label = input.previousElementSibling;
  const originalText = label.innerHTML;
  label.innerHTML = `<span class="spinner"></span>Subiendo...`;
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error al subir');
    
    // Recargar datos tras subir
    await loadPortfolio();
  } catch(e) {
    alert("Error al subir el CSV: " + e.message);
  } finally {
    label.innerHTML = originalText;
    input.value = ''; // Resetear el input para permitir resubir el mismo archivo si hace falta
  }
}

loadPortfolio();
