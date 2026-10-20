import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import Connection, Error

from backend.api import router as api_router
from backend.config import get_settings
from backend.db import get_db
from backend.insurance import router as insurance_router
from backend.routes import router

logger = logging.getLogger(__name__)
app = FastAPI(
    title="NIFS Ocean API",
    version="0.1.0",
    description="Streamlit에서 사용할 수온·적조 조회 API. 시각은 한국시간(Asia/Seoul)입니다.",
)
app.include_router(router)
app.include_router(api_router)
app.include_router(insurance_router)
# HTML 화면(insurance.html 등)이 브라우저에서 직접 부르므로 허용할 주소만 연다. 조회 전용 API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET"],
)


@app.exception_handler(Error)
async def database_error(_request: Request, exc: Error):
    # Do not expose SQL, connection details or credentials to clients/logs.
    logger.error("Database request failed (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "DB 연결 또는 스키마를 확인하세요."})


@app.get("/health/live", tags=["상태"])
def liveness():
    return {"status": "ok"}


@app.get("/health", tags=["상태"])
def health(db: Connection = Depends(get_db)):
    db.execute("SELECT 1").fetchone()
    return {"status": "connected"}


@app.get("/health/db", tags=["상태"])
def database_health(db: Connection = Depends(get_db)):
    db.execute("SELECT 1").fetchone()
    tables = (
        "stations", "sigungu", "sigungu_station_map", "coo_daily_raw",
        "risa_observation", "redtide_report", "daily_temp", "screen3_current",
        "screen3_recent7", "yearly_hotdays", "climatology_3y", "vw_redtide_latest",
    )
    missing = [name for name in tables if db.execute(
        "SELECT to_regclass(%s) AS relation", (name,)
    ).fetchone()["relation"] is None]
    if missing:
        return JSONResponse(status_code=503, content={"status": "schema_missing", "missing": missing})
    return {"status": "ok", "database": "connected", "schema": "ready"}
