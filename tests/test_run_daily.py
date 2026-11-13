"""run_daily.py：编排层的逻辑（参数解析、并发、成败判定、锁）。

不真的启动采集进程 —— subprocess.run 全部替身化。
这条边界的价值在于：编排逻辑出错（比如把失败判成成功）会导致
计划任务静默不报警，比采集脚本本身出错更隐蔽。
"""
from __future__ import annotations

import subprocess
import time

import pytest

import run_daily


class FakeCompleted:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def no_lock(monkeypatch, tmp_path):
    """把锁文件指到临时目录，避免测试碰真实的 logs/runner.lock。"""
    monkeypatch.setattr(run_daily, "LOCK_FILE", tmp_path / "runner.lock")


class TestParseNames:
    def test_no_args_means_all(self):
        assert run_daily.parse_names([]) == list(run_daily.TASKS)

    def test_all_keyword(self):
        assert run_daily.parse_names(["all"]) == list(run_daily.TASKS)

    def test_known_names(self):
        assert run_daily.parse_names(["baidu", "DouBan"]) == ["baidu", "douban"]

    def test_unknown_names_are_ignored_not_fatal(self):
        """计划任务里站点名写错了，不该导致整天不采集。"""
        assert run_daily.parse_names(["baidu", "no-such-site"]) == ["baidu"]

    def test_only_unknown_yields_empty(self):
        assert run_daily.parse_names(["nope"]) == []


class TestBuildCommand:
    def test_dev_mode_uses_python_and_script_path(self, monkeypatch):
        monkeypatch.setattr(run_daily, "is_frozen", lambda: False)
        monkeypatch.setattr(run_daily, "self_exe", lambda: "python.exe")

        cmd = run_daily.build_command("baidu_api.py")

        assert cmd == ["python.exe", str(run_daily.BASE_DIR / "baidu_api.py")]

    def test_frozen_mode_uses_task_flag(self, monkeypatch):
        """打包后 exe 自己当解释器，脚本名要变成模块名。"""
        monkeypatch.setattr(run_daily, "is_frozen", lambda: True)
        monkeypatch.setattr(run_daily, "self_exe", lambda: "CrawlerStudio.exe")

        cmd = run_daily.build_command("baidu_api.py")

        assert cmd == ["CrawlerStudio.exe", "--task", "baidu_api"]


class TestRunSite:
    def test_success(self, monkeypatch):
        monkeypatch.setattr(run_daily.subprocess, "run",
                            lambda *a, **k: FakeCompleted(0, "已保存 CSV".encode()))

        result = run_daily.run_site("baidu", "baidu_api.py")

        assert result.ok is True
        assert result.returncode == 0

    def test_nonzero_exit_is_failure(self, monkeypatch):
        monkeypatch.setattr(run_daily.subprocess, "run", lambda *a, **k: FakeCompleted(1))

        assert run_daily.run_site("baidu", "baidu_api.py").ok is False

    def test_timeout_is_failure_not_exception(self, monkeypatch):
        """超时必须被收敛成结果，否则线程池里抛异常会拖垮整个编排。"""
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)

        monkeypatch.setattr(run_daily.subprocess, "run", boom)

        result = run_daily.run_site("douban", "douban_boards.py")

        assert result.ok is False
        assert "未完成" in result.error

    def test_launch_error_is_failure_not_exception(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("cannot start process")

        monkeypatch.setattr(run_daily.subprocess, "run", boom)

        result = run_daily.run_site("baidu", "baidu_api.py")

        assert result.ok is False
        assert "启动失败" in result.error

    def test_fail_marker_with_zero_exit_is_warning_only(self, monkeypatch):
        """退出码 0 但输出里有「没有获取到数据」：算成功，但必须留警告。

        原版是直接把这种情况判为失败；改成警告是因为退出码才是契约，
        文案匹配太脆。但警告要留着，否则「跑了两小时一条没抓到」
        会被当成正常。
        """
        monkeypatch.setattr(run_daily.subprocess, "run",
                            lambda *a, **k: FakeCompleted(0, "没有获取到数据".encode()))

        result = run_daily.run_site("baidu", "baidu_api.py")

        assert result.ok is True
        assert result.warnings == ["没有获取到数据"]

    def test_records_elapsed_time(self, monkeypatch):
        monkeypatch.setattr(run_daily.subprocess, "run", lambda *a, **k: FakeCompleted(0))

        assert run_daily.run_site("baidu", "baidu_api.py").seconds >= 0


class TestCollect:
    def test_runs_all_requested_sites(self, monkeypatch):
        seen = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd[-1])
            return FakeCompleted(0)

        monkeypatch.setattr(run_daily.subprocess, "run", fake_run)

        results = run_daily.collect(["baidu", "douban"])

        assert len(results) == 2
        assert len(seen) == 2

    def test_results_keep_requested_order(self, monkeypatch):
        """并发跑，但结果按提交顺序返回 —— 日志才稳定可读。"""
        def slow_for_baidu(cmd, **kwargs):
            if "baidu_api.py" in cmd[-1]:
                time.sleep(0.05)
            return FakeCompleted(0)

        monkeypatch.setattr(run_daily.subprocess, "run", slow_for_baidu)

        results = run_daily.collect(["baidu", "douban"])

        assert [r.name for r in results] == ["baidu", "douban"]

    def test_sites_actually_run_concurrently(self, monkeypatch):
        """四个站点各睡 0.15 秒：串行要 0.6 秒，并发应明显更快。"""
        def sleep_then_ok(cmd, **kwargs):
            time.sleep(0.15)
            return FakeCompleted(0)

        monkeypatch.setattr(run_daily.subprocess, "run", sleep_then_ok)

        start = time.perf_counter()
        run_daily.collect(["baidu", "douban", "juejin", "toutiao"])
        elapsed = time.perf_counter() - start

        assert elapsed < 0.45, f"看起来还是串行跑的（{elapsed:.2f}s）"

    def test_one_failure_does_not_sink_the_others(self, monkeypatch):
        def flaky(cmd, **kwargs):
            return FakeCompleted(1 if "douban" in cmd[-1] else 0)

        monkeypatch.setattr(run_daily.subprocess, "run", flaky)

        results = run_daily.collect(["baidu", "douban"])

        assert [r.ok for r in results] == [True, False]


class TestMain:
    def test_all_success_returns_zero(self, monkeypatch, no_lock):
        monkeypatch.setattr(run_daily.subprocess, "run", lambda *a, **k: FakeCompleted(0))

        assert run_daily.main(["baidu"]) == 0

    def test_any_failure_returns_nonzero(self, monkeypatch, no_lock):
        """计划任务靠退出码判断要不要报警，这个返回值不能丢。"""
        def fail_first(cmd, **kwargs):
            return FakeCompleted(1 if "baidu_api.py" in cmd[-1] else 0)

        monkeypatch.setattr(run_daily.subprocess, "run", fail_first)

        assert run_daily.main(["baidu", "douban"]) == 1

    def test_report_failure_also_returns_nonzero(self, monkeypatch, no_lock):
        def report_fails(cmd, **kwargs):
            return FakeCompleted(1 if "analysis.report" in " ".join(cmd) else 0)

        monkeypatch.setattr(run_daily.subprocess, "run", report_fails)

        assert run_daily.main(["baidu"]) == 1

    def test_report_runs_even_when_collection_failed(self, monkeypatch, no_lock):
        """采集全挂了也要出报告 —— 仓库里已有的数据照样能分析。"""
        calls = []

        def record(cmd, **kwargs):
            calls.append(" ".join(cmd))
            return FakeCompleted(1 if "baidu_api.py" in cmd[-1] else 0)

        monkeypatch.setattr(run_daily.subprocess, "run", record)

        run_daily.main(["baidu"])

        assert any("analysis.report" in c for c in calls)

    def test_unknown_site_only_returns_nonzero(self, no_lock):
        """只给了未知站点 → 没有可采集项 → 非零退出（而不是静默成功）。"""
        assert run_daily.main(["nope"]) == 1

    def test_lock_blocks_concurrent_run(self, no_lock, monkeypatch):
        """上一个任务还在跑时（锁未过期），本次必须直接退出。"""
        monkeypatch.setattr(run_daily.subprocess, "run", lambda *a, **k: FakeCompleted(0))
        run_daily.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        run_daily.LOCK_FILE.write_text("now", encoding="utf-8")   # 刚写入 → 未过期

        assert run_daily.main(["baidu"]) == 1

    def test_lock_released_after_run(self, monkeypatch, no_lock):
        monkeypatch.setattr(run_daily.subprocess, "run", lambda *a, **k: FakeCompleted(0))

        run_daily.main(["baidu"])

        assert not run_daily.LOCK_FILE.exists()

    def test_lock_released_even_if_collection_raises(self, monkeypatch, no_lock):
        """采集中途抛异常也必须放锁，否则下次定时任务会被自己卡住 30 分钟。"""
        def explode(*a, **k):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(run_daily, "collect", explode)

        with pytest.raises(RuntimeError):
            run_daily.main(["baidu"])

        assert not run_daily.LOCK_FILE.exists()
