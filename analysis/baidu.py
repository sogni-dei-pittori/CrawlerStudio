"""百度单源分析：标签构成、分类构成。"""
from analysis.common import latest, value_counts_table
import pandas as pd

DATASET = "baidu_realtime"


def tag_composition(df) -> pd.DataFrame:
    """标签构成（空 / 热 / 新），最新快照。"""
    return value_counts_table(latest(df, DATASET)["tag"], "tag")


def category_composition(df) -> pd.DataFrame:
    """分类构成，最新快照。"""
    return value_counts_table(latest(df, DATASET)["category"], "category")