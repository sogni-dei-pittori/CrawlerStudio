"""utils/schema.py：核心列的约定（列顺序、URL 规范化、缺列补齐）。"""
from __future__ import annotations

import pandas as pd
import pytest

from utils.schema import BOARD_COLUMNS, fill_core, order_columns, snapshot_of


class TestCleanUrl:
    def test_strips_fragment(self):
        from utils.schema import clean_url

        assert clean_url("https://a.example/p#section") == "https://a.example/p"

    def test_lowercases_host_but_not_path(self):
        from utils.schema import clean_url

        # 域名大小写无关，路径大小写有关（很多静态站点区分）
        assert clean_url("https://Example.COM/Path") == "https://example.com/Path"

    def test_keeps_query(self):
        """查询参数可能是内容本身（百度跳转链接），不能删 —— 这是设计约束。"""
        from utils.schema import clean_url

        url = "https://m.baidu.com/s?word=%E4%BD%A0%E5%A5%BD"
        assert clean_url(url) == url

    def test_keeps_query_while_dropping_fragment(self):
        from utils.schema import clean_url

        assert clean_url("https://a.example/s?q=1#top") == "https://a.example/s?q=1"

    @pytest.mark.parametrize("url", ["", "not-a-url", "https://a.example"])
    def test_never_raises(self, url):
        """采集层会拿任意脏字符串调它，不能抛异常。"""
        from utils.schema import clean_url

        assert isinstance(clean_url(url), str)


class TestFillCore:
    def test_fills_missing_core_columns(self):
        row = fill_core({"rank": 1, "title": "x"}, "baidu", "realtime", "2026-09-01_08-00")

        assert row["source"] == "baidu"
        assert row["board"] == "realtime"
        assert row["snapshot"] == "2026-09-01_08-00"
        # 空值统一写空字符串，不是 None —— 否则 CSV 里会出现 nan
        assert row["score"] == ""
        assert row["category"] == ""

    def test_does_not_overwrite_parser_values(self):
        """解析器自己给出的 source/board 优先，不能被子默认值覆盖。"""
        row = fill_core({"source": "bilibili", "board": "ranking"}, "IGNORED", "IGNORED", "ts")

        assert row["source"] == "bilibili"
        assert row["board"] == "ranking"

    def test_mutates_in_place(self):
        """文档承诺 setdefault 语义：返回的就是传入的那个 dict。"""
        original = {"rank": 1}
        assert fill_core(original, "s", "b", "ts") is original


class TestOrderColumns:
    def test_core_columns_come_first(self):
        df = pd.DataFrame({"tag": ["x"], "title": ["t"], "rank": [1]})

        result = order_columns(df, ["rank", "title"])

        assert list(result.columns) == ["rank", "title", "tag"]

    def test_keeps_extra_columns(self):
        """站点特有列必须保留 —— 各站字段不同，删了就没法做单源分析。"""
        df = pd.DataFrame({"rank": [1], "votes": [5], "author": ["a"]})

        result = order_columns(df, BOARD_COLUMNS)

        assert "votes" in result.columns
        assert "author" in result.columns

    def test_creates_missing_columns_as_empty(self):
        """缺的核心列要补成 NA，而不是直接报 KeyError。"""
        df = pd.DataFrame({"rank": [1], "title": ["t"]})

        result = order_columns(df, BOARD_COLUMNS)

        assert list(result.columns)[: len(BOARD_COLUMNS)] == BOARD_COLUMNS
        assert result["score"].isna().all()


def test_snapshot_of_reads_directory_name(tmp_path):
    snap = tmp_path / "2026-09-01_08-00"
    snap.mkdir()
    assert snapshot_of(snap) == "2026-09-01_08-00"
