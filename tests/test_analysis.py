"""analysis/common.py 与 analysis/cross.py：统计口径的守卫。

这些函数全都「不报错但会算错」—— 比如 latest() 忘了筛快照，
同一部电影会被数 18 次，表格照样能生成，只是数字全错。
所以这里断言的是具体数值，不是「返回了 DataFrame」。
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.common import latest, pick, rank_changes, spearman, value_counts_table


def board(rows):
    """把 (snapshot, rank, title) 造成长表，省得每个用例写六行字面量。

    注意 date / snapshot_ts 两列是 warehouse 读取层派生的，
    跨源分析全部按 date 对齐，所以夹具必须跟真实长表长得一样。
    """
    df = pd.DataFrame(rows, columns=["snapshot", "rank", "title"])
    df["snapshot_ts"] = pd.to_datetime(df["snapshot"], format="%Y-%m-%d_%H-%M")
    df["date"] = df["snapshot_ts"].dt.strftime("%Y-%m-%d")
    df["dataset"] = "demo"
    return df


@pytest.fixture
def two_snapshots():
    return board([
        ("2026-09-01_08-00", 1, "甲"),
        ("2026-09-01_08-00", 2, "乙"),
        ("2026-09-02_08-00", 1, "乙"),
        ("2026-09-02_08-00", 2, "丙"),
    ])


class TestLatest:
    def test_returns_only_newest_snapshot(self, two_snapshots):
        result = latest(two_snapshots, "demo")

        assert len(result) == 2
        assert set(result["title"]) == {"乙", "丙"}

    def test_filters_by_dataset(self, two_snapshots):
        assert latest(two_snapshots, "other").empty

    def test_pick_returns_all_snapshots(self, two_snapshots):
        assert len(pick(two_snapshots, "demo")) == 4


class TestValueCountsTable:
    def test_counts_and_percentages(self):
        table = value_counts_table(pd.Series(["a", "a", "b", "c"]), "值")

        assert list(table.columns) == ["值", "count", "pct"]
        assert table.iloc[0]["count"] == 2
        assert table.iloc[0]["pct"] == 50.0

    def test_order_is_respected(self):
        """需要固定顺序时（例如年代分布）不能按出现次数排。"""
        table = value_counts_table(pd.Series(["b", "a"]), "值", order=["a", "b"])

        assert list(table["值"]) == ["a", "b"]

    def test_percentages_sum_to_100(self):
        table = value_counts_table(pd.Series(["a", "b", "c"]))

        assert abs(table["pct"].sum() - 100.0) < 0.5   # 有 round(1)，允许舍入误差


class TestRankChanges:
    def test_computes_span(self, two_snapshots):
        table = rank_changes(two_snapshots, "demo")
        by_title = table.set_index("title")

        assert by_title.loc["乙", "名次跨度"] == 1     # 2 → 1
        assert by_title.loc["甲", "名次跨度"] == 0     # 只出现一次
        assert by_title.loc["甲", "出现次数"] == 1

    def test_sorted_by_span_desc(self, two_snapshots):
        table = rank_changes(two_snapshots, "demo")

        assert table["名次跨度"].is_monotonic_decreasing


class TestSpearman:
    def test_perfect_positive_correlation(self):
        assert spearman(pd.Series([1, 2, 3]), pd.Series([10, 20, 30])) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        assert spearman(pd.Series([1, 2, 3]), pd.Series([30, 20, 10])) == pytest.approx(-1.0)

    def test_monotonic_but_nonlinear_still_one(self):
        """Spearman 只看名次，所以指数变换不影响结果 —— 这正是它比 Pearson 适合榜单的原因。"""
        assert spearman(pd.Series([1, 2, 3, 4]), pd.Series([1, 10, 100, 1000])) == pytest.approx(1.0)


# ---------------------------------------------------------------- cross
class TestLcsLen:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            ("今天天气很好", "今天天气不错", 4),
            ("完全不同", "毫无关系", 0),
            ("abc", "abc", 3),
            ("", "abc", 0),
            ("前缀共同", "前缀", 2),
        ],
    )
    def test_lcs(self, a, b, expected):
        from analysis.cross import lcs_len

        assert lcs_len(a, b) == expected

    def test_handles_non_string_input(self):
        """标题列里混进 NaN 时不能崩 —— 长表合并后这种情况很常见。"""
        from analysis.cross import lcs_len

        assert isinstance(lcs_len(float("nan"), "abc"), int)


class TestChurnRate:
    def test_identical_consecutive_days_is_one(self):
        from analysis.cross import churn_rate

        df = board([
            ("2026-09-01_08-00", 1, "甲"), ("2026-09-02_08-00", 1, "甲"),
        ])
        df["dataset"] = "baidu_realtime"

        result = churn_rate(df, n=10)

        assert result.iloc[0]["重合率"] == 1.0

    def test_completely_replaced_is_zero(self):
        from analysis.cross import churn_rate

        df = board([
            ("2026-09-01_08-00", 1, "甲"), ("2026-09-02_08-00", 1, "乙"),
        ])
        df["dataset"] = "baidu_realtime"

        assert churn_rate(df, n=10).iloc[0]["重合率"] == 0.0

    def test_single_day_has_no_churn_row(self):
        """只有一天数据时算不出翻新率，应返回空表而不是 0。"""
        from analysis.cross import churn_rate

        df = board([("2026-09-01_08-00", 1, "甲")])
        df["dataset"] = "baidu_realtime"

        assert churn_rate(df, n=10).empty


class TestDailyCoverage:
    def test_one_row_per_dataset_per_day(self):
        from analysis.cross import daily_coverage

        df = board([
            ("2026-09-01_08-00", 1, "甲"), ("2026-09-01_08-00", 2, "乙"),
            ("2026-09-02_08-00", 1, "甲"),
        ])
        df["dataset"] = "baidu_realtime"

        result = daily_coverage(df, datasets=["baidu_realtime"])

        assert list(result["条数"]) == [2, 1]

    def test_uses_last_snapshot_of_the_day(self):
        """同一天有多个快照时只算最后一个，否则条数会翻倍。"""
        from analysis.cross import daily_coverage

        df = board([
            ("2026-09-01_08-00", 1, "甲"), ("2026-09-01_08-00", 2, "乙"),
            ("2026-09-01_20-00", 1, "甲"),
        ])
        df["dataset"] = "baidu_realtime"

        result = daily_coverage(df, datasets=["baidu_realtime"])

        assert list(result["条数"]) == [1]
