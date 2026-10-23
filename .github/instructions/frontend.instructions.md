---
name: HTML screens
description: Use when creating or editing the HTML screens (app, home, insurance, response, loading) or the shared tab bar.
applyTo: "**/*.html,**/*.css,**/*.js"
---

# HTML screen conventions

## Structure
- One screen (feature) per HTML file, so each teammate connects only their own screen to data. A new screen is a new file, not a section inside someone else's file.
- Plain HTML/CSS/JS, opened by double-click. No build tool, framework, or CDN dependency unless the user approves.
- Inside a file: `<style>` is design, `<section>` is screen content, `<script>` is behavior. Keep that split.
- Mobile first: content column up to 420px, font "Noto Sans KR" stack, visible `:focus-visible` outline, like `common.css`.

## Shared tab bar
- Every screen with navigation uses `<link rel="stylesheet" href="common.css">`, `<nav id="tabbar" data-active="...">`, and `<script src="common.js"></script>`.
- `data-active` is one of `home`, `temp`, `response`, `insurance`, `me`.
- Tab names, links, and icons change only in `TABS` in `common.js`. Do not restyle the tab bar per page. Both files are shared (see team ownership).
- Short waiting or error screens (`loading.html`) have no tab bar.

## Data between screens
- Farm conditions live in `sessionStorage` key `farm`. Read it; do not rename the key or change its shape without approval from every screen owner.
- Deep links: `app.html#register` (edit conditions), `app.html#login`. `loading.html?state=loading|nodata|fail|input&region=..&species=..&next=..`.
- Every data-driven view has loading, empty, error, and success states. Server down means sample data plus a visible "⚠️ 서버에 연결하지 못해…" notice, never silent fake data.

## Wording
- Insurance and support text never promises payment. Use "약관 조건 확인 필요", not "보상됩니다".
- Forecast values are references, not guarantees. Show the data source and update time.
- Write UI text in plain Korean for farmers. Avoid jargon or explain it.
