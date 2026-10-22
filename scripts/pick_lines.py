# -*- coding: utf-8 -*-
"""按透明度轮廓自动建议呼吸图的胸线/腿线位置。

原理：对逐行非透明像素计数并平滑，在躯干范围内找"最窄行"作胸线
（约身体 20%~35%，颈到上胸候选区），找腿线（约 62%~80%）。
建议值仅供起步，务必对照 <prefix>_lines_preview.png 人工确认。

用法：
  python pick_lines.py 输入1.png [输入2.png ...]
  python pick_lines.py 输入.png --json lines.json     # 供 generate_breathing.py --lines 使用
"""
import argparse
import json
import os

import numpy as np
from PIL import Image


def row_profile(path):
    im = Image.open(path).convert('RGBA')
    a = np.array(im.getchannel('A'))
    rows = (a > 40).sum(axis=1).astype(float)
    # 平滑
    k = np.ones(15) / 15
    sm = np.convolve(rows, k, mode='same')
    ys = np.where(rows > 5)[0]
    if len(ys) < 2:
        raise SystemExit('图中可见主体至少需要两行: ' + path)
    top, bot = ys[0], ys[-1]
    return a, rows, sm, top, bot


def pick(sm, top, bot):
    H = bot - top
    # 颈到上胸的候选区；不具备人体部位识别能力
    lo, hi = top + 0.20 * H, top + 0.35 * H
    seg = sm[int(lo):int(hi) + 1]
    chest = int(lo) + int(np.argmin(seg))
    # 腿线：范围 62%-80%；不用固定 40px 间距，短主体也有非空区间
    lo2, hi2 = max(chest + 1, int(top + 0.62 * H)), max(chest + 1, int(top + 0.80 * H))
    seg2 = sm[int(lo2):int(hi2) + 1]
    leg = int(lo2) + int(np.argmin(seg2))
    return chest, leg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='一张或多张 1024x1024 RGBA PNG')
    ap.add_argument('--json', dest='json_out', help='把建议值写入该 JSON（键=文件名主干）')
    args = ap.parse_args()

    cfg = {}
    for path in args.inputs:
        stem = os.path.splitext(os.path.basename(path))[0]
        a, rows, sm, top, bot = row_profile(path)
        chest, leg = pick(sm, top, bot)
        cfg[stem] = {'src': os.path.basename(path), 'chest_line': int(chest), 'leg_line': int(leg),
                     'body_top': int(top), 'body_bottom': int(bot)}
        print('%s: 身体 y[%d..%d] 胸线 y=%d (%.0f%%) 腿线 y=%d (%.0f%%)' % (
            stem, top, bot, chest, 100 * (chest - top) / (bot - top), leg, 100 * (leg - top) / (bot - top)))
        print('  胸线附近宽度:', [int(sm[y]) for y in range(max(0, chest - 8), min(len(sm), chest + 9), 4)])
        print('  腿线附近宽度:', [int(sm[y]) for y in range(max(0, leg - 8), min(len(sm), leg + 9), 4)])

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        print('saved ' + args.json_out)


if __name__ == '__main__':
    main()
