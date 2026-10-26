"""
우리 바다 안심도우미 - 신청·주의 대시보드 (Streamlit Community Cloud 배포용)

그래프 모양과 DB 조회는 backend/backend/dashboard.py 를 그대로 씁니다.

실행 (sea_temperature 폴더에서)
  streamlit run streamlit_app.py
DB 접속: 로컬은 backend/backend/.env, Streamlit Cloud 는 Secrets 의 DATABASE_URL
"""

import sys
from pathlib import Path
from threading import Lock

import psycopg
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.dashboard import NotReady, fetch, monthly_figure, yearly_figure  # noqa: E402
from backend.db import connect  # noqa: E402

# Matplotlib font settings are global and Streamlit runs each session in its own thread.
_CHART_LOCK = Lock()


@st.cache_data(ttl=600, show_spinner="DB에서 불러오는 중…")
def load(region: str) -> tuple[list[str], list[dict], list[dict]]:
    with connect() as conn:
        conn.read_only = True
        yearly, monthly = fetch(conn, region)
        regions = [r["region"] for r in conn.execute(
            "SELECT DISTINCT region FROM public.dash_chart_yearly ORDER BY region")]
    return regions, yearly, monthly


st.set_page_config(page_title="우리 바다 안심도우미", page_icon="🌊")
st.title("신청·주의 현황")

region = st.session_state.get("region", "전체")
try:
    regions, yearly, monthly = load(region)
except NotReady as exc:
    st.error(str(exc))
    st.stop()
except psycopg.Error as exc:
    # Show only the error type so the connection string never reaches the page.
    st.error(f"DB 연결 또는 조회 실패 ({type(exc).__name__}). DATABASE_URL 설정을 확인해 주세요.")
    st.stop()

options = ["전체"] + [r for r in regions if r != "전체"]
st.selectbox("지역", options, key="region")

if not yearly:
    st.info(f"'{region}' 그래프 데이터가 없습니다.")
    st.stop()

with _CHART_LOCK:
    st.subheader("연도별")
    st.pyplot(yearly_figure(yearly))
    if monthly:
        st.subheader("월별")
        st.pyplot(monthly_figure(monthly))
