"""analysis/text.py：语料六项指标的算法。

这些指标是文本分析页面上那六个数字卡的来源，也是最容易被质疑
「你怎么算的」的部分 —— 因此每个指标都单独断言，并把口径写进用例名。
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.text import (
    MIN_SENT_CHARS,
    STOPWORDS,
    missing_detail,
    normalize,
    sentence_length_distribution,
    split_sentences,
    tokenize,
    total_counts,
    word_freq,
)


def corpus(*texts, missing=False):
    """造一份最小语料表，列和数据抽取层输出一致。"""
    return pd.DataFrame({
        "source": [f"doc{i}.txt" for i in range(len(texts))],
        "text": list(texts),
        "missing": [missing] * len(texts),
        "note": [""] * len(texts),
        "page": ["1"] * len(texts),
    })


class TestTokenize:
    def test_drops_punctuation_and_space(self):
        tokens = tokenize("你好，世界！")

        assert "，" not in tokens
        assert "！" not in tokens
        assert "你好" in tokens

    def test_empty_input(self):
        assert tokenize("") == []
        assert tokenize(None) == []

    def test_keeps_original_case(self):
        """分词不做小写化 —— 小写化只在算去重词汇量时做，否则词频图会显示全小写。"""
        assert "Python" in tokenize("Python")


class TestNormalize:
    def test_lowercases_latin(self):
        assert normalize("Python") == normalize("python")

    def test_chinese_unchanged(self):
        assert normalize("中文") == "中文"


class TestSplitSentences:
    def test_splits_on_chinese_terminators(self):
        assert split_sentences(["第一句。第二句！第三句？"]) == ["第一句", "第二句", "第三句"]

    def test_splits_on_newline(self):
        assert split_sentences(["上半段内容\n下半段内容"]) == ["上半段内容", "下半段内容"]

    def test_drops_pieces_shorter_than_threshold(self):
        """「好。嗯。」这类噪声不算句子 —— 否则平均句长会被拉得很低。"""
        result = split_sentences(["好。嗯。这是一句正常的话。"])

        assert all(len(s) >= MIN_SENT_CHARS for s in result)
        assert "这是一句正常的话" in result

    def test_multiple_texts_concatenate(self):
        assert len(split_sentences(["第一段内容。", "第二段内容。"])) == 2


class TestTotalCounts:
    def test_counts_are_consistent(self):
        stats = total_counts(corpus("今天天气很好。明天也不错。"))

        assert stats["总文本条数"] == 1
        assert stats["有效文本条数"] == 1
        assert stats["缺失文本数量"] == 0
        assert stats["总字数"] > 0
        assert stats["总词数"] >= stats["去重词汇量"]   # 词数不可能少于去重词汇量

    def test_missing_texts_excluded_from_char_count(self):
        """缺失行的 text 是空字符串，不能把它的 len 算进总字数，
        但「总文本条数」要包含它 —— 否则缺失数就统计不出来了。"""
        df = corpus("正常文本。", "")
        df.loc[1, "missing"] = True          # 只有第二行缺失

        stats = total_counts(df)

        assert stats["总文本条数"] == 2
        assert stats["有效文本条数"] == 1
        assert stats["缺失文本数量"] == 1
        # 总字数 = 去空白后的字符数（含标点）。这里 4 个汉字 + 1 个句号。
        assert stats["总字数"] == 5

    def test_empty_corpus_does_not_divide_by_zero(self):
        stats = total_counts(pd.DataFrame({
            "source": [], "text": [], "missing": [], "note": [], "page": [],
        }))

        assert stats["平均句子长度_字"] == 0.0
        assert stats["类型形符比TTR"] == 0.0

    def test_strict_char_count_excludes_punctuation(self):
        """「只算汉字字母数字」这一列用于和总字数对照（总字数含标点）。"""
        stats = total_counts(corpus("abc，中。"))

        assert stats["总字数"] == 6                              # a b c ， 中 。
        assert stats["总字数_只算汉字字母数字"] == 4              # a b c 中

    def test_stopwords_reduce_vocabulary(self):
        stats = total_counts(corpus("这是一个测试。"))

        assert stats["去重词汇量_去停用词"] <= stats["去重词汇量"]

    def test_ttr_is_bounded(self):
        stats = total_counts(corpus("甲。乙。丙。丁。"))

        assert 0 <= stats["类型形符比TTR"] <= 1


class TestMissingDetail:
    def test_empty_when_nothing_missing(self):
        result = missing_detail(corpus("正常。"))

        assert result.empty
        assert list(result.columns) == ["类型", "文件名", "位置", "原因"]

    @pytest.mark.parametrize(
        ("note", "expected"),
        [
            ("不支持的扩展名 .xyz", "不支持的类型"),
            ("请另存为 docx", "不支持的类型"),
            ("扫描件没有文本层", "抽出来是空的"),
            ("这个文件里没有再找到文本", "抽出来是空的"),
            ("打开失败：权限不足", "抽取失败"),
        ],
    )
    def test_reason_categories(self, note, expected):
        df = corpus("")
        df.loc[0, "missing"] = True
        df.loc[0, "note"] = note

        assert missing_detail(df).iloc[0]["类型"] == expected


class TestWordFreq:
    def test_returns_top_n_with_percentages(self):
        table = word_freq(corpus("苹果 苹果 苹果 香蕉 香蕉 橘子"), top=2)

        assert len(table) == 2
        assert table.iloc[0]["词"] == "苹果"
        assert table.iloc[0]["count"] == 3
        assert list(table.columns) == ["词", "count", "pct"]

    def test_percentages_sum_to_about_100(self):
        """pct 是「占全部词的比例」，全部行加起来应接近 100。"""
        table = word_freq(corpus("甲乙 丙丁 戊己"), top=20, drop_stopwords=False)

        assert abs(table["pct"].sum() - 100) < 1

    def test_stopwords_removed_by_default(self):
        table = word_freq(corpus("的 的 的 苹果"), drop_stopwords=True)

        assert "的" not in set(table["词"])

    def test_empty_corpus_returns_typed_empty_frame(self):
        result = word_freq(corpus(""))

        assert result.empty
        assert list(result.columns) == ["词", "count", "pct"]

    def test_lowercases_before_counting(self):
        """Python 和 python 要算同一个词，否则去重词汇量会被高估。"""
        table = word_freq(corpus("Python python PYTHON"), drop_stopwords=False)

        assert len(table) == 1
        assert table.iloc[0]["count"] == 3


class TestSentenceLengthDistribution:
    def test_buckets_are_bucketed_not_exact(self):
        result = sentence_length_distribution(corpus("短句。这是一句稍微长那么一点点的句子。" * 3))

        assert len(result) >= 2
        assert "bucket" in result.columns or "句长区间" in result.columns

    def test_empty_corpus(self):
        result = sentence_length_distribution(corpus(""))

        assert isinstance(result, pd.DataFrame)


def test_stopword_table_has_no_duplicates():
    """停用词表曾经把「是」「的」各写了两遍 —— set 会静默去重，
    但说明是复制粘贴出来的，所以用用例固定住「无重复」这个事实。"""
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / "analysis" / "text.py"
    body = source.read_text(encoding="utf-8")

    assert len(STOPWORDS) > 30
    assert re.search(r"STOPWORDS = \{", body)
