"""筛选看板：按「日期范围 / 数据源 / Top N」过滤长表，重新算统计并生成一张看板。

和 analysis/report.py 的分工：
    report.py     全量数据 → 归档一批报告（reports/<时间>/），历史留档、不参与筛选
    live_view.py  当前筛选条件 → 一张随时会重算的看板（views/筛选看板.html）

为什么做成独立模块、而不是在界面里直接算：
    1. 它要重算 16 张表，跑一次好几秒；放界面主线程会卡住。做成模块就能用现成的
       run_module 机制丢进子进程里跑（打包后是 exe 自己当解释器，不需要外部 Python）。
    2. 统计和画图全部复用现成函数，统计逻辑一行都不重复写：
       warehouse.load_boards / report.build_tables / report.build_charts /
       report.save_tables / report.write_meta / report.copy_assets / charts.make_page

用法（界面上的「筛选看板」页会自动带这些参数调用它）：
    python -m analysis.live_view --start 2026-09-16 --end 2026-09-18 \
        --datasets baidu_realtime,toutiao_hot --top 10
"""
import argparse
import json
import re
from pathlib import Path

from analysis import cross, report
from charts.basic import make_page
from utils.logger import get_logger
from utils.paths import BASE_DIR
from warehouse import load_boards

OUT_DIR = BASE_DIR / "views"                    # ← 别放 reports/ 里，那边的目录名会被当"报告批次"
OUT_HTML = OUT_DIR / "筛选看板.html"
CROSS_HTML = OUT_DIR / "跨源对比.html"           # 「跨源对比」子页：两张跨源图合成一页
TABLES_DIR = OUT_DIR / "表"                     # 每张统计表一份 CSV（界面预览 + 另存都用它）
CHARTS_DIR = OUT_DIR / "图表"                    # 每张图一份 HTML（界面按表名切图）
MANIFEST = OUT_DIR / "_清单.json"                # 界面读它来填指标卡和表下拉

# 界面上「数据源」那排勾选框用的名字（键 = 长表里的 dataset 列的值）
DATASET_LABELS = {
    "baidu_realtime": "百度热搜",
    "bilibili_ranking": "B站日榜",
    "douban_movie_top250": "豆瓣电影",
    "douban_book_top250": "豆瓣读书",
    "douban_doulist": "豆瓣豆列",
    "juejin_hot": "掘金热榜",
    "toutiao_hot": "头条热榜",
}

logger = get_logger("live_view")


def filter_boards(df, start=None, end=None, datasets=None):
    """按条件过滤长表。三个条件都是可选的：不传就等于不过滤。"""
    view = df
    if start:
        view = view[view["date"] >= start]
    if end:
        view = view[view["date"] <= end]
    if datasets:
        view = view[view["dataset"].isin(datasets)]
    return view


def describe(start, end, datasets, top) -> str:
    """把这次筛选写成一句话（进看板标题，也进日志）。"""
    parts = []
    if start or end:
        parts.append(f"{start or '最早'} ~ {end or '最新'}")
    if datasets:
        names = [DATASET_LABELS.get(d, d) for d in datasets]
        parts.append("、".join(names) if len(names) <= 3 else f"{len(names)} 个数据源")
    parts.append(f"Top{top}")
    return "筛选看板（" + " ｜ ".join(parts) + "）"


def write_notice(title: str, message: str, path=None) -> None:
    """没数据可画的时候也生成一页，总比留个空白页让人踏实。

    path 不传就写总览那页；「跨源对比」子页会传自己的路径进来。
    """
    target = path if path is not None else OUT_HTML
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{title}</title></head>"
        "<body style=\"font-family:'Microsoft YaHei',sans-serif;padding:40px;\">"
        f"<h2 style='margin:0 0 12px'>{title}</h2>"
        f"<p style='font-size:15px;line-height:1.8'>{message}</p>"
        "</body></html>",
        encoding="utf-8",
    )
    print(f"已生成提示页：{target}")


# 插到单图 HTML 的 <head> 里：让百分比有参照物 + 窗口变化时重画
RESPONSIVE_HEAD = (
    "<style>html,body{height:100%;margin:0;padding:0;overflow:hidden;}</style>"
    "<script>window.addEventListener('resize',function(){"
    "for(var k in window){var c=window[k];"
    "if(k.indexOf('chart_')===0&&c&&typeof c.resize==='function'){c.resize();}}});</script>"
)

# 把写死的 900×500 改成 100%（要连内联样式一起改，光插 CSS 压不住它）
SIZE_RE = re.compile(r'(class="chart-container" style=")width:\s*[\d.]+px;\s*height:\s*[\d.]+px;')


def make_responsive(path) -> None:
    """让单图 HTML 跟着面板大小走。

    pyecharts 生成的 div 尺寸是**写死在内联样式里**的（900×500），界面里面板一大
    就四周空一圈。做法：① 把内联尺寸改成 100% ② 给 html/body 补 height:100%
    （不然百分比没有参照）③ 挂 resize 监听，窗口变了图跟着变。
    只动"单图文件"，归档看板和总览页保持原样。
    """
    path = Path(path)
    html = path.read_text(encoding="utf-8")
    if "</head>" not in html or 'style="width:100%' in html:
        return
    html = SIZE_RE.sub(r"\1width:100%; height:100%;", html, count=1)
    html = html.replace("</head>", RESPONSIVE_HEAD + "</head>", 1)
    path.write_text(html, encoding="utf-8")


def write_manifest(title, args, df, view, tables, chart_files, cross_charts) -> None:
    """写 _清单.json —— 界面靠它填指标卡、表下拉、单图路径。

    ★ 没数据时也要写：界面是按固定路径找这个文件的，缺了就会在日志里报
      「没找到 views 下的 _清单.json，生成可能失败了」，而真实情况只是「仓库里还没有数据」。
      所以空仓库 / 筛空时也写一份（表为空、指标为 0），界面就能正常显示提示页。
    """
    rows = int(len(view)) if view is not None else 0
    snapshot_n = int(view["snapshot_ts"].nunique()) if rows else 0
    dataset_n = int(view["dataset"].nunique()) if rows else 0
    date_range = f"{view['date'].min()} ~ {view['date'].max()}" if rows else "（还没有数据）"
    MANIFEST.write_text(json.dumps({
        "标题": title,
        "筛选": {"起始": args.start, "结束": args.end, "数据源": args.datasets, "TopN": args.top},
        "指标": {
            "全量行数": int(len(df)),
            "当前视图": rows,
            "数据集": dataset_n,
            "快照数": snapshot_n,
            "日期范围": date_range,
        },
        "表": [
            {
                "名字": name,
                "行数": len(table),
                "列数": len(table.columns),
                "csv": f"表/{name}.csv",
                "图": chart_files.get(name),
            }
            for name, table in (tables or {}).items()
        ],
        "跨源对比": {
            "页面": CROSS_HTML.name,
            "有几张图": len(cross_charts or []),
            "同日TopN": {
                "表": "跨源_同日TopN",
                "csv": "表/跨源_同日TopN.csv",
                "行数": len(tables["跨源_同日TopN"]) if tables and "跨源_同日TopN" in tables else 0,
                "n": min(args.top, 10),
            },
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="按筛选条件生成看板")
    ap.add_argument("--start", default=None, help="起始日期 YYYY-MM-DD（含）")
    ap.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD（含）")
    ap.add_argument("--datasets", default=None,
                    help="逗号分隔的 dataset 名；不传 = 全部")
    ap.add_argument("--top", type=int, default=15, help="排行类图显示前几名")
    args = ap.parse_args()

    datasets = [d.strip() for d in (args.datasets or "").split(",") if d.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)   # ★ 后面 save_tables/render 都要求目录已存在
    df = load_boards()
    title = describe(args.start, args.end, datasets, args.top)

    if df.empty:
        print("仓库里还没有数据：先跑一次采集（或点界面上的「开始采集」）。")
        write_notice(title, "仓库里还没有数据。<br>先跑一次采集，再回来生成筛选看板。")
        write_manifest(title, args, df, None, {}, {}, [])   # ★ 空仓库也写清单，界面才不会报"生成失败"
        return 0

    view = filter_boards(df, args.start, args.end, datasets)
    print(f"{title}")
    print(f"数据实际范围：{df['date'].min()} ~ {df['date'].max()}（全量 {len(df)} 行）")
    print(f"筛选后：{len(view)} 行，{view['dataset'].nunique() if len(view) else 0} 个数据集")

    if view.empty:
        print("这个筛选条件下没有数据。")
        write_notice(title, f"当前筛选没有数据：{args.start} ~ {args.end}。<br>"
                            f"数据实际范围是 {df['date'].min()} ~ {df['date'].max()}，"
                            "把日期范围放宽一点再试。")
        write_manifest(title, args, df, view, {}, {}, [])   # ★ 筛空也写清单
        return 0

    tables = report.build_tables(view)
    # 额外加一张给「跨源对比」子页用（app.py 那一页也有这张）：同日各源 Top N
    tables["跨源_同日TopN"] = cross.top_by_source(view, n=min(args.top, 10))
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    report.save_tables(tables, TABLES_DIR)      # 每张统计表一份 CSV

    named = report.build_charts_named(tables, top=args.top)
    chart_files = {}
    for name, chart in named:                   # 逐张出图：界面按表名切换显示哪一张
        chart_path = CHARTS_DIR / f"{name}.html"
        chart.render(str(chart_path))
        make_responsive(chart_path)             # ★ 让单图跟着面板走（默认是写死的 900×500）
        chart_files[name] = chart_path.relative_to(OUT_DIR).as_posix()

    charts = [chart for _, chart in named]
    if charts:
        make_page(charts, title).render(str(OUT_HTML))
        report.copy_assets(OUT_DIR)             # 总览页离线可看
    else:
        print("筛选后每张图都没有内容（数据太少），生成提示页。")
        write_notice(title, "筛选后没有可画的图：这个条件下每个统计表都是空的，"
                            "把日期范围或数据源放宽一点再试。")
    if chart_files:
        report.copy_assets(CHARTS_DIR)          # 单图也要能离线打开

    # ★ 「跨源对比」子页：把两张跨源图合成一页；一张都没有就给提示页（附上原因）
    cross_names = ("跨源_翻新速度", "跨源_同话题")
    cross_charts = [chart for name, chart in named if name in cross_names]
    if cross_charts:
        make_page(cross_charts, "跨源对比").render(str(CROSS_HTML))
        report.copy_assets(OUT_DIR)
    else:
        write_notice("跨源对比",
                     "当前筛选下没有可比的跨源数据。<br>"
                     "翻新速度至少要两天的数据（把日期范围拉宽）；"
                     "同话题对比需要两个源在同一天出现相近的标题。",
                     path=CROSS_HTML)

    report.write_meta(view, tables, OUT_DIR)

    write_manifest(title, args, df, view, tables, chart_files, cross_charts)

    print(f"已生成：{OUT_HTML}（{len(charts)} 张图）")
    print(f"统计表 {len(tables)} 份 -> {TABLES_DIR}")
    print(f"单图 {len(chart_files)} 张 -> {CHARTS_DIR}")
    print(f"清单 -> {MANIFEST}")
    logger.info("[筛选] 已生成 %s（%d 张图 / %d 张表 / %d 行数据）",
                OUT_HTML, len(charts), len(tables), len(view))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
