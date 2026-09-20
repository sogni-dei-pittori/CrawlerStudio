"""抽取层的公共件：清洗、编码探测、字数统计。纯函数，不联网，不写盘"""
from pathlib import Path
import re

# 试编码的顺序，带BOM的tuf--sig放在最前面，然后utf-8，最后gbk
ENCODINGS = ("utf-8-sig", "utf-8", "gbk")
# 不可见控制字符：PDF抽出来的文本特别多（\x1d \x0c \x00 …）
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 连续空白（含全角空格）压成一个普通空格
SPACE_RE = re.compile(r"[ \t\u3000\xa0]+")


def read_text_any(path) -> tuple[str, str]:
    """
    按顺序试编码读文本，返回（内容，实际使用的编码）
    都失败时使用utf-8+errors="replace"兜底
    """
    raw = Path(path).read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    for enc in ENCODINGS:
        try:
            name = "utf-8(BOM)" if (enc == "utf-8-sig" and has_bom) else enc
            return raw.decode(enc), name
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def clean_text(text: str) -> str:
    """清洗一段文本，去控制字符、压空白、去首尾空白"""
    text = CTRL_RE.sub("", text or "")
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def count_chars(text: str, count_punct: bool = True) -> int:
    """去空白后的字数，count_punct=False时只数“汉字+字母+数字”"""
    t = re.sub(r"\s+", "", text or "")
    if count_punct:
        return len(t)
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", t))
