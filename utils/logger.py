import logging
from datetime import datetime
from utils.paths import BASE_DIR

LOG_DIR = BASE_DIR / "logs"

def get_logger(name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)               # 同名多次调用 → 返回同一个 logger

    if logger.handlers:
        return logger                              #    （防止重复 addHandler → 日志打两遍）

    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", # 时间 / 级别 / 消息（占位符，别改）
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = LOG_DIR / f"{name}-{datetime.now():%Y-%m-%d}.log"

    fh = logging.FileHandler(log_path, encoding="utf-8")
    sh = logging.StreamHandler()                   # 控制台

    for h in (fh, sh):                             # 两个渠道用同一套格式
        h.setFormatter(fmt)
        logger.addHandler(h)

    return logger