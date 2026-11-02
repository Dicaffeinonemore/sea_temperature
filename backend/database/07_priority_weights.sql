-- 07_priority_weights.sql
-- 연락 우선순위 가중치 (backend/contact_priority.py 가 읽는 키)
-- 이미 있는 키는 그대로 둠. 값을 바꾸면 다음 요청부터 바로 반영.
-- 화면 가상 데이터용 PRIORITY(consult_home.html · farm_detail.html)와 서버 DEFAULT_WEIGHTS 도 같이 맞출 것.
CREATE TABLE IF NOT EXISTS public.priority_weights (
  key   text PRIMARY KEY,
  value numeric NOT NULL,
  note  text
);

INSERT INTO public.priority_weights (key, value, note) VALUES
  ('stage_watch',   10, '위험 단계 관심'),
  ('stage_caution', 30, '위험 단계 주의'),
  ('stage_alert',   40, '위험 단계 경보'),
  ('per_day',        2, '주의 이상일 때 (7 - 도달일) × 이 값'),
  ('gap_none',      25, '보장 공백: 미가입'),
  ('gap_expired',   25, '보장 공백: 계약 만료'),
  ('gap_norider',   20, '보장 공백: 고수온(저수온) 특약 없음'),
  ('gap_noheat',    20, '보장 공백: 고수온(저수온) 보장이 없는 상품'),
  ('gap_unknown',   15, '보장 공백: 상품 보장 정보 확인 필요'),
  ('gap_excl',      10, '보장 공백: 부담보 특약 가입'),
  ('can_buy',       20, '지금 가입 가능 (판매 기간 · 특보 전)'),
  ('species_hit',   10, '7일 안 어종 한계 수온 도달')
ON CONFLICT (key) DO NOTHING;
