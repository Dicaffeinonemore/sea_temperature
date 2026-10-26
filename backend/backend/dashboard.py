"""대시보드 신청·주의 그래프 (n8n '대시보드 신청·주의 예측'이 만든 뷰 → SVG/PNG).

  dash_chart_yearly   연도별 (2년 전 · 1년 전 · 기준년 · 1년 후 예측, kind = 과거/예측)
  dash_chart_monthly  월별

  GET /api/v1/dashboard/chart/yearly.svg?region=전체    상담 홈이 들어갈 때마다 부르는 그래프 (DB에서 바로 그림)
  GET /api/v1/dashboard/chart/monthly.svg?region=전체
  (.png 도 됨)

모양은 상담 대시보드(sea_forecast.html) 21일 수온 그래프 기준. 색·모양은 이 파일에서만 고친다.
루트의 dash_chart.py(피그마용 파일 저장)도 이 파일의 함수를 그대로 쓴다.
dash 뷰가 public 이 아닌 스키마에 있으면 환경변수 DASH_SCHEMA 로 지정한다.
"""

from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from psycopg import Connection, sql

from backend.routes import DB

router = APIRouter(prefix="/api/v1/dashboard", tags=["대시보드"])

METRICS = ("신청", "주의")

# ── 그래프 스타일: 상담 대시보드(sea_forecast.html) :root 색과 맞춤. 색은 여기서만 바꿉니다 ──
COLOR = {"신청": "#1f5ae0", "주의": "#a8500a"}   # --accent / --warn
TEXT, SUB, MUTED = "#161a22", "#4b5363", "#6b7385"   # --text / --sub / --muted
GRID, BAND, AXIS = "#e8ecf1", "#f4f6f9", "#cdd3dd"   # .g-line / .g-band(예측 구간) / --line-strong
FONTS = ("Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", "AppleGothic", "NanumGothic", "Noto Sans CJK KR")


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
class NotReady(Exception):
    """dash 뷰가 없음 (n8n 워크플로우를 아직 안 돌림)"""


def fetch(conn: Connection, region: str = "전체", schema: str | None = None) -> tuple[list[dict], list[dict]]:
    """DB 뷰에서 (연도별, 월별)"""
    schema = schema or os.getenv("DASH_SCHEMA", "public")
    views = {}
    for name in ("dash_chart_yearly", "dash_chart_monthly"):
        if conn.execute("SELECT to_regclass(%s) AS rel", (f'"{schema}"."{name}"',)).fetchone()["rel"] is None:
            raise NotReady(f"{schema}.{name} 뷰가 없습니다. n8n '대시보드 신청·주의 예측' 워크플로우를 먼저 실행하세요."
                           " (다른 스키마에 있으면 DASH_SCHEMA 또는 --schema)")
        views[name] = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))
    yearly = conn.execute(sql.SQL("""
        SELECT year, years_ago, metric, value, low, high, kind
        FROM {} WHERE region = %s ORDER BY year, metric
    """).format(views["dash_chart_yearly"]), (region,)).fetchall()
    monthly = conn.execute(sql.SQL("""
        SELECT to_char(month, 'YYYY-MM-DD') AS month, years_ago, metric,
               value::float AS value, low::float AS low, high::float AS high, kind
        FROM {} WHERE region = %s ORDER BY month, metric
    """).format(views["dash_chart_monthly"]), (region,)).fetchall()
    return yearly, monthly


# ---------------------------------------------------------------------------
# 그래프 (matplotlib)
#   · pyplot 대신 Figure 를 직접 만듦 → API 서버에서 여러 요청이 동시에 와도 그림끼리 섞이지 않음
#   · svg.fonttype='none' → SVG를 피그마에 넣으면 글자가 글자로 남아 바로 고칠 수 있음
# ---------------------------------------------------------------------------
@lru_cache
def _mpl():
    try:
        import matplotlib
    except ImportError:
        raise RuntimeError("그래프를 그리려면 matplotlib 설치가 필요합니다: pip install matplotlib") from None
    matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib.figure import Figure

    installed = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in FONTS if f in installed), None)
    matplotlib.rcParams.update({"svg.fonttype": "none", "axes.unicode_minus": False, "font.size": 11, "legend.fontsize": 12, "legend.labelcolor": SUB})
    if font:
        matplotlib.rcParams["font.family"] = font
    return Figure


def _style(ax, *, hide_y: bool = False):
    ax.spines[["top", "right"] + (["left"] if hide_y else [])].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=11, length=0)
    ax.tick_params(axis="x", pad=8)
    ax.tick_params(axis="y", pad=6)
    if hide_y:
        ax.tick_params(left=False, labelleft=False)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def _heads(ax, x_split: float, past_txt: str, fc_txt: str):
    """sea_forecast.html 21일 그래프처럼: 예측 구간 회색 띠 + 위쪽 머리글 (실적 = accent, 예측 = muted)"""
    left, right = ax.get_xlim()
    ax.axvspan(x_split, right, color=BAND, zorder=0, linewidth=0)
    ax.set_xlim(left, right)
    kw = dict(xycoords=("data", "axes fraction"), xytext=(0, 6), textcoords="offset points",
              ha="center", va="bottom", fontsize=11, fontweight="bold", annotation_clip=False)
    ax.annotate(past_txt, ((left + x_split) / 2, 1), color=COLOR["신청"], **kw)
    ax.annotate(fc_txt, ((x_split + right) / 2, 1), color=MUTED, **kw)


def _header(fig, title: str, sub: str):
    """.sec-h 처럼: 굵은 제목(16px) + 옆에 회색 설명(13px)"""
    t = fig.text(0.012, 0.975, title, color=TEXT, fontsize=16, fontweight="bold", va="top")
    fig.canvas.draw()   # 제목 너비를 알아야 설명을 옆에 붙일 수 있음
    bb = t.get_window_extent().transformed(fig.transFigure.inverted())
    fig.text(bb.x1 + 0.012, 0.968, sub, color=MUTED, fontsize=12, va="top")


def _legend(fig, items):
    """.legend 처럼: 선 모양 + 글자(12px, --sub), 제목 바로 아래 한 줄"""
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, linewidth=lw, linestyle=ls) for _, c, ls, lw in items]
    fig.legend(handles, [n for n, *_ in items], loc="upper left", bbox_to_anchor=(0.006, 0.9), ncol=len(items),
               frameon=False, handlelength=1.8, columnspacing=1.6, fontsize=12)


def yearly_figure(rows: list[dict]):
    """신청·주의를 한 그래프에: 해마다 막대 두 개. 예측 해는 회색 띠 위 점선 빈 막대 + 예상 범위 선"""
    Figure = _mpl()
    rows = [r for r in rows if r.get("metric") in METRICS]
    years = sorted({int(r["year"]) for r in rows})
    fc_year = max((int(r["year"]) for r in rows if r["kind"] == "예측"), default=None)
    by = {(r["metric"], int(r["year"])): r for r in rows}

    fig = Figure(figsize=(10, 5), dpi=100)
    ax = fig.subplots()
    w, top_all = 0.36, 0.0
    for k, mt in enumerate(METRICS):
        for i, y in enumerate(years):
            r = by.get((mt, y))
            if not r:
                continue
            v, is_fc = float(r["value"]), r["kind"] == "예측"
            pos = i + (k - 0.5) * w
            ax.bar(pos, v, w * 0.9, color="white" if is_fc else COLOR[mt], edgecolor=COLOR[mt],
                   linewidth=1.6, linestyle=(0, (4, 3)) if is_fc else "-", zorder=2)
            top = v
            lo, hi = r.get("low"), r.get("high")
            if is_fc and lo is not None and hi is not None and float(hi) > float(lo):
                ax.errorbar(pos, v, yerr=[[v - float(lo)], [float(hi) - v]], color=COLOR[mt], capsize=5, linewidth=1.3, zorder=3)
                top = float(hi)
            ax.annotate(f"{round(v):,}", (pos, top), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", color=COLOR[mt], fontsize=11, fontweight="bold", zorder=4)
            top_all = max(top_all, top)

    ax.set_xticks(range(len(years)), [f"{y}\n(예측)" if y == fc_year else str(y) for y in years])
    ax.set_xlim(-0.6, len(years) - 0.4)
    ax.set_ylim(0, (top_all or 1) * 1.15)
    _style(ax, hide_y=True)
    if fc_year is not None:
        _heads(ax, years.index(fc_year) - 0.5, f"{years[0]}~{fc_year - 1} · 실적(가데이터)", "1년 후 · 예측 참고만")

    growth = []
    for mt in METRICS:
        cur, prev = by.get((mt, fc_year)), by.get((mt, (fc_year or 0) - 1))
        if cur and prev and float(prev["value"]):
            growth.append(f"{mt} {(float(cur['value']) / float(prev['value']) - 1) * 100:+.0f}%")
    _header(fig, "연도별 신청·주의 건수", f"{fc_year}년 예상 " + " · ".join(growth) if growth else "")
    _legend(fig, [("신청", COLOR["신청"], "-", 6), ("주의", COLOR["주의"], "-", 6),
                  ("예측 (점선 · 범위)", MUTED, (0, (4, 3)), 1.6)])
    fig.text(0.012, 0.015, "※ 가데이터 기반 시연용 · 예측은 연간 증가율 기하평균, 막대 위 선 = 예상 범위. 신청·주의 판단 기준이 아닌 참고값이에요.",
             color=MUTED, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.84))
    return fig


def monthly_figure(rows: list[dict]):
    """신청·주의를 한 그래프에: 월별 선 두 개 (실선 = 실적, 회색 띠 위 점선 = 예측, 연한 띠 = 예상 범위)"""
    Figure = _mpl()
    rows = [r for r in rows if r.get("metric") in METRICS]
    labels = sorted({r["month"][:7] for r in rows})
    idx = {m: i for i, m in enumerate(labels)}

    fig = Figure(figsize=(11, 5), dpi=100)
    ax = fig.subplots()
    for mt in METRICS:
        r = sorted((x for x in rows if x["metric"] == mt), key=lambda x: x["month"])
        past = [x for x in r if x["kind"] != "예측"]
        fc = [x for x in r if x["kind"] == "예측"]
        ax.plot([idx[x["month"][:7]] for x in past], [float(x["value"]) for x in past],
                color=COLOR[mt], linewidth=2.4, solid_joinstyle="round", solid_capstyle="round", zorder=3)
        if fc:
            head = past[-1:]   # 실적 마지막 달과 예측 첫 달을 끊김 없이 이어 그림
            ax.plot([idx[x["month"][:7]] for x in head + fc], [float(x["value"]) for x in head + fc],
                    color=COLOR[mt], linewidth=2.4, linestyle=(0, (4, 3)), zorder=3)
            if all(x.get("low") is not None and x.get("high") is not None for x in fc):
                ax.fill_between([idx[x["month"][:7]] for x in fc], [float(x["low"]) for x in fc],
                                [float(x["high"]) for x in fc], color=COLOR[mt], alpha=0.12, linewidth=0, zorder=2)

    ax.set_xticks(range(len(labels)), [m.replace("-", ".") if m.endswith(("-01", "-07")) else "" for m in labels])
    ax.set_xlim(-0.5, len(labels) - 0.5)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}건")
    _style(ax)
    first_fc = min((idx[x["month"][:7]] for x in rows if x["kind"] == "예측"), default=None)
    if first_fc is not None:
        _heads(ax, first_fc - 0.5, "실적(가데이터)", "1년 후 · 예측 참고만")
    _header(fig, "월별 신청·주의 건수", f"{labels[0].replace('-', '.')} ~ {labels[-1].replace('-', '.')} · 전체 지역 합계" if labels else "")
    _legend(fig, [("신청", COLOR["신청"], "-", 3), ("주의", COLOR["주의"], "-", 3),
                  ("예측 (점선 · 범위)", MUTED, (0, (4, 3)), 2)])
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    return fig


def render(fig, fmt: str = "svg") -> bytes:
    """그래프를 SVG/PNG 바이트로 (배경 투명, PNG는 2배 해상도)"""
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, transparent=True, **({"dpi": 200} if fmt == "png" else {}))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.get("/chart/{kind}.{fmt}", response_class=Response,
            responses={200: {"content": {"image/svg+xml": {}, "image/png": {}}}})
def chart(kind: Literal["yearly", "monthly"], fmt: Literal["svg", "png"], db: DB,
          region: Annotated[str, Query(min_length=1, max_length=30)] = "전체"):
    try:
        yearly, monthly = fetch(db, region)
    except NotReady as exc:
        raise HTTPException(404, str(exc)) from None
    rows = yearly if kind == "yearly" else monthly
    if not rows:
        raise HTTPException(404, f"'{region}' 대시보드 데이터가 없습니다.")
    try:
        fig = yearly_figure(rows) if kind == "yearly" else monthly_figure(rows)
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from None
    # n8n refreshes the views once a day, so a one-minute browser cache keeps every visit current.
    return Response(render(fig, fmt), media_type="image/svg+xml" if fmt == "svg" else "image/png",
                    headers={"Cache-Control": "max-age=60"})
