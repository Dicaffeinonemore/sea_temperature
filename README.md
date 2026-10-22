# sea_temperature

## HTML 버전

화면을 팀원별로 새로 구성하기 위해 홈과 사용자 정보 입력 화면만 남겼습니다. 새 화면은 파일 하나씩 만들고 아래 공통 하단 바를 씁니다.

| 파일 | 화면 | 데이터 연결 |
|---|---|---|
| `app.html` | 시작 · 양식장 등록 · 로그인 · 회원가입 | – |
| `home.html` | 홈 (홈 화면 v2) | `home_test.py` → `/api/home/{customer_id}` |
| `home_test.py` | 홈 화면 + 홈 API 서버. `http://localhost:8000/?customer=C-001` | DB 접속은 `DATABASE_URL` |
| `start_bg.jpg` | 시작 화면 배경 사진 | – |
| `common.css`, `common.js` | **모든 화면 공통** 하단 바(홈·수온·대응 요령·보험·내 정보) | – |
| `backend/` | 보험·지원제도 API (FastAPI) | DB `insurance`·`gov24` 스키마 |

- 시작 → 양식장 등록 → 홈으로 이동합니다. 홈 좌측 상단의 로그인 → 회원가입으로 가입 화면에 들어갑니다.
- 양식장 정보(지역·품종·방식·보험)는 sessionStorage `farm` 키에 저장되어 모든 화면에서 읽을 수 있습니다.
- 다른 화면에서 `app.html#register`(조건 수정), `app.html#login`(로그인)으로 들어오면 해당 화면이 바로 열립니다.

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

- `data-active`: `home` · `temp`(수온) · `response`(대응 요령) · `insurance`(보험) · `me`(내 정보) 중 하나.
- 탭 링크는 `common.js`의 `TABS`에서만 고칩니다. 지금은 홈만 연결되어 있고, 나머지 탭은 `href:null`이라 "준비 중" 안내가 뜹니다. 새 화면을 만들면 해당 탭의 `href`에 파일 이름을 넣으세요.
- 디자인은 `home.html`(홈 화면 v2) 기준입니다. 각 화면에서 하단 바 스타일을 따로 덮어쓰지 마세요.

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

4. `http://127.0.0.1:8000/docs`에서 API를 직접 눌러 볼 수 있습니다. 화면은 `python -m http.server 8765`로 열고 `http://localhost:8765/app.html`에서 시작합니다. localhost·127.0.0.1 주소는 CORS 허용되어 있고, 다른 주소는 `.env`의 `CORS_ORIGINS`에 추가합니다.
