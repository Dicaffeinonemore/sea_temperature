"""
우리 바다 안심도우미 - 홈 화면 API (초안 v3: RISA 실시간 수온 연동)

home.html 의 `data` 객체를 채워 주는 백엔드입니다.

데이터 출처
  - 양식장/고객   : customer_service.customers, farms, farm_species, species
  - 양식장 좌표   : public.sigungu_area_coordinates (farms.region_id)
                    없으면 public.sigungu (시군 대표점)
  - 관측소        : public.stations (source = 'risa')
                    좌표가 없으면 public.sigungu_station_map
  - 실시간 수온   : 국립수산과학원 RISA 웹 엔드포인트 (POST, 인증키 불필요)
                    https://www.nifs.go.kr/risa/selectTodayObsvtrMap.do  (obsvtrCd=관측소코드)
                    양식장 위경도 → 가까운 관측소를 골라 요청 시점에 호출
                    실패 시 public.risa_observation 최신값 → 오늘 예측값
  - 예측 수온     : public.example (없으면 public.roms_forecast, FORECAST_TABLE 로 지정 가능)
                    격자 예측: predc_dt, lat, lot, wtem / 향후 7일
  - 고수온 단계   : public.screen3_current 의 공식 특보(is_official)가 있으면 그 값,
                    없으면 실시간 + 예측값으로 앱 내부 기준 계산
  - 보험 보장     : finance.fin_ins_land_product / _rider / _exclusion
                    (해상 전복은 finance.sea_abalone_insurance_*)

엔드포인트
  GET /?customer=C-901                   홈 화면 (같은 폴더의 home.html)
  GET /api/home/{customer_id}?farm_id=   홈 화면 데이터 (home.html 의 data 객체 형태)
  GET /api/farms                         어종/지역/보험 가입 여부/양식 방식으로 양식장 필터링
  GET /health

실행
  pip install fastapi "uvicorn[standard]" asyncpg httpx pydantic
  export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
  uvicorn home_api:app --reload

※ TODO 표시는 실제 데이터를 보고 확정해야 하는 부분입니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from enum import Enum
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

log = logging.getLogger("home_api")
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

RISA_BASE_URL = os.getenv("RISA_BASE_URL", "https://www.nifs.go.kr/risa/")
RISA_TIMEOUT_SEC = 8.0
RISA_CACHE_SEC = 5 * 60           # 관측소별 실시간 값 캐시 (RISA 갱신 주기보다 짧게)
RISA_FAIL_CACHE_SEC = 60          # 호출 실패 시 재시도 간격
RISA_DEBUG = os.getenv("RISA_DEBUG") == "1"   # 1 이면 받은 원본 응답을 로그로 남김
STATION_CACHE_SEC = 60 * 60       # public.stations 는 거의 안 바뀜 → 1시간 캐시
OBS_STALE_HOURS = 3               # 이보다 오래된 관측값은 '실시간'으로 보지 않음
STATION_CANDIDATES = 5            # DB 대체 경로에서 가까운 관측소 몇 곳까지 볼지
# 양식장에서 이 거리 안의 관측소 값만 '우리 바다 실측값'으로 씀. 더 멀면 양식장 위치 예측값으로 대체
REALTIME_MAX_KM = float(os.getenv("REALTIME_MAX_KM", "15"))
RISA_LIST_MAX_PAGES = 20          # selectTodayObsvtrList 페이지를 최대 몇 장까지 넘길지

FORECAST_DAYS = 7                 # 내일부터 7일치 예측 (오늘 값은 따로 포함)
FORECAST_CHANGE_DEG = 0.5         # 이보다 작게 움직이면 '큰 변화 없음'으로 봄
GRID_SEARCH_DEG = 0.3             # 예측 격자 최근접점 탐색 범위 (위경도 ±도)
# 예측 테이블: 비워 두면 아래 후보 중 DB 에 실제로 있는 첫 테이블을 자동으로 사용
FORECAST_TABLE = os.getenv("FORECAST_TABLE", "")
FORECAST_TABLE_CANDIDATES = ("public.example", "public.roms_forecast")

# 앱 내부 고수온 단계 기준 (공식 특보가 없을 때만 사용)
#   ※ 국립수산과학원 고수온 특보 기준을 참고한 값입니다. 운영 전 최신 기준 확인 필요.
#   관심 : 7일 안에 25℃ 도달이 예측됨
#   주의 : 현재 25℃ 이상
#   경보 : 현재 28℃ 이상이고, 오늘 포함 28℃ 이상이 3일 이상 이어짐(예측 포함)
WATCH_TEMP = 25.0
CAUTION_TEMP = 25.0
ALERT_TEMP = 28.0
ALERT_STREAK_DAYS = 3

FARMING_METHOD_LABEL = {"cage": "가두리", "land_based": "육상"}


# ---------------------------------------------------------------------------
# 응답 모델 (home.html 의 data 객체와 같은 구조)
# ---------------------------------------------------------------------------
class InsuranceStatus(str, Enum):
    insured = "insured"
    uninsured = "uninsured"
    unknown = "unknown"


class CoverType(str, Enum):
    basic = "basic"          # 기본 계약으로 보장
    rider = "rider"          # 특약을 추가해야 보장
    excluded = "excluded"    # 보장하지 않음
    unknown = "unknown"      # 상품 정보로 판단 불가


class SeaLevel(str, Enum):
    normal = "normal"        # 정상
    watch = "watch"          # 관심
    caution = "caution"      # 주의
    alert = "alert"          # 경보
    unknown = "unknown"      # 정보 없음


RISK_TO_LEVEL = {"정상": SeaLevel.normal, "관심": SeaLevel.watch, "주의": SeaLevel.caution,
                 "경보": SeaLevel.alert, "정보 없음": SeaLevel.unknown}


class Farm(BaseModel):
    farmId: str
    region: str              # 화면 표기용 짧은 지역명 (예: 통영)
    regionFull: str          # 예: 통영시 산양읍
    species: str             # 예: 조피볼락(우럭)  (여러 어종이면 ', ' 로 연결)
    shortName: str           # 예: 우럭
    method: str              # 예: 가두리


class Forecast(BaseModel):
    trend: str               # rise(오름) | fall(내림) | flat(큰 변화 없음)
    days: int                # rise/fall: 최고/최저가 나타나는 날까지 남은 일수, flat: 예측 기간 일수
    temp: float              # rise: 최고 예측값, fall: 최저 예측값, flat: 최고 예측값 (모두 일평균)
    spanDays: int            # 예측이 있는 기간 (내일부터 며칠)
    min: float               # 기간 중 일평균 최저
    max: float               # 기간 중 일평균 최고


class ForecastDay(BaseModel):
    date: date
    avg: float
    max: float


class Sea(BaseModel):
    level: SeaLevel
    isOfficial: bool         # 국립수산과학원 공식 특보 기준이면 True
    now: Optional[float]
    forecast: Optional[Forecast]
    updatedAt: str           # 'MM/DD HH:MM'
    isForecast: bool         # now 가 실측이 아니라 예측값으로 대체된 경우 True
    source: str              # 'api' | 'db' | 'forecast' | 'none'
    stationName: Optional[str] = None
    stationDistanceKm: Optional[float] = None
    forecast7d: list[ForecastDay] = []


class Coverage(BaseModel):
    basic: list[str] = []
    rider: list[str] = []
    excluded: list[str] = []


class Insurance(BaseModel):
    status: InsuranceStatus
    productName: Optional[str] = None
    highTemp: CoverType = CoverType.unknown
    riderName: Optional[str] = None
    coverage: Coverage = Coverage()
    exclusions: list[str] = []   # 보상하지 않는 손해 요약 (최대 3개)


class HomeResponse(BaseModel):
    farm: Farm
    sea: Sea
    insurance: Insurance


class FarmSummary(BaseModel):
    farmId: str
    customerId: str
    customerName: Optional[str]
    membership: str
    regionFull: str
    species: list[str]
    method: str
    insurance: InsuranceStatus


# ---------------------------------------------------------------------------
# DB 연결
# ---------------------------------------------------------------------------
pool: Optional[asyncpg.Pool] = None
http_client = httpx.AsyncClient(timeout=RISA_TIMEOUT_SEC)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    log.info("DB pool ready")
    try:
        yield
    finally:
        await pool.close()
        await http_client.aclose()


def db() -> asyncpg.Pool:
    assert pool is not None, "DB pool not initialized"
    return pool


# ---------------------------------------------------------------------------
# 양식장 / 고객
# ---------------------------------------------------------------------------
# 고객 1명이 양식장을 여러 개 가질 수 있음 → farm_id 를 주면 그 양식장, 없으면 가장 먼저 등록한 양식장
# 좌표: 세부지역(region_id) 대표점 → 없으면 시군 대표점
FARM_SQL = """
SELECT
    f.farm_id::text           AS farm_id,
    f.customer_id,
    c.name                    AS customer_name,
    c.membership_status,
    f.farming_method,
    f.insurance_status,
    f.sigungu_name,
    f.town_name,
    COALESCE(ac.latitude, sg.latitude)::float8   AS lat,
    COALESCE(ac.longitude, sg.longitude)::float8 AS lon,
    COALESCE(
        array_agg(s.species_name ORDER BY s.species_id) FILTER (WHERE s.species_id IS NOT NULL),
        '{}'
    ) AS species
FROM customer_service.farms f
JOIN customer_service.customers c ON c.customer_id = f.customer_id
LEFT JOIN public.sigungu_area_coordinates ac ON ac.region_id = f.region_id
LEFT JOIN public.sigungu sg ON sg.sigungu_name = f.sigungu_name
LEFT JOIN customer_service.farm_species fs ON fs.farm_id = f.farm_id
LEFT JOIN customer_service.species s ON s.species_id = fs.species_id
WHERE f.customer_id = $1
  AND ($2::uuid IS NULL OR f.farm_id = $2::uuid)
GROUP BY f.farm_id, c.customer_id, ac.latitude, ac.longitude, sg.latitude, sg.longitude
ORDER BY f.created_at
LIMIT 1
"""


async def fetch_farm(customer_id: str, farm_id: Optional[UUID]) -> asyncpg.Record:
    row = await db().fetchrow(FARM_SQL, customer_id, farm_id)
    if row is None:
        raise HTTPException(status_code=404, detail="양식장 정보를 찾을 수 없어요")
    return row


def short_species(name: str) -> str:
    """'조피볼락(우럭)' → '우럭', '넙치' → '넙치'."""
    m = re.search(r"\(([^)]+)\)", name)
    return m.group(1).strip() if m else name.strip()


def short_region(sigungu: str) -> str:
    """'통영시' → '통영', '남해군' → '남해'."""
    return sigungu[:-1] if sigungu and sigungu[-1] in "시군구" and len(sigungu) > 2 else sigungu


# ---------------------------------------------------------------------------
# 관측소 매칭
# ---------------------------------------------------------------------------
STATIONS_SQL = """
SELECT station_id, sta_cde, sta_name, latitude::float8 AS lat, longitude::float8 AS lon
FROM public.stations
WHERE source = 'risa'
  AND latitude IS NOT NULL AND longitude IS NOT NULL
  AND COALESCE(is_active, end_date IS NULL)
  AND COALESCE(sur_tmp_yn, TRUE)
"""

STATION_BY_SIGUNGU_SQL = """
SELECT st.station_id, st.sta_cde, st.sta_name, m.risa_km::float8 AS km
FROM public.sigungu_station_map m
JOIN public.stations st ON st.station_id = m.risa_station_id
WHERE m.sigungu_name = $1
"""

_station_cache: tuple[float, list[dict]] = (float("-inf"), [])


async def get_stations() -> list[dict]:
    global _station_cache
    if _station_cache[1] and time.monotonic() - _station_cache[0] < STATION_CACHE_SEC:
        return _station_cache[1]
    rows = await db().fetch(STATIONS_SQL)
    stations = [dict(r) for r in rows]
    _station_cache = (time.monotonic(), stations)
    return stations


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


async def candidate_stations(lat: Optional[float], lon: Optional[float], sigungu: str) -> list[dict]:
    """가까운 순 관측소 후보. 각 항목에 km 포함."""
    if lat is not None and lon is not None:
        stations = await get_stations()
        ranked = sorted(
            ({**s, "km": round(haversine_km(lat, lon, s["lat"], s["lon"]), 1)} for s in stations),
            key=lambda s: s["km"],
        )
        # REALTIME_MAX_KM 안의 관측소만 후보 (멀리 있는 값은 그 바다를 대표하지 못함)
        return [s for s in ranked[:STATION_CANDIDATES] if s["km"] <= REALTIME_MAX_KM]
    row = await db().fetchrow(STATION_BY_SIGUNGU_SQL, sigungu)
    if row and (row["km"] is None or row["km"] <= REALTIME_MAX_KM):
        return [dict(row)]
    return []


# ---------------------------------------------------------------------------
# 실시간 수온: 국립수산과학원 RISA 웹 엔드포인트 (POST, 인증키 없음)
#   https://www.nifs.go.kr/risa/selectTodayObsvtrMap.do   obsvtrCd=<관측소코드>  → todayInfo
#   https://www.nifs.go.kr/risa/selectTodayObsvtrList.do  pageNo=1               → todayObsvtrList
#   ※ 공식 Open API 가 아니라 화면용 엔드포인트라 예고 없이 바뀔 수 있습니다.
#     실패하면 public.risa_observation → 오늘 예측값 순서로 자동 대체합니다.
#   todayInfo 필드 (실제 응답으로 확인):
#     obsvtrCd 관측소코드 / obsvtrKornNm, obsvtrNm 관측소명 / lat, lot 위경도
#     obsrvnDt 관측일시 / wtem 수온 / slntyS 염분 / doxnS 용존산소 / trn 탁도
#     sfclyrDpwt 표층 수심 / obsrvnExpln 관측 설명
#   필드명이 바뀌어도 버틸 수 있게 아래 후보 키를 차례로 보고, 그래도 없으면 패턴으로 찾습니다.
#   RISA_DEBUG=1 로 실행하면 받은 todayInfo 원본이 로그에 남습니다.
# ---------------------------------------------------------------------------
RISA_TEMP_KEYS = ("wtem", "wtrTmp", "wtrTemp", "srfWtrTmp", "surWtrTmp", "wtrTmpSrf", "waterTemp", "wtr_tmp", "tmp")
RISA_DATETIME_KEYS = ("obsrvnDt", "obsDtm", "obsDt", "obsrDt", "obsvtnDt", "obsDatetime", "regDt")
RISA_DATE_KEYS = ("obsDate", "obsDe", "obsDay", "obs_dat")
RISA_TIME_KEYS = ("obsTime", "obsTm", "obsHour", "obs_tim")
RISA_LAYER_KEYS = ("obsLay", "obsLayer", "obsvtrLayer", "layer", "obs_lay")
RISA_NAME_KEYS = ("obsvtrKornNm", "obsvtrNm", "obsvtrName", "staNm", "sta_nam_kor")
RISA_REPAIR_KEYS = ("rprYn", "rpr_yn", "repairYn")

_risa_cache: dict[str, tuple[float, Optional[dict]]] = {}

_DT_RE = re.compile(r"(\d{4})[-./]?(\d{2})[-./]?(\d{2})[ T]?(\d{2}):?(\d{2})(?::?(\d{2}))?")
_D_RE = re.compile(r"^(\d{4})[-./]?(\d{2})[-./]?(\d{2})$")
_T_RE = re.compile(r"^(\d{1,2}):?(\d{2})(?::?(\d{2}))?$")


def _first(d: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(str(v).replace("℃", "").strip())
    except (TypeError, ValueError):
        return None
    return f if -5.0 <= f <= 40.0 else None   # 해수 온도로 말이 안 되는 값은 버림


def _find_temp(d: dict) -> Optional[float]:
    v = _to_float(_first(d, RISA_TEMP_KEYS))
    if v is not None:
        return v
    # 후보 키가 없으면 이름에 tmp/temp 가 들어간 키 중 표층 → 일반 순으로 (기온 제외)
    keys = [k for k in d if re.search(r"tmp|temp|wtem", k, re.I) and not re.search(r"air|atm|ta$", k, re.I)]
    keys.sort(key=lambda k: 0 if re.search(r"sur|srf|top|1$", k, re.I) else 1)
    for k in keys:
        if (v := _to_float(d[k])) is not None:
            return v
    return None


def _epoch_to_kst(v: Any) -> Optional[datetime]:
    """1792473600000(ms) / 1792473600(s) 같은 숫자 시각 → KST."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        if not (isinstance(v, str) and v.isdigit() and len(v) == 13):
            return None
        v = int(v)
    if v > 1e11:          # 밀리초
        v = v / 1000
    if not (1e9 < v < 4e9):
        return None
    return datetime.fromtimestamp(v, tz=KST)


def _find_time(d: dict) -> Optional[datetime]:
    raw = _first(d, RISA_DATETIME_KEYS)
    if (epoch := _epoch_to_kst(raw)) is not None:
        return epoch
    if raw is None:
        day, tm = _first(d, RISA_DATE_KEYS), _first(d, RISA_TIME_KEYS)
        if day is not None and tm is not None:
            raw = f"{day} {tm}"
    candidates = [raw] if raw is not None else []
    # 그래도 없으면 모든 문자열 값에서 날짜+시각 패턴을 찾음
    candidates += [v for v in d.values() if isinstance(v, str)]
    for c in candidates:
        m = _DT_RE.search(str(c))
        if m:
            y, mo, da, h, mi, s = m.groups()
            try:
                return datetime(int(y), int(mo), int(da), int(h), int(mi), int(s or 0), tzinfo=KST)
            except ValueError:
                continue
    # 날짜와 시각이 다른 키에 따로 있는 경우
    day = next((m for v in d.values() if isinstance(v, str) and (m := _D_RE.match(v.strip()))), None)
    tm = next((m for v in d.values() if isinstance(v, str) and (m := _T_RE.match(v.strip()))), None)
    if day and tm:
        try:
            return datetime(int(day[1]), int(day[2]), int(day[3]), int(tm[1]), int(tm[2]), int(tm[3] or 0), tzinfo=KST)
        except ValueError:
            return None
    return None


def _is_surface(d: dict) -> bool:
    lay = _first(d, RISA_LAYER_KEYS)
    return lay is None or str(lay).strip() in ("1", "표층", "S", "SUR", "sur")


def parse_today_info(info: Any) -> Optional[dict]:
    """todayInfo(dict 또는 층별 list) → {"temp", "observed_at", "name"} (표층 최신값)."""
    rows = info if isinstance(info, list) else [info]
    rows = [r for r in rows if isinstance(r, dict)]
    best: Optional[dict] = None
    for r in rows:
        if not _is_surface(r):
            continue
        if str(_first(r, RISA_REPAIR_KEYS) or "N").upper() == "Y":
            continue  # 점검 중
        if re.search(r"점검|보수|고장|결측|수리", str(r.get("obsrvnExpln") or "")):
            continue  # 관측 설명에 이상 상태가 적혀 있으면 제외
        temp, obs = _find_temp(r), _find_time(r)
        if temp is None or obs is None:
            continue
        if best is None or obs > best["observed_at"]:
            best = {"temp": round(temp, 1), "observed_at": obs, "name": _first(r, RISA_NAME_KEYS)}
    return best


async def risa_post(path: str, params: dict) -> Any:
    res = await http_client.post(
        RISA_BASE_URL + path,
        data=params,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": RISA_BASE_URL + "main.do",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    res.raise_for_status()
    return res.json()


async def fetch_station_today(sta_cde: str) -> Optional[dict]:
    """관측소 하나의 최신 표층 수온 (실시간 호출, 관측소별 캐시)."""
    hit = _risa_cache.get(sta_cde)
    if hit and time.monotonic() < hit[0]:
        return hit[1]

    result: Optional[dict] = None
    ok = False
    try:
        payload = await risa_post("selectTodayObsvtrMap.do", {"obsvtrCd": sta_cde})
        info = payload.get("todayInfo") if isinstance(payload, dict) else None
        if RISA_DEBUG:
            log.info("RISA todayInfo %s: %s", sta_cde, json.dumps(info, ensure_ascii=False)[:2000])
        result = parse_today_info(info) if info else None
        if info and result is None:
            sample = info[0] if isinstance(info, list) and info else info
            sample = sample if isinstance(sample, dict) else {}
            log.warning("RISA %s 응답에서 수온/시각을 못 읽음. wtem=%r obsrvnDt=%r 키=%s", sta_cde,
                        sample.get("wtem"), sample.get("obsrvnDt"), sorted(sample.keys()))
        ok = True
    except (httpx.HTTPError, ValueError) as e:
        detail = f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else type(e).__name__
        log.warning("RISA %s 조회 실패: %s", sta_cde, detail)

    # 성공은 RISA_CACHE_SEC, 실패는 짧게 캐시해서 장애 때 매 요청마다 두드리지 않게
    _risa_cache[sta_cde] = (time.monotonic() + (RISA_CACHE_SEC if ok else RISA_FAIL_CACHE_SEC), result)
    return result


# obs_at 은 timestamp without time zone → KST 로 저장돼 있다고 가정 (TODO: 적재 코드 확인)
DB_LATEST_OBS_SQL = """
SELECT DISTINCT ON (station_id) station_id, obs_at, wtr_tmp::float8 AS wtr_tmp
FROM public.risa_observation
WHERE station_id = ANY($1::bigint[])
  AND obs_lay = 1
  AND wtr_tmp IS NOT NULL
  AND COALESCE(rpr_yn, 'N') <> 'Y'
  AND COALESCE(repair_gbn, '1') <> '2'
  AND obs_at >= $2
ORDER BY station_id, obs_at DESC
"""


async def resolve_from_candidates(candidates: list[dict]) -> tuple[Optional[dict], Optional[dict], str]:
    """(대체 경로) DB 관측소 후보를 가까운 순으로 보며 관측소별 RISA 값 → DB 적재값 순서로 확인.
    반환: (관측소, {"temp", "observed_at"}, source)   source = 'api' | 'db' | 'none'
    """
    if not candidates:
        return None, None, "none"

    stale_before = datetime.now(KST) - timedelta(hours=OBS_STALE_HOURS)
    # 후보(보통 1~3곳)를 동시에 호출
    async def db_latest() -> list:
        try:
            return await db().fetch(
                DB_LATEST_OBS_SQL, [c["station_id"] for c in candidates], stale_before.replace(tzinfo=None))
        except asyncpg.UndefinedTableError:
            log.warning("public.risa_observation 없음 → DB 대체값 없이 동작")
            return []

    api_results, db_rows = await asyncio.gather(
        asyncio.gather(*(fetch_station_today(c["sta_cde"]) for c in candidates)),
        db_latest(),
    )
    db_map = {
        r["station_id"]: {"temp": round(r["wtr_tmp"], 1), "observed_at": r["obs_at"].replace(tzinfo=KST)}
        for r in db_rows
    }

    for st, o in zip(candidates, api_results):
        if o and o["observed_at"] >= stale_before:
            return st, o, "api"
        if st["station_id"] in db_map:
            return st, db_map[st["station_id"]], "db"
    return None, None, "none"


# ---------------------------------------------------------------------------
# RISA 전체 관측소 최신값 (selectTodayObsvtrList.do)
#   지금 실제로 값을 보내는 관측소 목록 + 위치 + 최신 수온을 한 번에 받습니다.
#   DB 의 public.stations 에 빠진 관측소(예: 고성 장좌·고성 용정)도 이 목록으로 잡힙니다.
#   항목에 위경도가 없으면 searchRisaStationList.do (관측소 목록) 와 DB 좌표로 채웁니다.
# ---------------------------------------------------------------------------
RISA_CODE_KEYS = ("obsvtrCd", "staCde", "sta_cde")
RISA_LAT_KEYS = ("lat", "latitude", "la")
RISA_LON_KEYS = ("lot", "lon", "lng", "longitude", "lo")

_live_cache: tuple[float, list[dict]] = (float("-inf"), [])
_coord_cache: tuple[float, dict[str, dict]] = (float("-inf"), {})


def _coord(v: Any, lo: float, hi: float) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo <= f <= hi else None


def _row_position(r: dict) -> tuple[Optional[float], Optional[float]]:
    # 한국 주변 바다 범위 밖 값은 버림
    return _coord(_first(r, RISA_LAT_KEYS), 32.0, 39.5), _coord(_first(r, RISA_LON_KEYS), 124.0, 132.0)


async def risa_station_coords() -> dict[str, dict]:
    """관측소코드 → {"lat", "lon", "name"}. RISA 관측소 목록 + DB stations (1시간 캐시)."""
    global _coord_cache
    if time.monotonic() < _coord_cache[0]:
        return _coord_cache[1]
    coords: dict[str, dict] = {}
    for st in await get_stations():
        coords[st["sta_cde"]] = {"lat": st["lat"], "lon": st["lon"], "name": st["sta_name"]}
    try:
        payload = await risa_post("risa/risaC/searchRisaStationList.do", {"pageNo": 1, "rowCountPage": 500})
        for r in (payload.get("retList") or []) if isinstance(payload, dict) else []:
            code = str(_first(r, RISA_CODE_KEYS) or "").strip()
            lat, lon = _row_position(r)
            if code and lat is not None and lon is not None:
                coords[code] = {"lat": lat, "lon": lon, "name": _first(r, RISA_NAME_KEYS)}
    except (httpx.HTTPError, ValueError) as e:
        log.warning("RISA 관측소 목록 조회 실패: %s", type(e).__name__)
    _coord_cache = (time.monotonic() + STATION_CACHE_SEC, coords)
    return coords


async def risa_live_list() -> list[dict]:
    """[{"sta_cde", "sta_name", "lat", "lon", "obs"}] — 지금 값이 있는 RISA 관측소 전체 (5분 캐시)."""
    global _live_cache
    if time.monotonic() < _live_cache[0]:
        return _live_cache[1]

    rows: list[dict] = []
    seen: set[str] = set()
    ok = False
    try:
        for page in range(1, RISA_LIST_MAX_PAGES + 1):
            payload = await risa_post("selectTodayObsvtrList.do", {"pageNo": page})
            page_rows = (payload.get("todayObsvtrList") or []) if isinstance(payload, dict) else []
            new = [r for r in page_rows if isinstance(r, dict)
                   and str(_first(r, RISA_CODE_KEYS) or "") not in seen]
            if not new:            # 빈 페이지거나, 페이지 구분 없이 같은 목록이 반복되면 끝
                break
            for r in new:
                seen.add(str(_first(r, RISA_CODE_KEYS) or ""))
            rows.extend(new)
        ok = True
    except (httpx.HTTPError, ValueError) as e:
        log.warning("RISA 최신 수온 목록 조회 실패: %s", type(e).__name__)

    live: list[dict] = []
    if rows:
        if RISA_DEBUG:
            log.info("RISA todayObsvtrList %d건, 첫 항목: %s", len(rows), json.dumps(rows[0], ensure_ascii=False)[:1000])
        need_coords = any(None in _row_position(r) for r in rows)
        coords = await risa_station_coords() if need_coords else {}
        for r in rows:
            code = str(_first(r, RISA_CODE_KEYS) or "").strip()
            lat, lon = _row_position(r)
            if (lat is None or lon is None) and code in coords:
                lat, lon = coords[code]["lat"], coords[code]["lon"]
            obs = parse_today_info(r)
            if code and lat is not None and lon is not None and obs:
                live.append({"sta_cde": code, "sta_name": obs.get("name") or coords.get(code, {}).get("name") or code,
                             "lat": lat, "lon": lon, "obs": obs})
        if not live:
            log.warning("RISA 최신 수온 목록에서 쓸 수 있는 항목이 없음. 첫 항목 키: %s", sorted(rows[0].keys()))

    _live_cache = (time.monotonic() + (RISA_CACHE_SEC if ok else RISA_FAIL_CACHE_SEC), live)
    return live


async def resolve_realtime(lat: Optional[float], lon: Optional[float], sigungu: str
                           ) -> tuple[Optional[dict], Optional[dict], str]:
    """양식장 위치에서 REALTIME_MAX_KM 안에 있는, 지금 값이 있는 가장 가까운 관측소를 고릅니다.
      1) RISA 전체 최신 목록 (DB 에 없는 관측소 포함)
      2) 1)이 실패하면 DB 관측소 후보 → 관측소별 RISA 호출 → DB 적재값
    반환: (관측소, {"temp", "observed_at"}, source)   source = 'api' | 'db' | 'none'
    """
    stale_before = datetime.now(KST) - timedelta(hours=OBS_STALE_HOURS)
    if lat is not None and lon is not None:
        live = await risa_live_list()
        ranked = sorted(
            ({**s, "km": round(haversine_km(lat, lon, s["lat"], s["lon"]), 1)}
             for s in live if s["obs"]["observed_at"] >= stale_before),
            key=lambda s: s["km"],
        )
        if ranked and ranked[0]["km"] <= REALTIME_MAX_KM:
            best = ranked[0]
            return {"sta_cde": best["sta_cde"], "sta_name": best["sta_name"], "km": best["km"]}, best["obs"], "api"
        if ranked:
            log.info("가장 가까운 실시간 관측소가 %.1fkm (%s) → %skm 밖이라 사용 안 함",
                     ranked[0]["km"], ranked[0]["sta_name"], REALTIME_MAX_KM)
            return None, None, "none"
    # 전체 목록을 못 받았거나 좌표가 없을 때
    return await resolve_from_candidates(await candidate_stations(lat, lon, sigungu))

# ---------------------------------------------------------------------------
# 예측 수온: public.example 또는 public.roms_forecast (격자, 컬럼 구조 동일)
#   predc_dt 는 timestamp without time zone → KST 로 가정 (TODO: 적재 코드 확인)
#   양식장 좌표에서 가장 가까운, 값이 있는 격자점 하나를 골라 일별 평균/최고를 냅니다.
# ---------------------------------------------------------------------------
FORECAST_SQL = """
WITH grid AS (
    SELECT lat, lot
    FROM {table}
    WHERE predc_dt >= $3 AND predc_dt < $4
      AND wtem IS NOT NULL
      AND lat BETWEEN $1::float8 - $5::float8 AND $1::float8 + $5::float8
      AND lot BETWEEN $2::float8 - $5::float8 AND $2::float8 + $5::float8
    GROUP BY lat, lot
    ORDER BY power(lat - $1::float8, 2) + power((lot - $2::float8) * cos(radians($1::float8)), 2)
    LIMIT 1
)
SELECT e.predc_dt::date AS day,
       avg(e.wtem)::float8 AS avg_t,
       max(e.wtem)::float8 AS max_t
FROM {table} e
JOIN grid g ON g.lat = e.lat AND g.lot = e.lot
WHERE e.predc_dt >= $3 AND e.predc_dt < $4
  AND e.wtem IS NOT NULL
GROUP BY 1
ORDER BY 1
"""


_forecast_table: Optional[str] = None
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


async def get_forecast_table() -> Optional[str]:
    """사용할 예측 테이블 이름. 한 번 찾으면 캐시. 없으면 None."""
    global _forecast_table
    if _forecast_table:
        return _forecast_table
    candidates = (FORECAST_TABLE,) if FORECAST_TABLE else FORECAST_TABLE_CANDIDATES
    for name in candidates:
        if not _TABLE_NAME_RE.match(name):
            log.warning("FORECAST_TABLE 형식이 잘못됨: %s (schema.table 형식)", name)
            continue
        if await db().fetchval("SELECT to_regclass($1) IS NOT NULL", name):
            _forecast_table = name
            log.info("예측 수온 테이블: %s", name)
            return name
    log.warning("예측 수온 테이블을 찾지 못함 (확인한 이름: %s) → 예측 없이 동작", ", ".join(candidates))
    return None


async def fetch_forecast(lat: Optional[float], lon: Optional[float], today: date) -> list[ForecastDay]:
    if lat is None or lon is None:
        return []
    table = await get_forecast_table()
    if not table:
        return []
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=FORECAST_DAYS + 1)   # 오늘 + 앞으로 7일
    # 테이블 이름은 위 후보/형식 검사를 통과한 값만 들어감
    rows = await db().fetch(FORECAST_SQL.format(table=table), lat, lon, start, end, GRID_SEARCH_DEG)
    return [ForecastDay(date=r["day"], avg=round(r["avg_t"], 1), max=round(r["max_t"], 1)) for r in rows]


def summarize_forecast(days: list[ForecastDay], today: date, now: Optional[float]) -> Optional[Forecast]:
    """앞으로 7일 예측 전체를 보고 흐름을 한 문장용으로 요약합니다.
    기준값(현재 수온)보다
      - 최고값이 FORECAST_CHANGE_DEG 이상 높으면 'rise' : 'N일 뒤 X℃까지 오를 것으로 예측돼요'
      - 최저값이 FORECAST_CHANGE_DEG 이상 낮으면 'fall' : 'N일 뒤 X℃까지 내려갈 것으로 예측돼요'
      - 둘 다 아니면 'flat'                          : '앞으로 7일 동안 X~Y℃로 큰 변화 없을 것으로 예측돼요'
    오르는 흐름과 내리는 흐름이 함께 있으면 위험 쪽(오름)을 먼저 알려 줍니다.
    """
    future = [d for d in days if d.date > today]
    if not future:
        return None
    if now is None:
        today_fc = next((d for d in days if d.date == today), None)
        now = today_fc.avg if today_fc else future[0].avg

    hi = max(future, key=lambda d: (d.avg, -d.date.toordinal()))   # 같은 값이면 더 이른 날
    lo = min(future, key=lambda d: (d.avg, d.date.toordinal()))
    span = (future[-1].date - today).days
    common = dict(spanDays=span, min=lo.avg, max=hi.avg)

    if hi.avg - now >= FORECAST_CHANGE_DEG:
        return Forecast(trend="rise", days=(hi.date - today).days, temp=hi.avg, **common)
    if now - lo.avg >= FORECAST_CHANGE_DEG:
        return Forecast(trend="fall", days=(lo.date - today).days, temp=lo.avg, **common)
    return Forecast(trend="flat", days=span, temp=hi.avg, **common)


# ---------------------------------------------------------------------------
# 고수온 단계
# ---------------------------------------------------------------------------
SCREEN3_SQL = """
SELECT risk_level, is_official, streak_ge28
FROM public.screen3_current
WHERE sigungu_name = $1
"""


def compute_level(now: Optional[float], days: list[ForecastDay], today: date) -> SeaLevel:
    if now is None and not days:
        return SeaLevel.unknown
    # 오늘부터 이어지는 28℃ 이상 일수 (오늘은 실측 우선)
    seq = [now if d.date == today and now is not None else d.avg for d in days if d.date >= today]
    if not seq and now is not None:
        seq = [now]
    streak = 0
    for t in seq:
        if t < ALERT_TEMP:
            break
        streak += 1

    if now is not None and now >= ALERT_TEMP and streak >= ALERT_STREAK_DAYS:
        return SeaLevel.alert
    if now is not None and now >= CAUTION_TEMP:
        return SeaLevel.caution
    if any(d.avg >= WATCH_TEMP for d in days):
        return SeaLevel.watch
    return SeaLevel.normal


async def decide_level(sigungu: str, now: Optional[float], days: list[ForecastDay], today: date
                       ) -> tuple[SeaLevel, bool]:
    """공식 특보(screen3_current.is_official)가 있으면 그 값, 없으면 앱 기준 계산."""
    try:
        row = await db().fetchrow(SCREEN3_SQL, sigungu)
    except asyncpg.UndefinedTableError:
        log.warning("public.screen3_current 없음 → 앱 기준으로 단계 계산")
        row = None
    if row and row["is_official"]:
        return RISK_TO_LEVEL.get(row["risk_level"], SeaLevel.unknown), True
    return compute_level(now, days, today), False


# ---------------------------------------------------------------------------
# 보험 보장 정보 (finance 스키마)
# ---------------------------------------------------------------------------
COVER_COLUMNS: list[tuple[str, str]] = [
    ("cov_typhoon", "태풍"), ("cov_tidal_wave", "해일"), ("cov_high_seas", "풍랑"),
    ("cov_heavy_rain", "호우"), ("cov_flood", "홍수"), ("cov_heavy_snow", "대설"),
    ("cov_cold_wave", "한파"), ("cov_high_water_temp", "고수온"), ("cov_low_water_temp", "저수온"),
    ("cov_red_tide", "적조"), ("cov_low_salinity", "저염분"), ("cov_nutrients", "영양염류"),
    ("cov_dissolved_oxygen", "용존산소"),
]

# 상품군별 테이블. 해상 전복만 별도 테이블이 있고 나머지는 fin_ins_land_* 사용
# TODO: fin_ins_land_* 가 '육상' 전용인지, 해상 가두리 어종도 포함하는지 확인 필요
PRODUCT_TABLES = {
    "land": ("finance.fin_ins_land_product", "finance.fin_ins_land_rider", "finance.fin_ins_land_exclusion"),
    "sea_abalone": ("finance.sea_abalone_insurance_product", "finance.sea_abalone_insurance_rider",
                    "finance.sea_abalone_insurance_exclusion"),
}


def pick_product_family(species: list[str], method: str) -> str:
    if method == "cage" and any("전복" in s for s in species):
        return "sea_abalone"
    return "land"


# cov_* 컬럼은 자유 텍스트라 키워드로 분류합니다.
# TODO: 실제 값 분포를 보고 규칙을 확정하세요. (SELECT DISTINCT cov_high_water_temp ...)
_EXCLUDED_RE = re.compile(r"미보장|불보장|보장\s*(안|않|제외|불가)|제외|해당\s*없|비보장|^\s*[X×✕N\-]\s*$")
_RIDER_RE = re.compile(r"특약|선택|추가\s*가입")
_BASIC_RE = re.compile(r"보장|기본|포함|^\s*[O○◯Y]\s*$")


def classify_cover(text: Optional[str]) -> CoverType:
    if text is None or not str(text).strip():
        return CoverType.unknown
    t = str(text)
    if _RIDER_RE.search(t):
        return CoverType.rider
    if _EXCLUDED_RE.search(t):
        return CoverType.excluded
    if _BASIC_RE.search(t):
        return CoverType.basic
    return CoverType.unknown


async def fetch_insurance(status: str, species: list[str], method: str) -> Insurance:
    ins = Insurance(status=InsuranceStatus(status))
    if not species:
        return ins

    product_t, rider_t, excl_t = PRODUCT_TABLES[pick_product_family(species, method)]
    names = sorted({n.strip() for s in species for n in (s, short_species(s), re.sub(r"\(.*?\)", "", s)) if n.strip()})
    cols = ", ".join(c for c, _ in COVER_COLUMNS)

    # 테이블명은 위 상수에서만 오므로 f-string 사용 (사용자 입력 아님)
    product = await db().fetchrow(
        f"""SELECT product_id, product_name, {cols}
            FROM {product_t}
            WHERE EXISTS (
                SELECT 1 FROM unnest($1::text[]) AS n(name)
                WHERE item ILIKE '%' || n.name || '%'      -- 상품 품목에 어종명이 들어 있거나
                   OR n.name ILIKE '%' || item || '%'      -- 어종명에 상품 품목이 들어 있으면
            )
            ORDER BY revision_date DESC
            LIMIT 1""",
        names,
    )
    if product is None:
        return ins

    riders = await db().fetch(
        f"""SELECT rider_name, target_disaster FROM {rider_t}
            WHERE product_id = $1 ORDER BY rider_order""",
        product["product_id"],
    )
    exclusions = await db().fetch(
        f"""SELECT summary FROM {excl_t}
            WHERE product_id = $1 AND summary IS NOT NULL
            ORDER BY exclusion_order LIMIT 3""",
        product["product_id"],
    )

    cover = {label: classify_cover(product[col]) for col, label in COVER_COLUMNS}
    # 특약 대상 재해에 들어 있으면 '특약으로 보장'으로 보정
    for r in riders:
        target = r["target_disaster"] or ""
        for label in cover:
            if label in target and cover[label] != CoverType.basic:
                cover[label] = CoverType.rider

    ins.productName = product["product_name"]
    ins.highTemp = cover["고수온"]
    ins.riderName = next(
        (r["rider_name"] for r in riders if "고수온" in (r["target_disaster"] or "") + (r["rider_name"] or "")),
        None,
    )
    ins.coverage = Coverage(
        basic=[k for k, v in cover.items() if v == CoverType.basic],
        rider=[k for k, v in cover.items() if v == CoverType.rider],
        excluded=[k for k, v in cover.items() if v == CoverType.excluded],
    )
    ins.exclusions = [r["summary"] for r in exclusions]
    return ins


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
app = FastAPI(title="우리 바다 안심도우미 - 홈 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: 운영 도메인으로 제한
    allow_methods=["GET"],
    allow_headers=["*"],
)


HOME_HTML = Path(__file__).with_name("home_test.html")


@app.get("/", include_in_schema=False)
async def home_page():
    """같은 폴더의 home.html 을 보여 줍니다.  예: http://localhost:8000/?customer=C-901"""
    if not HOME_HTML.exists():
        return PlainTextResponse(f"home.html 이 없어요. {HOME_HTML.parent} 폴더에 두세요.", status_code=404)
    return FileResponse(HOME_HTML, media_type="text/html; charset=utf-8")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/home/{customer_id}", response_model=HomeResponse)
async def get_home(customer_id: str, farm_id: Optional[UUID] = None) -> HomeResponse:
    f = await fetch_farm(customer_id, farm_id)
    today = datetime.now(KST).date()
    species: list[str] = list(f["species"])

    # 수온
    station, realtime, source = await resolve_realtime(f["lat"], f["lon"], f["sigungu_name"])
    forecast_days = await fetch_forecast(f["lat"], f["lon"], today)

    if realtime:
        now_temp, updated_at, is_forecast = realtime["temp"], realtime["observed_at"], False
    else:
        today_fc = next((d for d in forecast_days if d.date == today), None)
        now_temp = today_fc.avg if today_fc else None
        updated_at = datetime.now(KST)
        is_forecast = today_fc is not None
        source = "forecast" if today_fc else "none"

    level, is_official = await decide_level(f["sigungu_name"], now_temp, forecast_days, today)

    return HomeResponse(
        farm=Farm(
            farmId=f["farm_id"],
            region=short_region(f["sigungu_name"]),
            regionFull=f"{f['sigungu_name']} {f['town_name']}".strip(),
            species=", ".join(species) if species else "어종 미등록",
            shortName=short_species(species[0]) if species else "양식장",
            method=FARMING_METHOD_LABEL.get(f["farming_method"], f["farming_method"]),
        ),
        sea=Sea(
            level=level,
            isOfficial=is_official,
            now=now_temp,
            forecast=summarize_forecast(forecast_days, today, now_temp),
            updatedAt=updated_at.astimezone(KST).strftime("%m/%d %H:%M"),
            isForecast=is_forecast,
            source=source,
            stationName=station["sta_name"] if station else None,
            stationDistanceKm=station.get("km") if station else None,
            forecast7d=forecast_days,
        ),
        insurance=await fetch_insurance(f["insurance_status"], species, f["farming_method"]),
    )


@app.get("/api/debug/realtime/{customer_id}")
async def debug_realtime(customer_id: str, farm_id: Optional[UUID] = None) -> dict:
    """실시간 수온이 왜 그 값(또는 예측값)이 됐는지 단계별로 보여주는 진단용 API.
    예: http://localhost:8000/api/debug/realtime/C-901   (운영 배포 전에는 막아 두세요)"""
    f = await fetch_farm(customer_id, farm_id)
    lat, lon = f["lat"], f["lon"]
    now = datetime.now(KST)
    stale_before = now - timedelta(hours=OBS_STALE_HOURS)
    out: dict[str, Any] = {
        "farm": {"region": f"{f['sigungu_name']} {f['town_name']}", "lat": lat, "lon": lon},
        "settings": {"REALTIME_MAX_KM": REALTIME_MAX_KM, "OBS_STALE_HOURS": OBS_STALE_HOURS},
    }

    # 1) RISA 목록 원본 (캐시 무시하고 새로 호출)
    raw_rows: list = []
    try:
        payload = await risa_post("selectTodayObsvtrList.do", {"pageNo": 1})
        out["list_top_keys"] = sorted(payload.keys()) if isinstance(payload, dict) else str(type(payload))
        raw_rows = (payload.get("todayObsvtrList") or []) if isinstance(payload, dict) else []
        out["list_page1_count"] = len(raw_rows)
        out["list_first_item"] = raw_rows[0] if raw_rows else None
    except Exception as e:  # 진단용이라 모든 오류를 그대로 보여줌
        out["list_error"] = f"{type(e).__name__}: {e}"

    # 2) 파싱 결과
    global _live_cache
    _live_cache = (float("-inf"), [])
    live = await risa_live_list()
    out["parsed_live_count"] = len(live)
    if raw_rows and not live:
        r0 = raw_rows[0]
        out["parse_check_first_item"] = {
            "code": _first(r0, RISA_CODE_KEYS), "position": _row_position(r0),
            "parsed": parse_today_info(r0),
        }

    # 3) 가까운 관측소 5곳
    if lat is not None and lon is not None:
        ranked = sorted(
            ({"sta_cde": s["sta_cde"], "name": s["sta_name"],
              "km": round(haversine_km(lat, lon, s["lat"], s["lon"]), 1),
              "temp": s["obs"]["temp"], "observed_at": s["obs"]["observed_at"].strftime("%Y-%m-%d %H:%M"),
              "fresh": s["obs"]["observed_at"] >= stale_before} for s in live),
            key=lambda x: x["km"],
        )[:5]
        out["nearest_live"] = ranked

    # 4) 실제 선택 결과
    station, obs, source = await resolve_realtime(lat, lon, f["sigungu_name"])
    out["result"] = {"source": source, "station": station,
                     "temp": obs["temp"] if obs else None,
                     "observed_at": obs["observed_at"].strftime("%Y-%m-%d %H:%M") if obs else None}
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


@app.get("/api/farms", response_model=list[FarmSummary])
async def list_farms(
    species: Optional[str] = Query(None, description="어종명 일부 (예: 우럭, 넙치)"),
    sigungu: Optional[str] = Query(None, description="시군구 (예: 통영시)"),
    town: Optional[str] = Query(None, description="읍면동 (예: 산양읍)"),
    insurance: Optional[InsuranceStatus] = Query(None, description="insured | uninsured | unknown"),
    method: Optional[str] = Query(None, pattern="^(cage|land_based)$", description="cage | land_based"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[FarmSummary]:
    """값을 준 조건만 적용합니다. 어종은 양식장의 어종 중 하나라도 맞으면 포함."""
    rows = await db().fetch(
        """
        SELECT f.farm_id::text AS farm_id, f.customer_id, c.name, c.membership_status,
               f.sigungu_name, f.town_name, f.farming_method, f.insurance_status,
               COALESCE(array_agg(s.species_name ORDER BY s.species_id)
                        FILTER (WHERE s.species_id IS NOT NULL), '{}') AS species
        FROM customer_service.farms f
        JOIN customer_service.customers c ON c.customer_id = f.customer_id
        LEFT JOIN customer_service.farm_species fs ON fs.farm_id = f.farm_id
        LEFT JOIN customer_service.species s ON s.species_id = fs.species_id
        WHERE ($1::text IS NULL OR f.sigungu_name = $1)
          AND ($2::text IS NULL OR f.town_name = $2)
          AND ($3::text IS NULL OR f.insurance_status = $3)
          AND ($4::text IS NULL OR f.farming_method = $4)
        GROUP BY f.farm_id, c.customer_id
        HAVING $5::text IS NULL OR bool_or(s.species_name ILIKE '%' || $5 || '%')
        ORDER BY f.created_at
        LIMIT $6 OFFSET $7
        """,
        sigungu, town, insurance.value if insurance else None, method, species, limit, offset,
    )
    return [
        FarmSummary(
            farmId=r["farm_id"],
            customerId=r["customer_id"],
            customerName=r["name"],
            membership=r["membership_status"],
            regionFull=f"{r['sigungu_name']} {r['town_name']}".strip(),
            species=list(r["species"]),
            method=FARMING_METHOD_LABEL.get(r["farming_method"], r["farming_method"]),
            insurance=InsuranceStatus(r["insurance_status"]),
        )
        for r in rows
    ]
