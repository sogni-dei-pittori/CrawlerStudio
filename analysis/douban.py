"""豆瓣单源分析：评分分布、年代分布。

口径常量放模块顶部 —— 论文里要交代"评分怎么分箱、年份怎么取"。
"""
import pandas as pd
from analysis.common import pick
from analysis.common import latest, value_counts_table

DATASET = "douban_movie_top250"

RATING_BINS = [0.0, 8.0, 8.5, 9.0, 9.5, 10.01]
RATING_LABELS = ["<8.0", "8.0-8.4", "8.5-8.9", "9.0-9.4", "9.5-10.0"]
YEAR_RE = r"((?:19|20)\d{2})"


def rating_distribution(df) -> pd.DataFrame:
    """评分分布（最新快照）。"""
    sub = latest(df, DATASET)
    bucket = pd.cut(sub["rating"], bins=RATING_BINS, labels=RATING_LABELS, right=False)
    table = bucket.value_counts().reindex(RATING_LABELS)
    table = table.rename_axis("bucket").reset_index(name="count")
    table["pct"] = (table["count"] / table["count"].sum() * 100).round(1)
    return table


def decade_distribution(df) -> pd.DataFrame:
    """年代分布（最新快照）。年份从 info 列抽取。"""
    sub = latest(df, DATASET)
    year = sub["info"].str.extract(YEAR_RE)[0].astype("float")
    decade = (year // 10 * 10).astype("Int64")
    return value_counts_table(decade, "decade").sort_values("decade")


def votes_growth(df) -> pd.DataFrame:
    """用全部快照算评价人数增长（首快照 vs 末快照）。

    豆瓣的名次几乎不动，votes 才是它真正在变化的字段。
    """
    sub = pick(df, DATASET)
    first = sub[sub["snapshot_ts"] == sub["snapshot_ts"].min()]
    last = sub[sub["snapshot_ts"] == sub["snapshot_ts"].max()]
    table = first[["title", "votes", "rank"]].merge(
        last[["title", "votes", "rank"]], on="title", suffixes=("_首", "_末"))
    table["投票增长"] = table["votes_末"] - table["votes_首"]
    table["增长率%"] = (table["投票增长"] / table["votes_首"] * 100).round(2)
    for col in ("votes_首", "votes_末", "投票增长"):
        table[col] = table[col].astype("Int64")
    return table.sort_values("投票增长", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    from warehouse import load_boards

    df = load_boards()

    print("--- 评分分布 ---")
    t = rating_distribution(df)
    print(t.to_string(index=False))
    print(f"合计 {t['count'].sum()} 行 / pct {t['pct'].sum():.1f}")

    print("\n--- 年代分布 ---")
    t2 = decade_distribution(df)
    print(t2.to_string(index=False))
    print(f"合计 {t2['count'].sum()} 行")
