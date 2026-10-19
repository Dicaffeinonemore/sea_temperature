"""FastAPI 호출. API 주소는 NIFS_API_URL 환경변수로 바꿀 수 있습니다."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic

import requests
import streamlit as st

API_URL = os.getenv("NIFS_API_URL", "http://127.0.0.1:8000").rstrip("/")
# API가 꺼져 있어도 등록 화면을 쓸 수 있도록 DB의 경남 7개 시군을 기본값으로 둔다.
DEFAULT_REGIONS = ["거제시", "고성군", "남해군", "사천시", "창원시(진해구)", "통영시", "하동군"]


def _regions_from_api() -> list[str]:
    response = requests.get(f"{API_URL}/api/v1/sigungu", timeout=5)
    response.raise_for_status()
    return [row["sigungu_name"] for row in response.json()]


class RegionCache:
    """API를 기다리지 않고 최근 목록을 반환하는 스레드 안전 캐시."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock = Lock()
        self.pending = None
        self.retry_at = 0.0
        self.regions = list(DEFAULT_REGIONS)
        self.from_api = False

    def snapshot(self) -> tuple[list[str], bool]:
        with self.lock:
            if self.pending is not None and self.pending.done():
                try:
                    regions = self.pending.result()
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    regions = []
                if regions:
                    self.regions = regions
                    self.from_api = True
                # 실패 시 마지막 목록을 유지하고 30초 뒤 다시 시도한다.
                self.retry_at = monotonic() + (600 if regions else 30)
                self.pending = None
            if self.pending is None and monotonic() >= self.retry_at:
                # 작업 스레드에서는 Streamlit UI/세션 API를 호출하지 않는다.
                self.pending = self.executor.submit(_regions_from_api)
            return list(self.regions), self.from_api


@st.cache_resource(show_spinner=False)
def _region_cache() -> RegionCache:
    return RegionCache()


def fetch_regions() -> tuple[list[str], bool]:
    """백그라운드 조회를 시작하고 사용 가능한 지역 목록을 즉시 반환한다."""
    return _region_cache().snapshot()
