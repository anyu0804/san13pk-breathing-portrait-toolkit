# -*- coding: utf-8 -*-
"""校验三层呼吸图 BMP 并生成模拟游戏呼吸动画的预览 GIF。

校验：文件头（BM、54 偏移、BITMAPINFOHEADER、1024x1024、32 位、BI_RGB、
文件长度自洽），并统计各层非透明像素。
预览：胸层绕胸线做 ±1% 垂直缩放、头层上下 ±2px 浮动、腰层静止，近似游戏
内的呼吸合成方式，叠到灰底上便于肉眼检查接缝。预览只能证明素材效果，
不等于游戏运行验收。

用法：
  python verify_and_gif.py --prefix sample --dir sample_breathing --chest-line 465
"""
import argparse
import os
import struct

import numpy as np
from PIL import Image

BMP_HEADER_SIZE = 54


def read_bmp_header(path):
    with open(path, 'rb') as f:
        d = f.read(BMP_HEADER_SIZE)
    if len(d) < BMP_HEADER_SIZE:
        return None
    sig = d[0:2]
    fs = struct.unpack_from('<I', d, 2)[0]
    off = struct.unpack_from('<I', d, 10)[0]
    dib = struct.unpack_from('<I', d, 14)[0]
    w = struct.unpack_from('<i', d, 18)[0]
    h = struct.unpack_from('<i', d, 22)[0]
    bpp = struct.unpack_from('<H', d, 28)[0]
    comp = struct.unpack_from('<I', d, 30)[0]
    ok = (sig == b'BM' and off == BMP_HEADER_SIZE and dib == 40 and bpp == 32
          and comp == 0 and abs(w) == abs(h) and fs == BMP_HEADER_SIZE + abs(w) * abs(h) * 4)
    return ok, w, h, fs


def load_bmp_rgba(path):
    """读 32 位 BI_RGB BMP 为 RGBA numpy 数组（自下而上行序自动翻转）。"""
    with open(path, 'rb') as f:
        d = f.read()
    off = struct.unpack_from('<I', d, 10)[0]
    w = struct.unpack_from('<i', d, 18)[0]
    h_signed = struct.unpack_from('<i', d, 22)[0]
    h = abs(h_signed)
    arr = np.frombuffer(d, dtype=np.uint8, count=h * w * 4, offset=off).reshape(h, w, 4)
    if h_signed > 0:  # 正高度 = 自下而上存储
        arr = arr[::-1]
    return arr[:, :, [2, 1, 0, 3]].copy()  # BGRA -> RGBA


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prefix', required=True, help='generate_breathing.py 输出的文件名前缀')
    ap.add_argument('--dir', default='.', help='三张 BMP 所在目录')
    ap.add_argument('--chest-line', type=int, required=True, help='胸线 y 坐标（缩放锚点，与生成时一致）')
    ap.add_argument('--frames', type=int, default=16, help='GIF 帧数（默认 16）')
    ap.add_argument('--duration', type=int, default=90, help='每帧毫秒（默认 90）')
    args = ap.parse_args()

    layers = {}
    for tag in ['chest', 'waist', 'head']:
        p = os.path.join(args.dir, '%s_%s.bmp' % (args.prefix, tag))
        ok, w, h, fs = read_bmp_header(p)
        rgba = load_bmp_rgba(p)
        nz = int((rgba[:, :, 3] > 0).sum())
        print('%s: 格式OK=%s 尺寸=%dx%d 文件长=%d 非透明像素=%d' % (tag, ok, w, h, fs, nz))
        layers[tag] = rgba

    # 生成模拟呼吸 GIF
    chest, waist, head = layers['chest'], layers['waist'], layers['head']
    hh, ww = chest.shape[:2]
    bg = np.array([70, 70, 70, 255], dtype=np.uint8)
    frames = []
    for i in range(args.frames):
        t = i / args.frames * 2 * np.pi
        dy = int(round(2 * np.sin(t)))
        scale = 1.0 + 0.010 * np.sin(t)
        canvas = np.tile(bg, (hh, ww, 1))
        # 胸：以胸线为锚点垂直缩放
        src_ys = np.arange(hh)
        new_ys = np.clip(np.round(args.chest_line + (src_ys - args.chest_line) * scale), 0, hh - 1).astype(int)
        for yy in range(hh):
            sy = new_ys[yy]
            m = chest[sy, :, 3] > 0
            if m.any():
                canvas[yy, m] = chest[sy, m]
        # 腰（静态，覆盖腿）
        m = waist[:, :, 3] > 0
        canvas[m] = waist[m]
        # 头（上下移动）
        target = np.zeros_like(canvas)
        sy0, sy1 = max(0, dy), min(hh, hh + dy)
        ty0, ty1 = max(0, -dy), min(hh, hh - dy)
        target[ty0:ty1, :, :] = head[sy0:sy1, :, :]
        m = target[:, :, 3] > 0
        canvas[m] = target[m]
        frames.append(Image.fromarray(canvas, 'RGBA'))

    gif_path = os.path.join(args.dir, '%s_breathing_preview.gif' % args.prefix)
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=args.duration, loop=0, disposal=2)
    print('GIF: ' + gif_path)


if __name__ == '__main__':
    main()
