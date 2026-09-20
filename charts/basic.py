"""图表层通用件：只把统计表画出来，不含任何统计逻辑。"""
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Page, Pie, Scatter
from pyecharts.commons.utils import JsCode
from pyecharts.globals import CurrentConfig

CurrentConfig.ONLINE_HOST = "assets/"


def bar_v(table, x_col, y_col, title) -> Bar:
    """纵向柱状图（适合区间 / 类别这种短标签，如 <8.0、1990）。"""
    return (
        Bar()
        .add_xaxis([str(v) for v in table[x_col]])
        .add_yaxis(title, [float(v) for v in table[y_col]])
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=x_col),
            yaxis_opts=opts.AxisOpts(name=y_col),
        )
    )


def _truncate_js(max_chars: int) -> JsCode:
    """生成 JS 函数：轴标签超过 max_chars 就截断加省略号。

    只作用于"坐标轴上的显示"——数据本身仍是完整标题，所以
    ① 鼠标悬停的 tooltip 显示完整标题 ② 落盘 CSV 也是完整标题。
    """
    return JsCode(
        "function (name) { "
        f"return name.length > {max_chars} ? name.slice(0, {max_chars}) + '...' : name; "
        "}"
    )


def bar_h(table, x_col, y_col, title, top=None, label_max=None) -> Bar:
    """横向条形图（适合名字很长的排行）。

    label_max：轴标签最多显示几个字（超出用 ... 截断；只影响显示，tooltip 仍完整）。
    """
    data = table.head(top) if top else table
    return (
        Bar()
        .add_xaxis([str(v) for v in data[x_col]])
        .add_yaxis(title, [float(v) for v in data[y_col]])
        .reversal_axis()
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=y_col),
            yaxis_opts=opts.AxisOpts(
                name=x_col,
                axislabel_opts=(
                    opts.LabelOpts(formatter=_truncate_js(label_max)) if label_max else None
                ),
            ),
        )
    )


def line_multi(table, x_col, group_col, y_col, title, smooth=False) -> Line:
    """多系列折线图：按 group_col 分组，每组一条线。

    ⚠️ 某个源在某天没数据时要传 None（echarts 会断线），**不能填 0**
    —— 0 表示"重合率真的是 0"，和"那天没采到数据"是两回事。
    """
    xs = sorted(table[x_col].unique())
    chart = Line().add_xaxis([str(x) for x in xs])
    for group, g in table.groupby(group_col):
        series = g.set_index(x_col)[y_col].reindex(xs)  # ★ 对齐横轴，否则线会错位
        chart.add_yaxis(
            str(group),
            [None if pd.isna(v) else float(v) for v in series],
            is_smooth=smooth,
            is_connect_nones=True,
        )
    return chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        xaxis_opts=opts.AxisOpts(name=x_col),
        yaxis_opts=opts.AxisOpts(name=y_col),
    )


def topic_rank_bar(table, label_max=10) -> Bar:
    """同一话题在两个源上的名次对比。

    ⚠️ 名次是"越小越好"，所以 y 轴设 is_inverse=True，否则图会反着讲。
    """
    labels = [
        f"{str(r['标题A'])[:label_max]}…（{r['源A']}{r['名次A']} vs {r['源B']}{r['名次B']}）"
        for _, r in table.iterrows()
    ]
    return (
        Bar()
        .add_xaxis(labels)
        .add_yaxis("源A 名次", [int(v) for v in table["名次A"]])
        .add_yaxis("源B 名次", [int(v) for v in table["名次B"]])
        .set_global_opts(
            title_opts=opts.TitleOpts(title="同一话题的跨源名次对比"),
            yaxis_opts=opts.AxisOpts(name="名次", is_inverse=True),
            xaxis_opts=opts.AxisOpts(name="话题（源A名次 vs 源B名次）"),
        )
    )


def make_page(charts: list, title: str) -> Page:
    """把多张图合成一页（看板）。"""
    page = Page(layout=Page.SimplePageLayout, page_title=title)
    page.add(*charts)
    return page


def scatter(table, x_col, y_col, label_col, title, x_name="", y_name="") -> Scatter:
    """散点图：每个点是一份文档（x=词数，y=去重词汇量，点旁边标文件名）。"""
    points = [[row[x_col], row[y_col], str(row[label_col])] for _, row in table.iterrows()]
    chart = Scatter(init_opts=opts.InitOpts(width="900px", height="500px"))
    chart.add_xaxis([p[0] for p in points])  # x 轴只占位，真实坐标在 data 里
    chart.add_yaxis(
        y_name or y_col,
        points,  # [x, y, 文件名] 三元组
        symbol_size=14,
        label_opts=opts.LabelOpts(
            is_show=True, position="right",  # 直接把文件名标在点旁边，比 tooltip 直观
            formatter=JsCode("function(p){return p.data[2];}"),
        ),
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        xaxis_opts=opts.AxisOpts(name=x_name or x_col, type_="value"),
        yaxis_opts=opts.AxisOpts(name=y_name or y_col, type_="value"),
    )
    return chart


def pie_top(table, name_col, value_col, title, top: int = 8, other_label: str = "其他") -> Pie:
    """饼图：只画"占比"，而且**切片别超过 8~10 片**（再多就看不清谁是谁）。

    超出 top 的部分合并成一片「其他」，名字里写清合并了几项 ——
    这样占比加起来仍然是 100%，不会让人误以为少算了一截。
    """
    data = table.sort_values(value_col, ascending=False)
    head = data.head(top)
    names = [str(v) for v in head[name_col]]
    values = [float(v) for v in head[value_col]]
    rest = float(data[value_col].astype(float).iloc[top:].sum()) if len(data) > top else 0.0
    if rest > 0:
        names.append(f"{other_label}（{len(data) - top} 项）")
        values.append(rest)
    return (
        Pie(init_opts=opts.InitOpts(width="900px", height="500px"))
        .add(
            "",
            [list(z) for z in zip(names, values)],
            radius=["35%", "65%"],
            label_opts=opts.LabelOpts(formatter="{b}: {d}%"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )
