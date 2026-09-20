import time
from utils.schema import BOARD_COLUMNS, order_columns, snapshot_of
from utils.net import describe_session, is_allowed, make_browser_session
from utils.dirs import make_run_dir
import pandas as pd
from pathlib import Path
from utils.logger import get_logger

URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
DOMAIN = "www.toutiao.com"
logger = get_logger("toutiao")
sess = make_browser_session()
sess.headers.update({
    "Origin": "https://www.toutiao.com",
    "Referer": "https://www.toutiao.com/",
})
logger.info("本次伪装身份：%s", describe_session(sess))

def make_row(item, rank, snapshot, category=None):
    """一条头条热榜数据 → schema 行（置顶与榜内共用，保证字段完全一致）。"""
    hot_value = item.get("HotValue", "")
    return {
        "rank": rank,
        "title": item.get("Title", ""),
        "url": f"https://www.toutiao.com/trending/{item.get('ClusterIdStr', '')}/" if item.get("ClusterIdStr") else item.get("Url", ""),
        "source": "toutiao",
        "board": "hot",
        "snapshot": snapshot,
        "score": int(hot_value) if str(hot_value).isdigit() else "",
        "category": category if category is not None else item.get("LabelDesc", ""),
        # —— 站点特有列（置顶没有的字段会兜底成空字符串，不再出现 NaN）——
        "label": item.get("Label", ""),
        "cluster_id": item.get("ClusterIdStr", "") or item.get("Id", ""),
        "query_word": item.get("QueryWord", ""),
    }


def fetch_toutiao_ranking(out_dir):
    allowed, reason = is_allowed(sess, URL)
    if not allowed:
        logger.error("robots 不允许抓取：%s（%s）", URL, reason)
        return []
    snapshot = snapshot_of(out_dir)
    time.sleep(1.5)
    resp = sess.get(URL, timeout=10)

    if resp.status_code != 200:
        logger.error("状态码异常 %s", resp.status_code)
        return []
    data = resp.json()

    if data.get("status") != "success":
        logger.error("接口返回异常：status=%s", data.get("status"))
        return []

    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "hot.json").write_text(resp.text, encoding="utf-8")

    # ① 置顶：藏在 fixed_top_data 里（字段只有 Id/Title/Url）→ 按 schema 约定 rank = 0
    rows = [make_row(it, 0, snapshot, category="置顶")
            for it in data.get("fixed_top_data") or []]
    # ② 榜内 50 条
    rows += [make_row(it, rank, snapshot)
             for rank, it in enumerate(data.get("data") or [], start=1)]
    return rows


def main() -> int:
    """命令行入口：python -m toutiao_api（开发）／ CrawlerStudio.exe --task toutiao_api（打包）。"""
    out_dir = make_run_dir(DOMAIN)
    rows = fetch_toutiao_ranking(out_dir)
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
