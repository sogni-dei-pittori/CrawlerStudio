"""pytest 共享夹具。

原则：单元测试不联网、不读用户的 data/ 目录。
所有涉及磁盘的用例都在 tmp_path 里造一份「迷你仓库」，
再用 monkeypatch 把模块里的路径常量指过去。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 tests/ 在任何工作目录下都能 import 到项目包
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------- 假响应对象
class FakeResponse:
    """最小化的 requests.Response 替身，够 utils.net 用就行。"""

    def __init__(self, status_code: int = 200, text: str = "", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def json(self):
        if self._json is None:
            raise ValueError("响应不是 JSON")
        return self._json


class FakeSession:
    """按 URL 关键字返回预设响应的假 session，并记录被请求过的 URL。

    用法：
        sess = FakeSession({"robots.txt": FakeResponse(404)})
    任何未匹配的 URL 都会抛 AssertionError —— 这样「意外的网络请求」
    会直接让测试失败，而不是悄悄走真网络。
    """

    def __init__(self, routes: dict[str, FakeResponse] | None = None):
        self.routes = routes or {}
        self.calls: list[str] = []
        self.headers: dict[str, str] = {}
        self.encoding = "utf-8"

    def get(self, url, **kwargs):
        self.calls.append(url)
        for needle, response in self.routes.items():
            if needle in url:
                return response
        raise AssertionError(f"测试里出现了未预设的网络请求：{url}")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def fake_session():
    """返回一个工厂函数，方便每个用例自己定义路由表。"""
    return FakeSession


@pytest.fixture(autouse=True)
def _clear_robots_cache():
    """utils.net 的 robots 缓存是模块级全局变量，用例之间必须隔离，
    否则第 2 个用例会命中第 1 个用例写进去的缓存，测不到真实逻辑。"""
    from utils import net

    net._ROBOTS_CACHE.clear()
    yield
    net._ROBOTS_CACHE.clear()


# ---------------------------------------------------------------- 迷你仓库
def make_snapshot(data_root: Path, domain: str, stamp: str, filename: str, csv_text: str) -> Path:
    """在 data_root 下造一个快照目录 + 一个 CSV 文件。"""
    snap = data_root / domain / stamp
    snap.mkdir(parents=True, exist_ok=True)
    (snap / filename).write_text(csv_text, encoding="utf-8-sig")
    return snap


@pytest.fixture
def mini_repo(tmp_path, monkeypatch):
    """一份只含两个快照的迷你数据仓库，并把 warehouse 的 DATA_ROOT 指过去。"""
    from warehouse import boards

    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(boards, "DATA_ROOT", data_root)

    make_snapshot(
        data_root, "top.baidu.com", "2026-09-01_08-00", "board.csv",
        "rank,title,url,source,board,snapshot,score,category,tag\n"
        "1,话题甲,https://a.example/1,baidu,realtime,2026-09-01_08-00,,热搜,热搜\n"
        "2,话题乙,https://a.example/2,baidu,realtime,2026-09-01_08-00,,热搜,热搜\n",
    )
    make_snapshot(
        data_root, "top.baidu.com", "2026-09-02_08-00", "board.csv",
        "rank,title,url,source,board,snapshot,score,category,tag\n"
        "1,话题乙,https://a.example/2,baidu,realtime,2026-09-02_08-00,,热搜,热搜\n"
        "2,话题丙,https://a.example/3,baidu,realtime,2026-09-02_08-00,,热搜,热搜\n",
    )
    return data_root
