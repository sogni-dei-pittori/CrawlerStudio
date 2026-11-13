"""跑外部脚本的工作器：QProcess 天生异步，输出通过信号送出去，界面不会卡。"""
import subprocess

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from utils.childio import decode_output


class ScriptRunner(QObject):
    """跑一个 Python 脚本，实时把 stdout/stderr 发出来，结束时发完成信号。"""

    output = Signal(str)            # 每读到一段输出就发一次
    finished = Signal(int)          # 结束时发退出码
    error = Signal(str)             # 启动失败

    def __init__(self, python_exe: str, script: str, args: list[str] | None = None, cwd: str = "."):
        super().__init__()
        self.python_exe = python_exe
        self.script = script
        self.args = args or []
        self.cwd = cwd
        self.process: QProcess | None = None
        self._running = False       # ★ 用它挡住"上一次还在跑就又启动一次"
        self._stopped = False       # ★ 记录"这次是用户主动停的"，界面上好区分

    def is_running(self) -> bool:
        return self._running

    def was_stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """停掉正在跑的脚本，连它起的子进程一起（否则会留下孤儿进程继续跑）。

        为什么要 taskkill /T：run_daily 自己还会再起 5 个站点脚本，
        只结束它一个的话，那 5 个会变成没人管的孤儿，继续联网抓。
        """
        if not self._running or self.process is None:
            return
        self._stopped = True
        pid = int(self.process.processId() or 0)
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            self.process.kill()

    def start(self) -> None:
        proc = QProcess(self)            # 先拿到局部引用，避免到处写 self.process（可能为 None）
        self.process = proc
        proc.setWorkingDirectory(self.cwd)

        env = QProcessEnvironment.systemEnvironment()      # ★ 让子进程按 UTF-8 输出
        env.insert("PYTHONIOENCODING", "utf-8")            #   打包后这句会被忽略，所以下面
        env.insert("PYTHONUTF8", "1")                      #   还得按实际字节解码（utils/childio.py）
        proc.setProcessEnvironment(env)

        # stdout+stderr 合并，顺序才不乱。
        # 用完整枚举路径：Qt 6 里 QProcess.MergedChannels 只是兼容别名，
        # 类型桩只认 ProcessChannelMode.MergedChannels。写全了就不用 type: ignore ——
        # CI 里不装 PySide6（模块变 Any）时，那条 ignore 反而会变成「多余的 ignore」报错。
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_output)   # ★ 有输出就触发，不阻塞
        proc.finished.connect(self._on_finished)                # ★ 用方法，不用 lambda
        proc.errorOccurred.connect(self._on_error)              # ★ 启动失败也要发信号
        self._running = True
        proc.start(self.python_exe, [self.script, *self.args])

    def _on_output(self) -> None:
        if self.process is None:         # 理论上不会发生，但别让空引用把界面搞崩
            return
        # .data() 返回 bytes/bytearray/memoryview 之一（类型桩的说法），
        # 统一转成 bytes 再交给解码函数
        raw = bytes(self.process.readAllStandardOutput().data())
        self.output.emit(decode_output(raw))                  # ★ 按实际编码解，别写死 utf-8

    def _on_finished(self, code: int, _status) -> None:
        self._running = False
        self.finished.emit(code)

    def _on_error(self, _error) -> None:
        self._running = False
        try:
            message = self.process.errorString() if self.process is not None else "进程未启动"
        except RuntimeError:                 # QProcess 已被回收
            message = "QProcess 已被回收（进程可能已经结束）"
        self.error.emit(message)
