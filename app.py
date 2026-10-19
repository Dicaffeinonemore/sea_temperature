"""우리 바다 안심도우미 - 모바일 웹앱 화면.

프로젝트 최상위 폴더에서 실행: .\\.venv\\Scripts\\python.exe -m streamlit run frontend/app.py
"""
from html import escape
from pathlib import Path

import streamlit as st

from client import fetch_regions

SPECIES = ["조피볼락 (우럭)", "넙치 (광어)", "참돔", "돌돔", "감성돔", "숭어", "굴", "멍게", "전복", "기타"]
METHODS = ["가두리", "육상"]
INSURANCE = ["미가입", "가입", "잘 모름"]

HERO_ART = """
<svg viewBox="0 0 360 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#cfe7f7"/><stop offset="1" stop-color="#f1f8fd"/>
    </linearGradient>
    <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#6aa9d0"/><stop offset="1" stop-color="#1b5a8a"/>
    </linearGradient>
  </defs>
  <rect width="360" height="330" fill="url(#sky)"/>
  <path d="M0 330V268Q55 232 105 255Q160 214 225 250Q285 222 360 258V330Z" fill="#8db4c8"/>
  <path d="M0 330V292Q85 266 160 288Q240 270 360 294V330Z" fill="#5d8ea6"/>
  <rect y="328" width="360" height="272" fill="url(#sea)"/>
  <path d="M286 104q7-6 13 0q6-6 13 0M250 132q5-4 9 0q4-4 9 0" fill="none" stroke="#5b7f95" stroke-width="2"/>
  <g fill="#2a6f9e" stroke="#e6f2fa" stroke-width="2">
    <ellipse cx="58" cy="352" rx="24" ry="5"/><ellipse cx="130" cy="350" rx="24" ry="5"/>
    <ellipse cx="205" cy="353" rx="24" ry="5"/><ellipse cx="280" cy="351" rx="24" ry="5"/>
    <ellipse cx="40" cy="388" rx="34" ry="8"/><ellipse cx="135" cy="390" rx="34" ry="8"/>
    <ellipse cx="232" cy="388" rx="34" ry="8"/><ellipse cx="328" cy="391" rx="34" ry="8"/>
    <ellipse cx="80" cy="440" rx="48" ry="12"/><ellipse cx="210" cy="442" rx="48" ry="12"/>
    <ellipse cx="335" cy="440" rx="48" ry="12"/>
  </g>
  <g fill="none" stroke="#bcdcef" stroke-width="1.2" opacity=".8">
    <ellipse cx="40" cy="388" rx="27" ry="6"/><ellipse cx="135" cy="390" rx="27" ry="6"/>
    <ellipse cx="232" cy="388" rx="27" ry="6"/><ellipse cx="80" cy="440" rx="39" ry="9"/>
    <ellipse cx="210" cy="442" rx="39" ry="9"/><ellipse cx="335" cy="440" rx="39" ry="9"/>
  </g>
</svg>
"""


def go(page: str):
    st.session_state.page = page


def start_page():
    # 빈 줄이나 4칸 들여쓰기가 섞이면 마크다운이 HTML을 코드 블록으로 바꾸므로 한 덩어리로 넘긴다.
    st.markdown(
        f'<div class="hero">{HERO_ART.strip()}<div class="hero-text">'
        "<h1>우리 바다<br>안심도우미</h1>"
        "<p>기후위험 진단부터<br>보험·지원까지,<br>양식어가의 든든한 파트너</p>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.button("시작하기 →", key="start_button", type="primary", width="stretch",
              on_click=go, args=("register",))


def index_of(options: list[str], value: str | None) -> int | None:
    return options.index(value) if value in options else None


def register_page():
    saved = st.session_state.get("farm", {})
    st.button("‹ 처음으로", type="tertiary", on_click=go, args=("start",))
    st.markdown('<div class="page-title">내 양식장 등록</div>', unsafe_allow_html=True)

    regions, from_api = fetch_regions()
    with st.form("farm_form", border=False):
        region = st.selectbox("양식 지역", regions, index=index_of(regions, saved.get("region")),
                              placeholder="지역을 선택하세요")
        species = st.selectbox("양식 품종", SPECIES, index=index_of(SPECIES, saved.get("species")),
                               placeholder="품종을 선택하세요")
        method = st.segmented_control("양식 방식", METHODS, default=saved.get("method"), width="stretch")
        insurance = st.segmented_control("보험 가입 상태", INSURANCE, default=saved.get("insurance"),
                                         width="stretch")
        submitted = st.form_submit_button("등록하기", type="primary", width="stretch")

    if not from_api:
        st.caption("서버에 연결하지 못해 기본 지역 목록을 표시합니다.")
    st.caption("※ 입력한 정보는 맞춤형 정보 제공에만 사용됩니다.")

    if submitted:
        farm = {"region": region, "species": species, "method": method, "insurance": insurance}
        labels = {"region": "양식 지역", "species": "양식 품종", "method": "양식 방식", "insurance": "보험 가입 상태"}
        missing = [labels[name] for name, value in farm.items() if not value]
        if missing:
            st.error(f"{', '.join(missing)}을(를) 선택해 주세요.")
            return
        st.session_state.farm = farm
        go("done")
        st.rerun()


def done_page():
    farm = st.session_state.farm
    st.markdown('<div class="page-title">등록이 완료되었습니다</div>', unsafe_allow_html=True)
    rows = "".join(
        f"<dt>{label}</dt><dd>{escape(farm[key])}</dd>"
        for key, label in (("region", "양식 지역"), ("species", "양식 품종"),
                           ("method", "양식 방식"), ("insurance", "보험 가입"))
    )
    st.markdown(f'<div class="summary"><dl>{rows}</dl></div>', unsafe_allow_html=True)
    st.write("")
    # 3번 '오늘의 위험정보' 화면은 다음 단계에서 연결한다.
    st.button("오늘의 위험정보 보기 (준비 중)", type="primary", width="stretch", disabled=True)
    st.button("정보 수정", width="stretch", on_click=go, args=("register",))


st.set_page_config(page_title="우리 바다 안심도우미", page_icon="🌊", layout="centered")
# <style>만 담은 st.html은 화면에 빈칸을 만들지 않는다.
st.html(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>")

page = st.session_state.setdefault("page", "start")
if page == "done" and "farm" not in st.session_state:
    page = "register"
{"start": start_page, "register": register_page, "done": done_page}[page]()
