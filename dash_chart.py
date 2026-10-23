"""
우리 바다 안심도우미 - 대시보드 신청·주의 그래프를 피그마용 파일(SVG·PNG)로 저장

데이터: n8n '대시보드 신청·주의 예측' 워크플로우가 만든 뷰
  dash_chart_yearly   연도별 (2년 전 · 1년 전 · 기준년 · 1년 후 예측, kind = 과거/예측)
  dash_chart_monthly  월별

결과 (기본 out/ 폴더)
  신청주의_연도별.svg / .png   신청·주의를 한 그래프에 (예측 해는 점선 빈 막대 + 예상 범위)
  신청주의_월별.svg / .png     월별 신청·주의 선 그래프
  - SVG는 피그마에 끌어다 놓으면 선·글자를 하나하나 고칠 수 있음 (글자가 글자로 남음)
  - PNG는 2배 해상도, 배경 투명
  - 모양은 '고수온 선제 상담 대시보드'(sea_forecast.html) 21일 수온 그래프 기준:
    신청 --accent · 주의 --warn, 예측 구간은 회색 띠(.g-band) + 점선, 머리글 '실적 / 예측 · 참고만'.
    색은 아래 COLOR 등에서만 바꾸세요.

이 파일 하나만 추가하면 됩니다. 다른 파일은 고치지 않습니다.
DB 접속은 insurance_test.py와 같습니다: backend/backend/.env 또는 환경변수 DATABASE_URL

실행 (sea_temperature 폴더에서)
  pip install matplotlib                       (나머지는 backend/backend/requirements.txt 그대로)
  python dash_chart.py --db                    DB 뷰에서
  python dash_chart.py --db --region 통영      지역별
  python dash_chart.py --db --schema 스키마명   dash 뷰가 public 이 아닐 때 (또는 환경변수 DASH_SCHEMA)
  python dash_chart.py --url http://localhost:5678/webhook/dash-forecast   n8n Webhook 응답에서
  python dash_chart.py --json 응답.json        저장해 둔 n8n 응답 파일에서 (DB 없이 시험용)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # sea_temperature/
sys.path.insert(0, str(ROOT / "backend"))       # backend 패키지(DB 접속)를 불러오기 위해

METRICS = ("신청", "주의")

# ── 그래프 스타일: 상담 대시보드(sea_forecast.html) :root 색과 맞춤. 색은 여기서만 바꿉니다 ──
COLOR = {"신청": "#1f5ae0", "주의": "#a8500a"}   # --accent / --warn
TEXT, SUB, MUTED = "#161a22", "#4b5363", "#6b7385"   # --text / --sub / --muted
GRID, BAND, AXIS = "#e8ecf1", "#f4f6f9", "#cdd3dd"   # .g-line / .g-band(예측 구간) / --line-strong
FONTS = ("Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", "AppleGothic", "NanumGothic", "Noto Sans CJK KR")


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
def fetch_db(region: str, schema: str) -> tuple[list[dict], list[dict]]:
    """DB 뷰에서 (연도별, 월별). 접속은 backend/backend/.env 또는 DATABASE_URL (insurance_test.py와 같음)"""
    from psycopg import sql
    from backend.db import connect

    with connect() as conn:
        conn.read_only = True
        views = {}
        for name in ("dash_chart_yearly", "dash_chart_monthly"):
            if conn.execute("SELECT to_regclass(%s) AS rel", (f'"{schema}"."{name}"',)).fetchone()["rel"] is None:
                sys.exit(f"{schema}.{name} 뷰가 없습니다. n8n '대시보드 신청·주의 예측' 워크플로우를 먼저 실행하세요."
                         " (다른 스키마에 있으면 --schema 스키마명)")
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


def load(args) -> tuple[list[dict], list[dict]]:
    if args.db:
        import psycopg

        try:
            return fetch_db(args.region, args.schema)
        except psycopg.Error as exc:
            # 접속 문자열·비밀번호가 화면에 찍히지 않도록 오류 종류만 보여 줌
            sys.exit(f"DB 연결 또는 조회 실패 ({type(exc).__name__}). backend/backend/.env 또는 DATABASE_URL을 확인하세요.")
    if args.url:
        import requests

        r = requests.get(args.url, timeout=60)
        r.raise_for_status()
        data = r.json()
    else:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    # n8n 응답은 '전체' 기준. kind 가 '2년 전'처럼 와도 그래프는 '예측' 여부만 봄
    return data["chart_yearly"], data["chart"]


# ---------------------------------------------------------------------------
# 그래프 (matplotlib)
#   · pyplot 대신 Figure 를 직접 만듦 → 나중에 API 서버에서 불러 써도 요청끼리 섞이지 않음
#   · svg.fonttype='none' → SVG를 피그마에 넣으면 글자가 글자로 남아 바로 고칠 수 있음
# ---------------------------------------------------------------------------
@lru_cache
def _mpl():
    try:
        import matplotlib
    except ImportError:
        sys.exit("그래프를 그리려면 matplotlib 설치가 필요합니다: pip install matplotlib")
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
# 실행
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="대시보드 그래프를 피그마용 SVG·PNG로 저장")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", action="store_true", help="DB 뷰 dash_chart_yearly / dash_chart_monthly")
    src.add_argument("--url", help="n8n Webhook 주소")
    src.add_argument("--json", help="저장해 둔 n8n 응답 파일")
    p.add_argument("--region", default="전체", help="'전체'(기본) 또는 통영·거제·고성·남해·창원 …")
    p.add_argument("--schema", default=os.getenv("DASH_SCHEMA", "public"), help="dash 뷰가 있는 스키마 (기본 public)")
    p.add_argument("--out", default="out", help="저장 폴더 (기본 out)")
    p.add_argument("--format", choices=["svg", "png", "both"], default="both")
    a = p.parse_args()

    yearly, monthly = load(a)
    if not yearly:
        sys.exit(f"'{a.region}' 데이터가 없습니다. n8n '대시보드 신청·주의 예측'을 먼저 실행했는지, --region 값을 확인하세요.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if a.region == "전체" else f"_{a.region}"
    fmts = ["svg", "png"] if a.format == "both" else [a.format]
    charts = [("연도별", yearly_figure(yearly))] + ([("월별", monthly_figure(monthly))] if monthly else [])
    for name, fig in charts:
        for fmt in fmts:
            path = out / f"신청주의_{name}{suffix}.{fmt}"
            path.write_bytes(render(fig, fmt))
            print("저장:", path)


if __name__ == "__main__":
    main()
