'use strict';
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (n, digits=2) => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('ko-KR',{maximumFractionDigits:digits});
const pct = n => n == null ? '—' : `${n>0?'+':''}${fmt(n)}%`;
const color = n => n == null || n===0 ? '' : n>0 ? 'positive':'negative';
const badge = s => `<span class="badge ${s==='가격 유지'?'good':s==='가격 이탈'?'bad':s==='주의 관찰'?'caution':''}">${esc(s)}</span>`;
let snapshot = null, market = 'ALL', displayed = [], selected = null;
function notice(message, error=false) { $('notice').hidden=false; $('notice').textContent=message; $('notice').className=`notice ${error?'error':''}`; }
function chooseTop() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const rows = snapshot.tracking.filter(r=>r.days<5 && r.last_close!=null && (market==='ALL'||r.market===market) && (!query||r.name.toLocaleLowerCase().includes(query)||r.ticker.toLocaleLowerCase().includes(query)));
  rows.sort((a,b)=>b.score-a.score||b.signal_date.localeCompare(a.signal_date)||b.ticker.localeCompare(a.ticker));
  const unique = new Map(); rows.forEach(r=>{if(!unique.has(r.ticker))unique.set(r.ticker,r)});
  displayed = [...unique.values()].slice(0,10);
  $('resultCount').textContent=`선택 범위에서 ${fmt(unique.size)}종목 발견 · ${displayed.length}종목 표시${snapshot.meta.errors.length?' · 일부 시세 누락':''}`;
  $('top').className='';
  $('top').innerHTML=displayed.length?displayed.map((r,i)=>`<button class="stock-row" data-key="${esc(r.ticker)}|${esc(r.signal_date)}" aria-label="${esc(r.name)} 상세 보기"><div class="stock-first"><span class="rank">${String(i+1).padStart(2,'0')}</span><div><span class="stock-name">${esc(r.name)}</span><span class="sub">${esc(r.market)} · ${esc(r.ticker)}<br>${esc(r.signal_date)} 발견</span></div></div><div><span class="tiny-label">거래량 배수</span><span class="ratio">${fmt(r.volume_ratio)}<small>배</small></span></div><div><span class="tiny-label">발견일 등락률</span><span class="${color(r.signal_change_pct)}">${pct(r.signal_change_pct)}</span></div><div><span class="tiny-label">발견 이후</span><span class="${color(r.since_signal_pct)}">${pct(r.since_signal_pct)}</span><br>${badge(r.status)}</div><div><span class="tiny-label">점수 </span><span class="score">${fmt(r.score,1)}</span><span class="sub">/ 75</span></div></button>`).join(''):'<div class="empty">이 범위에 조건을 충족한 종목이 없습니다.<br>검색어 또는 시장 선택을 확인해 주세요.</div>';
}
function render() {
  const d=snapshot,m=d.meta;
  $('updated').textContent=`${m.market_date} 기준`;
  $('date').textContent='한국 시장 일봉 · 최근 5거래일 탐색';
  $('count').textContent=fmt(m.signal_count,0); $('trackingCount').textContent=fmt(m.tracking_stock_count,0); $('coverage').textContent=fmt(m.scanned_size,0);
  $('coverageDetail').textContent=`전체 ${fmt(m.universe_size,0)}종목 · ${fmt(m.coverage_pct)}%`;
  $('source').textContent=`출처: ${m.data_source} · KOSPI ${fmt(m.universe_by_market.KOSPI)} / KOSDAQ ${fmt(m.universe_by_market.KOSDAQ)} · 조회 누락 ${m.errors.length}종목`;
  $('generated').textContent=`수집 완료 ${new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',dateStyle:'medium',timeStyle:'short'}).format(new Date(m.generated_at))} KST · 거래대금은 추정치이며 기본 필터에 사용하지 않습니다.`;
  chooseTop();
  $('tracking').className='tracking-list';
  $('tracking').innerHTML=d.tracking.length?d.tracking.map(r=>`<button class="track-card" data-key="${esc(r.ticker)}|${esc(r.signal_date)}"><div class="track-top"><div><span class="stock-name">${esc(r.name)}</span><span class="sub">${esc(r.market)} · ${esc(r.ticker)}</span></div><div><span class="track-return ${color(r.since_signal_pct)}">${pct(r.since_signal_pct)}</span><br>${badge(r.status)}</div></div><div class="track-bottom"><span>${esc(r.signal_date)} 발견 · ${r.days}거래일 경과</span><span>${fmt(r.volume_ratio)}배</span></div></button>`).join(''):'<div class="empty">최근 추적할 신호가 없습니다.</div>';
  $('backtest').innerHTML=['5','10','20'].map(h=>{const r=d.backtest[h];return `<article class="stat"><span>${h}거래일 후</span><strong>${fmt(r.win_rate_pct,1)}${r.win_rate_pct==null?'':'%'}</strong><p>종가가 상승한 신호의 비율</p><p>완료 표본 ${fmt(r.sample_size)}건 · 미완료/누락 ${fmt(r.pending_or_missing)}건</p><dl><div><dt>평균 변화</dt><dd class="${color(r.average_return_pct)}">${pct(r.average_return_pct)}</dd></div><div><dt>중앙값</dt><dd class="${color(r.median_return_pct)}">${pct(r.median_return_pct)}</dd></div></dl></article>`}).join('');
  $('backtestMethod').textContent=m.backtest_method;
  $('backtestScope').textContent=`일봉 수집 범위 ${m.history_start} ~ ${m.history_end} · 현재 상장 목록 기준일 ${m.universe_as_of}. 최초 수집 이전 신호는 과거 일봉에서 재구성했습니다. 이후 발견 기록은 저장됩니다. 미완료 구간과 종가 누락은 상승·하락 어느 쪽에도 포함하지 않습니다.`;
  $('dailyHistory').innerHTML=d.daily_history.slice(-20).reverse().map(r=>`<div class="history-item">${esc(r.market_date)}<b>${r.count}건</b></div>`).join('');
  ['csvTop','csvTrack','csvHistory'].forEach(id=>$(id).disabled=false);
}
function showDetail(key) {
  const [ticker,date]=key.split('|');
  selected=snapshot.tracking.find(r=>r.ticker===ticker&&r.signal_date===date);
  if(!selected)return;
  const r=selected, rows=snapshot.charts[ticker]||[];
  $('detailCode').textContent=`${r.market} · ${r.ticker} · ${r.price_date} 기준`;
  $('detailName').textContent=r.name;
  $('detailStats').innerHTML=`<div>기준일 종가<b>${fmt(r.last_close,0)}원</b></div><div>발견일 거래량<b>${fmt(r.volume_ratio)}배</b></div><div>발견 이후<b class="${color(r.since_signal_pct)}">${pct(r.since_signal_pct)}</b></div>`;
  $('sourceLink').href=`https://finance.naver.com/item/main.naver?code=${encodeURIComponent(ticker)}`;
  $('chartData').innerHTML=rows.slice().reverse().map(p=>`<tr><td>${esc(p.date)}</td><td>${fmt(p.close,0)}</td><td>${fmt(p.volume,0)}</td></tr>`).join('');
  $('detail').showModal();
  drawChart(rows,date);
}
function drawChart(rows,signalDate) {
  const valid=rows.filter(p=>p.close>0&&p.volume!=null);
  if(valid.length<2){$('chart').innerHTML='<div class="empty">표시할 차트 이력이 부족합니다.</div>';return;}
  const w=Math.max(310,Math.min(660,$('detail').clientWidth-40)), left=60,right=16,top=35,priceH=155,volTop=242,volH=65;
  const barWidth=Math.max(1,(w-left-right)/rows.length*.75);
  const lo=Math.min(...valid.map(p=>p.close))*.98,hi=Math.max(...valid.map(p=>p.close))*1.02,maxVol=Math.max(...valid.map(p=>p.volume),1);
  const x=i=>left+i*(w-left-right)/Math.max(1,rows.length-1), y=p=>top+(hi-p)/(hi-lo)*priceH;
  let path='',prev=false;
  rows.forEach((p,i)=>{if(p.close>0){path+=`${prev?'L':'M'}${x(i).toFixed(1)},${y(p.close).toFixed(1)} `;prev=true;}else{prev=false;}});
  const grid=[0,.5,1].map(f=>{const price=lo+f*(hi-lo);return `<line x1="${left}" y1="${y(price)}" x2="${w-right}" y2="${y(price)}" stroke="#e8edf3"/><text x="${left-8}" y="${y(price)+4}" text-anchor="end" fill="#8290a2" font-size="10">${fmt(price,0)}</text>`}).join('');
  const bars=rows.map((p,i)=>p.volume==null?'':`<rect x="${x(i)-barWidth/2}" y="${volTop+volH-p.volume/maxVol*volH}" width="${barWidth}" height="${p.volume/maxVol*volH}" fill="${p.date===signalDate?'#187c67':'#c8d9e4'}" rx="1"/>`).join('');
  const si=rows.findIndex(p=>p.date===signalDate), marker=si>=0&&rows[si].close>0?`<line x1="${x(si)}" y1="${top}" x2="${x(si)}" y2="${volTop+volH}" stroke="#8dbba9" stroke-dasharray="4 4"/><circle cx="${x(si)}" cy="${y(rows[si].close)}" r="5" fill="#187c67" stroke="white" stroke-width="2"/>`:'';
  $('chart').innerHTML=`<svg viewBox="0 0 ${w} 343" role="img" aria-label="${esc(selected.name)}의 ${rows[0].date}부터 ${rows.at(-1).date}까지 종가 선과 거래량 막대 차트. 아래 데이터 표에서도 확인할 수 있습니다."><text x="${left}" y="15" font-size="11" fill="#607087">종가 (원)</text>${grid}${marker}<path d="${path}" fill="none" stroke="#348879" stroke-width="2.2" stroke-linejoin="round"/><text x="${left}" y="228" font-size="11" fill="#607087">거래량 (주) · 최대 ${fmt(maxVol,0)}</text>${bars}<text x="${left}" y="335" fill="#8290a2" font-size="10">${rows[0].date}</text><text x="${w-right}" y="335" text-anchor="end" fill="#8290a2" font-size="10">${rows.at(-1).date}</text></svg>`;
}
function csvCell(value) {
  let text=String(value??'');
  if(/^[=+@\-\t\r]/.test(text)&&typeof value!=='number')text="'"+text;
  return '"'+text.replace(/"/g,'""')+'"';
}
function downloadCsv(rows,columns,name) {
  const lines=[columns.map(c=>c[1]),...rows.map(r=>columns.map(c=>c[0]==='ticker'?`'${r.ticker}`:r[c[0]]))];
  const blob=new Blob(['\ufeff'+lines.map(row=>row.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`volume-radar-${name}-${snapshot.meta.market_date}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const columns=[['ticker','종목코드'],['name','종목명'],['market','시장'],['signal_date','발견일'],['price_date','현재가격 기준일'],['volume_ratio','직전20일대비 거래량 배수'],['signal_change_pct','발견일 등락률(%)'],['signal_close','발견일 종가'],['last_close','기준일 종가'],['since_signal_pct','발견 이후 변화(%)'],['score','관찰 점수(최대75)'],['status','상태'],['5','5거래일 변화(%)_비용미반영'],['10','10거래일 변화(%)_비용미반영'],['20','20거래일 변화(%)_비용미반영'],['origin','신호기록 방식']];
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));});document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==button.dataset.tab);}));
document.querySelectorAll('[data-market]').forEach(button=>button.addEventListener('click',()=>{market=button.dataset.market;document.querySelectorAll('[data-market]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});if(snapshot)chooseTop();}));
$('search').addEventListener('input',()=>{if(snapshot)chooseTop();});
['top','tracking'].forEach(id=>$(id).addEventListener('click',e=>{const button=e.target.closest('[data-key]');if(button)showDetail(button.dataset.key);}));
$('closeDetail').addEventListener('click',()=>$('detail').close());
$('csvTop').addEventListener('click',()=>downloadCsv(displayed,columns,'top10'));
$('csvTrack').addEventListener('click',()=>downloadCsv(snapshot.tracking,columns,'tracking'));
$('csvHistory').addEventListener('click',()=>downloadCsv(snapshot.signals,columns,'signals'));
$('csvChart').addEventListener('click',()=>downloadCsv(snapshot.charts[selected.ticker]||[],[['date','거래일'],['close','종가'],['volume','거래량'],['baseline','직전20거래일 평균거래량']],selected.ticker));
async function start() {
  if(location.protocol==='file:') {
    $('updated').textContent='로컬 서버로 열어 주세요';$('date').textContent='파일을 직접 열면 데이터 요청이 제한됩니다.';
    notice('프로젝트 폴더의 start.command를 실행한 뒤 http://localhost:8000으로 접속하세요.\n또는 터미널: python3 -m http.server 8000 --directory web',true);
    $('top').textContent='웹 주소로 접속하면 저장된 실제 시세를 표시합니다.';return;
  }
  try {
    const request=await fetch(new URL('./data/latest.json',location.href),{cache:'no-store',signal:AbortSignal.timeout(15000)});
    if(!request.ok)throw Error(`시세 파일 HTTP ${request.status}`);
    const data=await request.json();
    if(!data.meta?.verified){$('updated').textContent='실제 시세 수집 대기';$('date').textContent='아직 정상 수집된 데이터가 없습니다.';notice('실제 시세 수집이 완료되면 종목이 표시됩니다. 프로젝트에서 .venv/bin/python -m pipeline.build를 실행해 주세요.');}
    else {
      if(data.meta.schema_version!==2 || !Array.isArray(data.tracking) || !Array.isArray(data.signals) || !data.backtest || !data.charts || !Array.isArray(data.meta.errors))throw Error('시세 파일 형식이 올바르지 않습니다. 수집기를 다시 실행해 주세요.');
      snapshot=data;render();
      const messages=[];
      if(Date.now()>Date.parse(data.meta.next_update_due))messages.push(`${data.meta.market_date}에 저장된 시세입니다. 다음 갱신 시각이 지나 최신 여부를 확인해야 합니다.`);
      if(data.meta.errors.length)messages.push(`시세 ${data.meta.errors.length}종목${data.meta.errors.length<=5?' ('+data.meta.errors.map(e=>e.ticker).join(', ')+')':''}을 확인하지 못했습니다. 표시 순위와 통계는 조회 성공 범위 기준입니다.`);
      if(data.meta.price_revision_count)messages.push(`저장 당시와 가격 기준이 달라진 ${data.meta.price_revision_count}개 신호의 신규 성과 계산을 보류했습니다.`);
      if(messages.length)notice(messages.join('\n'));
    }
    try {
      const r=await fetch(new URL('./data/status.json',location.href),{cache:'no-store',signal:AbortSignal.timeout(8000)});
      if(!r.ok)throw Error('상태 파일 없음'); const status=await r.json();
      if(status.state==='error' && (!snapshot||Date.parse(status.attempted_at)>=Date.parse(snapshot.meta.generated_at)))notice(`최근 시세 갱신에 실패했습니다. ${snapshot?`${snapshot.meta.market_date}의 이전 정상 시세를 표시합니다.`:'정상 시세가 아직 없습니다.'}\n${status.message}`,true);
    }catch{notice(($('notice').hidden?'':$('notice').textContent+'\n')+'수집 상태를 확인할 수 없습니다. 화면의 기준 거래일을 확인해 주세요.');}
  }catch(error){$('updated').textContent='데이터 연결 실패';$('date').textContent='시세를 표시할 수 없습니다.';$('top').textContent='저장된 시세 파일을 불러오지 못했습니다.';notice(`${error.message}\n로컬 서버 실행 여부와 web/data/latest.json 파일을 확인한 뒤 새로고침하세요.`,true);}
}
start();
