"""Dashboard API for sea_forecast.html, consult_home.html and farm_detail.html."""
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from backend.routes import DB

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])

# Change in ECMWF daily max (°C) between its first and last day that counts as a 2-3 week trend.
TREND_THRESHOLD = 0.5
# om_region_bias rows with this basis borrowed the average of other regions instead of their own comparison.
SHARED_BIAS_BASIS = "7개 지역 평균"


class Point(BaseModel):
    i: int
    max: float
    mean: float
    min: float
    src: str


class Bias(BaseModel):
    diff: float
    own: bool


class Alert(BaseModel):
    type: str
    since: str


class Region(BaseModel):
    id: str
    trend: str
    bias: Bias | None
    alert: Alert | None
    series: list[Point]


class Regions(BaseModel):
    base_date: date
    regions: list[Region]


def trend_of(series: list[Point]) -> str:
    om = [p.max for p in series if p.src == "ECMWF"]
    if len(om) < 2:
        return "flat"
    change = om[-1] - om[0]
    if change >= TREND_THRESHOLD:
        return "up"
    if change <= -TREND_THRESHOLD:
        return "down"
    return "flat"


@router.get("/regions", response_model=Regions)
def regions(db: DB):
    rows = db.execute("""
        SELECT f.region, f.day_no - 1 AS i, f.max_c, f.mean_c, f.min_c,
               CASE WHEN f.source = 'ROMS' THEN 'ROMS' ELSE 'ECMWF' END AS src,
               b.bias, b.basis
        FROM public.forecast_21d f
        LEFT JOIN public.om_region_bias b ON b.region = f.region
        ORDER BY f.region, f.day_no
    """).fetchall()
    base_date = db.execute("SELECT (now() AT TIME ZONE 'Asia/Seoul')::date AS d").fetchone()["d"]

    by_region: dict[str, dict] = {}
    for r in rows:
        region = by_region.setdefault(r["region"], {"series": [], "bias": None})
        region["series"].append(Point(i=r["i"], max=r["max_c"], mean=r["mean_c"], min=r["min_c"], src=r["src"]))
        if r["bias"] is not None:
            # The view adds bias to raw ECMWF, so the screen's diff (ECMWF minus observed) is its negative.
            region["bias"] = Bias(diff=-r["bias"], own=r["basis"] != SHARED_BIAS_BASIS)

    return Regions(
        base_date=base_date,
        regions=[
            # No official NIFS alert data in the DB yet, so alert stays null.
            Region(id=name, trend=trend_of(v["series"]), bias=v["bias"], alert=None, series=v["series"])
            for name, v in by_region.items()
        ],
    )
