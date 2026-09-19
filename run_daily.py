"""
用来定时爬取
"""

import subprocess  # 标准库：用来"启动另一个程序"
import sys  # 标准库：用来知道"当前用的是哪个 python"
from utils.childio import child_env, decode_output
from utils.logger import get_logger
from utils.paths import BASE_DIR
import os
import time

logger = get_logger("run_daily")

TASKS = {
    "baidu": "baidu_api.py",
    "bilibili": "bilibili_rank.py",
    "douban": "douban_boards.py",
    "juejin": "juejin_api.py",
    "toutiao": "toutiao_api.py",
}
FAIL_MARKERS = ["没有获取到数据", "重试用尽仍未拿到数据", "状态码异常"]
LOCK_FILE = BASE_DIR / "logs" / "runner.lock"
LOCK_EXPIRE = 30 * 60  # 秒：锁超过 30 分钟就认为上次异常退出，不再阻塞


def acquire_lock() -> bool:
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


args = [a.lower() for a in sys.argv[1:]]

if not args or "all" in args:
    names = list(TASKS)
else:
    names = [a for a in args if a in TASKS]
    for unknown in [a for a in args if a not in TASKS]:
        logger.warning("忽略未知的站点：%s（可选：%s）", unknown, "/".join(TASKS))
if not names:
    logger.error("没有指定站点，退出")
    sys.exit(1)

logger.info("本次计划采集：%s", names)
logger.info("开始定时采集")

if not acquire_lock():
    sys.exit(1)

faileds = []
try:
    for name in names:
        script_name = TASKS[name]
        script_path = BASE_DIR / script_name
        logger.info("---开始采集：%s---", script_name)
        try:
            if getattr(sys, "frozen", False):                       # ★ 打包后 exe 自己当解释器
                cmd = [sys.executable, "--task", script_name[:-3]]  # 去掉 .py 就是模块名
            else:
                cmd = [sys.executable, str(script_path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,
                env=child_env(os.environ),      # ★ 尽量让子进程说 utf-8（打包后会失效，见 utils/childio.py）
            )
        except subprocess.TimeoutExpired:
            logger.error("%s 超过十分钟还未完成，跳过", script_name)
            faileds.append(script_name)
            continue
        except Exception as e:
            logger.error("%s 启动失败：%s（跳过）", script_name, e)
            faileds.append(script_name)
            continue

        output = decode_output((result.stdout or b"") + (result.stderr or b""))   # ★ 按实际字节解
        for line in output.strip().splitlines():
            logger.info("    | %s", line)

        hit = [m for m in FAIL_MARKERS if m in output]

        if result.returncode != 0:
            logger.error("---%s 失败：退出码 %s---", script_name, result.returncode)
            faileds.append(script_name)
        elif hit:
            logger.error("---%s 失败：输出里出现 %s---", script_name, hit)
            faileds.append(script_name)
        else:
            logger.info("---%s 采集完成---", script_name)

finally:
    release_lock()

# ---- 采集完顺手把报告也生成出来：第二天打开看板就是新的 ----
# 就算上面有站点失败，报告也照跑（仓库里有多少数据就分析多少）
logger.info("---开始生成报告---")
if getattr(sys, "frozen", False):
    report_cmd = [sys.executable, "--task", "analysis.report"]      # 打包后：exe 自己当解释器
else:
    report_cmd = [sys.executable, "-m", "analysis.report"]          # 开发时：python -m analysis.report
try:
    result = subprocess.run(
        report_cmd,
        capture_output=True,
        timeout=600,
        env=child_env(os.environ),
    )
    for line in decode_output((result.stdout or b"") + (result.stderr or b"")).strip().splitlines():
        logger.info("    | %s", line)
    if result.returncode != 0:
        logger.error("---报告生成失败：退出码 %s---", result.returncode)
        faileds.append("analysis.report")
    else:
        logger.info("---报告生成完成---")
except subprocess.TimeoutExpired:
    logger.error("报告生成超过十分钟还未完成")
    faileds.append("analysis.report")
except Exception as e:
    logger.error("报告生成启动失败：%s", e)
    faileds.append("analysis.report")

if faileds:
    logger.error("本次有 %d 项失败：%s", len(faileds), faileds)
    sys.exit(1)

logger.info("全部流程结束")
