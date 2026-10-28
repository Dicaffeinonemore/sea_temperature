"""Isolated demo screens and read-only temperature simulation."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from backend import farm_detail as detail

router = APIRouter(prefix="/demo", tags=["시연"])
ROOT = Path(__file__).resolve().parents[2]
SCREENS = {"consult_home.html", "farm_detail.html", "sea_forecast.html", "consult_status.html"}
HEADERS = {"Cache-Control": "no-store"}


def adjust_sea(original: dict, offset: float, today) -> dict:
    sea = deepcopy(original)
    if offset == 0:
        return sea
    if sea["today"]["temp"] is not None:
        sea["today"]["temp"] = round(sea["today"]["temp"] + offset, 1)
    lookback = []
    for key in ("roms", "om"):
        for row in sea[key]:
            for metric in ("max", "mean", "min", "value"):
                if row.get(metric) is not None:
                    row[metric] = round(row[metric] + offset, 1)
        values = [row["value"] for row in sea[key]]
        for row, stage in zip(sea[key], detail.day_stages(values, lookback)):
            row.update(stage)
        lookback = values[-(detail.ALERT_STREAK_DAYS - 1):]
    days = sea["roms"] + sea["om"]
    sea["stage"] = detail.summarize_stage(days if detail.STAGE_INCLUDE_OM else sea["roms"], today)
    sea["stage_extended"] = detail.summarize_stage(days, today)
    valid = [row for row in sea["roms"] if row["value"] is not None]
    peak = max(valid, key=lambda row: (row["value"], -row["day"].toordinal()), default=None)
    sea["max7"] = {"temp": peak["value"], "date": peak["day"], "d": (peak["day"] - today).days} if peak else None
    return sea


@router.get("/api/households/{household_id}/detail")
def demo_detail(household_id: int, offset: float = Query(0.0, ge=0, le=15)):
    if not (offset * 2).is_integer():
        raise HTTPException(422, "보정값은 0.5℃ 단위로 지정해 주세요.")
    today = detail.today_kst()
    hh = detail.q_one(detail.HOUSEHOLD_SQL, (household_id,))
    if hh is None:
        raise HTTPException(404, "어가 정보를 찾을 수 없어요")
    species = [s for s in detail.q_all(detail.SPECIES_SQL, (household_id,)) if s["status"] != "폐업"]
    sea = adjust_sea(detail.build_sea(hh, today), offset, today)
    cards, insurance_source = detail.build_cards(household_id, species, sea, today, hh)
    region_stage = sea["stage"]["level"] or 0
    for card in cards:
        card["stage"] = max(region_stage, card["risk"]["stage"])
    stage = max([region_stage] + [card["stage"] for card in cards])
    lead = cards[0] if cards else None
    region = detail.normalize_sigungu(hh["sigungu_name"]) or sea["region"] or "-"
    response = detail.ok({
        "as_of": datetime.now(detail.KST).strftime("%Y-%m-%d %H:%M"),
        "household": {
            "household_id": hh["household_id"], "household_name": hh["household_name"],
            "owner_name": hh["owner_name"], "fishery_type": hh["fishery_type"],
            "license_number": hh["license_number"], "sigungu": hh["sigungu_name"],
            "area": hh["area_name"], "region": region, "lat": hh["lat"], "lon": hh["lon"],
            "phone": hh["phone_number"], "phone_masked": detail.mask_phone(hh["phone_number"]),
        },
        "sea": sea, "stage": {"level": stage, "label": detail.STAGE[stage]}, "cards": cards,
        "insurance_source": insurance_source,
        "gap_count": sum(1 for card in cards if card["ins"] in detail.GAP_CODES),
        "guide": detail.check_guide(lead), "checks": detail.talking_points(cards, sea, stage),
        "script": detail.example_script(hh["owner_name"], region, lead, sea),
        "consult": detail.load_consult(household_id, today),
    })
    response.headers.update(HEADERS)
    return response


@router.post("/api/households/{household_id}/claim-estimate")
def demo_estimate(household_id: int, body: detail.EstimateIn):
    return detail.claim_estimate(household_id, body)


@router.api_route("/api/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
def block_writes(path: str):
    raise HTTPException(403, "시연 사이트에서는 실제 기록을 저장하거나 삭제할 수 없어요.")


@router.get("/")
def index():
    return RedirectResponse("/demo/consult_home.html", headers=HEADERS)


@router.get("/out/{name}")
def chart_fallback(name: str):
    if name not in {"신청주의_연도별.svg", "신청주의_월별.svg"} or not (ROOT / "out" / name).is_file():
        raise HTTPException(404)
    return FileResponse(ROOT / "out" / name, media_type="image/svg+xml", headers=HEADERS)


@router.get("/{name}")
def screen(name: str):
    if name in SCREENS:
        html = (ROOT / name).read_text(encoding="utf-8")
        html = html.replace("<head>", '<head>\n<link rel="stylesheet" href="/demo/demo.css">\n<script src="/demo/demo.js"></script>', 1)
        html = html.replace("function applyRegions(data){", "function applyRegions(data){\n  data = window.DemoSimulation.adjustRegions(data);", 1)
        html = html.replace("function save(){", "function save(){\n  if(window.DemoSimulation) return;", 1)
        return HTMLResponse(html, headers=HEADERS)
    assets = {
        "shell.js": (ROOT / "shell.js", "text/javascript"),
        "shell.css": (ROOT / "shell.css", "text/css"),
        "demo.js": (ROOT / "demo" / "demo.js", "text/javascript"),
        "demo.css": (ROOT / "demo" / "demo.css", "text/css"),
    }
    if name not in assets:
        raise HTTPException(404)
    path, media_type = assets[name]
    return FileResponse(path, media_type=media_type, headers=HEADERS)
