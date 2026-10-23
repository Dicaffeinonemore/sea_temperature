"""
우리 바다 안심도우미 - 정부지원금(정부24) 조회 API  (insurance_test.py와 같은 방식, 새 파일 하나)

DB gov24 스키마의 지원사업을 양식 어가 기준(지역·품종)으로 골라 돌려줍니다.
다른 파일은 고치지 않습니다. DB 접속·공통 함수는 backend 쪽 것을 그대로 가져다 씁니다.

데이터 출처
  - gov24.gov24_service_list    정부24 공공서비스 목록 (서비스ID, 서비스명, 소관기관명, 지원내용, 지원대상 …)
  - gov24.gov24_service_detail  상세 (구비서류·문의처 등) — 서비스ID로 합침. 표가 없으면 목록만 씀
  - insurance.insurance_products.government_subsidy   보험료 국가 보조(%)

엔드포인트 (기존 /api/v1/support/services 와 겹치지 않게 /api/v1/gov-support 아래)
  GET /api/v1/gov-support/services?region=통영&species=조피볼락&keyword=&disaster_only=false&limit=20
        지역(해수부·경남·우리 시·군)과 어업 관련 지원사업, 점수순. 지원 비율(국비·도비·시군비 %)·금액도 뽑아 줌
  GET /api/v1/gov-support/services/{service_id}     한 건 전체 (목록 + 상세 모든 칸)
  GET /api/v1/gov-support/summary?region=&species=  상위 3건 짧은 카드 (화면·문자 안내용)
  GET /api/v1/gov-support/insurance-subsidy?species=조피볼락&region=통영&method=가두리
        보험료 지원: 국가 보조(보험 DB) + 지자체 추가 지원(정부24에서 찾은 도비·시군비)
  GET /docs                                          API 직접 눌러 보기 (기존 보험·지원제도 API도 함께 뜸)

실행 (sea_temperature 폴더에서)
  pip install -r backend/backend/requirements.txt
  DB 접속: backend/backend/.env 또는 환경변수 DATABASE_URL (insurance_test.py와 같음)

  python gov_support_api.py                          서버 → http://127.0.0.1:8000/docs
  python gov_support_api.py --port 8001              insurance_test.py와 동시에 켤 때

  서버 없이 파이썬에서 바로 가져오기
  python gov_support_api.py services --region 통영 --species 조피볼락
  python gov_support_api.py detail <서비스ID>
  python gov_support_api.py subsidy --species 조피볼락 --region 통영

  다른 파이썬 코드에서
      from gov_support_api import search_services, insurance_subsidy
      from backend.db import connect
      with connect() as conn:
          rows = search_services(conn, region="통영", species="조피볼락")

※ 보조 비율·금액은 정부24 문장에서 숫자를 뽑은 참고값입니다. 실제 지원 여부·금액은 소관기관 확인이 필요합니다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

ROOT = Path(__file__).resolve().parent          # sea_temperature/
sys.path.insert(0, str(ROOT / "backend"))       # backend 패키지를 불러오기 위해

from fastapi import APIRouter, HTTPException, Query  # noqa: E402
from psycopg import Connection  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend.insurance import escape_like, species_terms  # noqa: E402
from backend.routes import DB  # noqa: E402

router = APIRouter(prefix="/api/v1/gov-support", tags=["정부지원금"])

# ---------------------------------------------------------------------------
# 기준 값 (backend/support.py 와 같은 단어를 씀)
# ---------------------------------------------------------------------------
FISHERY = "양식|어업인|어업|어가|수산|어촌|어장"
DISASTER = "재해|보험|고수온|저수온|적조|피해|복구"
HEAT = "고수온|이상수온"
# 앱·n8n에서 쓰는 짧은 지역 이름 → 시·군 (locations.py 의 7개 시·군 + 별칭)
CITY = {"통영": "통영시", "산양": "통영시", "욕지": "통영시", "거제": "거제시", "고성": "고성군",
        "남해": "남해군", "미조": "남해군", "하동": "하동군", "사천": "사천시",
        "창원": "창원시", "진해": "창원시", "마산": "창원시"}
# 품종 별칭 (가두리 어류는 '어류'·'가두리'로도 찾음)
ALIAS = {"우럭": "조피볼락", "광어": "넙치", "우렁쉥이": "멍게", "참굴": "굴", "참전복": "전복"}
CAGE_FISH = {"조피볼락", "참돔", "돌돔", "감성돔", "농어", "점농어", "쥐치", "말쥐치", "숭어", "가숭어", "능성어", "방어", "넙치", "강도다리"}

# 지원 비율·금액 뽑기: '국비 50%', '도비 10%', '시·군비 15%', '최대 5천만원' …
_WHO = r"(국비|국고|도비|시\s*[·ㆍ.]?\s*군비|시비|군비|지방비|자부담|자기부담)"
SHARE = re.compile(_WHO + r"\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*%")          # '국비 50%'
SHARE_REV = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:를|을|는|은)?\s*" + _WHO)  # '50% 국비'
MONEY = re.compile(r"(?:최대|최고|한도|연|월|1인당|어가당|건당)?\s*\d[\d,.]*\s*(?:억|천만|백만|만|천)?\s*원")
SHARE_KEY = {"국비": "national", "국고": "national", "도비": "province", "시비": "city", "군비": "city",
             "지방비": "local", "자부담": "self", "자기부담": "self"}

# gov24 표의 한글 칸 → 응답 이름 (목록에 없으면 상세 표에서 채움)
FIELDS = {
    "name": ["서비스명"], "agency": ["소관기관명"], "support_type": ["지원유형"],
    "purpose": ["서비스목적요약", "서비스목적"], "target": ["지원대상"], "criteria": ["선정기준"],
    "content": ["지원내용"], "how_to_apply": ["신청방법"], "deadline": ["신청기한"],
    "reception": ["접수기관"], "phone": ["전화문의", "문의처"], "documents": ["구비서류"],
    "field": ["서비스분야"], "detail_url": ["상세조회URL"], "online_url": ["온라인신청사이트URL"],
}


class Shares(BaseModel):
    national: float | None = None    # 국비 %
    province: float | None = None    # 도비 %
    city: float | None = None        # 시·군비 %
    local: float | None = None       # 지방비 % (도·시군 구분 없음)
    self: float | None = None        # 자부담 %


class Amounts(BaseModel):
    shares: Shares                   # 문장에서 찾은 부담 비율
    percents: list[str]              # 그 밖의 % 표현 그대로 (예: '보험료의 50%')
    money: list[str]                 # 금액 표현 그대로 (예: '최대 5천만원')


class GovService(BaseModel):
    service_id: str
    name: str | None
    agency: str | None
    level: Literal["국가", "경상남도", "시·군", "기타"]
    support_type: str | None
    purpose: str | None
    target: str | None
    criteria: str | None
    content: str | None
    how_to_apply: str | None
    deadline: str | None
    reception: str | None
    phone: str | None
    documents: str | None
    detail_url: str | None
    tags: list[str]                  # 양식 · 재해·보험 · 고수온 · 우리 시·군 · 품종 이름
    score: int                       # 정렬 점수 (높을수록 우리 어가와 가까움)
    amounts: Amounts


class GovServiceDetail(GovService):
    raw: dict[str, Any]              # 목록 + 상세 표의 모든 칸 (한글 칸 이름 그대로)


class SummaryCard(BaseModel):
    service_id: str
    title: str
    agency: str | None
    why: str                         # 왜 골랐는지 (태그)
    amount: str | None               # 한 줄 금액·비율
    how: str | None                  # 신청 방법 · 기한
    phone: str | None
    detail_url: str | None


class SubsidyPart(BaseModel):
    source: str                      # 어디서 찾은 값인지
    pct: float | None
    text: str | None


class InsuranceSubsidy(BaseModel):
    species: str
    product_id: int | None
    product_name: str | None
    national: SubsidyPart            # 국가 보조 (보험 DB)
    local: list[GovService]          # 지자체 추가 지원 후보 (정부24)
    local_pct: float | None          # 찾은 도비 + 시·군비 합 (없으면 null)
    self_pct: float | None           # 100 - 국가 - 지자체 (모두 찾았을 때만)
    note: str


# ---------------------------------------------------------------------------
# 도움 함수
# ---------------------------------------------------------------------------
def city_of(region: str | None) -> str | None:
    """'통영' · '통영시' · '창원시(진해구)' · '진해' → '통영시' / '창원시'"""
    if not region:
        return None
    name = re.sub(r"\(.*\)", "", region).strip()
    return CITY.get(name, name) or None


def species_words(species: str | None) -> list[str]:
    """'조피볼락 (우럭)' → ['조피볼락', '우럭', '어류', '가두리']"""
    if not species:
        return []
    words = [ALIAS.get(t, t) for t in species_terms(species)]
    words += [t for t in species_terms(species) if t not in words]
    if any(w in CAGE_FISH for w in words):
        words += ["어류", "가두리"]
    return [w for w in dict.fromkeys(words) if w and w != "기타"]


def _first(row: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def extract_amounts(*texts: str | None) -> Amounts:
    text = " ".join(t for t in texts if t)
    shares: dict[str, float] = {}
    pairs = SHARE.findall(text) + [(who, pct) for pct, who in SHARE_REV.findall(text)]
    for label, pct in pairs:
        key = "city" if "군비" in label and "시" in label else SHARE_KEY.get(re.sub(r"\s", "", label), None)
        if key and key not in shares:
            shares[key] = float(pct)
    percents = [m.group(0).strip() for m in re.finditer(r"[^\s,.()]{0,12}\s*\d{1,3}(?:\.\d+)?\s*%", text)]
    money = [re.sub(r"\s+", " ", m.group(0)).strip() for m in MONEY.finditer(text)]
    return Amounts(shares=Shares(**shares), percents=list(dict.fromkeys(percents))[:6],
                   money=list(dict.fromkeys(money))[:6])


def _has_detail(db: Connection) -> bool:
    return db.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gov24' AND table_name = 'gov24_service_detail' AND column_name = '서비스ID'
    """).fetchone() is not None


def _rows(db: Connection, where: str, params: dict, limit: int) -> list[dict]:
    """목록 + 상세(있으면)를 서비스ID로 합친 행. 칸 이름을 몰라도 되게 JSON으로 꺼냄"""
    join = """
        LEFT JOIN LATERAL (SELECT * FROM gov24.gov24_service_detail d
                           WHERE d."서비스ID" = l."서비스ID" LIMIT 1) d ON true""" if _has_detail(db) else ""
    detail = "to_jsonb(d)" if join else "NULL::jsonb"
    rows = db.execute(f"""
        SELECT to_jsonb(l) AS list, {detail} AS detail
        FROM gov24.gov24_service_list l {join}
        WHERE {where}
        LIMIT %(limit)s
    """, {**params, "limit": limit}).fetchall()
    out = []
    for r in rows:
        merged = dict(r["detail"] or {})
        merged.update({k: v for k, v in (r["list"] or {}).items() if v is not None and str(v).strip()})
        out.append(merged)
    return out


def _service(row: dict, city: str | None, words: list[str]) -> dict:
    f = {k: _first(row, keys) for k, keys in FIELDS.items()}
    agency = f["agency"] or ""
    text = " ".join(x for x in (f["name"], f["purpose"], f["content"], f["target"], f["criteria"]) if x)
    tags, score = [], 0
    if agency == "해양수산부":
        level, score = "국가", score + 5
    elif agency == "경상남도":
        level, score = "경상남도", score + 10
    elif agency.startswith("경상남도 "):
        level = "시·군"
        if city and agency == f"경상남도 {city}":
            tags.append("우리 시·군")
            score += 30
    else:
        level = "기타"
    for tag, pattern, pts in (("양식", "양식", 20), ("재해·보험", DISASTER, 15), ("고수온", HEAT, 10)):
        if re.search(pattern, text):
            tags.append(tag)
            score += pts
    hit = [w for w in words if w in text]
    if hit:
        tags.append(hit[0])
        score += 25
    return {
        "service_id": str(_first(row, ["서비스ID", "service_id"]) or ""),
        **{k: f[k] for k in ("name", "agency", "support_type", "purpose", "target", "criteria", "content",
                              "how_to_apply", "deadline", "reception", "phone", "documents")},
        "detail_url": f["detail_url"] or f["online_url"],
        "level": level, "tags": tags, "score": score,
        "amounts": extract_amounts(f["content"], f["target"], f["criteria"]),
    }


# ---------------------------------------------------------------------------
# 파이썬에서 바로 쓰는 함수 (API도 이 함수를 그대로 부름)
# ---------------------------------------------------------------------------
def search_services(db: Connection, region: str | None = None, species: str | None = None,
                    keyword: str | None = None, disaster_only: bool = False, limit: int = 20) -> list[dict]:
    city = city_of(region)
    agencies = ["해양수산부", "경상남도"] + ([f"경상남도 {city}"] if city else [])
    where = ['l."소관기관명" = ANY(%(agencies)s)',
             """concat_ws(' ', l."서비스명", l."지원내용", l."지원대상", l."서비스목적요약") ~ %(fishery)s"""]
    params: dict[str, Any] = {"agencies": agencies, "fishery": FISHERY}
    if disaster_only:
        where.append("""concat_ws(' ', l."서비스명", l."지원내용", l."서비스목적요약") ~ %(disaster)s""")
        params["disaster"] = DISASTER
    if keyword:
        where.append("""concat_ws(' ', l."서비스명", l."지원내용", l."지원대상", l."서비스목적요약") ILIKE %(kw)s""")
        params["kw"] = f"%{escape_like(keyword)}%"
    rows = _rows(db, " AND ".join(where), params, limit=500)
    words = species_words(species)
    items = [_service(r, city, words) for r in rows]
    items.sort(key=lambda s: (-s["score"], s["name"] or ""))
    return items[:limit]


def service_detail(db: Connection, service_id: str) -> dict | None:
    rows = _rows(db, 'l."서비스ID" = %(id)s', {"id": service_id}, limit=1)
    if not rows:
        return None
    return {**_service(rows[0], None, []), "raw": rows[0]}


def summary_cards(db: Connection, region: str | None = None, species: str | None = None, n: int = 3) -> list[dict]:
    cards = []
    for s in search_services(db, region, species, limit=n):
        a: Amounts = s["amounts"]
        sh = a.shares
        parts = [f"{lbl} {v:g}%" for lbl, v in (("국비", sh.national), ("도비", sh.province), ("시·군비", sh.city),
                                                 ("지방비", sh.local), ("자부담", sh.self)) if v is not None]
        amount = " · ".join(parts + a.money[:1]) or (a.percents[0] if a.percents else None)
        how = " · ".join(x for x in (s["how_to_apply"], s["deadline"]) if x) or None
        cards.append({"service_id": s["service_id"], "title": s["name"] or "(이름 없음)", "agency": s["agency"],
                      "why": " · ".join(s["tags"]) or "어업 관련", "amount": amount,
                      "how": (how[:80] + "…") if how and len(how) > 80 else how,
                      "phone": s["phone"], "detail_url": s["detail_url"]})
    return cards


def insurance_subsidy(db: Connection, species: str, region: str | None = None,
                      method: Literal["가두리", "육상"] | None = None) -> dict:
    from backend.insurance import products   # 보험 화면과 같은 상품 찾기 규칙
    words = species_words(species)
    found = products(db, species, method) if words else []
    if not found and any(w in CAGE_FISH for w in words):
        found = products(db, "해상가두리어류", method)   # 조피볼락 등은 '해상가두리어류' 상품으로 가입
    p = next((x for x in found if not re.search("시설물|종자", x["product_name"] or "")), found[0] if found else None)
    text = (p or {}).get("government_subsidy")
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text or "")
    national = SubsidyPart(source="insurance.insurance_products.government_subsidy",
                           pct=float(m.group(1)) if m else None, text=text)

    local = [s for s in search_services(db, region, species, keyword="보험", limit=10)
             if s["level"] in ("경상남도", "시·군")]
    prov = next((s["amounts"].shares.province for s in local if s["amounts"].shares.province is not None), None)
    cty = next((s["amounts"].shares.city for s in local if s["amounts"].shares.city is not None), None)
    loc = next((s["amounts"].shares.local for s in local if s["amounts"].shares.local is not None), None)
    local_pct = (prov or 0) + (cty or 0) if (prov is not None or cty is not None) else loc
    self_pct = round(100 - national.pct - local_pct, 1) if national.pct is not None and local_pct is not None else None
    return {
        "species": species, "product_id": (p or {}).get("product_id"), "product_name": (p or {}).get("product_name"),
        "national": national, "local": local, "local_pct": local_pct, "self_pct": self_pct,
        "note": "참고값입니다. 국가 보조는 보험 상품 자료, 지자체 지원은 정부24 문장에서 찾은 비율이며 "
                "연도·예산에 따라 달라지므로 시·군 수산과와 수협에서 확인하세요.",
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
Region = Annotated[str | None, Query(max_length=30, description="통영 · 통영시 · 창원시(진해구) …")]
Species = Annotated[str | None, Query(max_length=50, description="조피볼락 · 조피볼락 (우럭) · 굴 · 전복 …")]


@router.get("/services", response_model=list[GovService])
def services(db: DB, region: Region = None, species: Species = None,
             keyword: Annotated[str | None, Query(max_length=30)] = None,
             disaster_only: bool = False, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return search_services(db, region, species, keyword, disaster_only, limit)


@router.get("/services/{service_id}", response_model=GovServiceDetail)
def service(service_id: str, db: DB):
    row = service_detail(db, service_id)
    if row is None:
        raise HTTPException(404, "해당 지원사업이 없습니다.")
    return row


@router.get("/summary", response_model=list[SummaryCard])
def summary(db: DB, region: Region = None, species: Species = None,
            n: Annotated[int, Query(ge=1, le=10)] = 3):
    return summary_cards(db, region, species, n)


@router.get("/insurance-subsidy", response_model=InsuranceSubsidy)
def insurance_subsidy_api(db: DB, species: Annotated[str, Query(min_length=1, max_length=50)],
                          region: Region = None, method: Literal["가두리", "육상"] | None = None):
    return insurance_subsidy(db, species, region, method)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="정부지원금 조회 API / 파이썬 조회")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("services", help="지원사업 목록 출력")
    s.add_argument("--region"); s.add_argument("--species"); s.add_argument("--keyword")
    s.add_argument("--disaster-only", action="store_true"); s.add_argument("--limit", type=int, default=20)
    d = sub.add_parser("detail", help="지원사업 한 건 출력"); d.add_argument("service_id")
    b = sub.add_parser("subsidy", help="보험료 지원(국가+지자체) 출력")
    b.add_argument("--species", required=True); b.add_argument("--region"); b.add_argument("--method", choices=["가두리", "육상"])
    ap.add_argument("--port", type=int, default=8000, help="서버 포트 (기본 8000)")
    a = ap.parse_args()

    if a.cmd is None:   # 서버
        import uvicorn
        from backend.main import app   # 기존 보험·지원제도 API, CORS, /health 포함

        app.include_router(router)
        print(f"정부지원금 API: http://127.0.0.1:{a.port}/docs  (/api/v1/gov-support/...)")
        uvicorn.run(app, host="127.0.0.1", port=a.port)
        return

    import psycopg
    from backend.db import connect

    try:
        with connect() as conn:
            conn.read_only = True
            if a.cmd == "services":
                out = search_services(conn, a.region, a.species, a.keyword, a.disaster_only, a.limit)
            elif a.cmd == "detail":
                out = service_detail(conn, a.service_id)
            else:
                out = insurance_subsidy(conn, a.species, a.region, a.method)
    except psycopg.Error as exc:
        # 접속 문자열·비밀번호가 화면에 찍히지 않도록 오류 종류만 보여 줌
        sys.exit(f"DB 연결 또는 조회 실패 ({type(exc).__name__}). backend/backend/.env 또는 DATABASE_URL, gov24 스키마 권한을 확인하세요.")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)))


if __name__ == "__main__":
    main()
