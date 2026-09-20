import time
from utils.schema import BOARD_COLUMNS, order_columns, snapshot_of
from utils.net import make_browser_session, describe_session, is_allowed
from utils.dirs import make_run_dir
import pandas as pd
from pathlib import Path
from utils.logger import get_logger

URL = "https://api.juejin.cn/content_api/v1/content/article_rank?category_id=1&type=hot&count=20"
DOMAIN = "api.juejin.cn"
logger = get_logger("juejin")
sess = make_browser_session()
sess.headers.update({
    "Origin": "https://juejin.cn",
    "Referer": "https://juejin.cn/",
})
logger.info("本次伪装身份：%s", describe_session(sess))


def fetch_juejin_ranking(out_dir):
    snapshot = snapshot_of(out_dir)
    allowed, reason = is_allowed(sess, URL)
    if not allowed:
        logger.error("robots 不允许抓取：%s（%s）", URL, reason)
        return []
    time.sleep(1.5)
    resp = sess.get(URL, timeout=10)

    if resp.status_code != 200:
        logger.error("状态码异常 %s", resp.status_code)
        return []
    data = resp.json()

    if data.get("err_no") != 0:
        logger.error("掘金接口返回错误：err_no=%s err_msg=%s", data.get("err_no"), data.get("err_msg"))
        return []

    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "hot.json").write_text(resp.text, encoding="utf-8")

    items = data.get("data") or []

    rows = []
    for rank, item in enumerate(items, start=1):
        rows.append({
            # —— schema 核心列 ——
            "rank": rank,
            "title": item["content"]["title"],
            "url": f"https://juejin.cn/post/{item['content']['content_id']}",
            "source": "juejin",
            "board": "hot",
            "snapshot": snapshot,
            "score": item['content_counter']['hot_rank'],
            "category": item["content"].get("category_id", ""),
            # —— 站点特有列 ——
            "view": item["content_counter"]["view"],
            "like": item["content_counter"]["like"],
            "collect": item["content_counter"]["collect"],
            "author": item["author"]["name"],
        })
    return rows


def main() -> int:
    """命令行入口：python -m juejin_api（开发）／ CrawlerStudio.exe --task juejin_api（打包）。"""
    out_dir = make_run_dir(DOMAIN)
    rows = fetch_juejin_ranking(out_dir)
    if not rows:
        logger.error("没有获取到数据，结束运行")
        return 1
    df = order_columns(pd.DataFrame(rows), BOARD_COLUMNS)
    csv_path = out_dir / "hot.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    logger.info("已保存 CSV：%s（%d 行）", csv_path, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
