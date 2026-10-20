"""우리 바다 안심도우미 - 모바일 웹앱 화면.

프로젝트 폴더에서 실행: py -m streamlit run app.py
"""
from html import escape
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import re

import streamlit as st

from client import (ABALONE_NAMES, APIError, fetch_regions, fetch_registration_catalog,
                    save_farm, signup_account, login_account, fetch_my_farms, local_farm, logout_account,
                    fetch_coordinate_regions, fetch_region_coordinates)
from locations import DISTRICTS

SPECIES = ["조피볼락 (우럭)", "넙치 (광어)", "참돔", "돌돔", "감성돔", "숭어", "가숭어",
           "볼락", "점농어", "말쥐치", "참쥐치", "능성어", "방어", "굴", "멍게", "미더덕", "오만둥이", "전복", "기타"]
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
    st.session_state.clear_password = True
    if page == "register":
        st.session_state.pop("registration_regions", None)
        st.session_state.pop("registration_initialized", None)
    st.session_state.page = page
    st.session_state.menu_open = False


def start_page():
    fetch_regions()  # 시작 화면을 보는 동안 지역 목록을 미리 조회한다.
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
    if not st.session_state.get("registration_initialized"):
        for field in ("region", "district", "species", "method", "insurance", "abalone_kind"):
            st.session_state[f"farm_{field}"] = saved.get(field)
        st.session_state.farm_district_custom = saved.get("district", "")
        st.session_state.registration_initialized = True
    st.button("‹ 처음으로", type="tertiary", on_click=go, args=("start",))
    st.markdown('<div class="page-title">내 양식장 등록</div>', unsafe_allow_html=True)
    st.button("목록 새로고침", type="tertiary", on_click=reload_registration_catalog)

    # Public lists use the client's short-lived cache, not a permanent session snapshot.
    # This lets added species become visible while preserving still-valid selections.
    try:
        catalog = fetch_registration_catalog()
    except APIError as exc:
        catalog = None
        st.warning(str(exc))
    regions = sorted({r["sigungu_name"] for r in catalog["regions"]}) if catalog else fetch_regions()[0]
    if st.session_state.get("farm_region") not in regions:
        st.session_state.farm_region = None
    # form 밖의 위젯은 선택 즉시 재실행되어 종속 목록을 갱신할 수 있다.
    region = st.selectbox("양식 지역", regions, index=None, key="farm_region",
                          placeholder="지역을 선택하세요", on_change=reset_district)
    districts = ([r["area_name"] for r in catalog["regions"] if r["sigungu_name"] == region]
                 if catalog else DISTRICTS.get(region, []))
    if region and not districts:
        district = st.text_input("읍·면·동", key="farm_district_custom",
                                 placeholder="읍·면·동 이름을 입력하세요",
                                 help="아직 선택 목록이 없는 지역입니다. 직접 입력해 주세요.").strip()
    else:
        if st.session_state.get("farm_district") not in districts:
            st.session_state.farm_district = None
        district = st.selectbox("읍·면·동", districts, index=None, key="farm_district",
                                placeholder="읍·면·동을 선택하세요" if region else "양식 지역을 먼저 선택하세요",
                                disabled=not region)
    species_options = list(dict.fromkeys(
        "전복" if s["species_name"] in ABALONE_NAMES.values() else s["species_name"]
        for s in catalog["species"])) if catalog else SPECIES
    if st.session_state.get("farm_species") not in species_options:
        st.session_state.farm_species = None
    species = st.selectbox("양식 품종", species_options, index=None, key="farm_species",
                           placeholder="품종을 선택하세요", on_change=reset_abalone_kind)
    abalone_kind = None
    if species == "전복":
        abalone_kind = st.segmented_control("전복 구분", ["육상", "해상"],
                                            key="farm_abalone_kind", width="stretch")
        method = {"육상": "육상", "해상": "가두리"}.get(abalone_kind)
        st.session_state.farm_method = method
        if method:
            st.caption(f"양식 방식: {method}")
    else:
        method = st.segmented_control("양식 방식", METHODS, key="farm_method", width="stretch")
    insurance = st.segmented_control("보험 가입 상태", INSURANCE, key="farm_insurance", width="stretch")
    submitted = st.button("등록하기", type="primary", width="stretch", disabled=not catalog or not species_options)

    if not catalog or not species_options:
        st.caption("연결 후 지역·품종 목록을 불러오면 등록할 수 있습니다.")
    st.caption("※ 입력한 정보는 맞춤형 정보 제공에만 사용됩니다.")

    if submitted:
        if not region:
            st.error("지역을 선택해주십시오")
            return
        farm = {"region": region, "district": district, "species": species, "method": method,
                "insurance": insurance, "abalone_kind": abalone_kind}
        labels = {"region": "양식 지역", "district": "읍·면·동", "species": "양식 품종", "method": "양식 방식", "insurance": "보험 가입 상태"}
        if species == "전복":
            labels["abalone_kind"] = "전복 구분"
        missing = [label for name, label in labels.items() if not farm.get(name)]
        if missing:
            st.error(f"{', '.join(missing)}을(를) 선택해 주세요.")
            return
        try:
            result = save_farm(farm, token=st.session_state.get("access_token"),
                               farm_id=st.session_state.get("remote_farm_id"))
        except APIError as exc:
            st.error(str(exc))
            return
        if "access_token" in result:
            st.session_state.access_token = result["access_token"]
            st.session_state.customer = result["customer"]
        st.session_state.remote_farm_id = result["farm"]["farm_id"]
        st.session_state.farm = farm
        go("risk")
        st.rerun()


def reset_district():
    """상위 지역이 바뀌면 이전 지역의 세부 주소를 지운다."""
    st.session_state.farm_district = None
    st.session_state.farm_district_custom = ""


def reload_registration_catalog():
    fetch_registration_catalog.clear()


def reset_abalone_kind():
    st.session_state.farm_abalone_kind = None
    st.session_state.farm_method = None


def login_page():
    st.button("‹ 비회원으로 계속 이용", type="tertiary", on_click=go, args=("risk",))
    st.markdown('<div class="page-title">로그인</div>', unsafe_allow_html=True)
    st.caption("가입한 전화번호로 로그인해 주세요.")
    with st.form("login_form", border=False, clear_on_submit=True):
        phone = st.text_input("전화번호", placeholder="010-1234-5678", max_chars=20)
        password = st.text_input("비밀번호", type="password", key="login_password", max_chars=128)
        submitted = st.form_submit_button("로그인", type="primary", width="stretch")
    if submitted:
        if not phone.strip() or not password:
            st.session_state.login_notice = ("error", "전화번호와 비밀번호를 입력해 주세요.")
        else:
            try:
                result = login_account(phone, password)
                farms = fetch_my_farms(result["access_token"])
                restored = local_farm(farms[0]) if farms else None
            except APIError as exc:
                st.session_state.login_notice = ("error", str(exc))
            else:
                st.session_state.access_token = result["access_token"]
                st.session_state.customer = result["customer"]
                st.session_state.pop("remote_farm_id", None)
                if restored:
                    st.session_state.farm = restored
                    st.session_state.remote_farm_id = farms[0]["farm_id"]
                go("risk" if restored else "register")
                st.rerun()
        st.session_state.clear_password = True
        st.rerun()
    notice = st.session_state.pop("login_notice", None)
    if notice:
        level, message = notice
        (st.error if level == "error" else st.info)(message)
    st.caption("아직 계정이 없으신가요?")
    st.button("회원가입", width="stretch", on_click=go, args=("signup",))


def signup_page():
    farm = st.session_state.farm
    st.button("‹ 로그인으로 돌아가기", type="tertiary", on_click=go, args=("login",))
    st.markdown('<div class="page-title">가입 정보 입력</div>', unsafe_allow_html=True)
    rows = "".join(
        f"<dt>{label}</dt><dd>{escape(farm.get(key) or '미선택')}</dd>"
        for key, label in (("region", "양식 지역"), ("district", "읍·면·동"), ("species", "양식 품종"),
                           ("abalone_kind", "전복 구분"), ("method", "양식 방식"), ("insurance", "보험 가입"))
        if key != "abalone_kind" or farm.get(key)
    )
    st.markdown(f'<div class="summary"><dl>{rows}</dl></div>', unsafe_allow_html=True)
    st.caption("기존 양식장 정보와 선택한 품종을 유지한 채 회원으로 가입합니다.")
    today = datetime.now(timezone(timedelta(hours=9))).date()
    with st.form("signup_form", border=False):
        name = st.text_input("이름", placeholder="이름을 입력하세요", max_chars=50)
        birth = st.date_input("생년월일", value=None, min_value=date(1900, 1, 1),
                              max_value=today, format="YYYY/MM/DD")
        phone = st.text_input("전화번호", placeholder="010-1234-5678", max_chars=20)
        password = st.text_input("비밀번호 설정", type="password", key="signup_password",
                                 placeholder="8자 이상 입력하세요", max_chars=128)
        submitted = st.form_submit_button("가입완료", type="primary", width="stretch")
    if submitted:
        errors = []
        if not name.strip():
            errors.append("이름을 입력해 주세요.")
        if birth is None:
            errors.append("생년월일을 선택해 주세요.")
        digits = re.sub(r"[\s-]", "", phone)
        if not re.fullmatch(r"010[0-9]{8}", digits):
            errors.append("010으로 시작하는 휴대전화 번호 11자리를 입력해 주세요.")
        if len(password) < 8 or not password.strip():
            errors.append("비밀번호를 8자 이상 입력해 주세요.")
        if errors:
            for error in errors:
                st.error(error)
            return
        profile = {"name": name.strip(), "birth": birth.isoformat(), "phone": digits}
        try:
            result = signup_account(profile, password, st.session_state.get("access_token"))
        except APIError as exc:
            st.error(str(exc))
            return
        st.session_state.access_token = result["access_token"]
        st.session_state.customer = result["customer"]
        st.session_state.clear_password = True
        go("risk")
        st.rerun()


def toggle_menu():
    st.session_state.menu_open = not st.session_state.get("menu_open", False)


def logout():
    try:
        logout_account(st.session_state["access_token"])
    except APIError as exc:
        st.session_state.account_notice = str(exc)
        return
    for key in ("access_token", "customer", "remote_farm_id", "profile"):
        st.session_state.pop(key, None)
    go("risk")


def navigation():
    if not st.session_state.get("menu_open", False):
        return
    with st.container(key="navigation_drawer"):
        st.button("✕ 메뉴 닫기", on_click=toggle_menu, width="stretch")
        st.subheader("우리 바다 안심도우미")
        customer = st.session_state.get("customer", {})
        if customer.get("membership_status") == "member":
            st.write(f"{customer['name']}님")
        else:
            st.write("비회원으로 이용 중")
            st.button("로그인 / 회원가입", key="nav_login", width="stretch", on_click=go, args=("login",))
        st.caption(st.session_state.farm["region"])
        st.divider()
        for label, target in (("오늘의 위험정보", "risk"), ("내 양식장 정보 수정", "register"),
                              ("맞춤형 대응 안내", "response"), ("보험 정보 비교", "insurance"),
                              ("상담 및 다음 단계", "consult")):
            st.button(label, key=f"nav_{target}", width="stretch", on_click=go, args=(target,))
        st.divider()
        st.button("시작 화면으로", width="stretch", on_click=go, args=("start",))


def page_header(title):
    if st.session_state.get("customer", {}).get("membership_status") == "member":
        st.button("로그아웃", key="header_logout", type="tertiary", on_click=logout)
    else:
        st.button("로그인", key="header_login", type="tertiary", on_click=go, args=("login",))
    if notice := st.session_state.pop("account_notice", None):
        st.error(notice)
    heading, menu = st.columns([4, 1], vertical_alignment="center")
    with heading:
        st.markdown(f'<h1 class="screen-title">{escape(title)}</h1>', unsafe_allow_html=True)
    with menu:
        st.button("☰", help="사이드바 메뉴 열기 / 닫기", on_click=toggle_menu, width="stretch")
    navigation()


def risk_chart():
    # 예시 이미지와 같은 7일 추이. 실제 관측 또는 진단에 사용하지 않는다.
    values = [22.0, 22.8, 23.5, 24.6, 25.5, 26.2, 28.4]
    points = [(38 + i * 45, 168 - (v - 20) * 12) for i, v in enumerate(values)]
    line = " ".join(f"{x},{y:.1f}" for x, y in points)
    grid = "".join(f'<line x1="38" y1="{168-(v-20)*12}" x2="308" y2="{168-(v-20)*12}" stroke="#e2e8f0"/>'
                   f'<text x="8" y="{172-(v-20)*12}">{v}</text>' for v in (20, 22, 24, 26, 28, 30))
    dots = "".join(f'<circle cx="{x}" cy="{y:.1f}" r="4" fill="white" stroke="#1677ff" stroke-width="2"/>'
                   f'<text x="{x}" y="192" text-anchor="middle">8/{14+i}</text>'
                   for i, (x, y) in enumerate(points))
    st.html(f'<svg class="risk-chart" viewBox="0 0 338 210" role="img" aria-label="예시 수온: 8월 14일 22도에서 20일 28.4도로 상승">'
            f'<text x="8" y="20">°C</text><rect x="38" y="48" width="270" height="48" fill="#fff0ef"/>{grid}'
            f'<polygon points="38,168 {line} 308,168" fill="#1677ff" opacity=".08"/>'
            f'<polyline points="{line}" fill="none" stroke="#1677ff" stroke-width="3"/>{dots}</svg>')


def reset_risk_area():
    st.session_state.risk_region_id = None


def risk_location_picker():
    st.subheader("지역 좌표 조회")
    try:
        regions = fetch_coordinate_regions()
    except APIError as exc:
        st.error(str(exc))
        return
    if not regions:
        st.info("등록된 지역이 없습니다.")
        return
    cities = sorted({row["sigungu_name"] for row in regions})
    farm = st.session_state.farm
    saved_location = (farm.get("region"), farm.get("district"))
    if st.session_state.get("risk_saved_location") != saved_location:
        st.session_state.risk_sigungu = farm.get("region") if farm.get("region") in cities else None
        matches = [row["region_id"] for row in regions
                   if (row["sigungu_name"], row["area_name"]) == saved_location]
        st.session_state.risk_region_id = matches[0] if len(matches) == 1 else None
        st.session_state.risk_saved_location = saved_location
    if st.session_state.get("risk_sigungu") not in cities:
        st.session_state.risk_sigungu = None
    city = st.selectbox("조회할 시·군·구", cities, index=None, key="risk_sigungu",
                        placeholder="시·군·구를 선택하세요", on_change=reset_risk_area)
    areas = {row["region_id"]: row for row in regions if row["sigungu_name"] == city}
    if st.session_state.get("risk_region_id") not in areas:
        st.session_state.risk_region_id = None
    selected_id = st.selectbox("조회할 읍·면·리 / 지역", list(areas), index=None,
                              format_func=lambda region_id: areas[region_id]["area_name"],
                              key="risk_region_id", disabled=not city,
                              placeholder="읍·면·리 또는 지역을 선택하세요" if city else "시·군·구를 먼저 선택하세요")
    if selected_id is None:
        st.caption("지역을 선택하면 위도와 경도가 표시됩니다.")
        return
    try:
        coordinates = fetch_region_coordinates(selected_id)
    except APIError as exc:
        st.error(str(exc))
        return
    latitude, longitude = st.columns(2)
    with latitude:
        st.metric("위도", f"{coordinates['latitude']:.6f}")
    with longitude:
        st.metric("경도", f"{coordinates['longitude']:.6f}")
    st.caption(f"{coordinates['sigungu_name']} · {coordinates['area_name']}")
    if coordinates.get("coordinate_type"):
        st.caption(f"좌표 유형: {coordinates['coordinate_type']}")
    st.caption("선택한 지역의 기준 좌표입니다.")


def risk_page():
    page_header("오늘의 위험정보")
    farm = st.session_state.farm
    species_label = ABALONE_NAMES.get(farm.get("abalone_kind"), farm["species"]) if farm["species"] == "전복" else farm["species"]
    st.caption(f"{farm['region']} · {species_label} · {farm['method']}")
    risk_location_picker()
    st.markdown('<div class="demo-label">미리보기 · 실제 관측·예측·특보가 아닌 예시 데이터</div>', unsafe_allow_html=True)
    st.caption("예시 기준: 2025년 8월 20일 10:00")
    current, forecast, alerts = st.tabs(["현재 상황", "예측 추이", "특보 정보"])
    with current:
        st.html('<div class="temperature-card"><strong>현재 수온</strong>'
                '<div class="temperature-row"><span class="temperature">28.4<small>°C</small></span>'
                '<span class="risk-badge">♨ 주의 단계</span></div>'
                '<p>최근 1주 평균 대비 +1.8°C<br>선택 지역 관측소 기준 (예시)</p></div>')
        st.markdown("#### 최근 7일 수온 추이")
        risk_chart()
        st.caption("🟥 고수온 주의 구간 (예시)")
    with forecast:
        st.markdown("#### 앞으로의 수온 변화")
        st.caption("화면 구성용 가상 예측입니다.")
        st.table({"날짜": ["8/21", "8/22", "8/23"], "예상 수온": ["28.6°C", "28.9°C", "29.1°C"]})
    with alerts:
        st.info("고수온 주의 알림 (예시)")
        st.write("실제 특보는 아직 연결되지 않았습니다. 추후 공식 발표와 발표 시각을 표시합니다.")
    st.button("대비 행동 보기 →", type="primary", width="stretch", on_click=go, args=("response",))


def placeholder_page():
    titles = {"response": "맞춤형 대응 안내", "insurance": "보험 정보 비교", "consult": "상담 및 다음 단계"}
    page_header(titles[st.session_state.page])
    st.info("준비 중인 화면입니다.")
    st.write("이 메뉴의 상세 내용은 다음 단계에서 추가할 예정입니다.")
    st.button("오늘의 위험정보로 돌아가기", width="stretch", on_click=go, args=("risk",))


st.set_page_config(page_title="우리 바다 안심도우미", page_icon="🌊", layout="centered")
# <style>만 담은 st.html은 화면에 빈칸을 만들지 않는다.
st.html(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>")

if st.session_state.pop("clear_password", False):
    st.session_state.pop("signup_password", None)
    st.session_state.pop("login_password", None)
page = st.session_state.setdefault("page", "start")
if page == "done":  # 기존 실행 세션의 완료 화면을 새 흐름에 연결한다.
    page = "signup"
if page not in ("start", "register") and "farm" not in st.session_state:
    page = "register"
st.session_state.page = page
{"start": start_page, "register": register_page, "login": login_page, "signup": signup_page,
 "risk": risk_page, "response": placeholder_page, "insurance": placeholder_page,
 "consult": placeholder_page}[page]()
