# -*- coding: utf-8 -*-
"""把带透明通道的 PNG/BMP 合成到纯色背景上，检查透明边缘（黑底/浅底两版）。

透明立绘直接看容易误判边缘：各存一张灰底和一张白底预览，
重点检查发梢、武器尖端有没有白边或黑边。

用法：
  python make_preview.py 输入.png [--out 输出目录]
"""
import argparse
import os

from PIL import Image

BACKGROUNDS = {
    'gray': (70, 70, 70, 255),
    'white': (255, 255, 255, 255),
    'black': (0, 0, 0, 255),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='RGBA 图（PNG 或本工具输出的 BMP）')
    ap.add_argument('--out', help='输出目录（默认：输入旁的 <输入名>_preview/）')
    args = ap.parse_args()

    stem = os.path.splitext(os.path.basename(args.input))[0]
    out_dir = args.out if args.out else os.path.join(os.path.dirname(os.path.abspath(args.input)), stem + '_preview')
    os.makedirs(out_dir, exist_ok=True)

    im = Image.open(args.input).convert('RGBA')
    for name, color in BACKGROUNDS.items():
        bg = Image.new('RGBA', im.size, color)
        bg.alpha_composite(im)
        dst = os.path.join(out_dir, '%s_on_%s.png' % (stem, name))
        bg.convert('RGB').save(dst)
        print(dst, im.size)


if __name__ == '__main__':
    main()
