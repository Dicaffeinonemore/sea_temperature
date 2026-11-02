"""연락 우선순위 · 상담 홈 수온 지역 API (상담 홈 · 어가 상세 공통)

이전에는 연락 순서 점수가 consult_home.html 과 farm_detail.html 안(JavaScript)에 각각 들어 있었습니다.
이 파일이 계산의 단일 출처이고, 두 화면은 결과만 받아 그립니다.

판정 규칙은 새로 만들지 않고 farm_detail.py 의 것을 그대로 씁니다 (어가 상세와 같은 결과).
  - 위험 단계      : fd.day_stages  (고수온 일최고 25·28℃·28℃ 3일 / 저수온 일최저 7·4℃·4℃ 3일, ROMS 7일)
  - 어종 한계 수온 : fd.species_risk (7일 안에 닿으면 그 어종은 최소 '주의')
  - 보장 상태      : fd.heat_profile + fd.heat_status (insurance_coverages 의 주계약/특약/부담보)
  - 판매 기간      : fd.sale_state (insurance_products.sale_period)

점수 (가중치는 public.priority_weights 에서 읽고, 없는 키는 아래 DEFAULT_WEIGHTS)
  위험 단계(관심 10 · 주의 30 · 경보 40)
  + 도달 임박도 (주의 이상일 때 (7 - 도달일) × 2)
  + 보장 공백 (미가입·만료 25 · 특약 없음 20 · 고수온 미보장 상품 20 · 확인 필요 15 · 부담보 10)
  + 지금 가입 가능 20 (공백이 있고, 판매 기간이고, 공식 특보 전인 지역)
  + 어종 한계 수온 도달 10
  어가 점수 = 가장 급한 어종(계약)의 점수

연락 목록에 올리는 조건 (list_reason)
  stage : 주의 이상
  alert : 관심 + 공식 특보 발령 지역
  soon  : 관심 + 보장 공백 + 이번 달 판매 마감

엔드포인트
  GET  /api/consult/forecast-regions?mode=      상담 홈 지역 카드 · 21일 수온 (화면 ENDPOINTS.regions)
  GET  /api/consult/priority?mode=              어가별 점수·순위·목록 사유 (화면이 바로 씀)
  POST /api/consult/priority/refresh?mode=      같은 계산 결과를 customer_service.contact_queue 에 저장 (n8n 예약 실행용)
  base_date=YYYY-MM-DD 를 붙이면 그 날짜 기준으로 계산 (시연·검증용)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from psycopg import Connection
from psycopg.types.json import Jsonb

from backend import farm_detail as fd
from backend.customer_api import request_protection
from backend.db import get_customer_db, get_db

log = logging.getLogger(__name__)

Mode = Literal["heat", "cold"]

DEFAULT_WEIGHTS: dict[str, float] = {
    "stage_watch": 10, "stage_caution": 30, "stage_alert": 40,   # 위험 단계 (정상 0)
    "per_day": 2,                                                # 주의 이상: (7 - 도달일) × per_day
    "gap_none": 25, "gap_expired": 25, "gap_norider": 20, "gap_noheat": 20,
    "gap_unknown": 15, "gap_excl": 10,                           # 보장 공백 (보장됨·청약 중 0)
    "can_buy": 20,                                               # 지금 가입 가능
    "species_hit": 10,                                           # 7일 안 어종 한계 수온 도달
}
GAP_INS = ("none", "expired", "norider", "noheat", "unknown", "excl")   # 점수상 보장 공백
NO_BUY_INS = ("full", "pending", "excl", "noheat")   # '지금 가입 가능' 점수를 주지 않는 상태
NOT_GAP_FOR_SOON = ("full", "pending", "excl")       # '판매 마감 임박' 사유에서 뺄 상태


def short_sigungu(name: Optional[str]) -> Optional[str]:
    """consult.py 의 REGION_SHORT(시·군 접미사 제거)와 같은 규칙 → 화면의 region 값과 일치."""
    return re.sub(r"(시|군)$", "", name) if name else None


def load_weights(db: Connection) -> dict[str, float]:
    w = dict(DEFAULT_WEIGHTS)
    try:
        with db.transaction():   # 테이블이 없어도 연결이 깨지지 않게 (savepoint)
            rows = db.execute("SELECT key, value FROM public.priority_weights").fetchall()
    except Exception as exc:   # noqa: BLE001 - 가중치 표가 없으면 기본값으로 계산
        log.warning("priority_weights 조회 실패, 기본 가중치 사용 (%s)", type(exc).__name__)
        return w
    unknown = []
    for r in rows:
        if r["key"] in w:
            w[r["key"]] = float(r["value"])
        else:
            unknown.append(r["key"])
    if unknown:
        log.info("priority_weights 에서 쓰지 않는 키: %s", ", ".join(unknown))
    return w


# ---------------------------------------------------------------------------
# 1. 지역별 수온 · 위험 단계 (시군 단위 = 화면의 region)
# ---------------------------------------------------------------------------

def _daily(db: Connection, table: str, region: str, start: date, end: date) -> list[dict]:
    rows = db.execute(f"""
        SELECT day, max_c::float8 AS max, mean_c::float8 AS mean, min_c::float8 AS min
        FROM public.{table} WHERE region = %s AND day BETWEEN %s AND %s ORDER BY day
    """, (region, start, end)).fetchall()
    return [dict(r) for r in rows]


def _bias(db: Connection, om_region: str) -> Optional[float]:
    r = db.execute("SELECT bias::float8 AS bias FROM public.om_region_bias WHERE region = %s",
                   (om_region,)).fetchone()
    return r["bias"] if r else None


def _r1(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 1)


def build_regions(db: Connection, today: date) -> dict[str, dict]:
    """시군(짧은 이름) → 지역 수온·단계. fd._MODE 가 정해진 상태에서 호출."""
    sig = db.execute("""
        SELECT sigungu_name, avg(latitude)::float8 AS lat, avg(longitude)::float8 AS lon
        FROM public.sigungu_area_coordinates GROUP BY sigungu_name
    """).fetchall()
    roms_regions = [dict(r) for r in db.execute(
        "SELECT region, lat::float8 AS lat, lon::float8 AS lon FROM public.roms_regions").fetchall()]
    om_regions = [dict(r) for r in db.execute(
        "SELECT region, lat::float8 AS lat, lon::float8 AS lon FROM public.om_regions").fetchall()]

    last7 = today + timedelta(days=fd.FORECAST_DAYS - 1)
    lookback_start = today - timedelta(days=fd.ALERT_STREAK_DAYS - 1)
    cache: dict[tuple[str, str], Any] = {}
    out: dict[str, dict] = {}
    for s in sig:
        short = short_sigungu(s["sigungu_name"])
        if short in out:
            continue
        roms_r = fd.pick_region(roms_regions, s["sigungu_name"], s["lat"], s["lon"])
        om_r = fd.pick_region(om_regions, s["sigungu_name"], s["lat"], s["lon"])
        if not roms_r:
            continue
        key = (roms_r["region"], om_r["region"] if om_r else "")
        if key not in cache:
            roms_all = _daily(db, "example_region_daily", roms_r["region"], lookback_start, last7)
            past = [r for r in roms_all if r["day"] < today]
            roms = [r for r in roms_all if r["day"] >= today]
            om, bias = [], None
            if om_r:
                om = _daily(db, "example_region_daily_om", om_r["region"], last7 + timedelta(days=1),
                            today + timedelta(days=fd.EXTENDED_DAYS - 1))
                bias = _bias(db, om_r["region"])
                if bias is not None:   # 8~21일은 ROMS 기준으로 보정해서 보여줌 (forecast_21d 와 같은 방식)
                    om = [{**r, **{k: (r[k] + bias if r[k] is not None else None) for k in ("max", "mean", "min")}}
                          for r in om]
            vals = [fd.metric(r) for r in roms]
            stages = [x["stage"] for x in fd.day_stages(vals, [fd.metric(r) for r in past])]
            cache[key] = (roms, om, vals, stages, bias)
        roms, om, vals, stages, bias = cache[key]
        if not roms:
            continue   # 오늘부터의 예측이 없는 지역은 빼고, 화면이 '예측 없음' 안내
        top = max(stages)
        alert = fd.OFFICIAL_ALERTS.get(short or "") or fd.OFFICIAL_ALERTS.get(roms_r["region"])
        series = ([{"i": (r["day"] - today).days, "max": _r1(r["max"]), "mean": _r1(r["mean"]), "min": _r1(r["min"]),
                    "src": "ROMS"} for r in roms]
                  + [{"i": (r["day"] - today).days, "max": _r1(r["max"]), "mean": _r1(r["mean"]), "min": _r1(r["min"]),
                      "src": "ECMWF"} for r in om])
        out[short] = {
            "id": short, "roms_region": roms_r["region"], "om_region": om_r["region"] if om_r else None,
            "trend": fd.trend_of(om) or "flat", "bias": {"diff": _r1(bias), "own": None},
            "alert": alert, "series": series,
            "stages": stages,                    # ROMS 날짜별 단계 (화면은 이 값을 그대로 씀)
            "top": top, "d": stages.index(top),  # 7일 중 가장 높은 단계와 그 단계가 처음 나오는 날
            "_roms_days": [{"day": r["day"], "value": v} for r, v in zip(roms, vals)],
        }
    return out


def regions_payload(regions: dict[str, dict], today: date) -> dict:
    return {"base_date": today.isoformat(), "mode": fd.M()["id"],
            "regions": [{k: v for k, v in r.items() if not k.startswith("_")} for r in regions.values()]}


# ---------------------------------------------------------------------------
# 2. 어종(계약)별 보장 상태 · 판매 기간
# ---------------------------------------------------------------------------

def _riders(rd: Any) -> list[str]:
    if isinstance(rd, str):
        rd = json.loads(rd or "{}")
    return list((rd or {}).get("riders") or [])


def load_items(db: Connection, today: date) -> dict[int, list[dict]]:
    """household_id → 어종 목록. 어종마다 ins(보장 상태 코드)와 판매 기간을 붙임."""
    species = [dict(r) for r in db.execute("""
        SELECT m.household_id, m.mapping_id, m.species_id, m.is_primary, s.standard_name, s.common_name
        FROM customer_service.household_species m
        JOIN customer_service.fish_species s ON s.species_id = m.species_id
        WHERE m.status <> '폐업'
        ORDER BY m.household_id, m.is_primary DESC, m.mapping_id
    """).fetchall()]
    # 수산물 계약만 (시설물 계약은 어종 보장과 무관) - consult.py 와 같은 기준
    contracts = db.execute("""
        SELECT t.mapping_id, c.insurance_id, c.product_id, c.contract_status AS status,
               c.start_date, c.end_date, t.rider_details
        FROM customer_service.insurance_targets t
        JOIN customer_service.insurance_contracts c ON c.insurance_id = t.insurance_id
        JOIN customer_service.household_species m ON m.mapping_id = t.mapping_id
        WHERE EXISTS (SELECT 1 FROM insurance.insurance_map im
                      WHERE im.product_id = c.product_id AND im.species_id = m.species_id
                        AND im.coverage_target = '수산물')
    """).fetchall()
    by_mapping: dict[int, list[tuple[dict, dict]]] = {}
    for r in contracts:
        by_mapping.setdefault(r["mapping_id"], []).append(
            ({"insurance_id": r["insurance_id"], "product_id": r["product_id"], "status": r["status"],
              "start_date": r["start_date"], "end_date": r["end_date"]},
             {"riders": _riders(r["rider_details"])}))
    cand: dict[int, list[int]] = {}
    for r in db.execute("""SELECT species_id, product_id FROM insurance.insurance_map
                           WHERE coverage_target = '수산물' ORDER BY product_id""").fetchall():
        cand.setdefault(r["species_id"], []).append(r["product_id"])
    products = {r["product_id"]: dict(r) for r in db.execute(
        "SELECT product_id, product_name, sale_period FROM insurance.insurance_products").fetchall()}
    covs: dict[int, list[dict]] = {}
    for r in db.execute("""SELECT product_id, coverage_key, contract_type, name, risk_types, effect
                           FROM insurance.insurance_coverages ORDER BY product_id, coverage_key""").fetchall():
        covs.setdefault(r["product_id"], []).append(dict(r))
    perils, word = fd.M()["perils"], fd.M()["word"]
    profiles = {pid: fd.heat_profile(c, perils) for pid, c in covs.items()}
    empty = fd.heat_profile([], perils)

    def product(pid: Optional[int]) -> Optional[dict]:
        if pid is None:
            return None
        p, prof = products.get(pid, {}), profiles.get(pid, empty)
        return {"product_id": pid, "name": p.get("product_name") or f"상품 {pid}",
                "heat": "base" if prof["main"] else "rider" if prof["riders"] else None,
                "sale": fd.sale_state(p.get("sale_period"), today)}

    out: dict[int, list[dict]] = {}
    for sp in species:
        chosen, state = fd.pick_contract(by_mapping.get(sp["mapping_id"], []), today)
        if chosen and state in ("active", "pending"):
            c, t = chosen
            if not covs.get(c["product_id"]):
                ins = "unknown" if state == "active" else "pending"
            else:
                ins, _ = fd.heat_status(profiles[c["product_id"]], t["riders"], perils, word)
                ins = "pending" if state == "pending" else ins
            prod = product(c["product_id"])
        else:
            # 미가입 · 만료 → 추천 상품 (farm_detail.build_cards 와 같은 순서)
            prev = chosen[0]["product_id"] if chosen else None
            pids = list(cand.get(sp["species_id"], []))
            if prev and prev not in pids:
                pids.insert(0, prev)

            def rank(pid: int) -> tuple:
                pr = profiles.get(pid, empty)
                sale = fd.sale_state(products.get(pid, {}).get("sale_period"), today)["code"]
                return (pid != prev, not pr["main"], not pr["riders"], sale in ("later", "closed"), pid)
            pids = sorted(set(pids), key=rank)
            ins = "expired" if state == "expired" else ("none" if pids else "unknown")
            prod = product(pids[0]) if pids else None
        out.setdefault(sp["household_id"], []).append({**sp, "ins": ins, "product": prod})
    return out


# ---------------------------------------------------------------------------
# 3. 점수 · 목록 사유 · 순위
# ---------------------------------------------------------------------------

def score_item(stage: int, region: dict, sp: dict, ins: str, sale_code: str, W: dict) -> tuple[int, dict]:
    detail = {"stage": [0, W["stage_watch"], W["stage_caution"], W["stage_alert"]][stage],
              "imminence": 0, "gap": 0, "can_buy": 0, "species": 0}
    if stage >= 2:
        d = region["d"] if region["top"] >= 2 else sp.get("d", 0)
        detail["imminence"] = max(0, 7 - d) * W["per_day"]
    if ins in GAP_INS:
        detail["gap"] = W[f"gap_{ins}"]
    if ins not in NO_BUY_INS and not region["alert"] and sale_code in ("open", "soon"):
        detail["can_buy"] = W["can_buy"]   # 특보가 난 지역은 이번 피해 보상이 안 되므로 0
    if sp.get("hit"):
        detail["species"] = W["species_hit"]
    detail = {k: int(round(v)) for k, v in detail.items()}
    return sum(detail.values()), detail


def why_item(stage: int, region: dict, ins: str, sale_code: str) -> Optional[str]:
    if stage >= 2:
        return "stage"
    if stage >= 1 and region["alert"]:
        return "alert"
    if stage >= 1 and ins not in NOT_GAP_FOR_SOON and sale_code == "soon":
        return "soon"
    return None


def _species_for_screen(r: dict) -> dict:
    """fd.species_risk 결과 → 화면 speciesRisk() 와 같은 모양."""
    return {"known": r["known"], "hit": r["hit"], "L": r.get("limit"), "d": r.get("d"), "stage": r["stage"],
            "pts": 15 if r["hit"] else 0, "short": r["short"], "text": r["text"]}


REASON_LABEL = {"stage": "위험 단계 주의 이상", "alert": "공식 특보 발령 지역", "soon": "판매 마감 임박"}


def compute_priority(db: Connection, today: date) -> tuple[dict, dict, dict]:
    """→ (regions, households{household_id: {...}}, weights). fd._MODE 가 정해진 상태에서 호출."""
    W = load_weights(db)
    regions = build_regions(db, today)
    hh_rows = db.execute("""
        SELECT h.household_id, r.sigungu_name
        FROM customer_service.fishery_households h
        LEFT JOIN public.sigungu_area_coordinates r ON r.region_id = h.region_code
    """).fetchall()
    items_by_hh = load_items(db, today)
    out: dict[int, dict] = {}
    for h in hh_rows:
        hid, short = h["household_id"], short_sigungu(h["sigungu_name"])
        region = regions.get(short or "")
        items = []
        for it in items_by_hh.get(hid, []):
            sale = (it["product"] or {}).get("sale") or {"code": "unknown", "text": "판매기간 확인 필요"}
            if region:
                sp = fd.species_risk(it, {"roms": region["_roms_days"]}, today)
                stage = max(region["top"], sp["stage"])
                score, detail = score_item(stage, region, sp, it["ins"], sale["code"], W)
                why = why_item(stage, region, it["ins"], sale["code"])
            else:
                sp = {"known": False, "hit": False, "stage": 0, "short": "예측 없음", "text": "이 지역 수온 예측 없음"}
                stage, score, detail, why = 0, 0, {}, None
            items.append({"mapping_id": it["mapping_id"], "species": it["standard_name"], "ins": it["ins"],
                          "stage": stage, "species_risk": _species_for_screen(sp), "product": it["product"],
                          "score": score, "score_detail": detail, "why": why})
        items.sort(key=lambda x: -x["score"])
        lead = items[0] if items else None
        out[hid] = {"household_id": hid, "region": short, "forecast": region is not None,
                    "score": lead["score"] if lead else 0,
                    "risk_stage": max((x["stage"] for x in items), default=0),
                    "list_reason": next((x["why"] for x in items if x["why"]), None),
                    "lead_mapping_id": lead["mapping_id"] if lead else None,
                    "items": items, "rank": None}
    ranked = sorted((h for h in out.values() if h["list_reason"]), key=lambda h: (-h["score"], h["household_id"]))
    for i, h in enumerate(ranked, start=1):
        h["rank"] = i
    return regions, out, W


def reason_text(h: dict) -> str:
    lead = next((x for x in h["items"] if x["mapping_id"] == h["lead_mapping_id"]), None)
    parts = [REASON_LABEL.get(h["list_reason"], "")]
    if lead:
        parts.append(f"{lead['species']} {fd.INS.get(lead['ins'], lead['ins'])}")
        if lead["score_detail"].get("can_buy"):
            parts.append("지금 가입 가능")
        if lead["species_risk"].get("hit"):
            parts.append(lead["species_risk"]["short"])
    return fd.tx(" · ".join(p for p in parts if p))[:200]


# ---------------------------------------------------------------------------
# 4. API
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/consult", tags=["상담 홈 · 연락 우선순위"], dependencies=[Depends(request_protection)])
ReadDB = Annotated[Connection, Depends(get_db)]
WriteDB = Annotated[Connection, Depends(get_customer_db, scope="function")]
BaseDate = Annotated[Optional[date], Query(description="계산 기준일 (비우면 오늘, 한국시간)")]


class _mode:
    """요청 동안 farm_detail 의 모드(고수온/저수온)를 정함."""
    def __init__(self, mode: str):
        self.mode = mode

    def __enter__(self):
        self.token = fd._MODE.set(self.mode)

    def __exit__(self, *exc):
        fd._MODE.reset(self.token)


@router.get("/forecast-regions")
def forecast_regions(db: ReadDB, mode: Mode = "heat", base_date: BaseDate = None):
    today = base_date or fd.today_kst()
    with _mode(mode):
        return regions_payload(build_regions(db, today), today)


@router.get("/priority")
def priority(db: ReadDB, mode: Mode = "heat", base_date: BaseDate = None):
    today = base_date or fd.today_kst()
    with _mode(mode):
        _, households, W = compute_priority(db, today)
    return {"base_date": today.isoformat(), "mode": mode, "weights": W,
            "households": sorted(households.values(), key=lambda h: (h["rank"] is None, h["rank"] or 0, h["household_id"]))}


@router.post("/priority/refresh")
def refresh_queue(db: WriteDB, mode: Mode = "heat", base_date: BaseDate = None):
    """기준일 연락 목록을 contact_queue 에 다시 저장 (같은 기준일 기존 행은 지우고 새로). n8n 예약 실행용."""
    today = base_date or fd.today_kst()
    with _mode(mode):
        _, households, _W = compute_priority(db, today)
        rows = [h for h in households.values() if h["rank"]]
        db.execute("DELETE FROM customer_service.contact_queue WHERE base_date = %s", (today,))
        # queue_id 에 자동 번호(identity·sequence)가 없으면 직접 채번
        col = db.execute("""
            SELECT is_identity, column_default FROM information_schema.columns
            WHERE table_schema = 'customer_service' AND table_name = 'contact_queue' AND column_name = 'queue_id'
        """).fetchone()
        auto_id = bool(col and (col["is_identity"] == "YES" or col["column_default"]))
        next_id = None if auto_id else db.execute(
            "SELECT COALESCE(max(queue_id), 0) + 1 AS n FROM customer_service.contact_queue").fetchone()["n"]
        for h in sorted(rows, key=lambda x: x["rank"]):
            lead = next((x for x in h["items"] if x["mapping_id"] == h["lead_mapping_id"]), None)
            values = {"base_date": today, "household_id": h["household_id"], "rank": h["rank"], "score": h["score"],
                      "risk_stage": h["risk_stage"], "list_reason": h["list_reason"], "reason_text": reason_text(h),
                      "lead_mapping_id": h["lead_mapping_id"],
                      "score_detail": Jsonb({"mode": mode,
                                             "items": {str(x["mapping_id"]): x["score_detail"] for x in h["items"]},
                                             "lead": lead["score_detail"] if lead else None})}
            if next_id is not None:
                values = {"queue_id": next_id, **values}
                next_id += 1
            cols = ", ".join(values)
            marks = ", ".join(f"%({k})s" for k in values)
            db.execute(f"INSERT INTO customer_service.contact_queue ({cols}) VALUES ({marks})", values)
    return {"base_date": today.isoformat(), "mode": mode, "saved": len(rows)}
