"""FastAPI 호출. API 주소는 NIFS_API_URL 환경변수로 바꿀 수 있습니다."""
import os

import requests
import streamlit as st

API_URL = os.getenv("NIFS_API_URL", "http://127.0.0.1:8000").rstrip("/")
# API가 꺼져 있어도 등록 화면을 쓸 수 있도록 DB의 경남 7개 시군을 기본값으로 둔다.
DEFAULT_REGIONS = ["거제시", "고성군", "남해군", "사천시", "창원시(진해구)", "통영시", "하동군"]


@st.cache_data(ttl=600, show_spinner=False)
def _regions_from_api() -> list[str]:
    # 실패는 예외로 끝나 캐시되지 않으므로 API가 다시 켜지면 바로 반영된다.
    response = requests.get(f"{API_URL}/api/v1/sigungu", timeout=5)
    response.raise_for_status()
    return [row["sigungu_name"] for row in response.json()]


def fetch_regions() -> tuple[list[str], bool]:
    """(지역 목록, API에서 받았는지 여부)를 반환한다."""
    try:
        regions = _regions_from_api()
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return DEFAULT_REGIONS, False
    return (regions, True) if regions else (DEFAULT_REGIONS, False)
