"""
우리 바다 안심도우미 - 정부지원금 조회 (backend/backend/gov_support.py 를 부르는 바로가기)

API와 함수는 backend/backend/gov_support.py 한 곳에만 있습니다. 이 파일은 예전 실행 방법을 그대로 쓰게 해 줍니다.
화면에서 쓰는 API(/api/v1/gov-support/...)는 팀 백엔드(uvicorn backend.main:app)에 등록되어 함께 뜹니다.

실행 (sea_temperature 폴더에서)
  python gov_support_api.py services --region 통영 --species 조피볼락
  python gov_support_api.py detail <서비스ID>
  python gov_support_api.py subsidy --species 굴 --region 통영

다른 파이썬 코드에서
    from gov_support_api import search_services
    from backend.db import connect
    with connect() as conn:
        rows = search_services(conn, region="통영", species="조피볼락")
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))   # backend 패키지를 불러오기 위해

from backend.gov_support import (  # noqa: E402
    insurance_subsidy, main, search_services, service_detail, summary_cards,
)

__all__ = ["insurance_subsidy", "search_services", "service_detail", "summary_cards"]   # 다른 코드에서 여기서 바로 가져다 씀

if __name__ == "__main__":
    main()
