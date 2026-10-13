const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const test=require('node:test');
function app(){
 const elements=new Map(),events={},windowEvents={},timers=[];
 const node=id=>{if(!elements.has(id))elements.set(id,{value:id==='scope'?'default':'',textContent:'',innerHTML:'',hidden:true,dataset:{},addEventListener(type,fn){events[id+':'+type]=fn;}});return elements.get(id);};
 const document={getElementById:node,querySelectorAll:()=>[],querySelector:s=>node(s),visibilityState:'visible',addEventListener(type,fn){events[type]=fn;}};
 const context=vm.createContext({document,window:{addEventListener(type,fn){windowEvents[type]=fn;}},setInterval:fn=>timers.push(fn),setTimeout,URL,Intl,Date,Map,Array,String,Number,Math,AbortSignal});
 vm.runInContext(fs.readFileSync('web/app.js','utf8').replace(/start\(\);\s*$/,''),context);
 return {context,node,events,windowEvents,timers,run:s=>vm.runInContext(s,context)};
}
function record(type='ordinary',pass=true){return {ticker:'0041L0',name:'단위검사 전용',market:'KOSDAQ',days:0,last_close:100,score:60,signal_date:'2026-10-12',stock_type:type,default_eligible:pass,type_label:'검사용',liquidity_pass:pass};}
function snapshot(rows){return {meta:{errors:[],next_update_due:'2026-10-13T18:00:00+09:00',market_date:'2026-10-12',generated_at:'2026-10-13T10:00:00+09:00',automatic_refresh_enabled:false,classification_status:{state:'ok'}},tracking:rows};}
test('default list never includes excluded, special, or absent eligibility records',()=>{
 const a=app(),rows=[record('ordinary',true),{...record('spac',false),ticker:'111111'},{...record('preferred',false),ticker:'222222'},{...record('unknown',false),ticker:'333333'}];
 a.run('snapshot='+JSON.stringify(snapshot(rows)));a.run('chooseTop()');assert.equal(a.run('displayed.length'),1);
 a.node('scope').value='spac';a.run('chooseTop()');assert.equal(a.run('displayed[0].stock_type'),'spac');
 a.node('scope').value='preferred';a.run('chooseTop()');assert.equal(a.run('displayed[0].stock_type'),'preferred');
 a.node('scope').value='other';a.run('chooseTop()');assert.equal(a.run('displayed[0].stock_type'),'unknown');
 a.node('scope').value='legacy';a.run('chooseTop()');assert.equal(a.run('displayed.length'),4);
});
test('code search remains case-insensitive; empty list is not padded',()=>{
 const a=app();a.run('snapshot='+JSON.stringify(snapshot([record()])));
 for(const query of ['0041L0','0041l0']){a.node('search').value=query;a.run('chooseTop()');assert.equal(a.run('displayed.length'),1);}
 a.node('search').value='NO_MATCH';a.run('chooseTop()');assert.equal(a.run('displayed.length'),0);assert.match(a.node('top').innerHTML,/임의로 채우지/);
});
test('open page expires at the deadline, removes fresh state, keeps auto refresh off',()=>{
 const a=app();a.run('snapshot='+JSON.stringify(snapshot([])));
 const deadline=Date.parse('2026-10-13T18:00:00+09:00');
 a.run(`updateFreshness(${deadline-1})`);assert.equal(a.node('.date-box').dataset.freshness,'fresh');
 a.run(`updateFreshness(${deadline})`);assert.equal(a.node('.date-box').dataset.freshness,'stale');assert.match(a.node('notice').textContent,/갱신이 필요/);assert.match(a.node('date').textContent,/자동 갱신 꺼짐/);
 assert.equal(a.timers.length,1);assert.equal(typeof a.events.visibilitychange,'function');assert.equal(typeof a.windowEvents.focus,'function');
 a.run("snapshot.meta.next_update_due='invalid';updateFreshness()");assert.equal(a.node('.date-box').dataset.freshness,'unknown');
});
test('periodic and focus checks update stale status without a reload',()=>{
 const a=app();a.run('snapshot='+JSON.stringify(snapshot([])));
 a.run("snapshot.meta.next_update_due='2999-01-01T00:00:00Z';updateFreshness()");
 assert.equal(a.node('.date-box').dataset.freshness,'fresh');
 a.run("snapshot.meta.next_update_due='2000-01-01T00:00:00Z'");a.timers[0]();
 assert.equal(a.node('.date-box').dataset.freshness,'stale');a.windowEvents.focus();a.events.visibilitychange();assert.equal(a.node('.date-box').dataset.freshness,'stale');
});
test('data failures and missing classification keep an explicit warning',()=>{
 const a=app();a.run('snapshot='+JSON.stringify(snapshot([])));
 a.run("snapshot.meta.classification_status.state='error';collectionStatus={state:'error',attempted_at:'2026-10-14T00:00:00Z',message:'검사 오류'};updateFreshness()");
 assert.match(a.node('notice').textContent,/유형 미확인/);assert.match(a.node('notice').textContent,/이전 정상 기록/);assert.match(a.node('notice').className,/error/);
});
test('UI explains the full signal population and treats change neutrally',()=>{
 const source=fs.readFileSync('web/app.js','utf8'),html=fs.readFileSync('web/index.html','utf8');
 assert.ok(!source.includes('가격 유지')&&!source.includes('가격 이탈'));
 assert.match(source,/관찰 후보 TOP 10의 투자성과가 아닙니다/);
 assert.match(html,/미래 상승 확률 아님/);assert.match(html,/DART 공시 검색/);
 const a=app();assert.equal(a.run("esc('<script>')"),'&lt;script&gt;');assert.equal(a.run("csvCell('=1+1')"),'"\'=1+1"');
});
