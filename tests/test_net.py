"""utils/net.py：会话头的自洽性 + robots.txt 判定与缓存。

这一层是整个采集器的「合规门面」，也是最容易悄悄坏掉的地方
（UA 说自己是 Firefox 却发了 sec-ch-ua，等于主动暴露是脚本）。
所以断言写得具体，不测「返回了对象」这种废话。
"""
from __future__ import annotations

import re

import pytest
from conftest import FakeResponse

from utils import net


class TestParseUserAgent:
    @pytest.mark.parametrize(
        ("ua", "browser", "major"),
        [
            (net.USER_AGENTS[0], "edge", "138"),
            (net.USER_AGENTS[1], "chrome", "138"),
            (net.USER_AGENTS[2], "chrome", "120"),
            (net.USER_AGENTS[3], "firefox", "120"),
            (net.USER_AGENTS[5], "firefox", "151"),
        ],
    )
    def test_detects_browser_and_version(self, ua, browser, major):
        info = net._parse_ua(ua)

        assert (info["browser"], info["major"]) == (browser, major)

    def test_edge_is_not_mistaken_for_chrome(self):
        """Edge 的 UA 里同时含有 'Chrome/'，判定顺序错了就会认错浏览器。"""
        edge_ua = next(ua for ua in net.USER_AGENTS if "Edg/" in ua)

        assert net._parse_ua(edge_ua)["browser"] == "edge"

    def test_unknown_ua_does_not_raise(self):
        info = net._parse_ua("curl/8.0")

        assert info["browser"] == "unknown"

    @pytest.mark.parametrize(
        ("ua", "platform"),
        [
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Windows"),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "macOS"),
            ("Mozilla/5.0 (Linux; Android 13)", "Android"),
        ],
    )
    def test_detects_platform(self, ua, platform):
        assert net._parse_ua(ua)["platform"] == platform


class TestMakeBrowserSession:
    def test_firefox_sends_no_client_hints(self):
        """核心不变量：Firefox 不支持 sec-ch-ua，发了就是自曝。"""
        firefox = next(ua for ua in net.USER_AGENTS if "Firefox/" in ua)

        headers = net.make_browser_session(ua=firefox).headers

        assert "sec-ch-ua" not in headers

    @pytest.mark.parametrize(
        ("ua", "major", "brand"),
        [
            (net.USER_AGENTS[0], "138", "Microsoft Edge"),
            (net.USER_AGENTS[1], "138", "Google Chrome"),
            (net.USER_AGENTS[2], "120", "Google Chrome"),
        ],
    )
    def test_chromium_version_matches_ua(self, ua, major, brand):
        """sec-ch-ua 里的版本号与品牌必须和 UA 里一致，否则两家一对就是矛盾。

        ★ 这里的期望值是**写死**的，不是从 _parse_ua 反推出来的。
          如果从同一个解析函数取期望值，解析器认错浏览器时两边会一起错，
          断言照样通过 —— 那就成了自证。
        """
        headers = net.make_browser_session(ua=ua).headers

        assert f'v="{major}"' in headers["sec-ch-ua"]
        assert brand in headers["sec-ch-ua"]

    def test_api_mode_accepts_anything(self):
        """接口调用发 Accept: */*，不是那一长串 HTML 类型。"""
        headers = net.make_browser_session(dest="empty").headers

        assert headers["Accept"] == "*/*"

    def test_document_mode_accepts_html(self):
        headers = net.make_browser_session(dest="document", mode="navigate").headers

        assert "text/html" in headers["Accept"]
        assert headers["sec-fetch-dest"] == "document"
        assert headers["Upgrade-Insecure-Requests"] == "1"

    def test_every_ua_produces_self_consistent_headers(self):
        """把自检脚本里的判断搬进测试：以后改 USER_AGENTS 会当场红。

        ★ 期望值从 UA **原文**用正则取，而不是从 _parse_ua 的返回值取 ——
          否则解析器把 Edge 认成 Chrome 时，头和期望会一起错，测试照样绿。
        """
        for ua in net.USER_AGENTS:
            headers = net.make_browser_session(ua=ua).headers

            if "Firefox/" in ua:                       # Firefox 不支持客户端提示
                assert "sec-ch-ua" not in headers, ua
                continue

            # 版本号直接读原文
            match = re.search(r"(?:Chrome|Edg)/(\d+)", ua)
            assert match, ua
            assert f'v="{match.group(1)}"' in headers["sec-ch-ua"], ua

            # 品牌也要对得上：Edg/ 的 UA 必须是 Microsoft Edge
            if "Edg/" in ua:
                assert "Microsoft Edge" in headers["sec-ch-ua"], ua
            else:
                assert "Google Chrome" in headers["sec-ch-ua"], ua

    def test_accept_encoding_only_lists_installed_codecs(self):
        """声明的压缩算法必须先有库能解，否则响应解不开。"""
        encoding = net._accept_encoding()

        assert "gzip" in encoding
        if "br" in encoding:
            assert net.importlib.util.find_spec("brotli") or net.importlib.util.find_spec("brotlicffi")


class TestRobots:
    def test_404_means_allowed(self, fake_session):
        sess = fake_session({"/robots.txt": FakeResponse(404)})

        allowed, reason = net.is_allowed(sess, "https://a.example/page")

        assert allowed is True
        assert "404" in reason

    def test_disallow_all_is_respected(self, fake_session):
        sess = fake_session({"/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /\n")})

        allowed, reason = net.is_allowed(sess, "https://a.example/page")

        assert allowed is False
        assert "禁止" in reason

    def test_specific_path_disallow(self, fake_session):
        sess = fake_session({"/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /private\n")})

        assert net.is_allowed(sess, "https://a.example/private/x")[0] is False
        assert net.is_allowed(sess, "https://a.example/public/x")[0] is True

    def test_network_failure_fails_open(self, fake_session):
        """拿不到 robots（网络挂了 / 5xx）时按「未声明」处理，不阻塞采集。"""
        class Boom(fake_session):
            def get(self, url, **kwargs):
                raise OSError("connection reset")

        allowed, reason = net.is_allowed(Boom(), "https://a.example/page")

        assert allowed is True
        assert "未取到" in reason

    def test_5xx_fails_open(self, fake_session):
        sess = fake_session({"/robots.txt": FakeResponse(503)})

        assert net.is_allowed(sess, "https://a.example/x")[0] is True

    def test_result_is_cached_per_host(self, fake_session):
        """同一域名第二次询问不能再发请求 —— 采集几百个页面时这是性能关键。"""
        sess = fake_session({"/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /\n")})

        net.is_allowed(sess, "https://a.example/1")
        net.is_allowed(sess, "https://a.example/2")
        net.is_allowed(sess, "https://a.example/3")

        assert len(sess.calls) == 1

    def test_cache_is_keyed_by_host_not_url(self, fake_session):
        sess = fake_session({"/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /\n")})

        net.is_allowed(sess, "https://a.example/x")
        net.is_allowed(sess, "https://b.example/x")   # 不同域名要重新取

        assert len(sess.calls) == 2

    def test_query_parameter_rules_are_judged_conservatively(self, fake_session):
        """历史原因：标准库会把 URL 的 query 丢掉再匹配，`Disallow: /*?*` 这类规则会失效。

        项目的对策是：robots 里只要存在带 ? 的规则，就**先**保守拒绝带参数的 URL，
        不依赖标准库版本 —— 旧版会误判成允许（走保守分支），3.13.18 起已能正确匹配
        （标准库自己就判禁止）；两种情况的结论都是拒绝，文案统一由保守分支给出。
        这是防止"技术上抓到了、道义上越界"的关键判断，必须有用例守着。
        """
        robots = "User-agent: *\nDisallow: /*?*\n"
        sess = fake_session({"/robots.txt": FakeResponse(200, robots)})

        allowed, reason = net.is_allowed(sess, "https://a.example/list?page=2")

        assert allowed is False
        assert "?" in reason

    def test_plain_url_allowed_even_with_query_rules(self, fake_session):
        robots = "User-agent: *\nDisallow: /*?*\n"
        sess = fake_session({"/robots.txt": FakeResponse(200, robots)})

        assert net.is_allowed(sess, "https://a.example/list")[0] is True

    def test_robots_url_uses_origin_only(self):
        assert net._robots_url("https://A.Example:8443/x/y?z=1#f") == "https://a.example:8443/robots.txt"

    def test_has_query_rule_detector(self):
        assert net._has_query_rule("Disallow: /*?*\n") is True
        assert net._has_query_rule("Disallow: /private\n") is False
        assert net._has_query_rule("# Disallow: /*?*\n") is False
