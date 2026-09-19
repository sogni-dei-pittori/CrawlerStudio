"""Streamlit 交互看板：吃 warehouse + analysis 的结果，做可筛选的展示。

跑法（在项目根目录，不要用 python app.py）：
    streamlit run app.py
    或 .\.venv\Scripts\python.exe -m streamlit run app.py
"""
import pandas as pd
import streamlit as st

from analysis import cross
from analysis.report import build_tables          # 复用报告的表定义，避免两处维护
from warehouse import audit, load_boards

st.set_page_config(page_title="爬虫项目看板", layout="wide")
st.title("多源热榜分析看板")


@st.cache_data
def get_data():
    """读全量长表（Streamlit 每次交互都会重跑整个脚本，所以必须缓存）。"""
    return load_boards()


@st.cache_data
def get_tables():
    """16 张统计表也缓存（统计很快，但没必要每次交互都重算）。"""
    return build_tables(get_data())


df = get_data()
tables = get_tables()

# ---------------- 侧栏：两个真旋钮 + 数据新鲜度 ----------------
with st.sidebar:
    st.header("筛选")
    top_n = st.slider("Top N", min_value=5, max_value=50, value=15, step=5)
    date_range = st.date_input(
        "日期范围",
        value=(pd.to_datetime(df["date"].min()), pd.to_datetime(df["date"].max())),
    )
    st.caption(f"数据最新到 {df['date'].max()}｜{df['snapshot_ts'].nunique()} 个快照")
    if st.button("重新读取数据"):
        st.cache_data.clear()
        st.rerun()

start, end = str(date_range[0]), str(date_range[1])      # date 对象 → "2026-09-16"（date 列是字符串）
view = df[(df["date"] >= start) & (df["date"] <= end)]

# ---------------- 指标卡 ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("总行数", f"{len(df):,}")
c2.metric("数据集", df["dataset"].nunique())
c3.metric("快照数", df["snapshot_ts"].nunique())
c4.metric("当前视图", f"{len(view):,} 行")
st.caption(f"当前视图：{start} ~ {end}")

# 表名 → (横轴列, 纵轴列)：单源指标统一用柱状图，轴列写死比"猜"清楚
CHART_SPEC = {
    "豆瓣_评分分布": ("bucket", "count"),
    "豆瓣_年代分布": ("decade", "count"),
    "百度_名次变化": ("title", "名次跨度"),
    "豆瓣_投票增长": ("title", "投票增长"),
    "B站_播放量分布": ("bucket", "count"),
    "B站_播放量增长": ("title", "播放增长"),
    "掘金_作者上榜": ("author", "上榜次数"),
}

tab_single, tab_cross, tab_check = st.tabs(["单源指标", "跨源对比", "数据体检"])

with tab_single:
    picked = st.selectbox("选择统计表", list(CHART_SPEC))
    x_col, y_col = CHART_SPEC[picked]
    table = tables[picked]
    st.bar_chart(table.head(top_n), x=x_col, y=y_col)
    st.dataframe(table, use_container_width=True)
    st.download_button("下载这张表 CSV",
                       table.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{picked}.csv")

with tab_cross:
    st.subheader(f"各源 Top{top_n} 跨天重合率（越低 = 翻新越快）")
    churn = cross.churn_rate(view, n=top_n)
    if churn.empty:
        st.info("翻新速度至少需要两天的数据 —— 把日期范围拉宽一点。")
    else:
        st.line_chart(churn.pivot(index="日期", columns="源", values="重合率"))
        st.caption("百度/头条 ≈ 0（实时替换型）｜B站逐日上升（内容型）｜豆瓣 = 1（长期榜）")

    st.subheader("同一话题的跨源名次对比")
    topic = cross.cross_topic(view, n=10)
    if topic.empty:
        st.info("当前日期范围内没有跨源同话题。")
    else:
        shaped = topic.assign(话题=topic["标题A"].str.slice(0, 10) + "…").set_index("话题")
        st.bar_chart(shaped[["名次A", "名次B"]])
        st.caption("名次越小越好；两根柱子差距越大 = 两个榜的关注点越不同")
        st.dataframe(topic, use_container_width=True)

    st.subheader(f"同日各源 Top{min(top_n, 10)}")
    st.dataframe(cross.top_by_source(view, n=min(top_n, 10)), use_container_width=True)

with tab_check:
    st.subheader("快照体检（磁盘 vs 登记表）")
    for key, items in audit().items():
        st.write(f"**{key}**：{len(items)} 个")
        if items:
            st.dataframe(pd.DataFrame(items[:10]), use_container_width=True)
    st.subheader("每天每源覆盖情况")
    st.dataframe(cross.daily_coverage(df), use_container_width=True)