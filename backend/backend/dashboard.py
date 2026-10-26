"""Dashboard sea-temperature forecast API (used by sea_forecast.html)."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from psycopg import Connection

from backend.db import get_db

router = APIRouter(prefix="/api/dashboard", tags=["대시보드 수온 예측"])
ReadDB = Annotated[Connection, Depends(get_db)]

# Same seven regions and order as the dashboard screens.
REGIONS = ["통영", "거제", "고성", "남해", "하동", "창원", "사천"]
ROMS_DAYS, OM_DAYS = 7, 14
TREND_LIMIT_C = 0.3   # change between first and last ECMWF day that counts as up/down


def _r1(value) -> float | None:
    return None if value is None else round(float(value), 1)


def build_regions(base_date: str, roms: list[dict], om: list[dict], bias: list[dict]) -> dict:
    """Shape DB rows into the sea_forecast.html contract.

    Contract: {base_date, regions:[{id, trend, bias:{diff, own}, alert, series:[{i, max, mean, min, src}]}]}
    - i: days from base_date (0 = today); ROMS covers 0-6, ECMWF (bias-corrected) covers 7-20.
    - bias.diff: ECMWF minus ROMS (om_bias.offset_c is the value added to ECMWF, so diff = -offset_c);
      null when the region has no correction record.
    - alert: official NIFS warnings are not stored in the DB yet, so always null.
    """
    start = date.fromisoformat(base_date)
    latest_bias = {}
    for row in bias:                       # rows arrive newest first per region
        latest_bias.setdefault(row["region"], row)

    regions = []
    for region in REGIONS:
        def points(rows, src, limit):
            out = []
            for row in [r for r in rows if r["region"] == region][:limit]:
                out.append({"i": (date.fromisoformat(row["day"]) - start).days, "max": _r1(row["max_c"]),
                            "mean": _r1(row["mean_c"]), "min": _r1(row["min_c"]), "src": src})
            return out

        roms_points = points(roms, "ROMS", ROMS_DAYS)
        if not roms_points:
            continue                      # no ROMS forecast for this region: the screen falls back to its own data
        last_roms = roms_points[-1]["i"]
        om_points = [p for p in points(om, "ECMWF", OM_DAYS) if last_roms < p["i"] <= 20]

        trend = "flat"
        if len(om_points) >= 2:
            change = om_points[-1]["max"] - om_points[0]["max"]
            trend = "up" if change > TREND_LIMIT_C else "down" if change < -TREND_LIMIT_C else "flat"

        b = latest_bias.get(region)
        regions.append({
            "id": region,
            "trend": trend,
            "bias": {"diff": -_r1(b["offset_c"]), "own": True} if b else None,
            "alert": None,
            "series": roms_points + om_points,
        })
    return {"base_date": base_date, "regions": regions}


@router.get("/regions")
def regions(db: ReadDB):
    base_date = db.execute("SELECT to_char(current_date, 'YYYY-MM-DD') AS d").fetchone()["d"]
    day_sql = """
        SELECT region, to_char(day, 'YYYY-MM-DD') AS day, max_c, mean_c, min_c
        FROM {table}
        WHERE day >= current_date AND region = ANY(%s)
        ORDER BY region, day
    """
    roms = db.execute(day_sql.format(table="public.example_region_daily"), (REGIONS,)).fetchall()
    om = db.execute(day_sql.format(table="public.example_region_daily_om"), (REGIONS,)).fetchall()
    bias = db.execute("""
        SELECT region, offset_c FROM public.om_bias
        WHERE offset_c IS NOT NULL AND region = ANY(%s)
        ORDER BY region, calc_at DESC
    """, (REGIONS,)).fetchall()
    return build_regions(base_date, roms, om, bias)
