"""掘金 / 头条热榜分析。"""
import pandas as pd
from analysis.common import latest, pick, spearman, value_counts_table

DATASET_JJ = "juejin_hot"
DATASET_TT = "toutiao_hot"


def author_ranking(df) -> pd.DataFrame:
    """掘金：作者累计上榜次数（全部快照）—— 掘金最有价值的指标。"""
    sub = pick(df, DATASET_JJ)
    table = sub["author"].value_counts().rename_axis("author").reset_index(name="上榜次数")
    return table


def label_composition(df) -> pd.DataFrame:
    """头条：label 构成。"""
    return value_counts_table(latest(df, DATASET_TT)["label"], "label")


def heat_rank_check(df) -> pd.DataFrame:
    """头条：HotValue 与名次的相关（实测 -1.000 = 完全单调）。"""
    sub = latest(df, DATASET_TT)
    hot = pd.to_numeric(sub["score"].replace("", None), errors="coerce")
    return pd.DataFrame([{
        "榜单": DATASET_TT, "样本数": int(hot.notna().sum()),
        "名次与热度相关": round(spearman(sub["rank"], hot), 3),
    }])