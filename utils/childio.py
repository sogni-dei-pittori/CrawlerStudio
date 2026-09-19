"""跟子进程打交道的小工具：输出编码 + 子进程环境变量。

为什么需要这个文件：
  打包成 exe 之后，PyInstaller 自己接管了 stdio，**PYTHONIOENCODING=utf-8 会被忽略**
  （2026-09-18 实测：exe --task analysis.common 的 stdout 前几个字节是
   c8 ab b1 ed a3 ba，按 GBK 解出来才是"全表："）。
  开发模式（真 python）下那个环境变量是有效的，打包后就失效了，
  所以不能"约定子进程输出 utf-8"，只能"拿到什么字节就按什么解"。
"""
import subprocess


def child_env(base: dict | None = None) -> dict:
    """准备子进程的环境变量：能让它说 utf-8 的都设上（设不上也没关系，读的时候会兜底）。"""
    env = dict(base or {})
    env["PYTHONIOENCODING"] = "utf-8"      # 开发模式下有效
    env["PYTHONUTF8"] = "1"                # UTF-8 模式，打包后也管用
    return env


def decode_output(raw: bytes) -> str:
    """把子进程的输出字节解成文字。

    整段一起判断，不要逐行猜 —— 逐行猜会把同一段文字解出两种编码，看起来更乱。
    先试 utf-8（开发模式和多数情况），不行就试系统默认的中文编码 gbk(cp936)，
    都不行才用 replace 兜底（至少不会抛异常把采集流程打断）。
    """
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


if __name__ == "__main__":
    # 自检：同样的中文，两种编码的字节都要能解对
    text = "全表： (18439, 30) 中文测试"
    for enc in ("utf-8", "gbk"):
        got = decode_output(text.encode(enc))
        print(f"{enc:5} -> {'OK' if got == text else '不对：' + got}")
    print("空字节 ->", repr(decode_output(b"")))
