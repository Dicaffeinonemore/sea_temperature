/* 시연 경로에서만 실행해 원본 화면과 실제 기록을 분리해요. */
(() => {
  const KEY = 'heat-dashboard-demo-temperature-v1';
  let storageMessage = '';
  function readState(){
    try{
      const raw = localStorage.getItem(KEY);
      if(raw === null) return {enabled:false, offset:5};
      const value = JSON.parse(raw);
      if(value && typeof value.enabled === 'boolean' && Number.isFinite(value.offset)
          && value.offset >= 0 && value.offset <= 15 && Number.isInteger(value.offset * 2)) return value;
      storageMessage = '저장된 시연 설정이 올바르지 않아 기본값으로 시작했어요.';
    }catch(error){
      if(!(error instanceof SyntaxError) && error.name !== 'SecurityError') throw error;
      storageMessage = '시연 설정을 읽지 못했어요. 브라우저의 사이트 저장 허용을 확인해 주세요.';
    }
    return {enabled:false, offset:5};
  }
  const state = readState();
  const offset = () => state.enabled ? state.offset : 0;
  window.DemoSimulation = {
    adjustRegions(data){
      if(!state.enabled) return data;
      return {...data, regions:data.regions.map(region => ({...region,
        series:region.series.map(point => ({...point,
          max:Math.round((point.max + state.offset) * 10) / 10,
          mean:Math.round((point.mean + state.offset) * 10) / 10,
          min:Math.round((point.min + state.offset) * 10) / 10,
        })),
      }))};
    },
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    const request = input instanceof Request;
    const url = new URL(request ? input.url : input, location.href);
    const method = (options?.method || (request ? input.method : 'GET')).toUpperCase();
    const sameOrigin = url.origin === location.origin;
    const estimate = sameOrigin && /^\/api\/households\/\d+\/claim-estimate$/.test(url.pathname) && method === 'POST';
    if(!['GET', 'HEAD'].includes(method) && !estimate){
      return Promise.resolve(new Response(JSON.stringify({detail:'시연 사이트에서는 실제 기록을 저장하거나 삭제할 수 없어요.'}),
        {status:403, headers:{'Content-Type':'application/json'}}));
    }
    if(sameOrigin && (/^\/api\/households\/\d+\/detail$/.test(url.pathname) || estimate)){
      url.pathname = '/demo' + url.pathname;
      if(!estimate) url.searchParams.set('offset', offset());
    }
    return originalFetch(request ? new Request(url, input) : url, options);
  };

  window.addEventListener('storage', event => {
    if(event.key === KEY || event.key === null) location.reload();
  });

  document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('demo-site');
    const toolbar = document.createElement('section');
    toolbar.className = 'demo-toolbar';
    toolbar.setAttribute('aria-label', '시연 수온 설정');
    toolbar.innerHTML = `<strong>시연 전용</strong>
      <label class="demo-switch"><input type="checkbox" id="demo-enabled">가상 수온</label>
      <label for="demo-offset" class="demo-range-label">보정</label>
      <input type="range" id="demo-offset" min="0" max="15" step="0.5" aria-label="수온 보정값">
      <output id="demo-value" for="demo-offset" aria-live="polite"></output>
      <button type="button" class="demo-help-button" id="demo-help-button" aria-haspopup="dialog" aria-controls="demo-help">설명</button>`;
    document.querySelector('.top-in').append(toolbar);
    const enabled = document.getElementById('demo-enabled');
    const slider = document.getElementById('demo-offset');
    const value = document.getElementById('demo-value');
    enabled.checked = state.enabled;
    slider.value = state.offset;
    slider.disabled = !state.enabled;
    value.textContent = state.enabled ? `+${state.offset.toFixed(1)}℃` : '꺼짐';

    const dialog = document.createElement('dialog');
    dialog.id = 'demo-help';
    dialog.className = 'demo-help';
    dialog.setAttribute('aria-labelledby', 'demo-help-title');
    dialog.innerHTML = `<h2 id="demo-help-title">수온 시뮬레이션 사용법</h2>
      <p>상단의 ‘가상 수온’을 켠 뒤 보정값을 조절하세요. 조절을 마치면 현재 화면이 새로고침됩니다.</p>
      <ul><li>원본 수온에 0~15℃를 더해 수온·등급·연락 우선순위를 다시 계산해요.</li>
      <li>왼쪽 메뉴로 이동해도 네 화면에서 같은 설정을 사용해요. 다른 시연 탭에도 반영돼요.</li>
      <li>어가 상세의 연속 고수온은 예측 시작일부터 계산해요.</li>
      <li>공식 특보·실적 그래프·과거 상담 기록은 원본이에요. 상담 현황에는 수온 항목을 새로 추가하지 않아요.</li>
      <li>실제 상담 저장·발송 기록·삭제는 잠겨 있어요. 보험료·보험금 계산은 사용할 수 있어요.</li>
      <li>가상 수온을 끄면 원본 수온으로 돌아가요.</li></ul>
      <p><a href="/consult_home.html">실제 상담 홈으로 나가기</a></p>
      <p id="demo-storage-message" role="status"></p>
      <form method="dialog"><button type="submit" class="btn" autofocus>닫기</button></form>`;
    document.body.append(dialog);
    document.getElementById('demo-storage-message').textContent = storageMessage;
    const help = document.getElementById('demo-help-button');
    help.addEventListener('click', () => dialog.showModal());
    dialog.addEventListener('close', () => help.focus());
    if(storageMessage) dialog.showModal();

    function saveState(){
      const next = {enabled:enabled.checked, offset:Number(slider.value)};
      if(!Number.isFinite(next.offset) || next.offset < 0 || next.offset > 15 || !Number.isInteger(next.offset * 2)){
        slider.value = state.offset;
        return;
      }
      try{ localStorage.setItem(KEY, JSON.stringify(next)); }
      catch(error){
        if(!['SecurityError', 'QuotaExceededError'].includes(error.name)) throw error;
        document.getElementById('demo-storage-message').textContent = '설정을 저장하지 못했어요. 사이트 저장 허용이나 저장 공간을 확인해 주세요.';
        enabled.checked = state.enabled;
        slider.value = state.offset;
        dialog.showModal();
        return;
      }
      location.reload();
    }
    enabled.addEventListener('change', saveState);
    slider.addEventListener('input', () => { value.textContent = `+${Number(slider.value).toFixed(1)}℃`; });
    slider.addEventListener('change', saveState);

    // 원본 화면이 다시 그려도 시연 사이트의 기록 버튼은 잠긴 상태를 유지해요.
    const lockWrites = () => {
      document.querySelectorAll('#bulk-sms, #log-save, #del-ok, [data-del], [data-act="save"], [data-act="api-save"]').forEach(button => {
        if(!button.disabled) button.disabled = true;
        if(button.title !== '시연 전용 · 기록 저장 잠금') button.title = '시연 전용 · 기록 저장 잠금';
      });
    };
    lockWrites();
    new MutationObserver(lockWrites).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['disabled']});
  });
})();
