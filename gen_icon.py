# -*- coding: utf-8 -*-
"""生成 Anti-antipaste 应用图标：低饱和渐变圆角方块 + 键盘键帽阵列。
4 倍超采样绘制再缩小，保证边缘平滑。"""
from PIL import Image, ImageDraw

SS = 4  # 超采样倍数
BASE = 256


def lerp(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def make_icon(size=BASE):
    u = (size * SS) / 256.0
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 背景：低饱和灰蓝 -> 灰紫 竖向渐变，圆角方块
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    c1, c2 = (107, 122, 154), (137, 131, 168)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(c1, c2, y / (S - 1)) + (255,))
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(56 * u), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)

    def key(x, y, w, h, fill):
        d.rounded_rectangle([x, y, x + w, y + h], radius=int(9 * u), fill=fill)
        d.rounded_rectangle([x, y + h - 5 * u, x + w, y + h],
                            radius=int(9 * u), fill=(0, 0, 0, 18))

    soft_white = (240, 241, 244, 225)
    sand = (216, 192, 138, 255)  # 低饱和沙色高亮键

    kw, kh, gap = 44 * u, 36 * u, 8 * u
    x0 = 30 * u
    y0 = 54 * u
    for r in range(3):
        y = y0 + r * (kh + gap)
        for c in range(4):
            x = x0 + c * (kw + gap)
            key(x, y, kw, kh, sand if (r == 1 and c == 1) else soft_white)
    space_w = 120 * u
    key((S - space_w) / 2, y0 + 3 * (kh + gap), space_w, kh, soft_white)

    # 高亮键上的输入光标
    cx = x0 + 1 * (kw + gap) + kw / 2
    cy = y0 + 1 * (kh + gap) + kh / 2
    d.line([(cx, cy - 9 * u), (cx, cy + 9 * u)], fill=(70, 70, 78, 255),
           width=max(2, int(3 * u)))

    return img.resize((size, size), Image.LANCZOS)


def main():
    icon = make_icon()
    icon.save("icon.png")
    icon.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                 (64, 64), (128, 128), (256, 256)])
    print("icon.ico / icon.png 生成完成")


if __name__ == "__main__":
    main()
