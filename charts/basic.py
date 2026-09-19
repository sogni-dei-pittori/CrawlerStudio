"""图表层通用件：只把统计表画出来，不含任何统计逻辑。"""
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Page
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
        series = g.set_index(x_col)[y_col].reindex(xs)          # ★ 对齐横轴，否则线会错位
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
