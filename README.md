# sea_temperature

## HTML 버전

화면은 팀원별로 새로 구성하는 중입니다. 시작·양식장 등록·로그인·회원가입 화면(`app.html`)은 삭제했고 새로 만들 예정입니다. 아래 파일들이 같은 폴더에 있어야 합니다. 화면(기능)별로 파일이 나뉘어 있어 담당자가 자기 화면만 데이터에 연결할 수 있습니다.

| 파일 | 화면 | 데이터 연결 (짝) |
|---|---|---|
| `home.html` | 홈 (홈 화면 v2). 주소에 `?customer=C-001`이 있으면 `home_test.py` API에서 받아 그리고, 없으면 예시 데이터로 보여 줌 | `home_test.py` → `/api/home/{customer_id}` |
| `home_test.py` | 홈 화면 + 홈 API를 한 번에 띄우는 서버. `http://localhost:8000/?customer=C-001` | DB 접속은 `DATABASE_URL` |
| `backend/` | 보험·지원제도 API (FastAPI, 아래 참고). 지금은 이 API를 쓰는 화면이 없음 | DB `insurance`·`gov24` 스키마 |
| `start_bg.jpg` | 시작 화면 배경 사진 (새 시작 화면에서 쓸 예정, 지금 쓰는 화면 없음) | – |
| `common.css`, `common.js` | **모든 화면 공통** 하단 바(홈·수온·대응 요령·보험·내 정보) | – |

### 공통 하단 바 쓰는 법 (새 화면을 만들 때 필수)

하단 바는 화면마다 만들지 않고 `common.css`·`common.js` 한 곳에서 관리합니다. 각 화면에는 아래만 넣으세요.

```html
<head>
  …
  <link rel="stylesheet" href="common.css">
</head>
<body>
  …
  <nav id="tabbar" data-active="insurance"></nav>  <!-- 지금 화면의 탭 -->
  <script src="common.js"></script>
</body>
```

- `data-active`: `home` · `temp`(수온) · `response`(대응 요령) · `insurance`(보험) · `me`(내 정보) 중 하나. 그 탭이 선택 상태로 표시됩니다.
- 화면 전체를 `.screen`(세로 flex) 안에 넣는 페이지는 `<nav id="tabbar">`를 `.screen`의 마지막 칸으로 두면 맨 아래에 붙습니다. 그 밖의 페이지는 화면 아래에 고정되므로 본문 아래 여백(약 104px)을 두세요.
- 탭 이름·링크·아이콘은 `common.js`의 `TABS`에서만 고칩니다. 링크가 `null`인 탭(지금은 수온·내 정보)은 화면이 생기기 전까지 "준비 중" 안내만 보여 줍니다. 대응 요령·보험 탭은 이전 화면(`response.html`·`insurance.html`)을 삭제해서 새 화면을 만들 때까지 열리지 않습니다.
- 디자인은 `home.html`(홈 화면 v2) 기준입니다. 각 화면에서 하단 바 스타일을 따로 덮어쓰지 마세요.

- HTML 버전은 Streamlit 버전과 별개입니다. `app.py` 수정이 자동 반영되지는 않습니다. HTML의 `<style>`은 디자인, `<section>`은 화면 항목, `<script>`는 동작을 담당합니다.


### 백엔드 실행

1. `backend/backend/team.env.example`을 같은 폴더에 `.env`로 복사하고 `DB_USER`·`DB_PASSWORD`에 **본인 팀 계정**을 적습니다. `.env`는 깃허브에 올라가지 않습니다. 비밀번호를 단톡·캡처에 노출하지 마세요.
2. 해당 계정에 `insurance` 스키마 조회 권한이 있어야 합니다(없으면 503). 권한은 스키마 소유자(nifs_team2)나 서버 관리자가 부여합니다.
3. 프로젝트 최상위 폴더에서:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
```

4. `http://127.0.0.1:8000/docs`에서 API를 직접 눌러 볼 수 있습니다. 화면은 `python -m http.server 8765`로 열고 `http://localhost:8765/home.html`을 엽니다. localhost·127.0.0.1 주소는 CORS 허용되어 있고, 다른 주소는 `.env`의 `CORS_ORIGINS`에 추가합니다.

## 실행

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## 화면 흐름

시작하기 → 양식장 등록 → 비회원으로 오늘의 위험정보 이용

선택 경로: 좌측 상단 로그인 → 로그인 화면 → 회원가입 → 가입 정보 입력 → 오늘의 위험정보

- 가입은 프로토타입입니다. 로그인 화면은 입력과 화면 이동만 제공하며, 제출 시 인증 준비 중 안내를 표시합니다. 실제 계정 생성, 로그인, 서버 저장 기능은 아직 없습니다. 체험용 가입 후에도 비회원 상태로 이용합니다.
- 이름·생년월일·전화번호와 양식장 정보는 현재 Streamlit 세션에만 유지됩니다. 비밀번호는 가입 후 버리며 파일이나 DB에 저장하지 않습니다.
- 위험정보 화면의 수온, 주의 단계, 추이, 예측은 모두 고정 예시입니다.
- 오른쪽 위 ☰ 버튼으로 사이드 메뉴를 열고 닫을 수 있습니다. 양식장 정보 수정은 작동하며 대응 안내·보험 비교·상담은 준비 중 화면으로 연결됩니다.

## 수동 확인

1. API 서버 없이 양식장 등록 화면의 입력 항목이 바로 보이는지 확인합니다.
2. 양식 정보를 모두 선택하고 등록하기를 누르면 가입 없이 위험정보 화면으로 이동합니다.
3. 좌측 상단 로그인 → 회원가입으로 이동합니다. 빈 이름, 미선택 생년월일, 잘못된 전화번호, 8자 미만 비밀번호는 가입을 막는지 확인합니다.
4. 정상 입력 후 가입완료를 누르면 위험정보 화면이 표시됩니다. 로그인 화면의 비회원으로 계속 이용도 같은 화면으로 돌아가며 양식장 설정을 유지합니다.
5. 모바일 폭에서도 메뉴와 입력 항목이 잘리지 않는지 확인합니다.
