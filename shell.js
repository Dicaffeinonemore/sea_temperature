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
      <label>담당 지역 <select id="office" aria-label="담당 지역"></select></label>
      <span id="updated"></span>
      <button class="ghost" id="reset" type="button" hidden>시연 처음으로</button>
      <div class="bell-wrap" id="cal-wrap">
        <button type="button" class="bell" id="cal-btn" aria-label="상담 일정" aria-expanded="false" aria-controls="cal-panel" title="상담 일정">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4.5" width="18" height="17" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>
          <span class="bell-n cal-n" id="cal-n" hidden></span>
        </button>
        <div class="bell-panel cal-panel" id="cal-panel" role="dialog" aria-label="상담 일정" hidden>
          <div class="cal-h">
            <b id="cal-title"></b>
            <div class="cal-nav">
              <button type="button" data-cal-move="-1" aria-label="이전 달">‹</button>
              <button type="button" data-cal-move="0">오늘</button>
              <button type="button" data-cal-move="1" aria-label="다음 달">›</button>
            </div>
          </div>
          <div class="cal-sub"><span id="cal-scope"></span><button type="button" class="cal-all" id="cal-all" aria-pressed="false">전체 지역</button></div>
          <div class="cal-week" aria-hidden="true"><span class="sun">일</span><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span><span class="sat">토</span></div>
          <div class="cal-grid" id="cal-grid"></div>
          <div class="cal-day" id="cal-day" aria-live="polite"></div>
        </div>
      </div>
      <div class="bell-wrap" id="bell-wrap">
        <button type="button" class="bell" id="bell" aria-label="알림" aria-expanded="false" aria-controls="bell-panel">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>
          <span class="bell-n" id="bell-n" hidden></span>
        </button>
        <div class="bell-panel" id="bell-panel" hidden>
          <div class="bell-h"><span>알림</span><button type="button" class="linkish" id="bell-read" disabled>모두 읽음</button></div>
          <ul class="bell-list" id="bell-list"><li class="empty">불러오는 중이에요…</li></ul>
        </div>
      </div>
      <button type="button" class="bell magnifier-toggle" id="magnifier-toggle" aria-label="돋보기 켜기" aria-pressed="false" title="돋보기 켜기">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg>
      </button>
    </div>
  </div>
</header>`);

  /* ===== 돋보기: 복제 화면은 별도 DOM에 격리해 원본 ID와 클릭 동작을 보존해요 ===== */
  const magnifierButton = document.getElementById('magnifier-toggle');
  const lens = document.createElement('div');
  lens.className = 'magnifier-lens';
  lens.hidden = true;
  lens.inert = true;
  lens.setAttribute('aria-hidden', 'true');
  document.body.append(lens);
  const caption = document.createElement('div');
  caption.className = 'magnifier-caption';
  caption.hidden = true;
  caption.inert = true;
  caption.setAttribute('aria-hidden', 'true');
  document.body.append(caption);
  const glass = lens.attachShadow({mode:'closed'});
  const viewport = document.createElement('div');
  viewport.style.cssText = 'position:absolute;overflow:hidden;transform-origin:0 0;pointer-events:none;';
  let zoom = 1.8, diameter = 240;
  let magnifying = false, dirty = true, frame = 0, pointer = null, copies = [];

  function rebuildMagnifier(){
    const styles = [...document.head.querySelectorAll('style, link[rel="stylesheet"]')].map(node => node.cloneNode(true));
    const body = document.body.cloneNode(true);
    const excluded = 'script, iframe, object, embed, .magnifier-lens, .magnifier-caption';
    body.querySelectorAll(excluded).forEach(node => node.remove());
    [body, ...body.querySelectorAll('*')].forEach(node => {
      for(const attr of [...node.attributes]){
        if(attr.name.startsWith('on') || attr.name === 'autofocus') node.removeAttribute(attr.name);
      }
    });
    const originals = [document.body, ...document.body.querySelectorAll('*')].filter(node => !node.closest(excluded));
    const clones = [body, ...body.querySelectorAll('*')];
    copies = originals.map((source, index) => [source, clones[index]]);
    viewport.replaceChildren(body);
    glass.replaceChildren(...styles, viewport);
    dirty = false;
  }

  function drawMagnifier(){
    frame = 0;
    if(!magnifying || !pointer) return;
    if(dirty) rebuildMagnifier();
    const text = `${zoom.toFixed(1)}배 · 지름 ${diameter}px\nQ / E 배율 · A / D 지름`;
    if(caption.textContent !== text) caption.textContent = text;
    caption.hidden = false;
    const size = Math.min(diameter, window.innerWidth - 8, Math.max(1, window.innerHeight - caption.offsetHeight - 16));
    const left = Math.max(0, Math.min(pointer.x - size / 2, window.innerWidth - size));
    const top = Math.max(4, Math.min(pointer.y - size / 2, window.innerHeight - size - caption.offsetHeight - 12));
    lens.style.cssText = `width:${size}px;height:${size}px;left:${left}px;top:${top}px;`;
    caption.style.left = `${Math.max(8, Math.min(left + size / 2 - caption.offsetWidth / 2, window.innerWidth - caption.offsetWidth - 8))}px`;
    caption.style.top = `${top + size + 8}px`;
    viewport.style.width = `${document.documentElement.clientWidth}px`;
    viewport.style.height = `${window.innerHeight}px`;
    viewport.style.transform = `translate(${pointer.x - left - pointer.x * zoom}px,${pointer.y - top - pointer.y * zoom}px) scale(${zoom})`;
    viewport.scrollTo(window.scrollX, window.scrollY);
    for(const [source, copy] of copies){
      if(!copy) continue;
      // 폼의 현재 값과 캔버스 픽셀은 cloneNode로 복사되지 않아요.
      if(source.tagName === 'CANVAS'){
        const context = copy.getContext('2d');
        if(context){ context.clearRect(0, 0, copy.width, copy.height); context.drawImage(source, 0, 0); }
      } else if(source.tagName === 'SELECT') copy.selectedIndex = source.selectedIndex;
      else if(source.tagName === 'INPUT' || source.tagName === 'TEXTAREA'){
        copy.value = source.value; copy.checked = source.checked;
      }
      if(copy.scrollTop !== source.scrollTop) copy.scrollTop = source.scrollTop;
      if(copy.scrollLeft !== source.scrollLeft) copy.scrollLeft = source.scrollLeft;
    }
    lens.hidden = false;
  }

  function requestMagnifier(){
    if(magnifying && !frame) frame = requestAnimationFrame(drawMagnifier);
  }

  function setMagnifier(active){
    magnifying = active;
    magnifierButton.setAttribute('aria-pressed', String(active));
    const label = active ? '돋보기 끄기 (Esc)' : '돋보기 켜기';
    magnifierButton.setAttribute('aria-label', label);
    magnifierButton.title = label;
    if(active){ dirty = true; requestMagnifier(); }
    else {
      cancelAnimationFrame(frame); frame = 0;
      lens.hidden = true;
      caption.hidden = true;
      viewport.replaceChildren(); copies = [];
    }
  }
  magnifierButton.addEventListener('click', () => setMagnifier(!magnifying));
  document.addEventListener('pointermove', event => {
    if(event.pointerType === 'touch') return;
    pointer = {x:event.clientX, y:event.clientY};
    requestMagnifier();
  });
  document.addEventListener('pointerleave', () => { pointer = null; lens.hidden = true; caption.hidden = true; });
  window.addEventListener('blur', () => { pointer = null; lens.hidden = true; caption.hidden = true; });
  document.addEventListener('keydown', event => {
    if(!magnifying) return;
    if(event.key === 'Escape'){ setMagnifier(false); return; }
    if(event.defaultPrevented || event.isComposing || event.ctrlKey || event.altKey || event.metaKey) return;
    if(event.target.isContentEditable || event.target.closest?.('input, textarea, select, [role="textbox"]')) return;
    switch(event.code){
      case 'KeyQ': zoom = Math.max(1, Math.round((zoom - 0.2) * 10) / 10); break;
      case 'KeyE': zoom = Math.min(4, Math.round((zoom + 0.2) * 10) / 10); break;
      case 'KeyA': diameter = Math.max(120, diameter - 20); break;
      case 'KeyD': diameter = Math.min(480, diameter + 20); break;
      default: return;
    }
    event.preventDefault();
    requestMagnifier();
  });
  document.addEventListener('scroll', requestMagnifier, true);
  document.addEventListener('input', requestMagnifier);
  document.addEventListener('change', requestMagnifier);
  window.addEventListener('resize', () => { dirty = true; requestMagnifier(); });
  new MutationObserver(records => {
    if(!magnifying || records.every(record => record.target === lens || record.target === caption || caption.contains(record.target))) return;
    dirty = true;
    requestMagnifier();
  }).observe(document.body, {childList:true, subtree:true, characterData:true, attributes:true});

  /* ===== 담당 지역 선택: 선택지는 지역 이름만 ('사천 지역 담당' → '사천') =====
     선택지는 각 화면이 채우므로, 채워질 때마다 여기서 글자만 정리해요 (값은 그대로라 화면 동작은 같아요). */
  const officeSel = document.getElementById('office');
  const tidyOffice = () => {
    for(const o of officeSel.options){
      const t = o.textContent.replace(/\s*지역\s*담당\s*$/, '').trim();
      if(t && t !== o.textContent) o.textContent = t;
    }
  };
  new MutationObserver(tidyOffice).observe(officeSel, {childList:true, subtree:true, characterData:true});

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
    if(typeof resetCal === 'function') resetCal();   // 상담 저장·삭제 뒤 일정도 새로 받아요
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
    closeCal();
    $('bell-panel').hidden = !$('bell-panel').hidden;
    $('bell').setAttribute('aria-expanded', String(!$('bell-panel').hidden));
  });
  document.addEventListener('click', e => { if(!$('bell-panel').hidden && !e.composedPath().includes($('bell-wrap'))) closePanel(); });
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

  /* ===== 상담 일정 캘린더 =====
     GET /api/dashboard/schedule?month=YYYY-MM  →  [{household_id, date, time, status, region, label, memo, staff_name}]
     consult_cases.next_contact_at(다음 연락·상담일)을 달력에 보여 줘요. 기본은 '담당 지역'만, '전체 지역'으로 모두.
     일정을 누르면 고객 상담 현황에서 그 고객이 선택돼요 (알림과 같은 동작). */
  const pad2 = v => String(v).padStart(2, '0');
  const WEEK = ['일','월','화','수','목','금','토'];
  const dstr = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const STATUS_CLS = {'상담 예약':'book', '부재·재연락':'again'};
  let calCache = {}, calY, calM, calSel, calAll = false;

  // 서버에 닿지 못할 때(가상 데이터 시연) 보여 주는 예시 일정: 오늘 기준 앞뒤 며칠
  function sampleSchedule(y, m){
    const base = new Date(); base.setHours(0, 0, 0, 0);
    const seed = [[0,'10:00','상담 예약','통영','김○○','A-012','견적 요청 · 방문 상담'], [0,'14:30','부재·재연락','통영','류○○','A-082','부재 2회 · 오후에 다시'],
                  [2,'11:00','상담 예약','통영','배○○','A-060','조피볼락 특약 상담'], [3,'09:30','부재·재연락','거제','이○○','B-007','부재'],
                  [6,'15:00','상담 예약','고성','최○○','C-019','굴 판매 시작 후 상담'], [-2,'16:00','상담 예약','통영','박○○','A-031','창구 방문']];
    return seed.map(([off, time, status, region, name, id, memo]) => {
      const d = new Date(base); d.setDate(d.getDate() + off);
      return {household_id:id, date:dstr(d), time, status, region, owner_name:name, label:`${region} - ${name}`, memo, staff_name:null};
    }).filter(it => it.date.startsWith(`${y}-${pad2(m + 1)}`));
  }

  async function loadMonth(y, m){
    const key = `${y}-${pad2(m + 1)}`;
    if(calCache[key]) return calCache[key];
    const entry = calCache[key] = {items:null, err:null};
    try{
      const r = await fetch(`${API_BASE}/api/dashboard/schedule?month=${key}`);
      if(r.ok) entry.items = await r.json();
      else{ entry.items = []; entry.err = r.status === 404 ? '일정 API가 아직 서버에 없어요 (dashboard.py 배포 확인)' : `일정을 불러오지 못했어요 (HTTP ${r.status})`; }
    }catch(e){
      entry.items = sampleSchedule(y, m);   // 서버에 닿지 못함 = 가상 데이터 시연
    }
    return entry;
  }
  const officeNow = () => $('office').value;
  const inScope = it => calAll || !officeNow() || it.region === officeNow();

  function updateCalBadge(){
    const t = new Date(), entry = calCache[`${t.getFullYear()}-${pad2(t.getMonth() + 1)}`];
    const n = entry && entry.items ? entry.items.filter(it => it.date === dstr(t) && inScope(it)).length : 0;
    $('cal-n').textContent = n; $('cal-n').hidden = !n;
    $('cal-btn').setAttribute('aria-label', n ? `상담 일정 · 오늘 ${n}건` : '상담 일정');
  }

  function renderCal(){
    const entry = calCache[`${calY}-${pad2(calM + 1)}`];
    const items = entry && entry.items ? entry.items.filter(inScope) : [];
    const byDay = {};
    items.forEach(it => (byDay[it.date] = byDay[it.date] || []).push(it));
    const today = dstr(new Date());

    $('cal-title').textContent = `${calY}년 ${calM + 1}월`;
    $('cal-scope').textContent = calAll || !officeNow() ? `전체 지역 · ${items.length}건` : `${officeNow()} 지역 · ${items.length}건`;
    $('cal-all').setAttribute('aria-pressed', String(calAll));

    const first = new Date(calY, calM, 1).getDay(), last = new Date(calY, calM + 1, 0).getDate();
    let html = '';
    for(let i = 0; i < first; i++) html += '<span class="cal-blank"></span>';
    for(let d = 1; d <= last; d++){
      const ds = `${calY}-${pad2(calM + 1)}-${pad2(d)}`, list = byDay[ds] || [], wd = (first + d - 1) % 7;
      const cls = ['cal-d', wd === 0 ? 'sun' : wd === 6 ? 'sat' : '', ds === today ? 'today' : '', ds === calSel ? 'sel' : '', ds < today ? 'past' : ''].filter(Boolean).join(' ');
      const dots = list.slice(0, 3).map(it => `<i class="${STATUS_CLS[it.status] || 'etc'}"></i>`).join('') + (list.length > 3 ? '<em>+</em>' : '');
      html += `<button type="button" class="${cls}" data-cal-day="${ds}" aria-label="${calM + 1}월 ${d}일${list.length ? ` 일정 ${list.length}건` : ''}"${ds === calSel ? ' aria-pressed="true"' : ''}>`
            + `<span>${d}</span><span class="cal-dots">${dots}</span></button>`;
    }
    $('cal-grid').innerHTML = html;

    const sd = new Date(calSel + 'T00:00:00'), list = byDay[calSel] || [];
    const head = `<div class="cal-day-h">${sd.getMonth() + 1}월 ${sd.getDate()}일 (${WEEK[sd.getDay()]})${calSel === today ? ' · 오늘' : ''}<span>${list.length ? list.length + '건' : ''}</span></div>`;
    let body;
    if(!entry || !entry.items) body = '<p class="cal-empty">불러오는 중이에요…</p>';
    else if(entry.err) body = `<p class="cal-empty err">${esc(entry.err)}</p>`;
    else if(!list.length) body = '<p class="cal-empty">이 날은 일정이 없어요</p>';
    else body = '<ul class="cal-list">' + list.map(it => `<li><button type="button" class="cal-ev${calSel < today ? ' past' : ''}" data-cal-cust="${esc(it.household_id)}" data-cal-region="${esc(it.region || '')}">
        <b class="tm">${esc(it.time)}</b>
        <span class="who">${esc(it.label)}</span>
        <span class="cal-st ${STATUS_CLS[it.status] || 'etc'}">${esc(it.status)}</span>
        ${it.memo || it.staff_name ? `<small>${esc([it.memo, it.staff_name && '상담자 ' + it.staff_name].filter(Boolean).join(' · '))}</small>` : ''}
      </button></li>`).join('') + '</ul>';
    $('cal-day').innerHTML = head + body;
    updateCalBadge();
  }

  async function showMonth(y, m, sel){
    calY = y; calM = m;
    const today = new Date();
    calSel = sel || (y === today.getFullYear() && m === today.getMonth() ? dstr(today) : `${y}-${pad2(m + 1)}-01`);
    renderCal();                     // 먼저 칸부터 (불러오는 중)
    await loadMonth(y, m);
    if(calY === y && calM === m) renderCal();
  }
  function closeCal(){ $('cal-panel').hidden = true; $('cal-btn').setAttribute('aria-expanded', 'false'); }
  function openCal(){
    closePanel();
    $('cal-panel').hidden = false; $('cal-btn').setAttribute('aria-expanded', 'true');
    const t = new Date();
    showMonth(calY ?? t.getFullYear(), calM ?? t.getMonth(), calSel);
  }
  function resetCal(){
    calCache = {};
    const t = new Date();
    loadMonth(t.getFullYear(), t.getMonth()).then(() => { if(!$('cal-panel').hidden && calY != null) showMonth(calY, calM, calSel); else updateCalBadge(); });
  }

  $('cal-btn').addEventListener('click', e => { e.stopPropagation(); $('cal-panel').hidden ? openCal() : closeCal(); });
  // 바깥 클릭 판단은 클릭 순간의 경로로 해요 (날짜를 누르면 달력을 다시 그려 누른 버튼이 사라지므로 e.target.closest 로는 '바깥'으로 잘못 판단)
  const clickedInside = (e, id) => e.composedPath().includes($(id));
  document.addEventListener('click', e => { if(!$('cal-panel').hidden && !clickedInside(e, 'cal-wrap')) closeCal(); });
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && !$('cal-panel').hidden){ closeCal(); $('cal-btn').focus(); } });
  $('cal-panel').addEventListener('click', e => {
    const mv = e.target.closest('[data-cal-move]');
    if(mv){
      const k = +mv.dataset.calMove, t = new Date();
      if(k === 0) showMonth(t.getFullYear(), t.getMonth(), dstr(t));
      else{ const d = new Date(calY, calM + k, 1); showMonth(d.getFullYear(), d.getMonth()); }
      return;
    }
    if(e.target.closest('#cal-all')){ calAll = !calAll; renderCal(); return; }
    const day = e.target.closest('[data-cal-day]');
    if(day){ calSel = day.dataset.calDay; renderCal(); $('cal-grid').querySelector(`[data-cal-day="${calSel}"]`)?.focus(); return; }
    const ev = e.target.closest('[data-cal-cust]');
    if(ev){
      closeCal();
      // 알림과 같은 길: 고객 상담 현황에서 그 고객 선택 (그 화면에 있으면 새로고침 없이)
      const n = {farm:ev.dataset.calCust, from:'calendar'};
      if(!document.dispatchEvent(new CustomEvent('shell:noti', {detail:n, cancelable:true}))) return;
      location.href = 'consult_status.html?cust=' + encodeURIComponent(n.farm);
    }
  });
  // 담당 지역이 바뀌면 오늘 건수·달력도 그 지역으로
  $('office').addEventListener('change', () => { if(!$('cal-panel').hidden) renderCal(); else updateCalBadge(); });
  new MutationObserver(updateCalBadge).observe($('office'), {childList:true});

  window.Shell = {
    reloadNoti: loadNoti,
    push(n){
      const d = new Date(), p = v => String(v).padStart(2, '0');
      noti.unshift({id:'local-' + (++localSeq), local:true, read:false,
                    at:`${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`, ...n});
      renderBell();
    },
  };
  loadNoti();   // 안에서 resetCal() 로 이번 달 일정도 받아요 (오늘 건수 배지)
})();
