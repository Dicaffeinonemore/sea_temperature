"""FastAPI 호출. API 주소는 NIFS_API_URL 환경변수로 바꿀 수 있습니다."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic

import requests
import streamlit as st

API_URL = os.getenv("NIFS_API_URL", "http://127.0.0.1:8000").rstrip("/")
ABALONE_NAMES = {"육상": "전복(육상)", "해상": "전복(해상)"}


class APIError(Exception):
    """A request failed; safe to display without credentials or request bodies."""


def _api(method, path, *, body=None, token=None):
    headers = {"X-CSRF-Protection": "1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(method, f"{API_URL}{path}", json=body, headers=headers, timeout=10)
    except requests.RequestException:
        raise APIError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from None
    if not response.ok:
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, list):
            detail = " / ".join(str(row.get("msg", "입력값을 확인하세요.")) for row in detail)
        raise APIError(detail if isinstance(detail, str) else "요청을 처리하지 못했습니다. 다시 시도해 주세요.")
    return response.json() if response.status_code != 204 else None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_registration_catalog():
    # Public lists expire after 60 seconds; registration reads this cache on each rerun.
    # Never cache tokens or customer-specific data here.
    return {"regions": _api("GET", "/api/regions"), "species": _api("GET", "/api/species")}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_coordinate_regions():
    """Public city/area choices independent of customer and species data."""
    return _api("GET", "/api/regions")


@st.cache_data(ttl=60, max_entries=256, show_spinner=False)
def fetch_region_coordinates(region_id: int):
    return _api("GET", f"/api/regions/{region_id}")


def save_farm(farm, *, token=None, farm_id=None):
    catalog = fetch_registration_catalog()
    name = farm["species"]
    if name == "전복":
        name = ABALONE_NAMES.get(farm.get("abalone_kind"))
        if name is None:
            raise APIError("전복은 육상·해상 구분을 선택해 주세요.")
    regions = [r for r in catalog["regions"] if r["sigungu_name"] == farm["region"] and r["area_name"] == farm["district"]]
    species = [s for s in catalog["species"] if s["species_name"] == name]
    if len(regions) != 1 or len(species) != 1:
        raise APIError("현재 목록과 맞지 않는 지역 또는 품종입니다. 목록을 새로 불러와 다시 선택해 주세요.")
    body = {"region_id": regions[0]["region_id"], "species_ids": [species[0]["species_id"]],
            "farming_method": {"가두리": "cage", "육상": "land_based"}[farm["method"]],
            "insurance_status": {"가입": "insured", "미가입": "uninsured", "잘 모름": "unknown"}[farm["insurance"]]}
    if not token:
        return _api("POST", "/api/guest-registrations", body=body)
    path = f"/api/me/farms/{farm_id}" if farm_id else "/api/me/farms"
    remote = _api("PATCH" if farm_id else "POST", path, body=body, token=token)
    return {"farm": remote}


def signup_account(profile, password, token):
    return _api("POST", "/api/auth/signup", token=token, body={
        "name": profile["name"], "birth_date": profile["birth"], "phone_number": profile["phone"], "password": password})


def login_account(phone, password):
    return _api("POST", "/api/auth/login", body={"phone_number": phone, "password": password})


def fetch_my_farms(token):
    return _api("GET", "/api/me/farms", token=token)


def logout_account(token):
    return _api("POST", "/api/auth/logout", token=token)


def local_farm(remote):
    names = {r["species_id"]: r["species_name"] for r in fetch_registration_catalog()["species"]}
    # Current UI edits one species. Don't silently discard a multi-species farm.
    if len(remote["species_ids"]) != 1:
        raise APIError("복수 품종 양식장은 현재 등록 화면에서 수정할 수 없습니다.")
    name = names.get(remote["species_ids"][0])
    if name is None:
        raise APIError("저장된 품종 정보를 불러오지 못했습니다.")
    kind = next((key for key, value in ABALONE_NAMES.items() if value == name), None)
    return {"region": remote["sigungu_name"], "district": remote["town_name"],
            "species": "전복" if kind else name, "abalone_kind": kind,
            "method": {"cage": "가두리", "land_based": "육상"}[remote["farming_method"]],
            "insurance": {"insured": "가입", "uninsured": "미가입", "unknown": "잘 모름"}[remote["insurance_status"]]}
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
