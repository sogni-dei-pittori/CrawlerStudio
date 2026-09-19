"""生成 assets/app.ico（托盘图标 + 窗口图标 + 打包时的 --icon）。

为什么要自己画一个：
  1. 托盘图标是必填的，没图标托盘上就是一块空白，点不着；
  2. 打包成 exe 时，没有图标和版本信息的自研程序更容易被杀软判成可疑（见 README 打包那节）。
用 PIL 现画，不用去找素材图。跑法：python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "assets" / "app.ico"
SIZE = 256
BG = (32, 96, 176, 255)          # 深蓝底
FG = (255, 255, 255, 255)        # 白字


def load_font(size):
    """找个能画中文的字体；都没有就返回 None（退化成画几何图形）。"""
    for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "arialbd.ttf", "arial.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return None


def main() -> int:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([6, 6, SIZE - 6, SIZE - 6], radius=52, fill=BG)

    font = load_font(150)
    if font:
        draw.text((SIZE / 2, SIZE / 2), "爬", font=font, fill=FG, anchor="mm")
    else:                                        # 没有中文字体就画个"网"字样的几何图形
        draw.ellipse([70, 70, 186, 186], outline=FG, width=16)
        draw.line([128, 70, 128, 186], fill=FG, width=12)
        draw.line([70, 128, 186, 128], fill=FG, width=12)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"已生成 {OUT}（{OUT.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
