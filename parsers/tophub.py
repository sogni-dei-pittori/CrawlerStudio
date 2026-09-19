"""今日热榜（tophub.today）榜单 HTML → rows（纯函数）。

只做一件事：**HTML 原料 → list[dict]**。不联网、不读文件、不写 CSV、不知道快照是谁。
（source / board / snapshot 由采集层用 utils/schema.fill_core 补，和 parsers/douban.py 的分工一样。）

页面结构（2026-09-16 实测，tophub B站日榜）：

    <tr>
      <td align="center">1.</td>                                   ← rank（带一个点）
      <td align="center" class="al"><img src="封面图"></td>        ← 封面（不要）
      <td class="al">
        <div><a href="https://www.bilibili.com/video/av117.../">标题</a></div>
        <div class="item-desc">830.4万</div>                       ← 热度（万/亿）
      </td>
      <td align="right"><a href="..."><i class="m-n"></i></a></td>   ← 图标链（不要）
    </tr>
"""
import re

from bs4 import BeautifulSoup

_RANK_RE = re.compile(r"^(\d+)\s*\.?$")
_HEAT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(亿|万)?")
_AV_RE = re.compile(r"/video/av(\d+)", re.IGNORECASE)
_BV_RE = re.compile(r"/video/(BV[0-9A-Za-z]+)")
_UNITS = {"亿": 100_000_000, "万": 10_000}


def parse_count(text: str):
    """把 tophub 的热度文本转成整数：'830.4万' → 8304000；转不了返回 ''（空值约定）。

    ⚠️ 精度：'万' 只保留到 0.1 万 = 1000，所以得到的是**近似值**。
    原始文本会一并保留在 heat_text 列，核对时以它为准。
    """
    if not text:
        return ""
    match = _HEAT_RE.search(text.replace(",", ""))
    if not match:
        return ""
    value = float(match.group(1))
    unit = match.group(2)
    if unit:
        value *= _UNITS[unit]
    return int(value)


def extract_video_id(url: str):
    """从 B站视频链接里取 (aid, bvid)。老链接是 av 号，新链接是 BV 号，两种都认。"""
    match = _AV_RE.search(url or "")
    if match:
        return int(match.group(1)), ""
    match = _BV_RE.search(url or "")
    if match:
        return "", match.group(1)
    return "", ""


def parse_board(html: str, link_keyword: str = "/video/"):
    """把榜单页解析成 rows。`link_keyword` 用来过滤"这不是榜单条目"的行。"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue                        # 表头 / 空行

        rank_match = _RANK_RE.match(cells[0].get_text(strip=True))
        if not rank_match:
            continue                        # 第一格不是"名次"的行不算

        link = cells[2].find("a", href=True)
        if link is None or link_keyword not in link["href"]:
            continue                        # 不是目标榜单的条目

        heat_node = cells[2].select_one("div.item-desc")
        heat_text = heat_node.get_text(strip=True) if heat_node else ""
        aid, bvid = extract_video_id(link["href"])

        rows.append({
            "rank": int(rank_match.group(1)),
            "title": link.get_text(strip=True),
            "url": link["href"],
            "score": parse_count(heat_text),   # 榜单热度（B站榜 = 播放量，单位"万"）
            "heat_text": heat_text,            # 原始文本，留作核对
            "aid": aid,
            "bvid": bvid,
        })

    return rows


if __name__ == "__main__":
    # 自检：给一个本地 HTML 路径，打印解析结果的前 3 条 + 条数
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("用法：python parsers/tophub.py <本地榜单 HTML>")
        raise SystemExit(0)

    demo_rows = parse_board(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(f"解析到 {len(demo_rows)} 条")
    for demo in demo_rows[:3]:
        print(demo)
