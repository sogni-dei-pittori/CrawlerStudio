"""分析报告：把统计表算出来、打印、落盘到 reports/<时间>/。

只做三件事：调统计函数 → 打印 → 写 CSV。统计逻辑一律在各自的模块里。
"""
import time
import shutil
from pathlib import Path
from charts.basic import bar_h, bar_v, line_multi, make_page, topic_rank_bar
from utils.logger import get_logger
from utils.paths import BASE_DIR
from warehouse import load_boards
from analysis import bilibili, common, douban, hot, baidu, cross

OUT_ROOT = BASE_DIR / "reports"
logger = get_logger("report")
PREVIEW_ROWS = 15


def build_tables(df) -> dict:
    """要出的统计表集中在这里 —— 加一个新指标就是加一行。

    ★ 每张表单独 try/except：空仓库、或者老快照缺某一列（比如历史数据没有 rating）时，
      坏一张表不该让整批报告都出不来 —— 跳过的会在日志里留一行原因。
      （2026-09-21 实测：新装的软件第一次点「生成报告」就是空仓库，
       旧写法直接 KeyError: rating 崩掉，整批报告一张表都没有。）
    """
    specs = {
        "豆瓣_评分分布": lambda: douban.rating_distribution(df),
        "豆瓣_年代分布": lambda: douban.decade_distribution(df),
        "百度_名次变化": lambda: common.rank_changes(df, "baidu_realtime"),
        "豆瓣_投票增长": lambda: douban.votes_growth(df),
        "B站_播放量分布": lambda: bilibili.score_distribution(df),
        "B站_名次相关": lambda: bilibili.rank_score_table(df),
        "B站_播放量增长": lambda: bilibili.views_growth(df),
        "掘金_作者上榜": lambda: hot.author_ranking(df),
        "头条_标签构成": lambda: hot.label_composition(df),
        "头条_热度相关": lambda: hot.heat_rank_check(df),
        "百度_标签构成": lambda: baidu.tag_composition(df),
        "百度_分类构成": lambda: baidu.category_composition(df),
        "跨源_覆盖情况": lambda: cross.daily_coverage(df),
        "跨源_同日Top5": lambda: cross.top_by_source(df, n=5),
        "跨源_同话题": lambda: cross.cross_topic(df, n=10),
        "跨源_翻新速度": lambda: cross.churn_rate(df, n=10),
    }
    tables = {}
    for name, make in specs.items():
        try:
            tables[name] = make()
        except Exception as exc:      # 空仓库 / 缺列 / 口径问题 → 跳过这一张，别毁整批
            logger.warning("统计表「%s」跳过：%s: %s", name, type(exc).__name__, exc)
    return tables


def _fill_blank(table, col):
    """把空值换成"（空）"：这几张构成表里有大量空标签，不换图上是没名字的柱子。"""
    return table.assign(**{col: table[col].replace("", "（空）")})


def chart_specs(top: int = 15) -> list:
    """图表清单：(图名, 依赖的表名, 画图函数)。

    单独抽出来，是为了让「筛选看板」能**按名字逐张出图**（选中哪张表就显示哪张图），
    不用再维护第二份清单。想加一张图就在这里加一行。

    top：排行类图最多显示几个（默认 15，和以前一样）。
    """
    return [
        ("豆瓣_评分分布", "豆瓣_评分分布",
         lambda t: bar_v(t["豆瓣_评分分布"], "bucket", "count", "豆瓣 Top250 评分分布")),
        ("豆瓣_年代分布", "豆瓣_年代分布",
         lambda t: bar_v(t["豆瓣_年代分布"], "decade", "count", "豆瓣 Top250 年代分布")),
        ("百度_名次变化", "百度_名次变化",
         lambda t: bar_h(t["百度_名次变化"], "title", "名次跨度",
                         f"百度热搜：名次跨度 Top{top}", top=top)),
        ("豆瓣_投票增长", "豆瓣_投票增长",
         lambda t: bar_h(t["豆瓣_投票增长"], "title", "投票增长",
                         f"豆瓣 Top250：评价人数增长 Top{top}", top=top)),
        ("B站_播放量分布", "B站_播放量分布",
         lambda t: bar_v(t["B站_播放量分布"], "bucket", "count", "B站日榜：播放量分布")),
        ("B站_播放量增长", "B站_播放量增长",
         lambda t: bar_h(t["B站_播放量增长"], "title", "播放增长",
                         f"B站日榜：3 天播放量增长 Top{top}", top=top, label_max=6)),
        ("掘金_作者上榜", "掘金_作者上榜",
         lambda t: bar_h(t["掘金_作者上榜"], "author", "上榜次数",
                         f"掘金热榜：作者上榜次数 Top{top}", top=top)),
        # ↓ 下面三张"构成表"以前没有图，单源指标里点开是空的 —— 这里补上
        ("百度_标签构成", "百度_标签构成",
         lambda t: bar_v(_fill_blank(t["百度_标签构成"], "tag"), "tag", "count",
                         "百度热搜：标签构成")),
        ("百度_分类构成", "百度_分类构成",
         lambda t: bar_v(_fill_blank(t["百度_分类构成"], "category"), "category", "count",
                         "百度热搜：分类构成")),
        ("头条_标签构成", "头条_标签构成",
         lambda t: bar_v(_fill_blank(t["头条_标签构成"], "label"), "label", "count",
                         "头条热榜：标签构成")),
        # ↓ 相关性：一两行的表也能画（一根柱子把系数画出来，比只看数字直观）
        ("B站_名次相关", "B站_名次相关",
         lambda t: bar_v(t["B站_名次相关"], "榜单", "名次与播放量相关",
                         "B站：名次与播放量的相关性（越负 = 越靠前播放越高）")),
        ("头条_热度相关", "头条_热度相关",
         lambda t: bar_v(t["头条_热度相关"], "榜单", "名次与热度相关",
                         "头条：名次与热度的相关性（越负 = 越靠前热度越高）")),
        # ↓ 覆盖情况：每天每源一条线，缺数据的日子一眼就看出来
        ("跨源_覆盖情况", "跨源_覆盖情况",
         lambda t: line_multi(t["跨源_覆盖情况"], "date", "dataset", "条数",
                              "各源每天抓到多少条（看哪天缺数据）")),
        ("跨源_翻新速度", "跨源_翻新速度",
         lambda t: line_multi(t["跨源_翻新速度"], "日期", "源", "重合率",
                              "各源 Top10 跨天重合率（越低 = 翻新越快）")),
        ("跨源_同话题", "跨源_同话题",
         lambda t: topic_rank_bar(t["跨源_同话题"], label_max=10)),
    ]


def build_charts_named(tables: dict, top: int = 15) -> list:
    """和 build_charts 一样，只是把图名一起返回：[(图名, 图), ...]。

    跳过规则：① 依赖的表不存在或为空 → 跳过（否则会留一个"只有标题没有柱子"的空画框）；
    ② 表在但缺列 → 兜住异常跳过。
    全量数据下 16 张表都非空，9 张图全在。
    """
    charts = []
    for name, table_name, make in chart_specs(top):
        table = tables.get(table_name)
        if table is None or len(table) == 0:
            logger.info("跳过一张图（%s）：这次数据下这张表是空的", name)
            continue
        try:
            charts.append((name, make(tables)))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("跳过一张图（%s）：%s: %s", name, exc.__class__.__name__, exc)
    return charts


def build_charts(tables: dict, top: int = 15) -> list:
    """只要图、不要名字的接口（report.py 自己用）。"""
    return [chart for _, chart in build_charts_named(tables, top)]


def save_tables(tables: dict, out_dir: Path) -> None:
    """每张表写一个 CSV（utf-8-sig，Excel 双击不乱码）。"""
    for name, table in tables.items():
        path = out_dir / f"{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("已保存：%s（%d 行）", path.name, len(table))


def write_meta(df, tables: dict, out_dir: Path) -> None:
    """写一份说明：这批报告基于哪些快照、每张表多少行、有哪些列。"""
    lines = [
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"数据范围：{df['date'].min()} ~ {df['date'].max()}"
        f"（共 {df['snapshot_ts'].nunique()} 个快照，{len(df)} 行）",
        "",
        "本目录内容：",
    ]
    for name, table in tables.items():
        lines.append(f"  {name}.csv —— {len(table)} 行，列：{', '.join(table.columns)}")
    (out_dir / "_说明.txt").write_text("\n".join(lines), encoding="utf-8")
    logger.info("已保存：_说明.txt")


def copy_assets(out_dir: Path) -> None:
    """把 echarts.min.js 复制到报告目录，让 看板.html 能离线打开。

    前提：charts/assets/echarts.min.js 已下载（见 README 坑 15），
    且 charts/basic.py 里设了 CurrentConfig.ONLINE_HOST = "assets/"。
    """
    src = BASE_DIR / "charts" / "assets" / "echarts.min.js"
    if not src.is_file():
        logger.warning("没找到 %s，看板.html 仍会依赖 CDN（断网打不开）", src)
        return
    dst_dir = out_dir / "assets"
    dst_dir.mkdir(exist_ok=True)
    shutil.copy(src, dst_dir / "echarts.min.js")
    logger.info("已复制：assets/echarts.min.js（离线可用）")


def main() -> int:
    df = load_boards()
    out_dir = OUT_ROOT / time.strftime("%Y-%m-%d_%H-%M")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ★ 空仓库不是错误：新装的软件第一次点「生成报告」就是这样。
    #   给一句人话 + 一个提示页，退出码 0（和「筛选看板」那边的做法一致）。
    if df.empty:
        print("仓库里还没有数据：data/ 下没读到任何快照。")
        print("先点界面上的「开始采集」跑一次，再回来生成报告。")
        (out_dir / "看板.html").write_text(
            "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<title>还没有数据</title></head>"
            "<body style=\"font-family:'Microsoft YaHei',sans-serif;padding:40px;\">"
            "<h2 style='margin:0 0 12px'>还没有数据，暂时画不出图</h2>"
            "<p style='font-size:15px;line-height:1.8'>仓库里没有读到任何快照。<br>"
            "先跑一次采集（界面上的「开始采集」），再回来生成报告。</p></body></html>",
            encoding="utf-8")
        logger.warning("仓库为空：只生成了提示页 %s", out_dir / "看板.html")
        return 0

    tables = build_tables(df)

    for name, table in tables.items():  # 表格用 print：它是给人看的结果
        print(f"\n--- {name}（共 {len(table)} 行，下面只显示前 {PREVIEW_ROWS} 行）---")
        print(table.head(PREVIEW_ROWS).to_string(index=False))

    save_tables(tables, out_dir)  # 运行信息用 logger：写进日志文件
    charts = build_charts(tables)
    make_page(charts, "爬虫项目分析看板").render(str(out_dir / "看板.html"))
    logger.info("已保存：看板.html（%d 张图）", len(charts))
    copy_assets(out_dir)
    write_meta(df, tables, out_dir)
    logger.info("报告目录：%s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
