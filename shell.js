/* 공통 상단 바 · 왼쪽 메뉴 · 알림 (모든 화면 같은 모양, 여기 한 곳만 고치면 돼요)

   쓰는 법: 스크립트가 놓인 자리에 바로 그려져요. defer·async 를 붙이지 마세요
   (그 자리에서 실행돼야 아래쪽 화면 스크립트가 #office 등을 바로 찾을 수 있어요).
     <script src="shell.js" data-part="header"></script>
     <div class="shell">
       <script src="shell.js" data-part="nav" data-page="home|detail|forecast|status"></script>
       <main class="wrap"> ...

   화면이 쓸 수 있는 것 (window.Shell)
     Shell.reloadNoti()  알림을 서버에서 다시 받아요 (상담 저장·삭제 뒤 등)
     Shell.push(n)       이 화면에서만 알림을 하나 더해요 (가상 예시용)
   어가 알림을 누르면 기본으로 consult_status.html?cust=어가번호 로 가서 그 고객이 선택된 화면이 열려요.
   알림을 누르면 document 에 'shell:noti' 이벤트(취소 가능)가 나가요.
   화면이 e.preventDefault() 하면 기본 동작(고객 상담 현황으로 이동 · 담당 지역 바꾸기)을 하지 않아요. */
(() => {
  const me = document.currentScript, part = me && me.dataset.part;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  /* ===== 왼쪽 메뉴 ===== */
  if(part === 'nav'){
    const MENU = [
      ['home',     'consult_home.html',   '☎', '상담 홈'],
      ['detail',   'farm_detail.html',    '☰', '어가 상세'],
      ['forecast', 'sea_forecast.html',   '〰', '수온 예측'],
      ['status',   'consult_status.html', '☷', '고객 상담 현황'],
    ];
    const cur = me.dataset.page;
    me.insertAdjacentHTML('beforebegin', `<nav class="side" aria-label="화면 이동">${MENU.map(([k, href, ic, label]) =>
      `<a class="nav" href="${href}"${k === cur ? ' aria-current="page"' : ''}><span class="ic" aria-hidden="true">${ic}</span>${label}${
        k === 'home' ? '<span class="cnt" id="nav-left" hidden></span>' : ''}</a>`).join('')}</nav>`);
    return;
  }
  if(part !== 'header') return;

  /* ===== 상단 바 ===== */
  me.insertAdjacentHTML('beforebegin', `
<header class="top">
  <div class="top-in">
    <h1>고수온 선제 상담 대시보드</h1>
    <span class="demo" id="data-mode">불러오는 중</span>
    <div class="top-meta">
      <label>담당 <select id="office" aria-label="담당 지역"></select></label>
      <span id="updated"></span>
      <button class="ghost" id="reset" type="button" hidden>시연 처음으로</button>
      <div class="bell-wrap">
        <button type="button" class="bell" id="bell" aria-label="알림" aria-expanded="false" aria-controls="bell-panel">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>
          <span class="bell-n" id="bell-n" hidden></span>
        </button>
        <div class="bell-panel" id="bell-panel" hidden>
          <div class="bell-h"><span>알림</span><button type="button" class="linkish" id="bell-read" disabled>모두 읽음</button></div>
          <ul class="bell-list" id="bell-list"><li class="empty">불러오는 중이에요…</li></ul>
        </div>
      </div>
    </div>
  </div>
</header>`);

  /* ===== 알림 ===== */
  const API_BASE = location.protocol === 'file:' ? 'http://127.0.0.1:8000'
    : location.port === '8765' ? `${location.protocol}//${location.hostname}:8000` : location.origin;
  // 서버에 연결하지 못했을 때만 보여 주는 예시 (각 화면도 그때는 가상 데이터를 보여 줘요)
  const SAMPLE_NOTI = [
    {id:'s1', ty:'apply', lbl:'가입 신청', farm:'A-060', at:'10/22 05:52', text:'통영 - 배○○ · 문자 링크로 고수온 특약 가입 상담 신청', read:false},
    {id:'s2', ty:'reply', lbl:'문자 회신', farm:'B-007', at:'10/22 05:31', text:'거제 - 이○○ · 판매 마감 문자에 "전화 주세요" 회신', read:false},
    {id:'s3', ty:'apply', lbl:'상담 요청', farm:'E-008', at:'10/21 18:20', text:'창원 - 서○○ · 오만둥이 보험 문의, 전화 요청', read:false},
    {id:'s4', ty:'alert', lbl:'특보', farm:null, region:'고성', at:'10/21 10:00', text:'고성 고수온 예비특보 발령 (수과원 발표)', read:true},
    {id:'s5', ty:'join', lbl:'가입 완료', farm:'F-002', at:'08/14 15:10', text:'하동 - 오○○ · 해상가두리어류 재해보험 + 고수온 특약 가입', read:true},
  ];
  const $ = id => document.getElementById(id);
  let noti = [], loadErr = null, localSeq = 0;

  // 읽은 알림 번호를 이 브라우저에 기억해요 (화면을 옮기거나 새로고침해도 읽음 유지)
  const READ_KEY = 'heat-dashboard-noti-read';
  const readIds = new Set((() => { try{ return JSON.parse(localStorage.getItem(READ_KEY) || '[]').map(String); }catch(e){ return []; } })());
  function markRead(list){
    list.forEach(n => { n.read = true; readIds.add(String(n.id)); });
    try{ localStorage.setItem(READ_KEY, JSON.stringify([...readIds].slice(-500))); }catch(e){}   // 너무 쌓이지 않게 최근 500개
  }

  function renderBell(){
    const un = noti.filter(n => !n.read).length;
    $('bell-n').textContent = un; $('bell-n').hidden = !un;
    $('bell').setAttribute('aria-label', un ? `알림 ${un}개 안 읽음` : '알림 (모두 읽음)');
    const btn = $('bell-read');
    btn.disabled = !un;
    btn.title = un ? '알림을 모두 읽음으로 표시' : '모두 읽었어요';
    $('bell-list').innerHTML = noti.length
      ? noti.map(n => `<li class="${n.read ? 'read' : 'unread'}">
          <button type="button" data-noti="${esc(n.id)}"><span class="ty ${esc(n.ty)}">${esc(n.lbl)}</span><span>${esc(n.text)}</span><small>${esc(n.at)}${n.read ? '' : ' · 안 읽음'}</small></button></li>`).join('')
      : `<li class="empty">${loadErr ? `알림을 불러오지 못했어요 (${esc(loadErr)})` : '새 알림이 없어요'}</li>`;
  }

  async function loadNoti(){
    loadErr = null;
    let list;
    try{
      const r = await fetch(API_BASE + '/api/dashboard/notifications');
      if(!r.ok){ list = []; loadErr = `HTTP ${r.status}`; }
      else list = await r.json();
    }catch(e){
      list = structuredClone(SAMPLE_NOTI);   // 서버에 닿지 못함 = 가상 데이터 시연
    }
    const local = noti.filter(n => n.local);   // 이 화면에서 더한 알림은 유지
    noti = local.concat(list);
    noti.forEach(n => { n.read = !!n.read || readIds.has(String(n.id)); });
    renderBell();
  }

  function closePanel(){ $('bell-panel').hidden = true; $('bell').setAttribute('aria-expanded', 'false'); }

  $('bell').addEventListener('click', e => {
    e.stopPropagation();
    $('bell-panel').hidden = !$('bell-panel').hidden;
    $('bell').setAttribute('aria-expanded', String(!$('bell-panel').hidden));
  });
  document.addEventListener('click', e => { if(!$('bell-panel').hidden && !e.target.closest('.bell-wrap')) closePanel(); });
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && !$('bell-panel').hidden){ closePanel(); $('bell').focus(); } });
  $('bell-read').addEventListener('click', () => { markRead(noti.filter(n => !n.read)); renderBell(); });
  $('bell-list').addEventListener('click', e => {
    const b = e.target.closest('[data-noti]'); if(!b) return;
    const n = noti.find(x => String(x.id) === b.dataset.noti); if(!n) return;
    markRead([n]); renderBell(); closePanel();
    // 화면이 직접 처리하고 싶으면 이 이벤트에서 preventDefault()
    const ev = new CustomEvent('shell:noti', {detail:n, cancelable:true});
    if(!document.dispatchEvent(ev)) return;
    if(n.farm){ location.href = 'consult_status.html?cust=' + encodeURIComponent(n.farm); return; }   // 어가 알림 → 고객 상담 현황에서 그 고객 선택
    if(n.region){   // 특보 알림 → 담당 지역을 그 지역으로 (각 화면의 '담당' 변경 처리가 그대로 동작)
      const sel = $('office');
      if([...sel.options].some(o => o.value === n.region)){ sel.value = n.region; sel.dispatchEvent(new Event('change', {bubbles:true})); }
    }
  });

  window.Shell = {
    reloadNoti: loadNoti,
    push(n){
      const d = new Date(), p = v => String(v).padStart(2, '0');
      noti.unshift({id:'local-' + (++localSeq), local:true, read:false,
                    at:`${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`, ...n});
      renderBell();
    },
  };
  loadNoti();
})();
