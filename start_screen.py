"""우리 바다 안심도우미 - 시작 화면

실행: streamlit run start_screen.py
"""
import base64
from pathlib import Path

import streamlit as st

# ============================================================
# 쉽게 바꾸는 설정값
# ============================================================
TITLE_LINE1 = "우리 바다"
TITLE_LINE2 = "안심도우미"
SUBTITLE = "양식어가 든든한 파트너"

# 배경 사진: 파일 경로를 넣으면 사진으로, 비워 두면("") 그라데이션으로 표시돼요.
# 예) BG_IMAGE = "assets/start_bg.jpg"  (start_screen.py 기준 상대 경로)
BG_IMAGE = "assets/start_bg.jpg"

# 글씨 크기
TITLE_SIZE = "44px"
SUBTITLE_SIZE = "22px"

# 색상 - 사진 배경일 때
PHOTO_TITLE_COLOR = "#FFFFFF"     # 제목 (흰색)
PHOTO_SUBTITLE_COLOR = "#E3EAF2"  # 부제목 (밝은 회색)
PHOTO_OVERLAY = 0.55              # 위쪽 어두운 막 진하기 (0~1, 클수록 글씨가 잘 보임)

# 색상 - 사진이 없을 때(그라데이션 배경)
TITLE_COLOR = "#0B2E5C"      # 제목 (진한 남색)
SUBTITLE_COLOR = "#4A5A6E"   # 부제목 (회색)
BG_GRADIENT = (
    "linear-gradient(180deg,"
    " #EAF4FB 0%, #CFE6F5 35%, #8EC3E6 60%, #3E8CC4 82%, #1D5F99 100%)"
)
PAGE_BG = "#DDE3EA"          # PC에서 폰 화면 바깥 배경색

# 폰 화면 폭 (PC에서 볼 때 가운데 정렬되는 최대 폭)
SCREEN_MAX_WIDTH = "430px"
# ============================================================

BG_PATH = Path(__file__).parent / BG_IMAGE if BG_IMAGE else None
USE_PHOTO = bool(BG_PATH and BG_PATH.exists())
if USE_PHOTO:
    TITLE_COLOR, SUBTITLE_COLOR = PHOTO_TITLE_COLOR, PHOTO_SUBTITLE_COLOR
TEXT_SHADOW = "0 2px 8px rgba(0,0,0,0.35)" if USE_PHOTO else "none"


def background_css() -> str:
    """사진 파일이 있으면 사진, 없으면 그라데이션을 배경으로 써요."""
    if USE_PHOTO:
        ext = BG_PATH.suffix.lower().lstrip(".").replace("jpg", "jpeg")
        data = base64.b64encode(BG_PATH.read_bytes()).decode()
        # 위쪽에 어두운 막을 덮어 흰 글씨가 하늘 위에서도 잘 보이게 해요.
        o = PHOTO_OVERLAY
        return (
            f"linear-gradient(180deg, rgba(5,25,50,{o}) 0%,"
            f" rgba(5,25,50,{o * 0.6:.2f}) 30%, rgba(5,25,50,0) 50%),"
            f" url('data:image/{ext};base64,{data}') center / cover no-repeat"
        )
    return BG_GRADIENT


st.set_page_config(page_title="우리 바다 안심도우미", page_icon="🌊", layout="centered")

st.markdown(
    f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

/* Streamlit 기본 메뉴·여백 숨기기 */
header, footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"] {{
    display: none !important;
}}
.stApp {{ background: {PAGE_BG}; }}
.block-container {{
    max-width: {SCREEN_MAX_WIDTH} !important;
    padding: 0 !important;
}}

/* 폰 화면 */
.start-screen {{
    position: relative;
    min-height: 100vh;
    overflow: hidden;
    background: {background_css()};
    font-family: 'Pretendard', 'NanumGothic', 'Apple SD Gothic Neo', sans-serif;
    padding: 96px 32px 0;
    box-sizing: border-box;
}}
.start-title {{
    color: {TITLE_COLOR} !important;
    font-size: {TITLE_SIZE} !important;
    font-weight: 800 !important;
    line-height: 1.25 !important;
    letter-spacing: -0.02em;
    margin: 0 !important;
    padding: 0 !important;
    font-family: inherit !important;
    text-shadow: {TEXT_SHADOW};
}}
.start-subtitle {{
    color: {SUBTITLE_COLOR} !important;
    font-size: {SUBTITLE_SIZE} !important;
    font-weight: 500 !important;
    margin: 20px 0 0 !important;
    font-family: inherit !important;
    text-shadow: {TEXT_SHADOW};
}}

/* 바다 물결 장식 (사진을 넣으면 숨겨져요) */
.waves {{
    position: absolute;
    left: 0; right: 0; bottom: 0;
    width: 100%;
    height: 45%;
    display: {"none" if USE_PHOTO else "block"};
}}
</style>

<div class="start-screen">
  <h1 class="start-title">{TITLE_LINE1}<br>{TITLE_LINE2}</h1>
  <p class="start-subtitle">{SUBTITLE}</p>

  <svg class="waves" viewBox="0 0 430 400" preserveAspectRatio="none" aria-hidden="true">
    <path d="M0 120 Q 55 95 110 120 T 220 120 T 330 120 T 440 120 V400 H0 Z" fill="#5FA4D6" opacity="0.55"/>
    <path d="M0 190 Q 55 165 110 190 T 220 190 T 330 190 T 440 190 V400 H0 Z" fill="#3A84BE" opacity="0.7"/>
    <path d="M0 270 Q 55 245 110 270 T 220 270 T 330 270 T 440 270 V400 H0 Z" fill="#1F639E" opacity="0.85"/>
    <!-- 양식장 가두리 -->
    <g fill="none" stroke="#FFFFFF" stroke-opacity="0.75" stroke-width="3">
      <ellipse cx="110" cy="225" rx="48" ry="12"/>
      <ellipse cx="240" cy="235" rx="52" ry="13"/>
      <ellipse cx="360" cy="222" rx="44" ry="11"/>
      <ellipse cx="170" cy="310" rx="60" ry="15"/>
      <ellipse cx="320" cy="320" rx="58" ry="15"/>
    </g>
  </svg>
</div>
""",
    unsafe_allow_html=True,
)

