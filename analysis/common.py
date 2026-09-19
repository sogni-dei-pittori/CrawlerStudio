"""分析层通用件：所有单源分析都从这里取数据。

只做三件事：筛数据集、取最新快照、做频次表。
不联网、不读文件、不画图。
"""
import pandas as pd


def pick(df, dataset):
    """筛出一个数据集的数据（dataset 列是 warehouse 读取层补的）。"""
    return df[df["dataset"] == dataset]


def latest(df, dataset):
    """只取这个数据集最新的那一份快照。

    算"榜单现状"必须用它 —— 长表里同一个数据集有很多快照，
    不筛的话同一部电影会被数 18 次（不报错，但结果全错）。
    """
    sub = pick(df, dataset)
    return sub[sub["snapshot_ts"] == sub["snapshot_ts"].max()]


def value_counts_table(series, name="值", order=None) -> pd.DataFrame:
    """通用频次表：count + pct（按出现次数降序；给了 order 就按 order 排）。"""
    counts = series.value_counts(dropna=False)
    if order is not None:
        counts = counts.reindex(order)          # ← 需要固定顺序时传进来
    table = counts.rename_axis(name).reset_index(name="count")
    table["pct"] = (table["count"] / table["count"].sum() * 100).round(1)
    return table


def rank_changes(df, dataset) -> pd.DataFrame:
    """用全部快照算每个条目的名次变化（只对"会变的榜单"有意义）。

    注意：豆瓣 Top250 在 20 个快照内名次零变化，跑出来是一张全 0 表；
    它适合百度 / 头条 / 掘金 / B站 这类日更或实时榜。
    """
    sub = pick(df, dataset)
    table = sub.groupby("title")["rank"].agg(
        出现次数="count", 最小名次="min", 最大名次="max",
    ).reset_index()
    table["名次跨度"] = table["最大名次"] - table["最小名次"]
    return table.sort_values(["名次跨度", "出现次数"], ascending=[False, False]).reset_index(drop=True)

def spearman(a, b) -> float:
    """Spearman 相关 = 对两列的"名次"算 Pearson —— 这样不需要装 scipy。"""
    return a.rank().corr(b.rank())


def pick_via(df, dataset, via):
    """筛出某个数据集里"经由某一来源"的行（B站有 api 与 tophub 两条来源）。"""
    sub = pick(df, dataset)
    return sub[sub["via"] == via]


def latest_via(df, dataset, via):
    """某个数据集、某一来源的最新快照。"""
    sub = pick_via(df, dataset, via)
    return sub[sub["snapshot_ts"] == sub["snapshot_ts"].max()]

if __name__ == "__main__":
    from warehouse import load_boards

    df = load_boards()
    print("全表：", df.shape)

    if df.empty:                # 空仓库时下面的列（tag 等）根本不存在，给句人话就退出
        print("\n仓库里还没有数据：data/ 下没读到任何快照。")
        print("先跑一次采集（python run_daily.py，或界面上的「开始采集」），再回来跑这个自检。")
        raise SystemExit(0)

    print("\n--- 各数据集：全部 / 最新快照 ---")
    for name in ["douban_movie_top250", "douban_book_top250", "douban_doulist",
                 "baidu_realtime", "juejin_hot", "toutiao_hot", "bilibili_ranking"]:
        print(f"{name:22s} 全部 {len(pick(df, name)):5d} 行 | 最新 {len(latest(df, name)):4d} 行")

    print("\n--- 频次表自检：百度 tag ---")
    print(value_counts_table(latest(df, "baidu_realtime")["tag"], "tag").to_string(index=False))