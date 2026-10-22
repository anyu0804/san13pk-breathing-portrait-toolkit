# -*- coding: utf-8 -*-
"""生成一张合成的 1024x1024 测试立绘，用于零素材跑通整套流程。

人形轮廓：头、颈、躯干（腰部收窄）、裙摆、双腿——保证
pick_lines.py 能在轮廓上找到合理的胸线/腿线。仅作管线测试用，
没有任何美术价值 :)

用法：
  python make_sample_portrait.py [--out sample_portrait.png]
然后：
  python ../scripts/pick_lines.py sample_portrait.png --json lines.json
  python ../scripts/generate_breathing.py sample_portrait.png --lines lines.json
  python ../scripts/verify_and_gif.py --prefix sample_portrait --dir sample_portrait_breathing --chest-line <建议值>
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw


def make_portrait(size=1024):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    cx = size // 2

    # 头（椭圆）
    dr.ellipse([cx - 110, 70, cx + 110, 310], fill=(232, 190, 160, 255))
    # 颈
    dr.rectangle([cx - 45, 290, cx + 45, 360], fill=(220, 175, 145, 255))
    # 躯干：肩宽 -> 腰窄 -> 裙摆展开（多段梯形拼出曲线）
    torso = [
        # (y0, y1, 半宽0, 半宽1, 颜色)
        (340, 430, 175, 150, (94, 122, 178, 255)),   # 上衣
        (430, 540, 150, 105, (94, 122, 178, 255)),   # 收腰
        (540, 660, 105, 200, (150, 62, 84, 255)),    # 裙摆展开
        (660, 790, 200, 215, (150, 62, 84, 255)),    # 裙摆
    ]
    for y0, y1, w0, w1, color in torso:
        dr.polygon([(cx - w0, y0), (cx + w0, y0), (cx + w1, y1), (cx - w1, y1)], fill=color)
    # 双腿（裙摆以下两条竖矩形，中间留缝 -> 轮廓收窄，方便定位腿线）
    for dx in (-95, 35):
        dr.rectangle([cx + dx, 790, cx + dx + 60, 1023], fill=(52, 58, 76, 255))
    # 手臂（两侧自然下垂）
    for side in (-1, 1):
        x0 = cx + side * 185 - (0 if side < 0 else 26)
        dr.polygon([(x0, 350), (x0 + 26, 350), (cx + side * 150, 700), (cx + side * 118, 700)],
                   fill=(84, 108, 158, 255))
    return img


def main():
    ap = argparse.ArgumentParser(description='生成合成测试立绘')
    ap.add_argument('--out', default='sample_portrait.png')
    args = ap.parse_args()
    img = make_portrait()
    img.save(args.out)
    print('saved %s (%dx%d)' % (args.out, img.size[0], img.size[1]))


if __name__ == '__main__':
    main()
