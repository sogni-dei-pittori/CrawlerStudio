"""warehouse/boards.py：读取层的核心承诺 —— 分散快照合并成一张带派生列的长表。"""
from __future__ import annotations

import pandas as pd
from conftest import make_snapshot


class TestLoadBoards:
    def test_merges_all_snapshots(self, mini_repo):
        from warehouse.boards import load_boards

        df = load_boards()

        # 2 个快照 × 2 行
        assert len(df) == 4
        assert df["snapshot"].nunique() == 2

    def test_adds_derived_columns(self, mini_repo):
        from warehouse.boards import load_boards

        df = load_boards()

        for col in ("dataset", "via", "snapshot_ts", "date"):
            assert col in df.columns
        # date 是从快照目录名派生的字符串列，供看板按天筛选
        assert set(df["date"]) == {"2026-09-01", "2026-09-02"}

    def test_snapshot_ts_is_datetime(self, mini_repo):
        from warehouse.boards import load_boards

        df = load_boards()

        # 断言的是 dtype 而不是具体值：后续 rank_changes 依赖它可排序
        assert pd.api.types.is_datetime64_any_dtype(df["snapshot_ts"])

    def test_rows_ordered_by_time_then_rank(self, mini_repo):
        from warehouse.boards import load_boards

        df = load_boards()

        assert df["snapshot_ts"].is_monotonic_increasing
        first_day = df[df["date"] == "2026-09-01"]
        assert list(first_day["rank"]) == sorted(first_day["rank"])

    def test_since_until_filter(self, mini_repo):
        from warehouse.boards import load_boards

        only_second = load_boards(since="2026-09-02")

        assert set(only_second["date"]) == {"2026-09-02"}
        assert len(only_second) == 2

    def test_filters_accept_strings(self, mini_repo):
        """看板传进来的是字符串，采集层传的是集合 —— 两种都得支持。"""
        from warehouse.boards import load_boards

        assert len(load_boards(sources=["baidu"])) == 4
        assert load_boards(sources=["douban"]).empty

    def test_empty_repo_returns_typed_empty_frame(self, tmp_path, monkeypatch):
        """空仓库不能返回 None —— 上层 app.py 会直接 df['date']，会崩。"""
        from warehouse import boards

        monkeypatch.setattr(boards, "DATA_ROOT", tmp_path / "nowhere")

        df = boards.load_boards()

        assert df.empty
        assert "rank" in df.columns
        assert "date" in df.columns

    def test_ignores_unregistered_domains(self, mini_repo):
        """data/ 下多出来的目录（用户手动放的）不该被当成数据源。"""
        from warehouse.boards import load_boards

        make_snapshot(mini_repo, "random.example", "2026-09-03_08-00", "board.csv",
                      "rank,title,url\n1,野数据,x\n")

        df = load_boards()

        assert "random.example" not in set(df["via"])
        assert len(df) == 4


class TestLoadOne:
    def test_fills_registry_metadata(self, mini_repo):
        """快照 CSV 缺 source/board 时，用登记表 SOURCES 里的值补。"""
        from warehouse.boards import SOURCES, load_one

        entry = SOURCES[0]
        snap = make_snapshot(mini_repo, "coupon.example", "2026-09-05_08-00", "board.csv",
                             "rank,title,url\n1,x,y\n")

        df = load_one(entry, snap)

        assert df.loc[0, "source"] == entry.source
        assert df.loc[0, "dataset"] == entry.dataset

    def test_csv_encoding_with_bom(self, mini_repo):
        """生产环境的 CSV 是 utf-8-sig 写入的，第一列名不能带 BOM 残留。"""
        from warehouse.boards import SOURCES, load_one

        snap = make_snapshot(mini_repo, "coupon.example", "2026-09-06_08-00", "board.csv",
                             "rank,title,url\n1,x,y\n")

        df = load_one(SOURCES[0], snap)

        assert df.columns[0] == "rank"


class TestAudit:
    def test_reports_unregistered_domain(self, mini_repo):
        from warehouse.boards import audit

        make_snapshot(mini_repo, "stray.example", "2026-09-03_08-00", "board.csv",
                      "rank,title\n1,x\n")

        result = audit()

        assert ("stray.example", "board.csv") in result["未登记"]

    def test_reports_empty_snapshot_dir(self, mini_repo):
        """采集失败会留下空目录，体检要能指出来。"""
        from warehouse.boards import audit

        (mini_repo / "top.baidu.com" / "2026-09-04_08-00").mkdir()

        assert any("2026-09-04" in item for item in audit()["空快照"])

    def test_reports_legacy_snapshot_without_source_column(self, mini_repo):
        from warehouse.boards import audit

        make_snapshot(mini_repo, "top.baidu.com", "2026-09-05_08-00", "board.csv",
                      "rank,title,url\n1,x,y\n")

        assert any("2026-09-05" in item for item in audit()["老格式快照"])

    def test_registered_but_absent_is_expected_for_uncollected_sources(self, mini_repo):
        """登记表里 8 个数据源，迷你仓库只采集了 baidu —— 其余出现在这条里是对的。

        这条用例守的是「语义」：这个键只该装 SOURCES 里有、磁盘上没有的组合，
        不该把已存在的数据源也算进去。
        """
        from warehouse.boards import SOURCES, audit

        result = audit()

        registered_missing = set(result["登记了但磁盘没有"])
        assert ("top.baidu.com", "board.csv") not in registered_missing
        assert len(registered_missing) == len({(e.domain, e.filename) for e in SOURCES}) - 1
        # 其余三项在「磁盘与登记表完全对得上」的前提下必须为空
        for key in ("未登记", "空快照", "老格式快照"):
            assert not result[key], (key, result[key])
