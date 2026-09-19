import time
import pandas as pd
from utils.net import is_allowed, make_browser_session
from utils.dirs import make_run_dir
from utils.schema import BOARD_COLUMNS, fill_core, order_columns, snapshot_of
from parsers.douban import parse_top250_movie, parse_top250_book, parse_doulist
from utils.logger import get_logger
from pathlib import Path

logger = get_logger("douban")
# 抓的是网页，按"地址栏直接打开"的样子发头（无 Referer）
sess = make_browser_session(dest="document", mode="navigate", site="none")
SLEEP = 3.0

MOVIE_DOMAIN = "movie.douban.com"
BOOK_DOMAIN = "book.douban.com"
DOULIST_DOMAIN = "www.douban.com"

def fetch_top250_movie(out_dir):
    rows = []
    allowed, reason = is_allowed(sess, "https://movie.douban.com/top250")
    if not allowed:
        logger.error("robots 不允许抓取：movie.douban.com（%s）", reason)
        return []
    for start in range(0, 250, 25):
        url = f"https://movie.douban.com/top250?start={start}"
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("状态码异常：HTTP %s %s", resp.status_code, url)
            continue
        raw_dir = Path(out_dir) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"top250_start{start}.html").write_text(resp.text, encoding="utf-8")  # ← 带 start

        rows.extend(parse_top250_movie(resp.text))
        time.sleep(SLEEP)
        logger.info("已抓 start=%d，累计 %d 条", start, len(rows))
    logger.info("共抓取 %d 条数据", len(rows))
    return [fill_core(r, "douban", "top250", snapshot_of(out_dir)) for r in rows]

def fetch_top250_book(out_dir):
    allowed, reason = is_allowed(sess, "https://book.douban.com/top250")
    if not allowed:
        logger.error("robots 不允许抓取：book.douban.com（%s）", reason)
        return []
    rows = []
    for start in range(0, 250, 25):
        url = f"https://book.douban.com/top250?start={start}"
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("状态码异常：HTTP %s %s", resp.status_code, url)
            continue
        raw_dir = Path(out_dir) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"top250_start{start}.html").write_text(resp.text, encoding="utf-8")  # ← 带 start

        rows.extend(parse_top250_book(resp.text, rank_offset=start))
        time.sleep(SLEEP)
        logger.info("已抓 start=%d，累计 %d 条", start, len(rows))
    logger.info("共抓取 %d 条数据", len(rows))
    return [fill_core(r, "douban", "top250", snapshot_of(out_dir)) for r in rows]

def fetch_doulist(out_dir,pages=5):
    rows = []
    allowed, reason = is_allowed(sess, "https://www.douban.com/doulist/116238969/")
    if not allowed:
        logger.error("robots 不允许抓取：www.douban.com（%s）", reason)
        return []
    for start in range(0, 25 * pages, 25):            # 0,25,50,75,100 → 5 页
        url = f"https://www.douban.com/doulist/116238969/?start={start}"
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("状态码异常：HTTP %s %s", resp.status_code, url)
            continue
        raw_dir = Path(out_dir) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"doulist_start{start}.html").write_text(resp.text, encoding="utf-8")
        page_rows = parse_doulist(resp.text)
        if not page_rows:                              # 已经到末页（列表没那么多）
            logger.info("已到末页，停止翻页")
            break
        rows.extend(page_rows)
        logger.info("已抓 start=%d，本页 %d 条，累计 %d 条", start, len(page_rows), len(rows))
        time.sleep(SLEEP)
    return [fill_core(r, "douban", "doulist", snapshot_of(out_dir)) for r in rows]

if __name__ == "__main__":
    movie_dir = make_run_dir(MOVIE_DOMAIN)
    book_dir = make_run_dir(BOOK_DOMAIN)
    doulist_dir = make_run_dir(DOULIST_DOMAIN)

    movie_rows = fetch_top250_movie(movie_dir)
    book_rows = fetch_top250_book(book_dir)
    doulist_rows = fetch_doulist(doulist_dir)


    if movie_rows:
        order_columns(pd.DataFrame(movie_rows), BOARD_COLUMNS).to_csv(
            movie_dir / "top250.csv", index=False, encoding="utf-8-sig")
        logger.info("已保存 CSV：%s（%d 行）", movie_dir / "top250.csv", len(movie_rows))
    if book_rows:
        order_columns(pd.DataFrame(book_rows), BOARD_COLUMNS).to_csv(
            book_dir / "top250.csv", index=False, encoding="utf-8-sig")
        logger.info("已保存 CSV：%s（%d 行）", book_dir / "top250.csv", len(book_rows))
    if doulist_rows:
        order_columns(pd.DataFrame(doulist_rows), BOARD_COLUMNS).to_csv(
            doulist_dir / "doulist.csv", index=False, encoding="utf-8-sig")
        logger.info("已保存 CSV：%s（%d 行）", doulist_dir / "doulist.csv", len(doulist_rows))
