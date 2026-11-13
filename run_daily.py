"""定时采集编排：并发跑各站点采集，然后生成报告。

用法：
    python run_daily.py                # 采集全部站点，完成后自动生成报告
    python run_daily.py baidu douban   # 只采集指定站点
    CrawlerStudio.exe --task run_daily # 打包后由主程序调起

相对原版的三处改动（行为向后兼容）：

1. **并发采集**。五个站点彼此独立，原来串行跑，总耗时是各自之和
   （豆瓣 250 条要翻 10 页，最慢）。现在用线程池并行，墙钟时间由
   最慢的那个站点决定。各站点仍是**独立子进程**，所以一个站点的
   崩溃/内存泄漏不会污染其它站点。

2. **成败判定以退出码为准，字符串匹配作为补充**。采集脚本本来就有
   0/1 的约定，所以先看退出码；但有些情况脚本会 return 0 却没有数据
   （robots 禁止、接口 success=false），这时靠 FAIL_MARKERS 把它抓出来，
   仍然判为失败 —— 「跑完了但一条没抓到」绝不能被当成成功，
   否则计划任务永远不会报警。

3. **结构化摘要**。结束时输出一份各站点耗时/状态的小结，并返回
   非零退出码 —— 计划任务（Windows Task Scheduler）能据此报警。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from utils.childio import child_env, decode_output
from utils.logger import get_logger
from utils.paths import BASE_DIR, is_frozen, self_exe

logger = get_logger("run_daily")

TASKS = {
    "baidu": "baidu_api.py",
    "bilibili": "bilibili_rank.py",
    "douban": "douban_boards.py",
    "juejin": "juejin_api.py",
    "toutiao": "toutiao_api.py",
}

# 这些字样说明「跑完了但没拿到数据」—— 退出码是 0，结果却不可用。
# 保留这个判断是因为采集脚本在「robots 禁止」「接口返回 success=false」时
# 确实会 return 0。但只作为**警告**，不再单独决定成败。
FAIL_MARKERS = ["没有获取到数据", "重试用尽仍未拿到数据", "状态码异常"]

LOCK_FILE = BASE_DIR / "logs" / "runner.lock"
LOCK_EXPIRE = 30 * 60          # 秒：锁超过 30 分钟认为上次异常退出
SITE_TIMEOUT = 600             # 秒：单个站点的上限
REPORT_TIMEOUT = 600
MAX_WORKERS = 5                # 最多同时跑几个站点（= 站点数，将来加了站点也不用改）


@dataclass
class SiteResult:
    """一个站点的执行结果，用于最后的小结表。"""

    name: str
    script: str
    ok: bool
    seconds: float
    returncode: int | None = None
    error: str = ""
    warnings: list[str] | None = None

    def summary_line(self) -> str:
        status = "成功" if self.ok else "失败"
        extra = f"（{self.error}）" if self.error else ""
        warn = f" 警告：{'、'.join(self.warnings)}" if self.warnings else ""
        return f"  {self.name:<9s} {status:<4s} {self.seconds:6.1f}s{extra}{warn}"


# ---------------------------------------------------------------- 进程锁
def acquire_lock() -> bool:
    """防止两个定时任务同时跑（比如计划任务和手动点了一下界面）。"""
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < LOCK_EXPIRE:
            logger.warning("上一次采集还在进行（%.0f 秒前开始），本次跳过", age)
            return False
        logger.warning("发现过期锁（%.0f 分钟前），忽略并继续", age / 60)

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(time.time()), encoding="utf-8")
    return True


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------- 子进程
def build_command(script_name: str) -> list[str]:
    """打包后由 exe 自己当解释器，开发时用当前 python。"""
    if is_frozen():
        return [str(self_exe()), "--task", script_name[:-3]]   # 去掉 .py 就是模块名
    return [str(self_exe()), str(BASE_DIR / script_name)]


def run_site(name: str, script_name: str) -> SiteResult:
    """跑一个站点。任何异常都收敛成 SiteResult，绝不让线程池里的异常冒出来。"""
    started = time.perf_counter()
    try:
        result = subprocess.run(
            build_command(script_name),
            capture_output=True,
            timeout=SITE_TIMEOUT,
            env=child_env(os.environ),      # 见 utils/childio.py：让子进程说 utf-8
        )
    except subprocess.TimeoutExpired:
        return SiteResult(name, script_name, False, time.perf_counter() - started,
                          error=f"超过 {SITE_TIMEOUT // 60} 分钟未完成")
    except Exception as exc:                # 启动失败（文件被占用 / 权限等）
        return SiteResult(name, script_name, False, time.perf_counter() - started,
                          error=f"启动失败：{type(exc).__name__}: {exc}")

    elapsed = time.perf_counter() - started
    output = decode_output((result.stdout or b"") + (result.stderr or b""))
    for line in output.strip().splitlines():
        logger.info("    | [%s] %s", name, line)

    hits = [marker for marker in FAIL_MARKERS if marker in output]
    if result.returncode != 0:
        return SiteResult(name, script_name, False, elapsed,
                          returncode=result.returncode,
                          error=f"退出码 {result.returncode}", warnings=hits)

    # 退出码 0 但输出里出现「没有获取到数据」这类字样：
    # 采集脚本在「robots 禁止」「接口返回 success=false」时确实会 return 0，
    # 但结果是不可用的。这种情况必须让整次任务**失败**（非零退出），
    # 否则计划任务会把「一条没抓到」当成成功，静默丢数据。
    if hits:
        logger.error("[%s] 退出码为 0，但输出里出现：%s（按失败处理）", name, hits)
        return SiteResult(name, script_name, False, elapsed, returncode=0,
                          error="未取到数据：" + "、".join(hits), warnings=hits)
    return SiteResult(name, script_name, True, elapsed, returncode=0, warnings=[])


def collect(names: list[str]) -> list[SiteResult]:
    """并发跑指定站点，返回按 TASKS 顺序排列的结果（日志才不会乱序得看不懂）。"""
    logger.info("开始采集，共 %d 个站点（并发）：%s", len(names), names)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(names)),
                            thread_name_prefix="site") as pool:
        futures = {name: pool.submit(run_site, name, TASKS[name]) for name in names}
        results = []
        for name in names:                  # 按提交顺序收集，保证日志顺序稳定
            result = futures[name].result()
            results.append(result)
            logger.info("---%s%s---", TASKS[name], "采集完成" if result.ok else "失败")
    return results


def run_report() -> tuple[bool, str]:
    """生成报告。采集失败也照跑 —— 仓库里有多少数据就分析多少。"""
    logger.info("---开始生成报告---")
    if is_frozen():
        cmd = [str(self_exe()), "--task", "analysis.report"]
    else:
        cmd = [str(self_exe()), "-m", "analysis.report"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=REPORT_TIMEOUT,
                                env=child_env(os.environ))
    except subprocess.TimeoutExpired:
        return False, f"超过 {REPORT_TIMEOUT // 60} 分钟未完成"
    except Exception as exc:
        return False, f"启动失败：{type(exc).__name__}: {exc}"

    for line in decode_output((result.stdout or b"") + (result.stderr or b"")).strip().splitlines():
        logger.info("    | %s", line)
    if result.returncode != 0:
        return False, f"退出码 {result.returncode}"
    return True, ""


# ---------------------------------------------------------------- 命令行
def parse_names(argv: list[str]) -> list[str]:
    """解析站点参数。不认识的名字只警告不中断 —— 计划任务里写错了不该整天不跑。"""
    args = [a.lower() for a in argv]
    if not args or "all" in args:
        return list(TASKS)

    names = [a for a in args if a in TASKS]
    for unknown in [a for a in args if a not in TASKS]:
        logger.warning("忽略未知的站点：%s（可选：%s）", unknown, "/".join(TASKS))
    return names


def main(argv: list[str] | None = None) -> int:
    """返回 0 = 全部成功；1 = 有失败项（计划任务据此报警）。"""
    names = parse_names(argv if argv is not None else sys.argv[1:])
    if not names:
        logger.error("没有指定站点，退出")
        return 1

    start = time.perf_counter()
    logger.info("本次计划采集：%s", names)

    if not acquire_lock():
        return 1
    try:
        results = collect(names)
    finally:
        release_lock()             # 无论采集怎么炸，锁都必须放掉

    report_start = time.perf_counter()
    report_ok, report_error = run_report()
    report_seconds = time.perf_counter() - report_start

    # ---- 小结 ----
    failed = [r for r in results if not r.ok]
    total = time.perf_counter() - start
    logger.info("---本次采集小结（总耗时 %.1f 秒）---", total)
    for r in results:
        logger.info("%s", r.summary_line())
    logger.info("  报告      %s %6.1fs%s", "成功" if report_ok else "失败",
                report_seconds, f"（{report_error}）" if report_error else "")

    if failed or not report_ok:
        names_failed = [r.name for r in failed] + ([] if report_ok else ["analysis.report"])
        logger.error("本次有 %d 项失败：%s", len(names_failed), names_failed)
        return 1

    logger.info("全部流程结束")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
