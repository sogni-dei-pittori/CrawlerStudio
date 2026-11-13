"""桌面端入口：URL 采集 / 站点采集 / 数据概况 / 资源管理 / 筛选看板。

跑法：python main.py （在项目根目录）

这个文件只做三件事：解析启动参数 → 起界面或起子任务 → 兜住顶层异常。
界面本体在 gui/main_window.py，打包相关逻辑在 gui/launcher.py。

支持的命令行形式：
    python main.py                 # 正常启动界面
    python main.py --minimized     # 开机自启：启动即收进托盘
    python main.py --probe         # 打印打包环境诊断信息
    CrawlerStudio.exe --task 模块名 [--silent] [参数...]
                                   # 打包后 exe 当解释器跑子任务
"""
import logging
import sys

from gui.launcher import hide_console, probe, run_task

logger = logging.getLogger(__name__)

USAGE = """用法：
  python main.py                启动图形界面
  python main.py --minimized    启动即最小化到托盘
  python main.py --probe        打印运行环境诊断
  main.exe --task <模块> [-s]   以子进程方式运行某个模块（打包后用）
"""


def parse_mode(argv: list[str]) -> tuple[str, list[str]]:
    """把 argv 解析成 (模式, 剩余参数)。

    返回的模式只有四种：probe / task / gui。
    task 模式下剩余参数是 [模块名, *模块参数]。
    """
    args = argv[1:]
    if args and args[0] == "--probe":
        return "probe", []

    if len(args) >= 2 and args[0] == "--task":
        rest = args[2:]
        # --silent 是定时任务专用参数，属于调度器而不属于被调模块，吃掉它
        return "task", [args[1], *[a for a in rest if a != "--silent"]]

    return "gui", args


def run_gui(argv: list[str]) -> int:
    """建 Qt 应用并进事件循环。延迟 import：--task 模式不该付 Qt 的启动开销（约 1 秒）。"""
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from gui.main_window import MainWindow

    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)  # ★ 关窗口只是收进托盘，程序别退
    win = MainWindow()
    if "--minimized" in argv:  # 开机自启用：启动就躲进托盘
        win.hide()
    else:
        win.show()
    if not QSystemTrayIcon.isSystemTrayAvailable():  # 没有托盘的机器（少见）必须给窗口
        win.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """真正的入口。返回退出码 —— 便于被 --task 方式调用与测试。"""
    argv = list(sys.argv if argv is None else argv)
    mode, rest = parse_mode(argv)

    if mode == "probe":
        probe()
        return 0

    if mode == "task":
        # ★ 无条件藏黑窗（不只是 --silent）：界面调起来的子任务也不该弹黑窗。
        #   hide_console() 内部会判断"这个控制台是不是我独占的"，
        #   所以从你自己的终端手敲 --task 时，它不会把你的终端藏掉。
        hide_console()
        return run_task(rest[0], rest[1:])

    hide_console()  # ★ 先藏黑窗，再建界面
    return run_gui(argv)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                      # 打包后没有控制台，异常必须落盘才看得见
        logger.exception("界面启动失败")
        raise
