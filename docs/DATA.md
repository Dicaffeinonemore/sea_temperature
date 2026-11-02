# 데이터 사전

확정 PRD(2026-11-02) 6장 "데이터와 DB 설계"를 기준으로, 저장소의 DB 설계 파일·CSV·백엔드 코드에서 실제 이름을 확인해 정리한 문서입니다. PRD와 코드가 다르면 "확인 필요"로 적었습니다.

- 컬럼 출처 표기: **DDL** = 저장소의 `CREATE TABLE` 파일, **CSV** = 가상 데이터 CSV 머리글, **코드** = 백엔드 SQL에서 쓰는 컬럼(테이블 전체 컬럼이 아닐 수 있음)
- 기준일: 2026-11-02 main

## 1. 데이터 원천 (PRD 6.1)

| 데이터 · 출처 | 형태 | 범위 · 단위 | 용도 | 저장소 위치 · 쓰는 코드 |
|---|---|---|---|---|
| ROMS 7일 수온 예측 · 국립수산과학원(NIFS) | API 수집 | 경남 연안 7개 지역, 일 최고·평균·최저 ℃ | 1~7일 예측, 위험 단계 판정 | 수집은 저장소 밖(n8n·DB). DB `public.example_region_daily` → `farm_detail.py`, `forecast_21d` 뷰 → `dashboard.py` |
| ECMWF 해양 예측 · Open-Meteo | API 수집 | 7개 지역, 일 최고·평균·최저 ℃ | 8~21일 전망 (참고값) | DB `public.example_region_daily_om`, 보정값 `public.om_region_bias` |
| 오늘 실측 수온 · 국립수산과학원 RISA | API 실시간 조회 | 관측소별 ℃ | 어가 상세 '오늘 수온' (실패 시 오늘 ROMS 예측값) | `farm_detail.py`가 화면 요청 때 직접 조회 (DB 저장 안 함) |
| 양식수산물재해보험 약관·상품설명서 · 수협 | PDF → AI 구조화 | 상품·문서 버전별, 원문 근거(`source_evidence`) 포함 (원문 근거는 구조화 원본 데이터에만 있고, 백엔드는 가공한 결과 테이블만 사용) | 계약별 보장 판정, 특약 유무 안내 | DB `insurance.insurance_products`·`insurance_coverages`·`insurance_map`. 보험금 산정 규칙 원본 `backend/aqua-claim-api/data/calc_rules.csv` |
| 보험 적용 가격표 · 수협 공시 | CSV | 공시월·어종·지역·크기·월별, 원 | 피해 정도별 예상 보험금 계산 | `backend/aqua-claim-api/data/applied_price_r7_r8.csv`, `applied_price_formula.csv` → DB `insurance.insurance_applied_price`, `insurance_applied_price_formula` |
| 시군·세부지역 좌표 · 공공 자료 | CSV | 경남 연안 시군·세부지역, WGS84 | 담당 지역 선택, 예측 지역과 어가 연결 | DB `public.sigungu_area_coordinates` |
| 정부 지원(재해복구비·정책자금) · 해양수산부 등 | CSV (직접 정리) | 제도·품목별 단가(원)·피해율별 상환연기 | 어가 상세 '정부 지원금' | `backend/backend/data/damage/*.csv` 4개 → `gov_support.py` (DB 미사용) |
| 어가·어종·보험 계약·상담 기록 | 가상 데이터 생성 | 어가·계약·상담 건별, 경남 연안 | 연락 대상, 보장 공백 판정, 상담 이력 | 원본 `sea_temperature/*_synthetic_2025.csv` 4개 → DB `customer_service` |
| 통화 녹음 → STT·요약 · OpenAI API | 파일 → API | 상담 기록 건별 | 통화 기록, 참고사항 후보 | 녹음 파일은 `**/data/call_recordings/` (Git 제외), 결과는 DB `customer_service.consult_call_records` → `consult_stt.py`, `consult.py` |

예측 지역 7곳: 통영 · 거제 · 남해 · 고성 · 하동 · 창원 · 사천

## 2. 테이블 (PRD 6.2)

### customer_service — 어가 · 상담

| 테이블 | 한 행의 의미 | 주요 컬럼 | 컬럼 출처 |
|---|---|---|---|
| `fishery_households` | 어가 1곳 | `household_id`, `household_name`, `owner_name`, `region_code`(→ 좌표 `region_id`), `fishery_type`, `license_number`, `created_at`, `phone_number` | CSV + `06_household_contact_columns.sql` |
| `household_species` | 어가 1곳의 양식 어종 1개 | `mapping_id`, `household_id`, `species_id`, `is_primary`, `production_ratio`, `status` | CSV |
| `fish_species` | 어종 기준표 | `species_id`, `standard_name`, `common_name`, `farming_method`, `category`, `life_stage` | 코드 |
| `insurance_contracts` | 어가 1곳의 보험 계약 1건 | `insurance_id`, `household_id`, `product_id`(→ insurance), `policy_number`, `total_premium`, `start_date`, `end_date`, `contract_status` | CSV |
| `insurance_targets` | 계약 1건의 어종별 가입 | `target_id`, `insurance_id`, `mapping_id`, `coverage_amount`, `rider_details` | CSV |
| `contact_queue` | 기준일 상담 대상 어가 1곳의 연락 순위 | `base_date`, `household_id`, `rank`, `score`, `risk_stage`(0~3), `list_reason`(위험 단계·공식 특보·판매 마감), `reason_text`, `lead_mapping_id`, `score_detail`, `computed_at` | DDL `05_consultation.sql` |
| `household_contacts` | 어가 연락처·문자 수신 동의 | `household_id`, `phone_number`, `sms_consent`, `consent_at`, `consent_source` | DDL `05_consultation.sql` |
| `consult_cases` | 어가 1곳의 시즌별 상담 상태 | `case_id`, `household_id`, `season`, `status`, `next_contact_at`, `last_contact_at` | DDL `05_consultation.sql` |
| `consult_logs` | 연락 1건 | `log_id`, `case_id`, `household_id`, `contacted_at`, `channel`, `result_status`, `memo`, `next_contact_at`, `staff_name` | DDL `05_consultation.sql` |
| `consult_log_items` | 연락 1건의 어종별 결과 | `log_item_id`, `log_id`, `mapping_id`, `result`, `insurance_id` | DDL `05_consultation.sql` |
| `customer_memos` | 고객 참고사항 1개 | `memo_id`, `household_id`, `category`, `content`, `source`, `log_id`, `staff_name`, `created_at` | 코드 (`consult.py`) |
| `consult_call_records` | 상담 1건의 통화 녹음 STT 결과 | `log_id`, `stt_status`, `duration_sec`, `lines`, `summary`, `found`, `error` | 코드 (`consult.py`) |

### insurance — 보험 기준

| 테이블 | 한 행의 의미 | 주요 컬럼 | 컬럼 출처 |
|---|---|---|---|
| `insurance_products` | 보험 상품 1개 | `product_id`, `product_name`, `species`, `sale_period`, `insurance_period`, `government_subsidy`, `deductible`, `premium_payment_method`, `contacts` | 코드 (`farm_detail.py`) |
| `insurance_coverages` | 상품 1개의 보장 항목 1개 (주계약·특약) | `product_id`, `coverage_key`, `contract_type`, `name`, `risk_types`, `effect` | 코드 (`farm_detail.py`) |
| `insurance_map` | 어종 → 가입 가능 상품 | `species_id`, `product_id`, `coverage_target` | 코드 |
| `insurance_applied_price` | 공시 적용 가격 1건 | `notice_month`, `product_id`, `species_id`, `region_no`, `size_label`, `month`, `price`, `unit`, `valid_from`, `valid_to`, `source` 등 | DDL `aqua-claim-api/sql/001_applied_price.sql` |
| `insurance_applied_price_formula` | 가격 산식 1건 | `product_id`, `variant`, `formula`, `base_price`, `valid_from`, `valid_to`, `source` 등 | DDL `aqua-claim-api/sql/001_applied_price.sql` |

`insurance_applied_price`·`insurance_applied_price_formula`는 PRD 6.2 표에는 없고 6.1 "보험 적용 가격표"에 해당합니다. 보험금 계산 API(`backend/aqua-claim-api`)가 씁니다.

### public — 수온 예측 · 지역 기준

| 테이블 | 한 행의 의미 | 주요 컬럼 | 컬럼 출처 |
|---|---|---|---|
| `example_region_daily` | 지역 1곳의 하루 ROMS 예측 | `region`, `day`, `max_c`, `mean_c`, `min_c`, `dist_km` | 코드 (`farm_detail.py`) |
| `example_region_daily_om` | 지역 1곳의 하루 ECMWF 예측 | `region`, `day`, `max_c`, `mean_c`, `min_c`, `dist_km` | 코드 (`farm_detail.py`) |
| `om_region_bias` | 지역 1곳의 ECMWF 보정값 | `region`, `bias`, `basis` | 코드 (`dashboard.py`) |
| `priority_weights` | 연락 우선순위 가중치 1개 (PRD 6.2에 없음, 2026-11-02 추가) | `key`, `value`, `note` | DDL `07_priority_weights.sql` |
| `forecast_21d` (뷰) | 지역 1곳의 21일 중 하루 (1~7일 ROMS + 8~21일 보정 ECMWF) | `region`, `day_no`, `max_c`, `mean_c`, `min_c`, `source` | 코드 (`dashboard.py`) |
| `sigungu_area_coordinates` | 시군·세부지역 1곳 | `region_id`, `sigungu_name`, `area_name`, `latitude`, `longitude` | 코드 |

`customer_service`·`insurance`·`public`의 위 테이블 대부분은 DB 관리자가 만들어 저장소에 `CREATE TABLE` 파일이 없습니다. 전체 컬럼은 DB에서 확인합니다.

## 3. 핵심 컬럼 · 파생변수 (PRD 6.3)

| 컬럼 · 지표 | 의미 · 산식 | 단위 · 처리 규칙 | 연결 원천 | 코드 위치 |
|---|---|---|---|---|
| 보정 최고 수온 (`max_c`) | 1~7일: ROMS 일 최고 / 8~21일: ECMWF 최고 + 지역 보정값 | ℃, 8~21일은 참고값으로 구분 표시 | `forecast_21d` ← `example_region_daily`, `example_region_daily_om`, `om_region_bias` | `dashboard.py` |
| 예측 보정값 (`bias`) | 같은 날짜의 ROMS − ECMWF 평균 차이 | ℃, 비교 일수가 적은 지역은 7개 지역 평균을 빌려 씀(`basis`='7개 지역 평균') | `om_region_bias` | `dashboard.py` |
| 위험 단계 | 고수온(일 최고): 관심 25℃ · 주의 28℃ · 경보 28℃ 이상 3일 연속 / 저수온(일 최저): 관심 7℃ · 주의 4℃ · 경보 4℃ 이하 3일 연속 | 4단계(정상·관심·주의·경보). 어가 단계는 지역 단계와 어종 한계 수온 도달 중 높은 쪽 | `forecast_21d`, `fish_species` | `farm_detail.py` `WATCH_TEMP`·`CAUTION_TEMP`·`MODE_RULES` |
| 어종 한계 수온 도달일 | 7일 예측 중 어종별 한계 수온에 처음 닿는 날 (D-n) | 일, 한계 수온 자료가 없는 어종은 지역 기준만 적용 | `forecast_21d`, 어종별 한계 수온 | `farm_detail.py` `SPECIES_LIMIT`·`SPECIES_COLD_LIMIT` |
| 보장 상태 | 계약·특약으로 판정: 가입(`full`) · 특약 없음(`norider`) · 미가입(`none`) · 만료(`expired`) · 청약 중(`pending`) · 보장 없는 상품(`noheat`) · 부담보(`excl`) · 확인 필요(`unknown`) | 어종(계약) 단위 | `insurance_contracts`, `insurance_targets`, `insurance_coverages` | `farm_detail.py` |
| 연락 우선순위 점수 | 위험 단계(관심 10·주의 30·경보 40) + 도달 임박((7 − 도달일) × 2) + 보장 공백(미가입·만료 25, 특약 없음·보장 없는 상품 20, 확인 필요 15, 부담보 10) + 지금 가입 가능 20 + 어종 한계 수온 도달 10. 어가 점수 = 가장 급한 어종의 점수 | 점수 높은 순. 목록 사유: 주의 이상 · 관심+공식 특보 · 관심+보장 공백+이번 달 판매 마감 | 가중치 `priority_weights`, 결과 `contact_queue` | `contact_priority.py` (`GET /api/consult/priority`로 화면에 제공, `POST /api/consult/priority/refresh`로 `contact_queue` 저장 · n8n 예약 실행). 서버 연결 실패 시에만 화면 `PRIORITY`로 같은 규칙 계산 |

## 4. 저장소 안 데이터 파일

| 파일 | 행 수 | 내용 |
|---|---|---|
| `sea_temperature/customer_service_fishery_households_synthetic_2025.csv` | 100 | 가상 어가 |
| `sea_temperature/customer_service_household_species_synthetic_2025.csv` | 126 | 가상 어가별 어종 |
| `sea_temperature/customer_service_insurance_contracts_synthetic_2025.csv` | 64 | 가상 보험 계약 |
| `sea_temperature/customer_service_insurance_targets_synthetic_2025.csv` | 73 | 가상 계약별 가입 어종 |
| `backend/aqua-claim-api/data/applied_price_r7_r8.csv` | 737 | 보험 적용 가격표 |
| `backend/aqua-claim-api/data/applied_price_formula.csv` | 13 | 가격 산식 |
| `backend/aqua-claim-api/data/calc_rules.csv` | 200 | 보험금 산정 규칙 |
| `backend/backend/data/damage/programs.csv` | 6 | 정부 지원 제도 |
| `backend/backend/data/damage/prices.csv` | 7 | 재해복구비 품목별 단가 |
| `backend/backend/data/damage/relief.csv` | 3 | 피해율별 정책자금 상환연기 |
| `backend/backend/data/damage/sources.csv` | 14 | 정부 자료 출처 |

개인정보: 저장소의 어가·연락처 데이터는 모두 가상 데이터이며, 실제 전화번호·API 키는 저장소에 없습니다(2026-11-02 검사). 통화 녹음은 `.gitignore`로 Git에서 제외합니다.

## 5. 품질 점검과 한계 (PRD 6.4)

- [ ] PK 중복 / FK 정합 (기준표에 없는 코드)
- [ ] 결측 처리 기준
- [ ] 집계 단위(일/월) 일치
- [ ] (모델 사용 시) 예측 시점 이후 정보 사용 금지, 학습·검증 기간 분리

화면 고지: 수온만으로 개별 양식장의 실제 폐사·피해 규모를 확정할 수 없습니다. 위험 단계는 앱 기준 참고값이며 공식 특보·보험금 지급 기준이 아닙니다. 보험 가입·보험금 지급·대출 여부를 자동 결정하지 않습니다.
