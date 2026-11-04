# 보관 파일 (archive)

지금 화면 4개와 백엔드가 쓰지 않는 파일을 지우지 않고 옮겨 둔 곳입니다. 확정 PRD(2026-11-02)에서 서비스 대상이 어민용 앱에서 수협 상담 담당자용 대시보드로 바뀌면서 남은 파일입니다.

- 백엔드와 배포 사이트는 이 폴더를 불러오지 않습니다.
- 다시 쓰려면 아래 "원래 위치"로 `git mv` 하고, 백엔드 파일이면 `backend/backend/main.py`에 다시 연결합니다.

| 파일 | 원래 위치 | 담당 | 옮긴 이유 |
|---|---|---|---|
| `insurance_api.py` | 저장소 최상위 | tpfl1510-maker | 어디서도 불러오지 않음. 같은 기능의 `backend/backend/insurance.py`도 이후 보관됨 |
| `skills-lock.json` | 저장소 최상위 | LSH | AI 도구 설정 파일. 앱 코드와 무관 |
| `backend/backend/support.py` | `backend/backend/` | sooui9 | `main.py`가 불러오기만 하고 연결하지 않아 배포 사이트에서 쓰이지 않음 |
| `backend/backend/api.py` | `backend/backend/` | LSH | 관측소·수온·적조·고수온 일수 API 5개. 예전 어민용 화면용이라 지금 화면 4개가 부르지 않음. 이 API의 테스트 4개(`test_api.py`의 `test_public_*`)는 함께 삭제 — 되돌릴 때 이 커밋에서 가져오기 |
| `backend/backend/insurance.py` | `backend/backend/` | sooui9 | 보험 상품 목록·상세·개요 API 3개. 어가 상세는 보험 정보를 `farm_detail.py`에서 받아 이 API를 부르지 않음. 정부 지원금이 쓰던 `species_terms` 함수는 `gov_support.py`로 옮김 |
