"""parsers/：HTML → rows。解析器是纯函数，最适合用固定 HTML 做回归测试。

这些断言的价值在于「结构一变就红」。站点改版时，与其等到采集跑完发现
CSV 只有 0 行，不如让测试当场告诉你哪个选择器失效了。
"""
from __future__ import annotations

import pytest

from parsers.douban import _digits_to_int, parse_doulist, parse_top250_book, parse_top250_movie
from parsers.tophub import extract_video_id, parse_board, parse_count

# ---------------------------------------------------------------- 豆瓣 Top250 电影
MOVIE_HTML = """
<html><body>
<div class="item">
  <div class="pic"><em class="">1</em></div>
  <div class="info">
    <div class="hd"><a href="https://movie.douban.com/subject/1/">
      <span class="title">肖申克的救赎</span></a></div>
    <div class="bd">
      <p class="">导演: 弗兰克·德拉邦特&nbsp;&nbsp;主演: 蒂姆·罗宾斯<br>
         1994&nbsp;/&nbsp;美国&nbsp;/&nbsp;犯罪 剧情</p>
      <div class="star"><span class="rating5-t"></span>
        <span class="rating_num" property="v:average">9.7</span>
        <span>3061234人评价</span></div>
      <p class="quote"><span class="inq">希望让人自由。</span></p>
    </div>
  </div>
</div>
<div class="item">
  <div class="pic"><em class="">2</em></div>
  <div class="info">
    <div class="hd"><a href="https://movie.douban.com/subject/2/">
      <span class="title">霸王别姬</span></a></div>
    <div class="bd">
      <p class="">导演: 陈凯歌&nbsp;&nbsp;主演: 张国荣<br>
         1993&nbsp;/&nbsp;中国&nbsp;/&nbsp;剧情 爱情</p>
      <div class="star"><span class="rating_num" property="v:average">9.6</span>
        <span>2210000人评价</span></div>
    </div>
  </div>
</div>
</body></html>
"""


class TestParseTop250Movie:
    @pytest.fixture
    def rows(self):
        return parse_top250_movie(MOVIE_HTML)

    def test_row_count(self, rows):
        assert len(rows) == 2

    def test_rank_and_title(self, rows):
        assert rows[0]["rank"] == 1
        assert rows[0]["title"] == "肖申克的救赎"

    def test_rating_kept_as_string(self, rows):
        """评分保留原始文本（9.7），转成 float 会丢精度且在 CSV 里出现 .0。"""
        assert rows[0]["rating"] == "9.7"

    def test_votes_parsed_to_int(self, rows):
        assert rows[0]["votes"] == 3061234

    def test_info_nbsp_replaced(self, rows):
        """\\xa0 换成普通空格，否则写进 CSV 后 pandas 读出来是怪字符。"""
        assert "\xa0" not in rows[0]["info"]
        assert "导演: 弗兰克·德拉邦特" in rows[0]["info"]

    def test_missing_quote_defaults_to_empty(self, rows):
        """第 2 条没有短评 —— 不能是 None，按约定要空字符串。"""
        assert rows[1]["quote"] == ""

    def test_url_absolute(self, rows):
        assert rows[0]["url"].startswith("https://movie.douban.com/subject/")

    def test_empty_html_yields_no_rows(self):
        assert parse_top250_movie("<html></html>") == []

    def test_malformed_row_does_not_kill_the_whole_page(self):
        """回归：一条缺字段的条目曾会让整页 250 条全部解析失败。

        豆瓣会插广告位、条目会失效，此时 select_one() 返回 None。
        原实现直接 .get_text()，抛 AttributeError 把好的条目一起带走。
        现在缺的字段记空字符串，条目本身保留。
        """
        html = """
        <div class="item"><div class="pic"><em>1</em></div>
          <div class="info"><div class="hd"><a href="/x"><span class="title">正常条目</span></a></div>
          <div class="bd"><p>导演: 某人</p><div><span class="rating_num">9.0</span></div></div></div></div>
        <div class="item"><div class="pic"><em>2</em></div>
          <div class="info"><div class="hd"><a href="/y"><span class="title">缺评分条目</span></a></div>
          <div class="bd"><p>导演: 某人</p></div></div></div>
        """
        rows = parse_top250_movie(html)

        assert len(rows) == 2
        assert rows[1]["rating"] == ""      # 缺失 → 空字符串，不是崩
        assert rows[0]["rating"] == "9.0"

    def test_item_without_title_is_skipped(self):
        """连标题都没有的节点是广告位，不该进数据。"""
        html = """
        <div class="item"><div class="pic"><em>1</em></div>
          <div class="info"><div class="bd"><p>广告</p></div></div></div>
        """
        assert parse_top250_movie(html) == []


# ---------------------------------------------------------------- 豆瓣 Top250 图书
BOOK_HTML = """
<html><body><table>
<tr class="item">
  <td><div class="pl2"><a href="https://book.douban.com/subject/1/" title="红楼梦">红楼梦</a></div>
      <p class="pl">曹雪芹&nbsp;/&nbsp;人民文学出版社&nbsp;/&nbsp;1996</p>
      <div class="star clearfix"><span class="rating_nums">9.6</span>
        <span class="pl">(400000人评价)</span></div>
      <p class="quote"><span class="inq">满纸荒唐言</span></p></td>
</tr>
</table></body></html>
"""


class TestParseTop250Book:
    def test_row(self):
        rows = parse_top250_book(BOOK_HTML)

        assert len(rows) == 1
        assert rows[0]["title"] == "红楼梦"
        assert rows[0]["rating"] == "9.6"
        assert rows[0]["votes"] == 400000

    def test_rank_offset_continues_numbering(self):
        """图书榜分页抓，第二页的名次要接着第一页往下数。"""
        rows = parse_top250_book(BOOK_HTML, rank_offset=25)

        assert rows[0]["rank"] == 26

    def test_no_quote_node(self):
        html = BOOK_HTML.replace('<p class="quote"><span class="inq">满纸荒唐言</span></p>', "")
        rows = parse_top250_book(html)

        assert rows[0]["quote"] == ""


# ---------------------------------------------------------------- 豆瓣豆列
DOULIST_HTML = """
<html><body>
<div class="doulist-item">
  <div class="title"><a href="https://www.douban.com/x/1">条目甲</a></div>
  <div class="rating"><span class="rating_nums">8.5</span><span>(1234人评价)</span></div>
  <div class="abstract">简介甲</div>
  <span class="pos">1</span>
</div>
<div class="doulist-item">
  <div class="abstract">结构不完整的失效条目</div>
  <span class="pos">2</span>
</div>
</body></html>
"""


class TestParseDoulist:
    def test_skips_broken_items(self):
        """失效条目的 .title a 不存在 —— 要跳过而不是崩。"""
        rows = parse_doulist(DOULIST_HTML)

        assert len(rows) == 1
        assert rows[0]["title"] == "条目甲"

    def test_rating_optional(self):
        html = DOULIST_HTML.replace('<span class="rating_nums">8.5</span>', "")
        rows = parse_doulist(html)

        assert rows[0]["rating"] == ""


# ---------------------------------------------------------------- 数字提取
@pytest.mark.parametrize(
    ("text", "expected"),
    [("1234人评价", 1234), ("( 5678 人评价)", 5678), ("路人甲", 0), ("", 0)],
)
def test_digits_to_int(text, expected):
    assert _digits_to_int(text) == expected


# ---------------------------------------------------------------- tophub 热度换算
class TestParseCount:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("830.4万", 8_304_000),
            ("1.2亿", 120_000_000),
            ("500", 500),
            ("3,000", 3000),
            ("", ""),
            ("热", ""),
        ],
    )
    def test_units(self, text, expected):
        assert parse_count(text) == expected

    def test_wan_precision_is_documented(self):
        """'万' 只精确到 1000，这是已知精度损失 —— 用例把语义固定下来。"""
        assert parse_count("0.1万") == 1000


class TestExtractVideoId:
    def test_av_url(self):
        assert extract_video_id("https://www.bilibili.com/video/av170001") == (170001, "")

    def test_bv_url(self):
        assert extract_video_id("https://www.bilibili.com/video/BV1xx411c7mD") == ("", "BV1xx411c7mD")

    @pytest.mark.parametrize("url", ["", None, "https://example.com/x"])
    def test_unrecognized(self, url):
        assert extract_video_id(url) == ("", "")


TOPHUB_HTML = """
<html><body><table>
<tr><th>排名</th><th>封面</th><th>标题</th></tr>
<tr><td align="center">1.</td><td align="center" class="al"></td>
    <td class="al"><div><a href="https://www.bilibili.com/video/av117/">视频甲</a></div>
    <div class="item-desc">830.4万</div></td>
    <td align="right"><a href="/x"><i class="m-n"></i></a></td></tr>
<tr><td align="center">2.</td><td align="center" class="al"></td>
    <td class="al"><div><a href="https://www.bilibili.com/video/BVabc123">视频乙</a></div></td>
    <td align="right"><a href="/x"><i class="m-n"></i></a></td></tr>
<tr><td align="center">—</td><td></td><td class="al"><div><a href="/ad">广告位</a></div></td></tr>
<tr><td align="center">3.</td><td></td><td class="al"><div><a href="/not-a-video">其它链接</a></div></td></tr>
</table></body></html>
"""


class TestParseBoard:
    def test_only_ranked_video_rows_survive(self):
        rows = parse_board(TOPHUB_HTML)

        assert [r["rank"] for r in rows] == [1, 2]

    def test_heat_and_ids(self):
        rows = parse_board(TOPHUB_HTML)

        assert rows[0]["score"] == 8_304_000
        assert rows[0]["heat_text"] == "830.4万"
        assert rows[0]["aid"] == 117
        assert rows[1]["bvid"] == "BVabc123"

    def test_missing_heat_is_empty_score(self):
        """没有 item-desc 时 score 记空字符串（不是 0 —— 0 会被当成真实热度）。"""
        rows = parse_board(TOPHUB_HTML)

        assert rows[1]["score"] == ""

    def test_empty_html(self):
        assert parse_board("<html></html>") == []
