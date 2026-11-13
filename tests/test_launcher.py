"""main.py 的参数分发 + gui/launcher.py 的子任务协议。

这块逻辑只在打包后才真正生效，平时跑界面根本走不到 ——
所以它是最容易「上线才发现坏了」的地方，用用例把协议固定住。

注意：这里只 import main 与 gui.launcher，不 import gui.main_window
（那个模块一 import 就要 Qt 的图形库，在没有图形环境的 CI 上会失败）。
"""
from __future__ import annotations

import sys

import pytest

import main as entry
from gui import launcher


class TestParseMode:
    @pytest.mark.parametrize(
        ("argv", "want_mode", "want_rest"),
        [
            (["main.py"], "gui", []),
            (["main.py", "--minimized"], "gui", ["--minimized"]),
            (["main.py", "--probe"], "probe", []),
            (["exe", "--task", "analysis.report"], "task", ["analysis.report"]),
            (["exe", "--task", "baidu_api", "extra"], "task", ["baidu_api", "extra"]),
        ],
    )
    def test_modes(self, argv, want_mode, want_rest):
        assert entry.parse_mode(argv) == (want_mode, want_rest)

    def test_silent_flag_is_stripped(self):
        """--silent 属于调度器，不该透给被调模块（否则模块会把它当成参数）。"""
        mode, rest = entry.parse_mode(["exe", "--task", "run_daily", "--silent", "baidu"])

        assert mode == "task"
        assert rest == ["run_daily", "baidu"]

    def test_silent_stripped_even_when_only_argument(self):
        _, rest = entry.parse_mode(["exe", "--task", "x", "--silent"])

        assert rest == ["x"]

    def test_task_without_module_falls_back_to_gui(self):
        """`--task` 后面没跟模块名时不该崩，退回启动界面。"""
        assert entry.parse_mode(["exe", "--task"])[0] == "gui"


class TestRunTask:
    def test_calls_module_main_and_returns_its_code(self):
        code = launcher.run_task("analysis.common")

        assert code == 0

    def test_passes_arguments_to_module(self, monkeypatch):
        """模块必须看到自己的参数，而不是 --task 那串。"""
        seen = {}

        def fake_main():
            seen["argv"] = list(sys.argv)
            return 7

        import types
        fake = types.ModuleType("fake_mod")
        fake.main = fake_main
        monkeypatch.setitem(sys.modules, "fake_mod", fake)

        code = launcher.run_task("fake_mod", ["arg1", "arg2"])

        assert code == 7
        # argv[0] 保留真实程序路径（run_daily 要靠它找到自己）
        assert seen["argv"][1:] == ["arg1", "arg2"]
        assert seen["argv"][0] != "fake_mod"

    def test_top_level_module_without_main_succeeds(self, monkeypatch):
        """run_daily 这类「import 即执行」的模块没有 main()，也要算成功。"""
        import types
        monkeypatch.setitem(sys.modules, "run_daily", types.ModuleType("run_daily"))

        assert launcher.run_task("run_daily") == 0

    def test_ordinary_module_without_main_fails_loudly(self, monkeypatch, capsys):
        import types
        monkeypatch.setitem(sys.modules, "noEntry", types.ModuleType("noEntry"))

        code = launcher.run_task("noEntry")

        assert code == 1
        assert "没有 main()" in capsys.readouterr().out

    def test_missing_module_propagates(self):
        """模块名写错时，ImportError 应该冒出来 —— 静默成功比崩溃更难查。"""
        with pytest.raises(ImportError):
            launcher.run_task("definitely_not_a_module")


class TestProbe:
    def test_prints_environment_facts(self, capsys):
        launcher.probe()

        out = capsys.readouterr().out
        for key in ("sys.frozen", "BASE_DIR", "is_frozen()", "self_exe()"):
            assert key in out


class TestMainEntry:
    def test_probe_mode_returns_zero(self, monkeypatch):
        called = []
        monkeypatch.setattr(entry, "probe", lambda: called.append(True))

        assert entry.main(["main.py", "--probe"]) == 0
        assert called == [True]

    def test_task_mode_dispatches_to_run_task(self, monkeypatch):
        captured = {}

        def fake_run_task(module, extra):
            captured["module"] = module
            captured["extra"] = extra
            return 3

        monkeypatch.setattr(entry, "run_task", fake_run_task)
        monkeypatch.setattr(entry, "hide_console", lambda: None)

        code = entry.main(["exe", "--task", "analysis.report", "--silent"])

        assert code == 3
        assert captured == {"module": "analysis.report", "extra": []}

    def test_gui_mode_calls_run_gui(self, monkeypatch):
        """这里替身化 run_gui —— 真起 Qt 事件循环会卡住测试。"""
        captured = {}
        monkeypatch.setattr(entry, "hide_console", lambda: None)
        monkeypatch.setattr(entry, "run_gui", lambda argv: captured.setdefault("argv", argv) and 0)

        entry.main(["main.py", "--minimized"])

        assert captured["argv"] == ["main.py", "--minimized"]
