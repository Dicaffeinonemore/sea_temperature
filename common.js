/* =====================================================================
   우리 바다 안심도우미 — 모든 화면이 함께 쓰는 하단 바
   사용법 (각 페이지 맨 아래):
     <nav id="tabbar" data-active="insurance"></nav>
     <script src="common.js"></script>
   data-active: home | temp | response | insurance | me  (지금 페이지의 탭)
   탭 이름·링크·아이콘을 바꿀 때는 아래 TABS만 고치세요. 모든 페이지에 반영됩니다.
   href가 null인 탭은 아직 화면이 없어서 누르면 "준비 중" 안내만 보여 줍니다.
   ===================================================================== */
(function(){
  const TABS=[
    {id:'home',      label:'홈',      href:'home.html',
     icon:'<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/><path d="M10 20v-5h4v5"/>'},
    {id:'temp',      label:'수온',    href:null,
     icon:'<path d="M3 9c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/><path d="M3 15c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>'},
    {id:'response',  label:'대응 요령', href:null,
     icon:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8.5 12 2.5 2.5 4.5-5"/>'},
    {id:'insurance', label:'보험',    href:null,
     icon:'<path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6l-8-3Z"/>'},
    {id:'me',        label:'내 정보', href:null,
     icon:'<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>'},
  ];

  const nav=document.getElementById('tabbar');
  if(!nav)return;
  const active=nav.dataset.active;
  nav.classList.add('tabbar');
  nav.setAttribute('aria-label','하단 메뉴');
  nav.innerHTML=TABS.map(t=>{
    const on=t.id===active, soon=!t.href;
    const attrs=on?' aria-current="page"':soon?' aria-disabled="true" data-soon=""':'';
    return `<a class="tabbar-item${on?' active':''}" href="${on||soon?'#':t.href}"${attrs}>`+
      `<svg viewBox="0 0 24 24" aria-hidden="true">${t.icon}</svg><span>${t.label}</span></a>`;
  }).join('');

  let timer;
  nav.addEventListener('click',e=>{
    const a=e.target.closest('a');
    if(!a)return;
    if(a.hasAttribute('aria-current')){e.preventDefault();return;}
    if(!a.hasAttribute('data-soon'))return;
    e.preventDefault();
    let toast=document.querySelector('.tabbar-toast');
    if(!toast){toast=document.createElement('div');toast.className='tabbar-toast';toast.setAttribute('role','status');document.body.append(toast);}
    toast.textContent=`${a.textContent.trim()} 화면은 준비 중이에요`;
    toast.hidden=false;
    clearTimeout(timer);timer=setTimeout(()=>{toast.hidden=true;},1800);
  });
})();
