"""HTTP 韧性层：重试 / 退避 / 限速。

为什么单独一层，而不是在每个采集脚本里写循环：
- 原来的写法是「一次 GET，失败就 return []」，一个瞬时 502 就整天没有数据；
- `time.sleep(1.5)` 散落在各脚本里，改一次限速要改五个文件；
- 重试策略、限速间隔、超时应该是**策略**，不是写死在业务里。

用法（对现有代码零侵入）：

    from utils.net import make_browser_session
    sess = make_browser_session()      # 已经自动挂上了重试与限速

挂载点是 requests 的 HTTPAdapter，所以 `sess.get(...)` 的调用方式完全不变，
原有脚本一行都不用改。

## 为什么重试是我们自己循环，而不是 urllib3 的 Retry

一开始的做法是给 adapter 设 `max_retries=Retry(...)`，让 urllib3 内部重试。
实测发现问题：`send()` 只被调用一次，urllib3 在 `super().send()` **内部**
重发，所以限速器只对第一次请求生效 —— 服务端 503 时会连打三下，
间隔 0.0s / 1.0s（要求是 5s）。而 503 恰恰是最需要放慢的时候。

更要命的是，这种做法下 `Retry-After` 也无从限制：urllib3 2.x 的
`retry_after_max` 才是那个开关，光有常量不传进去等于没有。

所以改成：adapter 关掉内部重试（`max_retries=0`），重试写在 `RateLimitedAdapter.send()`
的显式循环里，**每次尝试前都过一遍限速器**。代价是少了一点 urllib3 的便利，
换来的是「限速与重试在同一处、顺序确定」这个可以讲清楚的保证。

设计取舍：
- 只重试「值得重试」的：连接错误、超时、429、5xx。4xx（除 429）不重试 ——
  403 是站方明确拒绝，重试只会加重对方负担，也容易被判为攻击。
- 429 优先听 `Retry-After`，服务器说等多久就等多久（上限 `RETRY_AFTER_CAP` 兜住，
  防止被恶意站点用一个超长头拖死整个采集进程）。
- 限速按**域名**分别计算，不是全局 —— 抓 A 站的等待不该阻塞 B 站。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from requests.models import PreparedRequest, Response

# ---- 默认策略 ----
DEFAULT_TIMEOUT = (5, 15)      # (连接超时, 读取超时)：连接 5 秒内必须建立，读完给 15 秒
DEFAULT_RETRIES = 3            # 初次之外再试 3 次，共 4 次机会
BACKOFF_FACTOR = 0.5           # 退避基数：0.5s → 1s → 2s（指数）
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_AFTER_CAP = 30.0         # Retry-After 最长只认 30 秒
DEFAULT_MIN_INTERVAL = 1.0     # 同一域名两次请求之间至少间隔（秒）
RETRIABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@dataclass
class RateLimiter:
    """按域名的令牌间隔限速器（线程安全）。

    为什么是「最小间隔」而不是令牌桶：榜单采集的速率要求本来就低
    （一个站点每天几十次请求），间隔语义更直观，也更容易向答辩老师解释
    ——「我们保证对任一域名，相邻两次请求至少间隔 N 秒」。

    为什么用锁而不是队列：采集是并发的（见 run_daily.py 的线程池），
    但没有高吞吐需求，一把锁换来的是「绝不并发打同一个站」这个硬保证。
    """

    min_interval: float = DEFAULT_MIN_INTERVAL
    _last_hit: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, url: str) -> float:
        """如有必要就休眠，返回实际休眠的秒数（0 表示没等）。"""
        host = urlsplit(url).netloc.lower()
        if self.min_interval <= 0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            last = self._last_hit.get(host)
            if last is None:
                self._last_hit[host] = now
                return 0.0
            delay = self.min_interval - (now - last)
            if delay <= 0:
                self._last_hit[host] = now
                return 0.0
            # ★ 先「预约」下一次时间点再睡眠，且锁内不 sleep：
            #   如果把 sleep 放进锁里，一个域的等待会阻塞其它所有域。
            self._last_hit[host] = now + delay
        # 这里不封顶：delay 由我们自己的 min_interval 决定，不是外部输入
        time.sleep(delay)
        return delay

    def reset(self) -> None:
        """清空状态（测试用）。"""
        with self._lock:
            self._last_hit.clear()


# ---- 全局默认限速器 ----
# 所有用 make_session / make_browser_session 建出来的会话共用这一个，
# 所以同一个进程里「对某域名的最小间隔」是全局成立的。
#
# ⚠️ 它的作用范围是**单个进程**。run_daily 把五个站点跑在五个子进程里，
#    每个进程各有一份记录 —— 但五个站点本来就是五个不同域名，
#    所以实际采集行为不受影响。如果将来出现「多个进程打同一个站」的需求，
#    得把记录落到文件或加文件锁，那时再说。
GLOBAL_LIMITER = RateLimiter()


class RateLimitedAdapter(HTTPAdapter):
    """在真正发包之前先过限速器，并在这一层做重试。

    ★ 重试必须在**限速之内的显式循环**里做，不能交给 urllib3 的 max_retries：
      实测那样做时限速器只对第一次请求生效（503 时会连打三下，间隔 0.0s / 1.0s）。
    """

    def __init__(self, limiter: RateLimiter | None = None, retries: int = DEFAULT_RETRIES,
                 **kwargs):
        self.limiter = limiter if limiter is not None else GLOBAL_LIMITER
        self.retries = retries
        # 关掉 urllib3 的内部重试：重试由下面的 send() 负责
        kwargs["max_retries"] = 0
        super().__init__(**kwargs)

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        # 签名必须与 requests.adapters.HTTPAdapter.send 完全一致：
        # 这是覆写父类方法，类型不兼容会破坏 requests 的内部调用约定（mypy [override]）。
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> Response:
        url = request.url or ""
        last_exc: Exception | None = None

        for attempt in range(self.retries + 1):
            self.limiter.wait(url)                  # ★ 每次尝试前都限速
            try:
                response = super().send(request, stream=stream, timeout=timeout,
                                        verify=verify, cert=cert, proxies=proxies)
            except RETRIABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt >= self.retries:
                    raise
                self._sleep_before_retry(attempt, reason=type(exc).__name__)
                continue

            if response.status_code not in RETRY_STATUS or attempt >= self.retries:
                return response                     # 成功，或重试用尽把响应交回去

            self._sleep_before_retry(attempt, reason=f"HTTP {response.status_code}",
                                     response=response)

        # 循环只在重试用尽时退出；异常路径已在上面 raise
        if last_exc is not None:                    # pragma: no cover - 防御性
            raise last_exc
        raise RuntimeError("重试循环异常退出")       # pragma: no cover - 不可达

    def _sleep_before_retry(self, attempt: int, reason: str, response: Response | None = None) -> None:
        """退避等待。服务端给了 Retry-After 就听它的（但有上限）。"""
        delay = _retry_after(response) if response is not None else None
        if delay is None:
            delay = BACKOFF_FACTOR * (2 ** attempt)
        time.sleep(min(delay, RETRY_AFTER_CAP))


def _retry_after(response: Response) -> float | None:
    """解析 Retry-After 头，返回秒数；没有或解析不了返回 None。

    支持两种格式（RFC 7231）：秒数、以及 HTTP-date。
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    delta = when.timestamp() - time.time()
    return max(delta, 0.0)


def mount_retry(sess: requests.Session, retries: int = DEFAULT_RETRIES,
                limiter: RateLimiter | None = None) -> requests.Session:
    """给已有 session 装上「重试 + 限速」，返回同一个对象（便于链式调用）。

    两个协议共用同一个 adapter 实例：HTTPAdapter 不持有与协议相关的状态，
    限速器按 request.url 的域名分桶，所以共用是安全的。
    """
    adapter = RateLimitedAdapter(limiter=limiter, retries=retries)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess


def get(url: str, sess: requests.Session | None = None, *, timeout=DEFAULT_TIMEOUT,
        **kwargs) -> requests.Response:
    """带默认超时的一次 GET。

    存在的意义：项目里原来有 `sess.get(url)` 完全不带 timeout 的写法
    —— 那会让采集进程在某些站点上无限挂起，而定时任务只有十分钟总预算。
    这个函数的默认值把「必须给超时」变成不需要每次想起的事。
    """
    # 没传 session 就直接用模块级 requests.get（它内部会建临时 session）
    if sess is None:
        return requests.get(url, timeout=timeout, **kwargs)
    return sess.get(url, timeout=timeout, **kwargs)


def should_retry(status_code: int) -> bool:
    """给调用方判「这个状态码值得重试吗」（重试逻辑之外的只读查询）。"""
    return status_code in RETRY_STATUS


def host_of(urls: Iterable[str]) -> set[str]:
    """小工具：一批 URL 里出现了哪些域名（日志/自检用）。"""
    return {urlsplit(u).netloc.lower() for u in urls}
