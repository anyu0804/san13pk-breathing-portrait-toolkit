# -*- coding: utf-8 -*-
"""三国志13PK 呼吸图生成：把 1024x1024 透明全身立绘切成胸/腰/头三层羽化 BMP。

实验性矩形分层（尚未用原生纹理校准，见 README）：
  chest 胸层 = 胸线到腿线的躯干，上下向外羽化；
  waist 腰层 = 只保留腿线以下（上方羽化过渡），作为静态下层；
  head  头层 = 只保留胸线以上（下方羽化过渡），动画中整体上下小幅移动。

用法：
  python generate_breathing.py 输入.png --chest 465 --leg 658
  python generate_breathing.py 输入.png --lines lines.json        # 用 pick_lines.py 的建议值
  python generate_breathing.py 输入.png --chest 465 --leg 658 --out 输出目录 --prefix 角色ID

输出（均为 32 位 BGRA、无压缩、BI_RGB BMP，1024x1024）：
  <prefix>_chest.bmp / <prefix>_waist.bmp / <prefix>_head.bmp / <prefix>_lines_preview.png
"""
import argparse
import json
import os
import struct

import numpy as np
from PIL import Image

GAME_SIZE = 1024          # 游戏呼吸图纹理画布，宽高必须一致
FEATHER_LEG_DEFAULT = 20  # 腰层上缘羽化像素
FEATHER_CHEST_DEFAULT = 7  # 头层下缘羽化像素


def feather_factor(h, line, feather, keep_below):
    """返回每行的单向线性 alpha 系数，不等同于 PS 高斯羽化。"""
    y = np.arange(h, dtype=float)
    if feather == 0:
        return (y >= line if keep_below else y <= line).astype(float)
    if keep_below:
        # 保留腿线以下；上方羽化
        f = np.ones(h)
        lo = line - feather
        f[y < lo] = 0
        mask = (y >= lo) & (y <= line)
        f[mask] = (y[mask] - lo) / feather
        return f
    else:
        # 保留胸线以上；下方羽化
        f = np.ones(h)
        hi = line + feather
        f[y > hi] = 0
        mask = (y >= line) & (y <= hi)
        f[mask] = 1.0 - (y[mask] - line) / feather
        return f


def save_bmp_alpha(path, rgba):
    """按游戏可读格式写 32 位 BMP：BITMAPINFOHEADER、正高度（自下而上）、BGRA。"""
    h, w = rgba.shape[:2]
    rows = []
    for yy in range(h - 1, -1, -1):
        rows.append(rgba[yy])
    data = np.concatenate(rows).astype(np.uint8)  # RGBA 顺序
    # 转 BGRA
    bgra = data[:, [2, 1, 0, 3]].tobytes()
    filesize = 54 + len(bgra)
    with open(path, 'wb') as f:
        f.write(struct.pack('<2sIHHI', b'BM', filesize, 0, 0, 54))
        f.write(struct.pack('<IiiHHIIiiII', 40, w, h, 1, 32, 0, w * h * 4, 2835, 2835, 0, 0))
        f.write(bgra)


def alpha_apply(rgba, factor):
    out = rgba.copy()
    a = out[:, :, 3].astype(float) * factor[:, None]
    out[:, :, 3] = np.clip(a, 0, 255).astype(np.uint8)
    return out


def split_layers(rgba, chest, leg, feather_chest, feather_leg):
    """共用 RGB，仅分配 alpha；输出为待人工检查的候选层。"""
    h = rgba.shape[0]
    torso = (feather_factor(h, chest, feather_chest, True)
             * feather_factor(h, leg, feather_leg, False))
    return (alpha_apply(rgba, torso),
            alpha_apply(rgba, feather_factor(h, leg, feather_leg, True)),
            alpha_apply(rgba, feather_factor(h, chest, feather_chest, False)))


def resolve_lines(args, stem):
    """--chest/--leg 优先；否则从 --lines JSON 里按文件名主干取建议值。"""
    if args.chest is not None and args.leg is not None:
        return args.chest, args.leg
    if args.lines:
        with open(args.lines, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        key = args.prefix if args.prefix else stem
        if key not in cfg:
            raise SystemExit('lines JSON 中没有 %r 的记录；可用键：%s' % (key, ', '.join(cfg)))
        return int(cfg[key]['chest_line']), int(cfg[key]['leg_line'])
    raise SystemExit('需要 --chest/--leg，或提供 pick_lines.py 生成的 --lines JSON')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='输入 1024x1024 RGBA PNG')
    ap.add_argument('--chest', type=int, help='胸线 y 坐标（头/胸分界）')
    ap.add_argument('--leg', type=int, help='腿线 y 坐标（腰层上界）')
    ap.add_argument('--lines', help='pick_lines.py 输出的 JSON，代替 --chest/--leg')
    ap.add_argument('--out', help='输出目录（默认：输入旁的 <输入名>_breathing/）')
    ap.add_argument('--prefix', help='输出文件名前缀（默认：输入文件名主干）')
    ap.add_argument('--feather-leg', type=int, default=FEATHER_LEG_DEFAULT, help='腰层上缘羽化像素（默认 %d）' % FEATHER_LEG_DEFAULT)
    ap.add_argument('--feather-chest', type=int, default=FEATHER_CHEST_DEFAULT, help='头层下缘羽化像素（默认 %d）' % FEATHER_CHEST_DEFAULT)
    args = ap.parse_args()
    if args.feather_leg < 0 or args.feather_chest < 0:
        ap.error('羽化宽度必须 >= 0；0 表示硬切')

    stem = os.path.splitext(os.path.basename(args.input))[0]
    prefix = args.prefix if args.prefix else stem
    chest, leg = resolve_lines(args, stem)

    im = Image.open(args.input).convert('RGBA')
    rgba = np.array(im)
    h, w = rgba.shape[:2]
    if not (w == GAME_SIZE and h == GAME_SIZE):
        raise SystemExit('输入必须是 %dx%d（当前 %dx%d）：先裁切/缩放立绘再分层' % (GAME_SIZE, GAME_SIZE, w, h))
    if not (0 < chest < leg < h):
        raise SystemExit('线位不合法：需要 0 < 胸线(%d) < 腿线(%d) < %d' % (chest, leg, h))

    out_dir = args.out if args.out else os.path.join(os.path.dirname(os.path.abspath(args.input)), stem + '_breathing')
    os.makedirs(out_dir, exist_ok=True)

    chest_img, waist_img, head_img = split_layers(
        rgba, chest, leg, args.feather_chest, args.feather_leg)

    save_bmp_alpha(os.path.join(out_dir, prefix + '_chest.bmp'), chest_img)
    save_bmp_alpha(os.path.join(out_dir, prefix + '_waist.bmp'), waist_img)
    save_bmp_alpha(os.path.join(out_dir, prefix + '_head.bmp'), head_img)

    # 预览图：原图 + 胸线(红) + 腿线(蓝)
    prev = rgba.copy()

    def draw_line(arr, y, color):
        for x in range(w):
            arr[y, x] = color
            if y + 1 < h:
                arr[y + 1, x] = color

    draw_line(prev, chest, [255, 0, 0, 255])
    draw_line(prev, leg, [0, 100, 255, 255])
    Image.fromarray(prev, 'RGBA').save(os.path.join(out_dir, prefix + '_lines_preview.png'))

    print('%s: 实验性分层；请用 verify_and_gif.py 检查动态接缝，不代表游戏验收' % prefix)
    for tag, arr in [('chest', chest_img), ('waist', waist_img), ('head', head_img)]:
        nz = int((arr[:, :, 3] > 0).sum())
        print('  %s: 非透明像素 %d (%.1f%%)' % (tag, nz, 100.0 * nz / (GAME_SIZE * GAME_SIZE)))
    print('  输出目录: %s' % out_dir)


if __name__ == '__main__':
    main()
