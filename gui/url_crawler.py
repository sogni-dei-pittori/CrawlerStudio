"""URL 采集线程：调用 web_crawler 现成的函数，把进度发成信号。

为什么必须开线程：get_html() 里有请求重试 + 每页 1~5 秒随机间隔，
在主线程里跑界面会卡死（点不动、显示"未响应"）。

不重复实现抓取逻辑：get_html / extract_page_info / discover_subpages /
resolve_internal_url 全部复用 web_crawler.py 里现成的函数；
落盘复用 utils/site_csv.SiteCsvStore（数据落在 data/<域名>/<时间>/pages.csv）。
"""
from PySide6.QtCore import QThread, Signal

from utils.site_csv import SiteCsvStore
from web_crawler import (check_url, discover_subpages, extract_page_info, get_html,
                         is_blocked, normalize_url, resolve_internal_url)


class UrlCrawler(QThread):
    """抓一个 URL（可选抓站内子页），每抓一页发一次信号。"""

    progress = Signal(str)          # 进度文本
    page_done = Signal(dict)        # 抓到的一行数据
    done = Signal(str, int)         # (pages.csv 路径, 页数)
    failed = Signal(str)            # 失败原因
    stopped = Signal(str, int)      # 用户点了停止：(pages.csv 路径, 已抓页数)

    def __init__(self, url: str, subpages: bool = False,
                 max_subpages: int = 20, parent=None):
        super().__init__(parent)
        self.url = url
        self.subpages = subpages
        self.max_subpages = max_subpages

    def stop(self) -> None:
        """请求停止：线程会在"当前这一页抓完"之后收工，已经抓到的数据都留着。

        正在发出去的那个请求没法打断（最多等它超时，几秒），所以不是瞬间停。
        """
        self.requestInterruption()

    def run(self) -> None:
        """线程入口：这里允许阻塞，界面不会卡。"""
        try:
            ok, result = check_url(self.url)        # ★ 第一件事：域名校验
            if not ok:
                self.failed.emit(result)            # 不是网址 → 直接结束本次爬取
                return
            base = result
            store = SiteCsvStore(base)

            if self.isInterruptionRequested():      # 还没开始抓就被点了停止
                self.stopped.emit(str(store.path), 0)
                return

            resp = get_html(base)
            if resp is None:
                self.failed.emit("抓取失败：robots 不允许，或重试后仍拿不到页面")
                return
            if is_blocked(resp):
                self.failed.emit("被反爬拦截（403/429 或命中拦截关键词）")
                return

            row = extract_page_info(resp, base)
            store.save(row)
            count = 1
            self.page_done.emit(row)
            self.progress.emit(f"[1] 已抓取：{base}")

            if self.subpages:
                urls = resolve_internal_url(discover_subpages(resp, base), base)
                self.progress.emit(f"发现 {len(urls)} 个站内链接，最多抓 {self.max_subpages} 个")
                seen = {base}
                for target in urls:
                    if self.isInterruptionRequested():
                        self.progress.emit(f"收到停止请求：抓完当前这页就收工（已抓 {count} 页）")
                        break
                    if count >= self.max_subpages:
                        self.progress.emit(f"已达上限 {self.max_subpages} 页，停止")
                        break
                    sub = normalize_url(target)
                    if sub in seen:
                        continue
                    seen.add(sub)

                    sub_resp = get_html(sub, referer=base)
                    if sub_resp is None:
                        self.progress.emit(f"跳过（抓取失败）：{sub}")
                        continue
                    if is_blocked(sub_resp):
                        self.progress.emit(f"跳过（被拦截）：{sub}")
                        continue

                    sub_row = extract_page_info(sub_resp, sub)
                    store.save(sub_row)
                    count += 1
                    self.page_done.emit(sub_row)
                    self.progress.emit(f"[{count}] 已抓取：{sub}")

            if self.isInterruptionRequested():
                self.stopped.emit(str(store.path), count)
                return
            self.done.emit(str(store.path), count)

        except Exception as exc:            # 线程里的异常必须自己兜住，否则界面没有任何提示
            self.failed.emit(f"{exc.__class__.__name__}: {exc}")
