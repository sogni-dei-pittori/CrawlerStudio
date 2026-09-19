import time
from utils.net import is_allowed, make_browser_session
from utils.dirs import make_run_dir
from utils.schema import BOARD_COLUMNS, clean_url, order_columns, snapshot_of
from utils.logger import get_logger
import pandas as pd
from pathlib import Path

logger = get_logger("baidu")
URL = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
DOMAIN = "top.baidu.com"
sess = make_browser_session(site="same-origin")  # 榜单接口和页面同域，是 same-origin
sess.headers['Referer'] = 'https://top.baidu.com/'


def fetch_baidu_ranking(out_dir):
    snapshot = snapshot_of(out_dir)
    allowed, reason = is_allowed(sess, URL)
    if not allowed:
        logger.error("robots 不允许抓取：%s（%s）", URL, reason)
        return []
    sess.get("https://top.baidu.com/", timeout=10)  # 让 session 收下 Cookie
    time.sleep(1.5)
    resp = sess.get(URL, timeout=10)
    data = resp.json()
    if data['success'] is not True:
        logger.error("百度接口返回错误：success=%s error=%s", data["success"], data.get("error"))
        return []

    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "board.json").write_text(resp.text, encoding="utf-8")

    cards = data['data']['cards']
    items = cards[0]["content"][0]["content"]

    rows = []
    for item in items:
        rows.append({
            # —— schema 核心列 ——
            "rank": item.get("index", 0),
            "title": item["word"],
            "url": clean_url(item.get("url", "")),
            "source": "baidu",
            "board": "realtime",
            "snapshot": snapshot,
            "score": "",  # 接口没有可靠热度值，留空
            "category": item.get("labelTagName") or item.get("newHotName", ""),
            # —— 站点特有列 ——
            "tag": item.get("newHotName", ""),
        })
    return rows


if __name__ == "__main__":
    out_dir = make_run_dir(DOMAIN)
    rows = fetch_baidu_ranking(out_dir)
    if not rows:
        logger.error("没有获取到数据")
        exit(1)
    df = order_columns(pd.DataFrame(rows), BOARD_COLUMNS)

    df.to_csv(out_dir / "board.csv", index=False, encoding='utf-8-sig')
    logger.info("已保存 CSV：%s", out_dir / "board.csv")
