"""跨源分析：只比"名次"（rank）与标题，绝不跨源直接比 score。

口径三条：① 按 date 对齐，每源每天只取最后一个快照；② 只用 rank；③ 百度只参与名次类分析。
"""
from itertools import combinations

import pandas as pd

from analysis.common import pick

DATASETS = ["baidu_realtime", "bilibili_ranking", "juejin_hot", "toutiao_hot", "douban_movie_top250"]


def latest_per_day(df, dataset):
    """某数据集"每天最后一个快照"的全部行（不是压成一行！）。"""
    sub = pick(df, dataset).copy()
    last_ts = sub.groupby("date")["snapshot_ts"].transform("max")
    return sub[sub["snapshot_ts"] == last_ts]


def daily_coverage(df, datasets=None) -> pd.DataFrame:
    """每天每源多少条（数据完整性基线）——跨源分析的第一步。"""
    rows = []
    for name in (datasets or DATASETS):
        sub = latest_per_day(df, name)
        for date, g in sub.groupby("date"):
            rows.append({"date": date, "dataset": name, "条数": len(g)})
    return pd.DataFrame(rows).sort_values(["date", "dataset"]).reset_index(drop=True)


def top_by_source(df, date=None, n=5) -> pd.DataFrame:
    """某天各源 Top N 并排（只用名次，天然可比）。"""
    rows = []
    for name in DATASETS:
        sub = latest_per_day(df, name)
        if date is not None:
            sub = sub[sub["date"] == date]
        for _, r in sub.sort_values(["date", "rank"]).groupby("date").head(n).iterrows():
            rows.append({"date": r["date"], "dataset": name, "rank": r["rank"], "title": r["title"]})
    return pd.DataFrame(rows)


def lcs_len(a, b) -> int:
    """最长公共子串长度（判断两条标题是不是同一话题，不需要分词）。"""
    a, b = str(a), str(b)
    best, prev = 0, [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def cross_topic(df, date=None, n=10, min_lcs=5) -> pd.DataFrame:
    """同日跨源同一话题：两两比 Top N 标题，最长公共子串 >= min_lcs 就算同话题。"""
    dates = [date] if date else sorted(df["date"].unique())
    rows = []
    for d in dates:
        tops = {}
        for name in DATASETS[:4]:                       # 豆瓣是长期榜，不参与话题重叠
            sub = latest_per_day(df, name)
            sub = sub[sub["date"] == d]
            if not sub.empty:
                tops[name] = sub.sort_values("rank").head(n)[["rank", "title"]].values.tolist()
        for (n1, t1), (n2, t2) in combinations(tops.items(), 2):
            for r1, s1 in t1:
                for r2, s2 in t2:
                    L = lcs_len(s1, s2)
                    if L >= min_lcs:
                        rows.append({"date": d, "源A": n1, "名次A": r1, "标题A": s1,
                                     "源B": n2, "名次B": r2, "标题B": s2, "公共子串长度": L})
    return pd.DataFrame(rows)


def churn_rate(df, n=10) -> pd.DataFrame:
    """各源 Top N 的跨天重合率（Jaccard）：越低说明榜单翻新越快。"""
    rows = []
    for name in DATASETS:
        sub = latest_per_day(df, name).sort_values("date")
        prev_date, prev_set = None, None
        for d, g in sub.groupby("date"):
            cur = set(g.sort_values("rank").head(n)["title"])
            if prev_set is not None:
                rows.append({"源": name, "日期": d, "对比日期": prev_date,
                             "重合率": round(len(cur & prev_set) / len(cur | prev_set), 2)})
            prev_date, prev_set = d, cur
    return pd.DataFrame(rows)