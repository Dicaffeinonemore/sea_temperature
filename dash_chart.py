"""
대시보드 그래프 → Figma용 SVG/PNG 만들기
  · 데이터: n8n Webhook(JSON) 또는 DB 뷰(dash_chart_yearly / dash_chart_monthly)
  · 결과: out/신청주의_연도별.svg·png, out/신청주의_월별.svg·png
    - SVG는 Figma에 끌어다 놓으면 선·글자를 하나하나 고칠 수 있음 (svg.fonttype='none' → 글자가 글자로 남음)
    - PNG는 2배 해상도, 배경 투명

사용법
  pip install matplotlib requests            (DB에서 읽을 때만: pip install psycopg2-binary)
  python dash_chart.py --url http://localhost:5678/webhook/dash-forecast-demo
  python dash_chart.py --db                  (환경변수 PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD 사용)
  python dash_chart.py --json 응답.json      (Webhook 응답을 저장해 둔 파일)
"""
import argparse, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ── 스타일 (Figma에서 바꾸기 쉽게 색은 여기서만 정함) ──
COLOR = {"신청": "#2563EB", "주의": "#EA580C"}
GRID, TEXT, SUB = "#E5E7EB", "#111827", "#6B7280"
for f in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK TC"]:
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams.update({"svg.fonttype": "none", "axes.unicode_minus": False, "font.size": 11})


def load(args):
    """연도별·월별 '전체' 데이터를 [{...}] 두 개로 돌려줌"""
    if args.db:
        import psycopg2, psycopg2.extras
        con = psycopg2.connect(sslmode=os.getenv("PGSSLMODE", "require"))
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT year, metric, value, low, high, kind FROM dash_chart_yearly WHERE region='전체' ORDER BY metric, year")
        yearly = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT to_char(month,'YYYY-MM-DD') AS month, metric, value, low, high, kind FROM dash_chart_monthly WHERE region='전체' ORDER BY metric, month")
        monthly = [dict(r) for r in cur.fetchall()]
        return yearly, monthly
    if args.url:
        import requests
        data = requests.get(args.url, timeout=60).json()
    else:
        data = json.load(open(args.json, encoding="utf-8"))
    return data["chart_yearly"], data["chart"]


def yearly_chart(rows, out):
    """신청·주의를 한 그래프에: 연도마다 막대 두 개(나란히). 예측 해는 점선 막대 + 범위 선"""
    import numpy as np
    years = sorted({int(x["year"]) for x in rows})
    fc_year = max((int(x["year"]) for x in rows if x["kind"] == "예측"), default=None)
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=100)
    w, xs = 0.36, np.arange(len(years))
    top_all = 0
    for k, mt in enumerate(["신청", "주의"]):
        by = {int(x["year"]): x for x in rows if x["metric"] == mt}
        for i, y in enumerate(years):
            x = by.get(y)
            if not x:
                continue
            v = float(x["value"]); is_fc = x["kind"] == "예측"
            pos = xs[i] + (k - 0.5) * w
            ax.bar(pos, v, w * 0.92, color="white" if is_fc else COLOR[mt], edgecolor=COLOR[mt],
                   linewidth=1.5, linestyle="--" if is_fc else "-", label=mt if i == 0 else None)
            top = v
            if is_fc and x.get("low") is not None and x.get("high") is not None and float(x["high"]) > float(x["low"]):
                ax.errorbar(pos, v, yerr=[[v - float(x["low"])], [float(x["high"]) - v]], color=COLOR[mt], capsize=5, linewidth=1.2)
                top = float(x["high"])
            ax.text(pos, top, f"{int(round(v))}", ha="center", va="bottom", color=COLOR[mt], fontsize=10, fontweight="bold")
            top_all = max(top_all, top)
    # 제목: 두 지표의 예상 증가율
    parts = []
    for mt in ["신청", "주의"]:
        by = {int(x["year"]): float(x["value"]) for x in rows if x["metric"] == mt}
        if fc_year and fc_year in by and (fc_year - 1) in by and by[fc_year - 1]:
            parts.append(f"{mt} {(by[fc_year] / by[fc_year - 1] - 1) * 100:+.0f}%")
    ax.set_title(f"신청·주의 건수 추이와 {fc_year}년 예측" + (f"  ·  {' / '.join(parts)}" if parts else ""),
                 loc="left", color=TEXT, fontsize=13, fontweight="bold")
    ax.set_xticks(xs, [f"{y}\n(예측)" if y == fc_year else str(y) for y in years], color=SUB)
    ax.set_ylim(0, top_all * 1.2)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False, labelleft=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", ncol=2)
    fig.text(0.01, 0.01, "※ 가데이터 기반 시연용 · 점선 막대 = 예측, 막대 위 선 = 예상 범위 (연간 증가율 기하평균)", color=SUB, fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, out)


def monthly_chart(rows, out):
    """신청·주의를 한 그래프에: 월별 선 두 개(실선 = 과거·기준년, 점선 = 예측, 띠 = 예상 범위)"""
    labels = sorted({x["month"][:7] for x in rows})
    idx = {m: i for i, m in enumerate(labels)}
    fig, ax = plt.subplots(figsize=(11, 4.8), dpi=100)
    for mt in ["신청", "주의"]:
        r = sorted([x for x in rows if x["metric"] == mt], key=lambda x: x["month"])
        past = [x for x in r if x["kind"] != "예측"]
        fc = [x for x in r if x["kind"] == "예측"]
        ax.plot([idx[x["month"][:7]] for x in past], [float(x["value"]) for x in past], color=COLOR[mt], linewidth=2, label=f"{mt}")
        if fc:
            xs = ([idx[past[-1]["month"][:7]]] if past else []) + [idx[x["month"][:7]] for x in fc]
            ys = ([float(past[-1]["value"])] if past else []) + [float(x["value"]) for x in fc]
            ax.plot(xs, ys, color=COLOR[mt], linewidth=2, linestyle="--", label=f"{mt} (예측)")
            if all(x.get("low") is not None for x in fc):
                ax.fill_between([idx[x["month"][:7]] for x in fc], [float(x["low"]) for x in fc], [float(x["high"]) for x in fc], color=COLOR[mt], alpha=0.12, linewidth=0)
    first_fc = min((idx[x["month"][:7]] for x in rows if x["kind"] == "예측"), default=None)
    if first_fc is not None:
        ax.axvline(first_fc - 0.5, color=SUB, linewidth=0.8, linestyle=":")
        ax.text(first_fc - 0.3, ax.get_ylim()[1] * 0.95, "예측 →", color=SUB, fontsize=9, va="top")
    ax.set_title("월별 신청·주의 건수", loc="left", color=TEXT, fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(labels)), [l if l.endswith("-01") or l.endswith("-07") else "" for l in labels], color=SUB, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", ncol=4, fontsize=9)
    fig.tight_layout()
    save(fig, out)


def save(fig, base):
    os.makedirs(os.path.dirname(base), exist_ok=True)
    fig.savefig(base + ".svg", transparent=True)
    fig.savefig(base + ".png", dpi=200, transparent=True)
    plt.close(fig)
    print("저장:", base + ".svg /.png")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url"); g.add_argument("--db", action="store_true"); g.add_argument("--json")
    p.add_argument("--out", default="out")
    a = p.parse_args()
    yearly, monthly = load(a)
    yearly_chart(yearly, os.path.join(a.out, "신청주의_연도별"))
    monthly_chart(monthly, os.path.join(a.out, "신청주의_월별"))
