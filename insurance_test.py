"""
우리 바다 안심도우미 - 보험 정보 화면 서버 (home_test.py와 같은 방식)

이 파일 하나만 실행하면 보험 정보 화면(insurance.html)과 화면이 쓰는 API가 함께 뜹니다.
SQL·API는 backend/backend/insurance.py, support.py에 있는 것을 그대로 가져다 씁니다.
(같은 코드를 두 번 두지 않기 위해서입니다. 쿼리를 고칠 때는 backend 쪽만 고치세요.)

데이터 출처
  - 보험 상품   : insurance 스키마 (insurance_products / _coverages / _exclusions / _claim_rules)
  - 지원제도    : gov24 스키마 (gov24_service_list, 정부24 공공서비스)

엔드포인트
  GET /                                         보험 정보 화면 (insurance.html)
  GET /app.html, /home.html, /response.html …   하단 바·메뉴로 이동하는 다른 화면 (아래 PAGES에 있는 파일만)
  GET /api/v1/insurance/products?species=&method=   내 조건(품종·양식 방식)에 맞는 상품
  GET /api/v1/insurance/products/{product_id}       상품 상세 (보장·제외 조건·청구 규칙)
  GET /api/v1/insurance/overview                    전체 상품과 위험별 보장 분류
  GET /api/v1/support/services?region=              지원제도
  GET /docs                                     API 직접 눌러 보기
  GET /health

실행 (sea_temperature 폴더에서)
  pip install -r backend/backend/requirements.txt
  DB 접속: 둘 중 하나
    1) backend/backend/.env 에 DB_HOST·DB_USER·DB_PASSWORD (README '백엔드 실행' 참고)
    2) 환경변수 DATABASE_URL (home_test.py와 같은 방식)
       $env:DATABASE_URL = "postgresql://user:pass@host:5432/nifs_ocean?sslmode=prefer"
       ※ sslmode를 적지 않으면 require로 접속합니다. 팀 내부망 DB는 ?sslmode=prefer 를 붙이세요.
  python insurance_test.py
  → 브라우저에서 http://127.0.0.1:8000/  (양식장 정보가 없으면 양식장 등록 화면부터)

※ insurance.html은 http://127.0.0.1:8000 의 API를 부르도록 되어 있어서 포트는 8000을 씁니다.
  home_test.py도 8000을 쓰므로 둘을 동시에 띄우지 말고 하나씩 실행하세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.responses import FileResponse, PlainTextResponse

ROOT = Path(__file__).resolve().parent          # sea_temperature/
sys.path.insert(0, str(ROOT / "backend"))       # backend 패키지를 불러오기 위해

from backend.main import app  # noqa: E402  (보험·지원제도 API, CORS, /health 포함)

# 화면 파일은 이 목록에 있는 것만 내보낸다. 폴더 전체를 열면 backend/backend/.env 같은 파일까지 노출될 수 있다.
PAGES = {
    "insurance.html", "app.html", "home.html", "home_test.html", "response.html",
    "common.css", "common.js", "start_bg.jpg",
}


def page(name: str):
    path = ROOT / name
    if name not in PAGES or not path.is_file():
        return PlainTextResponse("없는 화면입니다.", status_code=404)
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def insurance_page():
    """보험 정보 화면. 예: http://127.0.0.1:8000/"""
    return page("insurance.html")


@app.get("/{name}", include_in_schema=False)
def other_page(name: str):
    """하단 바·메뉴로 이동하는 다른 화면과 공통 파일 (PAGES에 있는 파일만)."""
    return page(name)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
