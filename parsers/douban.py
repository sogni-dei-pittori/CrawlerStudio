import re

from bs4 import BeautifulSoup, Tag


def _digits_to_int(text: str) -> int:
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0


def _text(node: Tag | None, separator: str = "") -> str:
    """取节点文本；节点不存在时返回空字符串。

    ★ 这个函数是「一条坏数据不要毁掉整页」的关键。豆瓣会插入广告位、
      条目会失效，此时 select_one() 返回 None，直接 .get_text() 会抛
      AttributeError，把整页 250 条全部带走 —— 而其中 249 条是好的。
      缺失的字段按 schema 约定写成空字符串。
    """
    if node is None:
        return ""
    return node.get_text(separator=separator, strip=True).replace("\xa0", " ")


def _attr(node: Tag | None, name: str) -> str:
    """取属性（如 href）；节点不存在或属性缺失时返回空字符串。"""
    if node is None:
        return ""
    value = node.get(name, "")
    return value if isinstance(value, str) else ""


def parse_top250_movie(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for item in soup.select("div.item"):
        rank_text = _text(item.select_one("em"))
        title = _text(item.select_one("span.title"))
        if not rank_text or not title:
            continue                    # 连名次和标题都没有 → 不是有效条目，跳过
        spans = item.select(".bd div span")
        votes = _digits_to_int(_text(spans[-1]) if spans else "")
        rows.append({
            "rank": _digits_to_int(rank_text),
            "title": title,
            "info": _text(item.select_one(".bd p"), separator=" "),
            "rating": _text(item.select_one(".rating_num")),
            "votes": votes,
            "quote": _text(item.select_one("p.quote span")),
            "url": _attr(item.select_one(".hd a"), "href"),
        })

    return rows


def parse_top250_book(html, rank_offset=0):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for i, item in enumerate(soup.select("tr.item")):
        a = item.select_one(".pl2 a")
        title = _attr(a, "title") or _text(a)
        if not title:
            continue                      # 没有标题 → 不是有效条目
        rows.append({
            "rank": rank_offset + i + 1,  # 名次按顺序生成，不依赖页面上的数字
            "title": title,
            "url": _attr(a, "href"),
            "info": _text(item.select_one("p.pl")),
            "rating": _text(item.select_one(".rating_nums")),
            "votes": _digits_to_int(_text(item.select_one(".star .pl"))),
            "quote": _text(item.select_one(".inq")),
        })
    return rows


def parse_doulist(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for item in soup.select("div.doulist-item"):
        a = item.select_one(".title a")
        title = _text(a)
        if not title:                    # 结构不完整（失效条目）→ 跳过
            continue

        spans = item.select(".rating span")
        rows.append({
            "rank": _digits_to_int(_text(item.select_one(".pos"))),
            "title": title,
            "url": _attr(a, "href"),
            "info": _text(item.select_one(".abstract"), separator=" "),
            "rating": _text(item.select_one(".rating .rating_nums")),   # 非关键字段 → 空值
            "votes": _digits_to_int(_text(spans[-1]) if spans else ""),
            "quote": "",
        })
    return rows


