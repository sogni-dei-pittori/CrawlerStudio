"""B站全站日榜分析（数据源 tophub）。"""
import pandas as pd
from analysis.common import latest_via, pick_via, spearman, value_counts_table

DATASET = "bilibili_ranking"
VIA = "tophub.today"                       # ★ 必须限定来源：api 与 tophub 混在一起算会错

SCORE_BINS = [0, 500_000, 1_000_000, 2_000_000, 4_000_000, 100_000_000]
SCORE_LABELS = ["<50万", "50-100万", "100-200万", "200-400万", ">400万"]


def score_distribution(df) -> pd.DataFrame:
    """播放量分布（最新 tophub 快照）。"""
    sub = latest_via(df, DATASET, VIA)
    score = pd.to_numeric(sub["score"], errors="coerce")
    bucket = pd.cut(score, bins=SCORE_BINS, labels=SCORE_LABELS, right=False)
    return value_counts_table(bucket, "bucket", order=SCORE_LABELS)


def rank_score_table(df) -> pd.DataFrame:
    """名次与播放量的相关（一行表，实测 -0.408）。"""
    sub = latest_via(df, DATASET, VIA)
    score = pd.to_numeric(sub["score"], errors="coerce")
    return pd.DataFrame([{
        "榜单": DATASET, "样本数": int(score.notna().sum()),
        "名次与播放量相关": round(spearman(sub["rank"], score), 3),
    }])


def views_growth(df) -> pd.DataFrame:
    """tophub 内部：首末快照按 aid 对齐算播放量增长。"""
    sub = pick_via(df, DATASET, VIA)
    first = sub[sub["snapshot_ts"] == sub["snapshot_ts"].min()]
    last = sub[sub["snapshot_ts"] == sub["snapshot_ts"].max()]
    table = first[["aid", "title", "score"]].merge(
        last[["aid", "score"]], on="aid", suffixes=("_首", "_末"))
    table["播放量_首"] = pd.to_numeric(table["score_首"], errors="coerce")
    table["播放量_末"] = pd.to_numeric(table["score_末"], errors="coerce")
    table["播放增长"] = (table["播放量_末"] - table["播放量_首"]).astype("Int64")
    table = table.drop(columns=["score_首", "score_末"])
    return table.sort_values("播放增长", ascending=False).reset_index(drop=True)