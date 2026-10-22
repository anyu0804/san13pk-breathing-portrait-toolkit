# -*- coding: utf-8 -*-
"""按透明度轮廓自动建议呼吸图的胸线/腿线位置。

原理：对逐行非透明像素计数并平滑，在躯干范围内找"最窄行"作胸线
（约身体 38%~52%），在其下方较窄范围内找腿线（约 62%~80%）。
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
    if len(ys) == 0:
        raise SystemExit('图中没有可见主体（非透明像素过少）: ' + path)
    top, bot = ys[0], ys[-1]
    return a, rows, sm, top, bot


def pick(sm, top, bot):
    H = bot - top
    # 胸线：躯干最窄点，范围 38%-52%
    lo, hi = top + 0.38 * H, top + 0.52 * H
    seg = sm[int(lo):int(hi) + 1]
    chest = int(lo) + int(np.argmin(seg))
    # 腿线：范围 62%-78%，且必须低于胸线
    lo2, hi2 = max(int(chest + 40), int(top + 0.62 * H)), top + 0.80 * H
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
        print('  胸线附近宽度:', [int(sm[y]) for y in range(chest - 8, chest + 9, 4)])
        print('  腿线附近宽度:', [int(sm[y]) for y in range(leg - 8, leg + 9, 4)])

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        print('saved ' + args.json_out)


if __name__ == '__main__':
    main()
