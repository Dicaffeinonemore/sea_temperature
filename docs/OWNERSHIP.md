# 파일 담당자

AI(언어 모델)와 팀원이 코드를 고치기 전에 담당자를 확인하는 표입니다. 규칙은 `.github/instructions/team-ownership.instructions.md`에 있습니다.

- 담당자가 아닌 파일은 AI가 수정·삭제하지 않습니다. 꼭 필요하면 변경안을 보여 주고 사용자의 승인을 받습니다.
- **공동** 파일은 줄 단위로 작성자를 확인하고(`git blame`), 추가만 합니다. 괄호 안 비율은 지금 파일에서 각자 쓴 줄의 비율입니다.
- 이 표는 2026-11-02 기준 `git blame` 작성자 비율로 만든 **초안**입니다. 한 사람이 80% 이상 쓴 파일은 그 사람, 아니면 **공동**으로 적었습니다. 팀 회의에서 확인한 뒤 "확인" 칸에 ✅를 적어 주세요. 담당이 바뀌면 이 표부터 고칩니다.
- 표에 없는 새 파일은 만든 사람이 담당입니다. 파일을 추가·삭제하는 PR에서 이 표도 함께 고칩니다.

## 팀원과 git 이름

| 팀원 | GitHub | git user.name | 확인 |
|---|---|---|---|
| | sooui9 (팀 저장소 관리자) | sooui9 | |
| | Dicaffeinonemore | Dicaffeinonemore | |
| | seungwonyyii-ai | seungwonyyii-ai | |
| | agh3724 | agh3724 | |
| | tpfl1510-maker | tpfl1510-maker | |
| | UseUpname | UseUpname | |
| | 확인 필요 | LSH | |

## 화면 (HTML)

| 파일 | 담당 | 비고 | 확인 |
|---|---|---|---|
| `consult_home.html` | **공동** · 주 sooui9 (sooui9 77% · seungwonyyii-ai 13% · agh3724 6%) | 상담 홈 | |
| `consult_status.html` | **공동** · 주 seungwonyyii-ai (seungwonyyii-ai 64% · Dicaffeinonemore 25% · UseUpname 5% · sooui9 5%) | 고객 상담 현황, 통화 기록(STT) | |
| `farm_detail.html` | **공동** · 주 sooui9 (sooui9 60% · seungwonyyii-ai 20% · agh3724 12% · tpfl1510-maker 5%) | 어가 상세 | |
| `sea_forecast.html` | **공동** · 주 sooui9 (sooui9 59% · agh3724 28% · seungwonyyii-ai 8%) | 수온 예측 | |

## 화면 공통 (상단 바 · 왼쪽 메뉴 · 알림 · 테마)

네 화면이 모두 불러오는 파일입니다. 고치면 모든 화면이 바뀌므로 PR에 어느 화면에서 확인했는지 적어 주세요.

| 파일 | 담당 | 비고 | 확인 |
|---|---|---|---|
| `shell.js` | **공동** · 주 seungwonyyii-ai (seungwonyyii-ai 59% · Dicaffeinonemore 19% · agh3724 16% · sooui9 5%) | 상단 바·왼쪽 메뉴·알림·고수온/저수온 모드 | |
| `shell.css` | seungwonyyii-ai (88%) | | |
| `figma-theme.css` | **공동** (sooui9 75% · Dicaffeinonemore 25%) | Figma 디자인 색·글꼴·사이드바 폭 | |
| `suhyup-logo.png` | sooui9 | 상단 바 로고 | |
| `out/*.svg` | Dicaffeinonemore | 상담 홈 예비 그래프 (`dash_chart.py`로 생성) | |

## 백엔드 (`backend/backend/`)

| 파일 | 담당 | 확인 |
|---|---|---|
| `main.py` | **공동** (LSH 39% · sooui9 24% · Dicaffeinonemore 22% · seungwonyyii-ai 10%) | |
| `routes.py`, `schemas.py`, `team.py`, `config.py`, `manage.py`, `__init__.py` | LSH | |
| `requirements-dev.txt`, `requirements-lock.txt` | LSH | |
| `requirements.txt` | **공동** (Dicaffeinonemore 58% · LSH 25% · seungwonyyii-ai 17%) | |
| `db.py` | **공동** (Dicaffeinonemore 65% · LSH 35%) | |
| `.env.example` | **공동** (LSH 70% · Dicaffeinonemore 30%) | |
| `team.env.example` | **공동** (Dicaffeinonemore 65% · LSH 35%) | |
| `customer_api.py`, `customer_schemas.py`, `customer_security.py`, `species_catalog.py`, `farm_detail_query_cache.py` | Dicaffeinonemore | |
| `dashboard.py` | **공동** · 주 Dicaffeinonemore (Dicaffeinonemore 70% · seungwonyyii-ai 21%) | |
| `consult.py` | **공동** · 주 seungwonyyii-ai (seungwonyyii-ai 60% · Dicaffeinonemore 36%) | |
| `consult_stt.py`, `contact_priority.py` | seungwonyyii-ai | |
| `farm_detail.py`, `insurance.py` | sooui9 | |
| `gov_support.py`, `n8n_bridge.py`, `data/damage/*.csv` | agh3724 | |

## 보험금 계산 (`backend/aqua-claim-api/`)

| 파일 | 담당 | 확인 |
|---|---|---|
| 폴더 전체 (`app/`, `data/`, `sql/`, `tests/`, `tools/`, `README.md`, `requirements.txt`) | sooui9 | |

## DB · 테스트

| 파일 | 담당 | 확인 |
|---|---|---|
| `backend/database/*.sql` | Dicaffeinonemore | |
| `backend/database/07_priority_weights.sql` | seungwonyyii-ai | |
| `backend/run_tests.py` | Dicaffeinonemore | |
| `backend/backend/tests/test_api.py`, `test_db.py` | LSH | |
| `backend/backend/tests/test_dashboard.py` | UseUpname | |
| `backend/backend/tests/` 나머지 (`integration/` 포함, `README.md`) | Dicaffeinonemore | |
| `tests/test_consult_navigation.cjs` | Dicaffeinonemore | |

## 최상위 스크립트

| 파일 | 담당 | 비고 | 확인 |
|---|---|---|---|
| `dash_chart.py` | agh3724 | 상담 홈 그래프 (백엔드 `dashboard.py`가 사용) | |
| `gov_support_api.py` | agh3724 | 정부지원 조회 바로가기 (`n8n_bridge.py`가 사용) | |
| `sea_temperature/*.csv` (가상 데이터 4개) | Dicaffeinonemore | 어디서도 참조하지 않음 · 삭제 여부 확인 필요 | |

## 보관 (`archive/`)

지금 화면·백엔드가 쓰지 않아 옮겨 둔 파일입니다. 자세한 내용은 `archive/README.md`에 있습니다.

| 파일 | 담당 | 확인 |
|---|---|---|
| `archive/insurance_api.py` | tpfl1510-maker | |
| `archive/skills-lock.json` | LSH | |
| `archive/backend/backend/support.py` | sooui9 | |
| `archive/backend/backend/api.py` | LSH | |

## 문서 · 규칙

| 파일 | 담당 | 확인 |
|---|---|---|
| `README.md` | sooui9 | |
| `AGENTS.md`, `CLAUDE.md`, `.github/instructions/*.md` | Dicaffeinonemore | |
| `DESIGN.md`, `docs/design/*.md` | Dicaffeinonemore | |
| `docs/DATA.md` | sooui9 | |
| `docs/OWNERSHIP.md` | **공동** (Dicaffeinonemore 작성 · 2026-11-02 sooui9 갱신) | |
| `backend/CUSTOMER_API.md` | Dicaffeinonemore | |
| `LAN_SETUP.md` | LSH | |
| `.gitignore` | **공동** (Dicaffeinonemore 67% · LSH 25%) | |
