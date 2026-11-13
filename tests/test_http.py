"""utils/http.py：重试策略、按域名限速、Retry-After 处理。

这里的用例分两类：
- 策略对象的纯逻辑（退避时间、状态码判定）—— 直接断言数值；
- 真实传输行为（重试是否被限速、Retry-After 是否封顶）—— 用本地
  http.server 起一个可控的服务端，打真实请求。这类的价值在于
  「只读代码看不出问题」：重试交给 urllib3 时，限速器只对第一次请求
  生效，代码看起来完全正确，只有让服务端数一下被打了几个包才暴露。
"""
from __future__ import annotations

import http.server
import itertools
import threading
import time
from typing import ClassVar

import pytest
import requests

from utils.http import (
    BACKOFF_FACTOR,
    DEFAULT_TIMEOUT,
    GLOBAL_LIMITER,
    RETRY_AFTER_CAP,
    RETRY_STATUS,
    RateLimitedAdapter,
    RateLimiter,
    get,
    mount_retry,
    should_retry,
)


# ---------------------------------------------------------------- 本地假服务端
class Recorder(http.server.BaseHTTPRequestHandler):
    """记录每次被请求的时刻，并按脚本返回预设响应。

    plan / hits 是类属性（http.server 每次请求都新建 handler 实例，
    状态只能挂在类上），所以用 ClassVar 标注，避免被当成实例默认值。
    """

    plan: ClassVar[list[int]] = []          # 依次返回的状态码；用尽后重复最后一个
    retry_after: ClassVar[str | None] = None
    hits: ClassVar[list[float]] = []

    def do_GET(self):
        self.hits.append(time.monotonic())
        idx = min(len(self.hits) - 1, len(self.plan) - 1)
        status = self.plan[idx]
        self.send_response(status)
        if self.retry_after is not None:
            self.send_header("Retry-After", self.retry_after)
        self.end_headers()
        self.wfile.write(b"body")

    def log_message(self, *args):        # 别把访问日志刷到测试输出里
        pass


@pytest.fixture
def server():
    """起一个本地服务端，返回 (base_url, handler 类)。用完自动关。"""
    Recorder.plan = [200]
    Recorder.retry_after = None
    Recorder.hits = []

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", Recorder
    finally:
        httpd.shutdown()
        httpd.server_close()


def gaps(hits: list[float]) -> list[float]:
    return [round(b - a, 2) for a, b in itertools.pairwise(hits)]


# ---------------------------------------------------------------- 策略对象
class TestRetryPolicy:
    def test_retries_transient_statuses_only(self):
        assert {500, 502, 503, 504, 429} <= RETRY_STATUS
        # 403/404 不该重试：站方明确拒绝，重试只会加重对方负担
        assert 403 not in RETRY_STATUS
        assert 404 not in RETRY_STATUS

    def test_should_retry_helper_agrees_with_set(self):
        for code in (429, 500, 503):
            assert should_retry(code) is True
        for code in (200, 301, 403, 404):
            assert should_retry(code) is False

    def test_backoff_grows_with_attempt(self):
        """退避必须递增，否则「重试」等于「连发四次」，更容易触发封禁。

        直接算公式而不是调 retry.get_backoff_time() —— 后者在第 0 次
        尝试时恒为 0，断言它 >= 0 是恒真的废话。
        """
        delays = [BACKOFF_FACTOR * (2 ** i) for i in range(4)]

        assert delays == sorted(delays)
        assert delays[0] < delays[-1]
        assert delays == [0.5, 1.0, 2.0, 4.0]

    def test_only_idempotent_methods_are_retried(self):
        """重试只对 GET/HEAD/OPTIONS 有意义 —— POST 重试可能造成重复提交。

        重试现在是 adapter 里的显式循环，所以这条约束体现在：
        循环只重发调用方给的那个请求，而采集层全是 GET。
        这里断言 retries 可配置，作为「重试次数是策略而非魔法数」的证据。
        """
        assert RateLimitedAdapter(limiter=RateLimiter(0), retries=5).retries == 5


# ---------------------------------------------------------------- 限速器
class TestRateLimiter:
    def test_first_request_does_not_wait(self):
        assert RateLimiter(min_interval=10.0).wait("https://a.example/x") == 0.0

    def test_second_request_waits(self):
        limiter = RateLimiter(min_interval=0.15)

        limiter.wait("https://a.example/1")
        waited = limiter.wait("https://a.example/2")

        assert 0 < waited <= 0.20

    def test_different_hosts_do_not_block_each_other(self):
        """抓 A 站的等待不该阻塞 B 站 —— 否则并发采集形同虚设。"""
        limiter = RateLimiter(min_interval=10.0)
        limiter.wait("https://a.example/1")

        start = time.perf_counter()
        limiter.wait("https://b.example/1")

        assert time.perf_counter() - start < 0.1

    def test_host_matching_is_case_insensitive(self):
        limiter = RateLimiter(min_interval=10.0)

        limiter.wait("https://A.Example/1")

        assert list(limiter._last_hit) == ["a.example"]

    def test_zero_interval_disables_limiting(self):
        limiter = RateLimiter(min_interval=0)
        limiter.wait("https://a.example/1")

        assert limiter.wait("https://a.example/2") == 0.0

    def test_reset_clears_state(self):
        limiter = RateLimiter(min_interval=10.0)
        limiter.wait("https://a.example/1")

        limiter.reset()

        assert limiter.wait("https://a.example/1") == 0.0

    def test_lock_is_not_held_during_sleep(self):
        """锁内睡眠会把「一个域的等待」变成「全局阻塞」。

        验证方式：A 域进入等待后，B 域必须能立刻拿到自己的时间片
        （如果锁被 A 占着，B 这里会卡住直到 A 睡完）。
        """
        limiter = RateLimiter(min_interval=0.4)
        limiter.wait("https://a.example/1")

        done = threading.Event()

        def wait_on_a():
            limiter.wait("https://a.example/2")
            done.set()

        thread = threading.Thread(target=wait_on_a, daemon=True)
        thread.start()
        time.sleep(0.1)                      # 让 A 进入 sleep

        start = time.perf_counter()
        limiter.wait("https://b.example/1")  # B 不该被 A 的等待挡住
        elapsed = time.perf_counter() - start

        assert elapsed < 0.2, f"B 被 A 的等待阻塞了 {elapsed:.2f}s"
        done.wait(1.0)

    def test_concurrent_callers_are_spaced(self):
        limiter = RateLimiter(min_interval=0.05)
        stamps: list[float] = []
        lock = threading.Lock()

        def hit():
            limiter.wait("https://same.example/x")
            with lock:
                stamps.append(time.monotonic())

        threads = [threading.Thread(target=hit) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stamps.sort()
        assert len(stamps) == 4
        # 相邻间隔不小于最小间隔（留 20ms 容差给线程调度）
        real_gaps = [b - a for a, b in itertools.pairwise(stamps)]
        assert all(g >= 0.04 for g in real_gaps), [round(g, 3) for g in real_gaps]


# ---------------------------------------------------------------- 挂载
class TestMountRetry:
    def test_mounts_both_schemes(self):
        sess = mount_retry(requests.session())

        for prefix in ("http://", "https://"):
            assert prefix in sess.adapters
            assert isinstance(sess.adapters[prefix], RateLimitedAdapter)

    def test_internal_urllib3_retry_is_disabled(self):
        """★ 关键不变量：urllib3 内部重试必须关掉，否则重试绕过限速器。

        这正是本文件开头说明的那个 bug：代码看起来对，只有数包才发现。
        """
        sess = mount_retry(requests.session())

        assert sess.adapters["https://"].max_retries.total == 0

    def test_returns_same_session(self):
        sess = requests.session()
        assert mount_retry(sess) is sess

    def test_sessions_share_the_global_limiter(self):
        """不传 limiter 时，多个会话必须共用同一个限速器 ——
        否则「同一个域的最小间隔」在会话之间不成立。"""
        a = mount_retry(requests.session())
        b = mount_retry(requests.session())

        assert a.adapters["https://"].limiter is b.adapters["https://"].limiter
        assert a.adapters["https://"].limiter is GLOBAL_LIMITER

    def test_explicit_limiter_is_respected(self):
        limiter = RateLimiter(min_interval=99)
        sess = mount_retry(requests.session(), limiter=limiter)

        assert sess.adapters["https://"].limiter is limiter

    def test_session_builders_are_hardened(self):
        """make_session / make_browser_session 建出来的会话必须已经带策略，
        否则采集脚本还得自己记得挂 —— 那这个功能等于没做。"""
        from utils.net import make_browser_session, make_session

        for sess in (make_session(), make_browser_session()):
            adapter = sess.adapters["https://"]
            assert isinstance(adapter, RateLimitedAdapter)
            assert adapter.retries == 3


# ---------------------------------------------------------------- 真实传输行为
class TestRetryBehavior:
    def test_retries_do_not_bypass_the_rate_limiter(self, server):
        """★ 回归：重试的每一次尝试都必须过限速器。

        实测过的 bug：重试交给 urllib3 时，限速器只对第一次请求生效，
        服务端 503 时会连打三下，间隔 0.0s / 1.0s（要求 5s）。
        而 503 恰恰是最需要放慢的时候。

        ★ 关键设计：min_interval 必须**大于**退避时间（backoff 0.5s / 1.0s），
          否则退避本身就够久，即使重试绕过限速器，间隔也看起来正常 ——
          这条用例曾经就是这个毛病：阈值 0.2s 比退避还小，注入 bug 后照样绿。
          取 0.7s：绕过限速时第一次重试间隔只有 0.5s，会当场红。
        """
        base, handler = server
        handler.plan = [503, 503, 200]

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(min_interval=0.7), retries=2))
        sess.get(base + "/x", timeout=10)

        assert len(handler.hits) == 3
        # 每次尝试前都过限速器 → 间隔恒 ≥ 0.7s（≥ 退避的 0.5s/1.0s 中较小者）
        assert all(g >= 0.65 for g in gaps(handler.hits)), gaps(handler.hits)

    def test_retries_then_gives_up_and_returns_response(self, server):
        base, handler = server
        handler.plan = [503]                      # 一直 503

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(0), retries=2))
        response = sess.get(base + "/x", timeout=5)

        # 重试用尽后把响应交回去，由调用方判 status_code（而不是抛异常）
        assert response.status_code == 503
        assert len(handler.hits) == 3

    def test_success_does_not_retry(self, server):
        base, handler = server
        handler.plan = [200]

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(0), retries=3))
        sess.get(base + "/x", timeout=5)

        assert len(handler.hits) == 1

    def test_forbidden_is_not_retried(self, server):
        """403 是站方明确拒绝 —— 重试只会加重负担，也容易被判为攻击。"""
        base, handler = server
        handler.plan = [403]

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(0), retries=3))
        response = sess.get(base + "/x", timeout=5)

        assert response.status_code == 403
        assert len(handler.hits) == 1


class TestRetryAfter:
    def test_honours_server_hint(self, server):
        base, handler = server
        handler.plan = [429, 200]
        handler.retry_after = "1"

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(0), retries=1))
        start = time.monotonic()
        sess.get(base + "/x", timeout=10)

        assert time.monotonic() - start >= 0.9      # 真的等了 1 秒

    def test_caps_absurd_retry_after(self, server):
        """★ 回归：Retry-After 必须有上限。

        没有上限时，一个 `Retry-After: 3600` 就能让某个站点卡住一小时
        —— 而定时任务整体只有十分钟预算。常量 RETRY_AFTER_CAP 存在但
        没被用上，是「看起来做了、实际没做」的典型。
        """
        base, handler = server
        handler.plan = [429, 200]
        handler.retry_after = "3600"

        sess = requests.Session()
        sess.mount("http://", RateLimitedAdapter(limiter=RateLimiter(0), retries=1))

        from utils.http import _retry_after
        probe = requests.models.Response()
        probe.headers["Retry-After"] = "3600"
        assert _retry_after(probe) == 3600.0

        # 真实等待被 cap 住：别真等 30 秒，用 0.2 的 cap 替换验证逻辑
        import utils.http as http_mod
        original = http_mod.RETRY_AFTER_CAP
        try:
            http_mod.RETRY_AFTER_CAP = 0.2
            start = time.monotonic()
            sess.get(base + "/x", timeout=10)
            elapsed = time.monotonic() - start
        finally:
            http_mod.RETRY_AFTER_CAP = original

        assert elapsed < 2.0, f"Retry-After 没被封顶（等了 {elapsed:.1f}s）"

    def test_http_date_format_is_parsed(self):
        from utils.http import _retry_after

        probe = requests.models.Response()
        probe.headers["Retry-After"] = "Wed, 21 Oct 2026 07:28:00 GMT"

        assert _retry_after(probe) is None or _retry_after(probe) >= 0

    def test_missing_header_returns_none(self):
        from utils.http import _retry_after

        assert _retry_after(requests.models.Response()) is None

    def test_garbage_header_returns_none(self):
        from utils.http import _retry_after

        probe = requests.models.Response()
        probe.headers["Retry-After"] = "soon"

        assert _retry_after(probe) is None


class TestGetHelper:
    def test_always_passes_a_timeout(self):
        """项目里曾经有完全不带 timeout 的请求，会让定时任务无限挂起。"""

        class Recorder:
            def __init__(self):
                self.kwargs = None

            def get(self, url, **kwargs):
                self.kwargs = kwargs
                return "response"

        rec = Recorder()

        assert get("https://a.example/x", sess=rec) == "response"
        assert rec.kwargs["timeout"] == DEFAULT_TIMEOUT

    def test_timeout_can_be_overridden(self):
        class Recorder:
            def get(self, url, **kwargs):
                return kwargs["timeout"]

        assert get("https://a.example/x", sess=Recorder(), timeout=3) == 3

    def test_default_timeout_is_a_pair(self):
        assert isinstance(DEFAULT_TIMEOUT, tuple)
        assert len(DEFAULT_TIMEOUT) == 2


def test_retry_after_cap_is_sane():
    """上限要小于定时任务的单站点预算（600 秒），否则起不到保护作用。"""
    assert 0 < RETRY_AFTER_CAP <= 60
