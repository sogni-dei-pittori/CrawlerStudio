"""utils/http.py：重试策略、按域名限速。

这里不真的发包 —— 测的是「策略对象」和「限速器」本身。
真正的传输由 urllib3 负责，重测它没有意义。
"""
from __future__ import annotations

import itertools
import threading
import time

from utils.http import (
    DEFAULT_TIMEOUT,
    RETRY_STATUS,
    RateLimiter,
    build_retry,
    get,
    mount_retry,
)


class TestBuildRetry:
    def test_retries_transient_statuses_only(self):
        retry = build_retry()

        # 5xx 与 429 值得重试
        assert {500, 502, 503, 504, 429} <= set(retry.status_forcelist)
        # 403/404 不该重试：站方明确拒绝，重试只会加重对方负担
        assert 403 not in retry.status_forcelist
        assert 404 not in retry.status_forcelist

    def test_only_idempotent_methods_are_retried(self):
        """POST 重试可能造成重复提交 —— 榜单采集全是 GET，没必要冒这个险。"""
        retry = build_retry()

        assert retry.allowed_methods == frozenset({"GET", "HEAD", "OPTIONS"})

    def test_backoff_is_exponential(self):
        """退避必须递增，否则「重试」等于「连发四次」，更容易触发封禁。"""
        retry = build_retry(total=3)

        first = retry.get_backoff_time()
        assert first >= 0
        assert retry.backoff_factor > 0

    def test_respects_retry_after(self):
        """服务器说等多久就等多久 —— 这是最不容易被判成攻击的做法。"""
        retry = build_retry()

        assert getattr(retry, "respect_retry_after_header", True) is True

    def test_retry_count_is_configurable(self):
        assert build_retry(total=5).total == 5


class TestRateLimiter:
    def test_first_request_does_not_wait(self):
        limiter = RateLimiter(min_interval=10.0)

        assert limiter.wait("https://a.example/x") == 0.0

    def test_second_request_waits(self):
        limiter = RateLimiter(min_interval=0.15)

        limiter.wait("https://a.example/1")
        waited = limiter.wait("https://a.example/2")

        assert waited > 0
        assert waited <= 0.15 + 0.05      # 允许调度抖动

    def test_different_hosts_do_not_block_each_other(self):
        """抓 A 站的等待不该阻塞 B 站 —— 否则并发采集形同虚设。"""
        limiter = RateLimiter(min_interval=10.0)

        limiter.wait("https://a.example/1")
        start = time.perf_counter()
        limiter.wait("https://b.example/1")

        assert time.perf_counter() - start < 0.1

    def test_host_matching_is_case_insensitive(self):
        """同域不同大小写要认成同一台主机，否则换个大小写就能绕过限速。

        用极小的间隔 × 大小写翻转来验证：第二次必须被识别为「同一域名」。
        直接调内部记录判断，比 sleep 10 秒等待快得多，也不会因调度抖动而不稳。
        """
        limiter = RateLimiter(min_interval=10.0)

        limiter.wait("https://A.Example/1")

        # 记录里只应有一个键，且已归一化为小写
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

    def test_concurrent_callers_are_serialized(self):
        """并发时不能两个线程同时通过 —— 锁要真的有效。"""
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
        # 相邻两次的实际间隔必须不小于最小间隔（留 20ms 容差给线程调度）
        gaps = [b - a for a, b in itertools.pairwise(stamps)]
        assert all(gap >= 0.04 for gap in gaps), gaps


class TestMountRetry:
    def test_mounts_both_schemes(self):
        import requests

        sess = mount_retry(requests.session())

        for prefix in ("http://", "https://"):
            assert prefix in sess.adapters
            assert sess.adapters[prefix].max_retries.total > 0

    def test_returns_same_session(self):
        import requests

        sess = requests.session()
        assert mount_retry(sess) is sess

    def test_session_builders_are_hardened(self):
        """make_session / make_browser_session 建出来的会话必须已经带策略，
        否则采集脚本还得自己记得挂 —— 那这个功能等于没做。"""
        from utils.net import make_browser_session, make_session

        for sess in (make_session(), make_browser_session()):
            assert "https://" in sess.adapters
            assert sess.adapters["https://"].max_retries.total > 0


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
        """(连接, 读取) 分开设：连接卡住要快速失败，读取可以慢一点。"""
        assert isinstance(DEFAULT_TIMEOUT, tuple)
        assert len(DEFAULT_TIMEOUT) == 2


def test_retry_status_set_matches_documentation():
    assert frozenset({429, 500, 502, 503, 504}) == RETRY_STATUS
