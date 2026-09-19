"""网络层：会话构造 + 请求头自洽。

两个入口：
- make_browser_session()  发一整套自洽的浏览器头（默认按"接口调用"来发）
- make_session()          精简版，只发 UA / Accept / Accept-Language

"自洽"是指：UA 说是 Edge，sec-ch-ua 就必须是 Edge；UA 是 Firefox，
就一个 sec-ch-ua 都不许发 —— Firefox 根本不支持客户端提示，
发了等于主动告诉对方"我是脚本"。
"""
import importlib.util
import random
import re
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import requests

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
]

# 只有这两个浏览器支持客户端提示；键名必须和 _parse_ua 返回的 browser 对上
_BRANDS = {
    "chrome": '"Chromium";v="{v}", "Not)A;Brand";v="24", "Google Chrome";v="{v}"',
    "edge": '"Chromium";v="{v}", "Not)A;Brand";v="24", "Microsoft Edge";v="{v}"',
}

_ACCEPT_HTML = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,"
    "application/signed-exchange;v=b3;q=0.7"
)
_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7"
_ROBOTS_CACHE: dict[str, tuple] = {}  # host → (规则对象 或 None, robots 原文)


def _robots_url(url: str) -> str:
    """由目标 URL 推出它所属站点的 robots.txt 地址。"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), "/robots.txt", "", ""))


def _parse_robots(text: str) -> RobotFileParser:
    """把 robots 文本变成规则对象。

    ⚠️ 必须走 parse()，不能用 rp.read()：read() 会自己发一次请求，
    而且带的是 Python-urllib/3.x 这个 UA（等于主动自报家门）。
    """
    rp = RobotFileParser()
    rp.parse(text.splitlines())
    return rp


def _has_query_rule(text: str) -> bool:
    """robots 原文里有没有"带 ? 的规则"。

    标准库匹配前会把 URL 的 query 丢掉，所以这类规则必然失效（实测 zol 的
    /?* 、/*html?* 、/router.php?* 三条全部被判成"允许"）。这里只做探测，
    真正的判断放在 is_allowed 里。
    """
    for line in text.splitlines():
        line = line.strip().lower()
        if line.startswith(("disallow", "allow")) and "?" in line:
            return True
    return False


def get_robots(sess, url: str) -> tuple:
    """取 + 解析 + 缓存，返回 (规则对象 或 None, robots 原文)。

    None  = 没拿到（网络错误 / 5xx）→ 调用方自行决定，且不写缓存（下次还要试）
    空规则 = 站方明确"没有 robots.txt"（404）→ 视为允许，且必须缓存
    """
    host = urlsplit(url).netloc.lower()
    if host in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[host]  # ② 命中缓存，不再发请求

    robots_url = _robots_url(url)
    try:
        resp = sess.get(robots_url, timeout=5)  # robots 用短超时，别拖慢采集
    except Exception as exc:
        return None, f"请求 {robots_url} 失败：{exc}"

    if resp.status_code == 404:
        # 注意：裸 RobotFileParser() 在没读过规则时会一律返回 False（= 禁止），
        # 所以这里必须 parse([]) 显式声明"没有任何规则"。
        _ROBOTS_CACHE[host] = (_parse_robots(""), "")
        return _ROBOTS_CACHE[host]

    if resp.status_code != 200:
        return None, f"robots.txt 状态码异常：HTTP {resp.status_code}"

    _ROBOTS_CACHE[host] = (_parse_robots(resp.text), resp.text)
    return _ROBOTS_CACHE[host]


def is_allowed(sess, url: str) -> tuple[bool, str]:
    """给调用方用：(能不能抓, 原因)。原因文本要打印进日志 —— 这是合规证据。"""
    rp, text = get_robots(sess, url)

    if rp is None:
        return True, "robots 未取到（网络错误或 5xx），按未声明处理"

    ua = sess.headers.get("User-Agent", "*")  # 用我们真正在用的 UA 去问
    if not rp.can_fetch(ua, url):  # 注意方法名：can_fetch，不是 canfetch
        return False, "robots 明确禁止"

    if "?" in url and _has_query_rule(text):
        return False, "URL 带查询参数，且 robots 里有含 ? 的规则（标准库会误判），保守拒绝"

    if not text:
        return True, "没有 robots.txt（404），视为允许"
    return True, "robots 允许"


def _accept_encoding() -> str:
    """装了哪个压缩库，才敢在头里写哪个编码"""
    encodings = ["gzip", "deflate"]
    for module, token in (("brotli", "br"), ("brotlicffi", "br"), ("zstandard", "zstd")):
        if importlib.util.find_spec(module) is None:  # 只探测，不真的把模块加载进内存
            continue
        if token not in encodings:
            encodings.append(token)
    return ", ".join(encodings)


_ACCEPT_ENCODING = _accept_encoding()


def make_session() -> requests.Session:
    """精简版会话：保持原样别动。"""
    sess = requests.session()
    sess.headers["User-Agent"] = random.choice(USER_AGENTS)
    sess.headers["Accept-Language"] = _ACCEPT_LANGUAGE
    sess.headers["Accept"] = _ACCEPT_HTML
    return sess


def _parse_ua(ua: str) -> dict:
    """从 UA 里读出浏览器 / 大版本号 / 平台 / 是否移动端。"""
    browser, major = "unknown", "0"  # 兜底：都没匹配上时用

    # ① 必须先判 Edge —— 因为 Edge 的 UA 里也含 "Chrome/"
    m = re.search(r"Edg/(\d+)", ua)
    if m:
        browser, major = "edge", m.group(1)
    else:
        # ② Chrome
        m = re.search(r"Chrome/(\d+)", ua)
        if m:
            browser, major = "chrome", m.group(1)
        else:
            # ③ Firefox
            m = re.search(r"Firefox/(\d+)", ua)
            if m:
                browser, major = "firefox", m.group(1)

    # ④ 平台（客户端提示里的取值：Windows / macOS / Android / Linux）
    if "Windows NT" in ua:
        platform = "Windows"
    elif "Mac OS X" in ua:
        platform = "macOS"
    elif "Android" in ua:
        platform = "Android"
    else:
        platform = "Linux"
    # 注：iOS 的 Chrome 是 WebKit 内核、根本不发客户端提示，所以别往 USER_AGENTS 里放 iPhone/iPad

    # ⑤ 是否移动端
    mobile = ("Android" in ua) or ("iPhone" in ua)

    return {"browser": browser, "major": major,
            "platform": platform, "mobile": mobile}


def make_browser_session(ua: str | None = None, dest: str = "empty",
                         mode: str = "cors", site: str = "same-site",
                         ) -> requests.Session:
    """自洽浏览器会话。

    默认按「接口调用」发头。抓网页时传 dest="document", mode="navigate", site="none"。
    """
    ua = ua or random.choice(USER_AGENTS)
    info = _parse_ua(ua)

    sess = requests.session()
    sess.headers["User-Agent"] = ua
    # 接口请求真实浏览器发的是 */*；只有导航请求才发那一长串 HTML 的 Accept
    sess.headers["Accept"] = "*/*" if dest == "empty" else _ACCEPT_HTML
    sess.headers["Accept-Language"] = _ACCEPT_LANGUAGE
    sess.headers["Accept-Encoding"] = _ACCEPT_ENCODING
    sess.headers["Connection"] = "keep-alive"

    # sec-fetch-* ：三种浏览器都支持，可以都发
    sess.headers["sec-fetch-dest"] = dest
    sess.headers["sec-fetch-mode"] = mode
    sess.headers["sec-fetch-site"] = site
    if dest == "document":
        sess.headers["Upgrade-Insecure-Requests"] = "1"

    # 客户端提示：只有 Chrome / Edge 才发（Firefox 不支持，发了就自相矛盾）
    if info["browser"] in _BRANDS:
        v = info["major"]  # 版本号必须和 UA 里那个数字一样
        sess.headers["sec-ch-ua"] = _BRANDS[info["browser"]].format(v=v)
        sess.headers["sec-ch-ua-mobile"] = "?1" if info["mobile"] else "?0"
        sess.headers["sec-ch-ua-platform"] = f'"{info["platform"]}"'  # 引号别忘了

    return sess


def describe_session(sess: requests.Session) -> dict:
    """给日志用：一眼看出这次到底伪装成了谁。"""
    headers = sess.headers
    return {
        "ua": headers.get("User-Agent", ""),
        "browser": _parse_ua(headers.get("User-Agent", "")),
        "accept": headers.get("Accept", ""),
        "accept-encoding": headers.get("Accept-Encoding", ""),
        "sec-ch-ua": headers.get("sec-ch-ua", "(不发)"),
        "sec-ch-ua-mobile": headers.get("sec-ch-ua-mobile", "(不发)"),
        "sec-ch-ua-platform": headers.get("sec-ch-ua-platform", "(不发)"),
        "sec-fetch-dest": headers.get("sec-fetch-dest", ""),
        "sec-fetch-mode": headers.get("sec-fetch-mode", ""),
        "sec-fetch-site": headers.get("sec-fetch-site", ""),
    }


if __name__ == "__main__":
    # 自检：把每个 UA 都过一遍，看头部有没有互相打架
    print(f"Accept-Encoding = {_ACCEPT_ENCODING}\n")
    for i, ua in enumerate(USER_AGENTS, 1):
        info = _parse_ua(ua)
        headers = make_browser_session(ua).headers
        verdict = "OK"

        if info["browser"] == "firefox" and "sec-ch-ua" in headers:
            verdict = "MISMATCH: firefox must not send sec-ch-ua"
        elif info["browser"] in _BRANDS:
            needle = 'v="%s"' % info["major"]
            if "sec-ch-ua" not in headers or needle not in headers["sec-ch-ua"]:
                verdict = "MISMATCH: version not in sec-ch-ua"

        print(f"[{i}] {info['browser']:7s} v{info['major']:<4s} "
              f"{info['platform']:8s} mobile={str(info['mobile']):5s} "
              f"sec-ch-ua={headers.get('sec-ch-ua', '(none)')}  -> {verdict}")

    print("\n--- robots 检查 ---")
    cases = [
        ("https://www.douban.com/", "允许"),
        ("https://www.weibo.com/", "禁止（Disallow: /）"),
        ("https://example.com/", "404 → 视为允许"),
    ]
    for i, (url, expect) in enumerate(cases, 1):
        probe = make_browser_session(dest="document", mode="navigate", site="none")
        allowed, reason = is_allowed(probe, url)
        print(f"[{i}] {url:26s} 期望={expect:18s} allowed={allowed}  {reason}")

    # 缓存自检：同一域名再问一次，应该瞬间返回（说明没有重新请求）
    probe = make_browser_session(dest="document", mode="navigate", site="none")
    t0 = time.perf_counter()
    is_allowed(probe, "https://www.douban.com/")
    print(f"第二次查询耗时 {time.perf_counter() - t0:.4f} 秒（接近 0 = 走了缓存）")
    print(f"缓存里的域名：{sorted(_ROBOTS_CACHE)}")
