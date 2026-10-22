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
import json
import os
import struct

import numpy as np
from PIL import Image

BMP_HEADER_SIZE = 54


def read_bmp_header(path):
    with open(path, 'rb') as f:
        d = f.read(BMP_HEADER_SIZE)
    if len(d) < BMP_HEADER_SIZE:
        raise ValueError('BMP 文件头不足 54 字节: ' + path)
    sig = d[0:2]
    fs = struct.unpack_from('<I', d, 2)[0]
    off = struct.unpack_from('<I', d, 10)[0]
    dib = struct.unpack_from('<I', d, 14)[0]
    w = struct.unpack_from('<i', d, 18)[0]
    h = struct.unpack_from('<i', d, 22)[0]
    bpp = struct.unpack_from('<H', d, 28)[0]
    comp = struct.unpack_from('<I', d, 30)[0]
    ok = (sig == b'BM' and off == BMP_HEADER_SIZE and dib == 40 and bpp == 32
          and comp == 0 and w == 1024 and abs(h) == 1024
          and fs == BMP_HEADER_SIZE + w * abs(h) * 4 and fs == os.path.getsize(path))
    if not ok:
        raise ValueError('需要完整的 1024x1024、32 位 BI_RGB BMP: ' + path)
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


def render_frame(chest, waist, head, chest_line, phase, background=(70, 70, 70, 255)):
    """模拟帧：逆向采样缩放，Pillow source-over 保留羽化透明度。"""
    hh, ww = chest.shape[:2]
    dy = int(round(2 * np.sin(phase)))
    scale = 1.0 + 0.010 * np.sin(phase)
    src_y = np.clip(np.round(chest_line + (np.arange(hh) - chest_line) / scale), 0, hh - 1).astype(int)
    canvas = Image.new('RGBA', (ww, hh), background)
    canvas = Image.alpha_composite(canvas, Image.fromarray(chest[src_y]))
    canvas = Image.alpha_composite(canvas, Image.fromarray(waist))
    shifted = Image.new('RGBA', (ww, hh))
    shifted.paste(Image.fromarray(head), (0, -dy))
    return Image.alpha_composite(canvas, shifted)


def alpha_deficit(source_alpha, frame_alpha, threshold):
    """只检查原图接近不透明的主体；返回坐标为画布像素，bbox 两端均包含。"""
    mask = (source_alpha >= threshold) & (frame_alpha < threshold)
    ys, xs = np.where(mask)
    rows = np.count_nonzero(mask, axis=1)
    return {
        'pixels': int(len(ys)),
        'min_alpha': int(frame_alpha[mask].min()) if len(ys) else None,
        'bbox': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(ys) else None,
        'rows': [[int(y), int(rows[y])] for y in np.flatnonzero(rows)],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prefix', required=True, help='generate_breathing.py 输出的文件名前缀')
    ap.add_argument('--dir', default='.', help='三张 BMP 所在目录')
    ap.add_argument('--chest-line', type=int, required=True, help='胸线 y 坐标（缩放锚点，与生成时一致）')
    ap.add_argument('--frames', type=int, default=16, help='GIF 帧数（默认 16）')
    ap.add_argument('--duration', type=int, default=90, help='每帧毫秒（默认 90）')
    ap.add_argument('--source', help='可选原图：逐相位透明度缺口检查及静态差异')
    ap.add_argument('--alpha-threshold', type=int, default=250, help='主体/缺口 alpha 分界，默认 250')
    ap.add_argument('--warn-pixels', type=int, default=0, help='缺口像素数超过此值时警告，默认 0')
    args = ap.parse_args()
    if args.frames < 2 or args.duration <= 0 or not 0 < args.chest_line < 1024:
        ap.error('需要 frames >= 2、duration > 0、0 < chest-line < 1024')
    if not 1 <= args.alpha_threshold <= 255 or args.warn_pixels < 0:
        ap.error('需要 1 <= alpha-threshold <= 255、warn-pixels >= 0')
    source = None
    if args.source:
        source = Image.open(args.source).convert('RGBA')
        if source.size != (1024, 1024):
            ap.error('--source 必须是生成时的 1024x1024 原图')

    layers = {}
    for tag in ['chest', 'waist', 'head']:
        p = os.path.join(args.dir, '%s_%s.bmp' % (args.prefix, tag))
        try:
            ok, w, h, fs = read_bmp_header(p)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        rgba = load_bmp_rgba(p)
        nz = int((rgba[:, :, 3] > 0).sum())
        print('%s: 格式OK=%s 尺寸=%dx%d 文件长=%d 非透明像素=%d' % (tag, ok, w, h, fs, nz))
        layers[tag] = rgba

    # 生成模拟呼吸 GIF
    chest, waist, head = layers['chest'], layers['waist'], layers['head']
    frames = []
    metrics = []
    for i in range(args.frames):
        t = i / args.frames * 2 * np.pi
        frame = render_frame(chest, waist, head, args.chest_line, t, (0, 0, 0, 0))
        bg = Image.new('RGBA', frame.size, (70, 70, 70, 255))
        frames.append(Image.alpha_composite(bg, frame))
        if source is not None:
            deficit = alpha_deficit(np.asarray(source)[:, :, 3], np.asarray(frame)[:, :, 3], args.alpha_threshold)
            metrics.append({'frame': i, 'phase_radians': float(t), **deficit})
            print('相位 %d/%d: alpha<%d 缺口=%d 最低=%s bbox=%s%s' % (
                i, args.frames, args.alpha_threshold, deficit['pixels'], deficit['min_alpha'],
                deficit['bbox'], ' WARNING' if deficit['pixels'] > args.warn_pixels else ''))
    if source is not None:
        report = {'alpha_threshold': args.alpha_threshold, 'warn_pixels': args.warn_pixels,
                  'region': 'source alpha >= threshold; original canvas coordinates', 'frames': metrics}
        with open(os.path.join(args.dir, args.prefix + '_alpha_phases.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    # 保存无调色板量化的关键帧；透明帧和黑白底能暴露 alpha 缺口/重影
    panels = []
    for i, phase in enumerate((0, np.pi / 2, np.pi, 3 * np.pi / 2)):
        frame = render_frame(chest, waist, head, args.chest_line, phase, (0, 0, 0, 0))
        frame.save(os.path.join(args.dir, '%s_frame_%d.png' % (args.prefix, i)))
        for color in ('black', 'white'):
            bg = Image.new('RGBA', frame.size, color)
            panels.append(Image.alpha_composite(bg, frame).resize((256, 256)))
    sheet = Image.new('RGB', (512, 1024))
    for i, panel in enumerate(panels):
        sheet.paste(panel, ((i % 2) * 256, (i // 2) * 256))
    sheet.save(os.path.join(args.dir, args.prefix + '_seams.png'))
    if source is not None:
        static = render_frame(chest, waist, head, args.chest_line, 0, (0, 0, 0, 0))
        diff = np.abs(np.array(static).astype(int) - np.array(source).astype(int))
        print('静态 over alpha 差异 max=%d mean=%.3f；仅诊断，不是游戏 PASS' % (
            diff[:, :, 3].max(), diff[:, :, 3].mean()))
        Image.fromarray(diff.astype(np.uint8)).save(os.path.join(args.dir, args.prefix + '_static_diff.png'))

    gif_path = os.path.join(args.dir, '%s_breathing_preview.gif' % args.prefix)
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=args.duration, loop=0, disposal=2)
    print('GIF: ' + gif_path)


if __name__ == '__main__':
    main()
