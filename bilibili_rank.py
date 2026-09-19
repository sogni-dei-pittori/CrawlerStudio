"""B站「全站日榜」采集（数据源：今日热榜 tophub.today）。

为什么换源：B站官方接口域 `api.bilibili.com` 的 robots.txt 是
`User-agent: *` + `Disallow: /`（全站禁止），按本项目「遵守 robots.txt」的原则，
2026-09-16 起**停止采集该域**（实测记录见 sites.md 第一节）。
`tophub.today` 没有 robots.txt（HTTP 404 → 视为允许），榜单页是服务端渲染，
可以直接拿到 100 条日榜和播放量。

落盘约定（与其他采集脚本一致，见 README 第五节）：
  data/tophub.today/<快照>/raw/bilibili.html   ① 原始 HTML（页面改版后可离线重解析）
  data/tophub.today/<快照>/bilibili.csv        ② 结构化成品

与其他源的三点差异（分析、写论文时要注意）：
- `score` 是 tophub 展示的播放量，单位「万」（0.1 万 = 1000）→ 是**近似值**；
  原始文本保留在 `heat_text` 列，核对时以它为准。
- 榜单名次与展示热度**不严格单调**（榜首 830 万，第 100 名反而 334 万）→
  不要假设"名次越靠前分数越高"。
- 链接是 B站**老式 av 号**（`/video/av117.../`），所以 `bvid` 列为空、`aid` 有值；
  旧接口数据两列都有，跨新旧数据合并时用 `aid` 对齐。
"""
import sys
import time
from pathlib import Path

import pandas as pd

from parsers.tophub import parse_board
from utils.dirs import make_run_dir
from utils.logger import get_logger
from utils.net import describe_session, make_browser_session, is_allowed
from utils.schema import BOARD_COLUMNS, fill_core, order_columns, snapshot_of

BOARD_ID = "74KvxwokxM"  # tophub 榜单编号：哔哩哔哩全站日榜
URL = f"https://tophub.today/n/{BOARD_ID}"
DOMAIN = "tophub.today"  # 快照按"实际抓取的域名"归档（合规留痕）
RAW_NAME = "bilibili.html"  # raw 与成品同名，只差扩展名
CSV_NAME = "bilibili.csv"
BOARD = "ranking"  # 榜单名与其他源保持一致
VIA = "tophub.today"  # 数据经由谁获取
EXPECTED_ROWS = 100
RETRY_WAITS = (3.0, 10.0, 30.0)

logger = get_logger("bilibili")
sess = make_browser_session(dest="document", mode="navigate", site="none")
sess.headers["Referer"] = "https://tophub.today/"


def fetch_board(retries: int = 3):
    """取榜单页 HTML，失败就退避重试。成功返回 Response，放弃返回 None。"""
    allowed, reason = is_allowed(sess, URL)
    if not allowed:
        logger.error("robots 不允许抓取：%s（%s）", URL, reason)
        return None
    for attempt in range(1, retries + 1):
        wait = RETRY_WAITS[min(attempt - 1, len(RETRY_WAITS) - 1)]
        try:
            resp = sess.get(URL, timeout=15)
        except Exception as exc:
            logger.warning("网络错误：%s（第 %d 次），等 %.1f 秒重试", exc, attempt, wait)
        else:
            if resp.status_code == 200:
                logger.info("第 %d 次请求成功（HTTP 200，%d 字节）", attempt, len(resp.text))
                return resp
            logger.warning("状态码异常：HTTP %s（第 %d 次），等 %.1f 秒重试",
                           resp.status_code, attempt, wait)
        if attempt < retries:
            time.sleep(wait)
    return None


def build_rows(html: str, snapshot: str):
    """HTML → rows：解析（纯函数）+ 补核心列 + 记录"数据经由谁"。"""
    rows = []
    for row in parse_board(html):
        fill_core(row, source="bilibili", board=BOARD, snapshot=snapshot)
        row["via"] = VIA
        row["board_id"] = BOARD_ID
        row["view"] = row["score"]  # 与旧接口数据对齐的列名（含义都是播放量）
        rows.append(row)
    return rows


def main() -> int:
    out_dir = make_run_dir(DOMAIN)
    logger.info("本次伪装身份：%s", describe_session(sess))
    logger.info("请求榜单页：%s", URL)

    resp = fetch_board()
    if resp is None:
        logger.error("重试用尽仍未拿到数据：%s", URL)
        return 1

    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / RAW_NAME
    raw_path.write_text(resp.text, encoding="utf-8")  # ① 原料先落盘
    logger.info("原始 HTML 已保存：%s", raw_path)

    rows = build_rows(resp.text, snapshot_of(out_dir))  # ② 再解析
    if not rows:
        logger.error("解析结果为空，没有获取到数据（页面可能改版，见 parsers/tophub.py）")
        return 1
    if len(rows) != EXPECTED_ROWS:
        logger.warning("条数与预期不符：期望 %d，实际 %d（页面改版？请人工核对）",
                       EXPECTED_ROWS, len(rows))

    df = order_columns(pd.DataFrame(rows), BOARD_COLUMNS)  # ③ 成品落盘
    csv_path = out_dir / CSV_NAME
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info("已保存 CSV：%s（%d 行）", csv_path, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
