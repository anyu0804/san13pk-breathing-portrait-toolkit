# -*- coding: utf-8 -*-
"""量取一组原生呼吸图（胸、腰、头三张）的 alpha 分层参数，用来校准默认值。

本脚本只读取你自己导出的文件，仓库不附带也不接受任何游戏素材。
PK 版数据块 8 中每名武将三帧的顺序按社区资料为 胸、腰、头，参数也按这个顺序传入。

输出（打印 + 可选 JSON），坐标均为该图画布像素：
  - 画布尺寸、三层合并后的主体范围（可判断原生图是 1024 画布还是 633x900 有效区）；
  - 每层逐行最大 alpha 的范围、不透明段与上下渐变宽度；
  - 两两层之间同时有 alpha 的重叠行段；
  - 胸层完全不透明行段内，腰层与胸层各自对主体的覆盖率（判断底图是否带胸/手臂，
    以及胸层是否只抠胸口局部）；
  - 头层与胸层下缘真实接缝列（剔除悬空外轮廓）的逐列高度离散度与中位羽化宽度；
  - 建议参数：头层下缘（对应 --feather-chest）与胸层下缘羽化宽度的参考值。

用法：
  python measure_native.py 胸.bmp 腰.bmp 头.bmp [--json native_alpha.json]
"""
import argparse
import json
import struct

import numpy as np
from PIL import Image

_STD_RGB_MASKS = (0x00FF0000, 0x0000FF00, 0x000000FF)
_STD_ALPHA_MASK = 0xFF000000


def load_rgba(path):
    """读 32 位 BMP（BI_RGB 或标准 BGRA 位域）或 PIL 能读的带透明图为 RGBA 数组。"""
    with open(path, 'rb') as f:
        d = f.read()
    if d[:2] == b'BM':
        if len(d) < 54:
            raise ValueError('BMP 文件头不完整: ' + path)
        off = struct.unpack_from('<I', d, 10)[0]
        dib = struct.unpack_from('<I', d, 14)[0]
        if dib >= 40:
            w = struct.unpack_from('<i', d, 18)[0]
            h_signed = struct.unpack_from('<i', d, 22)[0]
            bpp = struct.unpack_from('<H', d, 28)[0]
            comp = struct.unpack_from('<I', d, 30)[0]
            h = abs(h_signed)
            if bpp == 32 and comp in (0, 3, 6):
                min_header = 14 + dib
                if dib == 40 and comp == 3:
                    min_header = 66  # 14 + 40 + 12 (RGB 掩码)
                elif dib == 40 and comp == 6:
                    min_header = 70  # 14 + 40 + 16 (RGBA 掩码)
                if len(d) < min_header:
                    raise ValueError('BMP 文件头不完整: ' + path)
                if comp in (3, 6):
                    need_alpha_mask = dib >= 56 or comp == 6
                    if len(d) < (70 if need_alpha_mask else 66):
                        raise ValueError('BMP 位域头不完整: ' + path)
                    masks = struct.unpack_from('<III', d, 54)
                    if masks != _STD_RGB_MASKS:
                        raise ValueError('不支持的 BMP 位域掩码: %s' % path)
                    if need_alpha_mask:
                        alpha_mask = struct.unpack_from('<I', d, 66)[0]
                        if alpha_mask == 0:
                            raise ValueError('BMP 位域不含 alpha 通道: ' + path)
                        if alpha_mask != _STD_ALPHA_MASK:
                            raise ValueError('不支持的 BMP alpha 掩码: %s' % path)
                if w <= 0 or h == 0 or off < min_header or off + w * h * 4 > len(d):
                    raise ValueError('BMP 数据不完整: ' + path)
                arr = np.frombuffer(d, dtype=np.uint8, count=h * w * 4, offset=off).reshape(h, w, 4)
                if h_signed > 0:
                    arr = arr[::-1]
                return arr[:, :, [2, 1, 0, 3]].copy()
    with Image.open(path) as im:
        if 'A' not in im.getbands():
            raise ValueError('图像没有 alpha 通道: ' + path)
        return np.array(im.convert('RGBA'))


def _runs(mask):
    """把布尔数组转成 [起, 止]（含两端）区间列表。"""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return [[int(a), int(b)] for a, b in zip(starts, ends)]


def _span_to_ramp(span):
    """连续半透明过渡行数转线性羽化参数：0 行表示硬切，其余为 span + 1。"""
    return span + 1 if span > 0 else 0


def layer_profile(alpha, threshold):
    """逐行最大 alpha 的范围与上下渐变宽度。"""
    rmax = alpha.max(axis=1)
    rows = np.flatnonzero(rmax > 0)
    solid = np.flatnonzero(rmax >= threshold)
    if not len(rows):
        return {'rows': None, 'solid_rows': None, 'top_ramp': None, 'bottom_ramp': None}
    top, bottom = int(rows[0]), int(rows[-1])
    if len(solid):
        s0, s1 = int(solid[0]), int(solid[-1])
        top_ramp = _span_to_ramp(s0 - top)
        bottom_ramp = _span_to_ramp(bottom - s1)
        solid_rows = [s0, s1]
    else:
        top_ramp = bottom_ramp = None
        solid_rows = None
    return {'rows': [top, bottom], 'solid_rows': solid_rows,
            'top_ramp': top_ramp, 'bottom_ramp': bottom_ramp}


def measure_bottom_seam(upper, lower, threshold):
    """逐列量取 upper 与 lower 实际衔接处的下缘轮廓与渐变宽度。

    只统计在 upper 渐隐收尾前与 lower 连续衔接（中间无全透明空气行）的列，
    避免把头部两侧悬空的耳朵/脸颊/发梢外轮廓误算进切口弧度或羽化宽度。
    """
    h = upper.shape[0]
    solid = upper >= threshold
    cols = np.flatnonzero(solid.any(axis=0))
    edge_y = []
    ramps = []
    for c in cols:
        y_solid = int(np.flatnonzero(solid[:, c])[-1])
        if y_solid + 1 >= h:
            continue
        after = upper[y_solid + 1:, c]
        zeros = np.flatnonzero(after == 0)
        if not len(zeros):
            continue
        span = int(zeros[0])
        end = y_solid + span + 1  # upper 第一行回到全透明的位置
        union_seg = np.maximum(upper[y_solid + 1:end + 1, c], lower[y_solid + 1:end + 1, c])
        if np.all(union_seg > 0) and lower[y_solid + 1:end + 1, c].max() > 0:
            edge_y.append(y_solid)
            ramps.append(_span_to_ramp(span))
    if not edge_y:
        return None
    ys = np.array(edge_y, dtype=float)
    return {
        'columns': len(edge_y),
        'min_y': int(ys.min()),
        'max_y': int(ys.max()),
        'std': round(float(ys.std()), 2),
        'ramp_median': int(round(float(np.median(ramps)))),
    }


def measure(chest, waist, head, threshold=250):
    if not (chest.shape == waist.shape == head.shape):
        raise ValueError('三张图尺寸必须一致: %s %s %s' % (chest.shape, waist.shape, head.shape))
    layers = {'chest': chest[:, :, 3], 'waist': waist[:, :, 3], 'head': head[:, :, 3]}
    union = np.maximum.reduce(list(layers.values()))
    ys, xs = np.nonzero(union > 0)
    report = {
        'canvas': [int(chest.shape[1]), int(chest.shape[0])],
        'subject_bbox': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(ys) else None,
        'alpha_threshold': threshold,
        'layers': {k: layer_profile(v, threshold) for k, v in layers.items()},
        'overlaps': {},
    }
    for a, b in (('chest', 'waist'), ('chest', 'head'), ('waist', 'head')):
        both = (layers[a] > 0) & (layers[b] > 0)
        report['overlaps'][a + '/' + b] = _runs(both.any(axis=1))

    # 胸层完全不透明行段内，腰层与胸层各自覆盖主体比例：
    # waist_covers 接近 1 说明底图带胸/手臂；chest_covers 明显 < 1 说明胸层只抠局部不含手臂
    solid = report['layers']['chest']['solid_rows']
    if solid:
        band = slice(solid[0], solid[1] + 1)
        subject = union[band] >= threshold
        denom = max(int(subject.sum()), 1)
        report['waist_covers_chest_band'] = round(
            float((subject & (layers['waist'][band] >= threshold)).sum()) / denom, 4)
        report['chest_covers_chest_band'] = round(
            float((subject & (layers['chest'][band] >= threshold)).sum()) / denom, 4)
    else:
        report['waist_covers_chest_band'] = None
        report['chest_covers_chest_band'] = None

    body = np.maximum(layers['chest'], layers['waist'])
    head_seam = measure_bottom_seam(layers['head'], body, threshold)
    chest_seam = measure_bottom_seam(layers['chest'], layers['waist'], threshold)
    report['head_bottom_edge'] = head_seam
    report['chest_bottom_seam'] = chest_seam

    chest_feather = (chest_seam['ramp_median'] if chest_seam is not None
                     else report['layers']['chest']['bottom_ramp'])
    head_feather = (head_seam['ramp_median'] if head_seam is not None
                    else report['layers']['head']['bottom_ramp'])
    report['suggested'] = {
        'chest_bottom_feather': chest_feather,
        'feather_chest': head_feather,
        'note': '按该图画布像素；若原生有效区不是 1024 高，需要按比例换算后再对照 generate_breathing.py 参数',
    }
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('chest', help='胸层图（数据块 8 中该武将的第 1 帧）')
    ap.add_argument('waist', help='腰层图（第 2 帧）')
    ap.add_argument('head', help='头层图（第 3 帧）')
    ap.add_argument('--alpha-threshold', type=int, default=250, help='视为不透明的 alpha，默认 250')
    ap.add_argument('--json', dest='json_out', help='把结果写入该 JSON')
    args = ap.parse_args()
    if not 1 <= args.alpha_threshold <= 255:
        ap.error('需要 1 <= alpha-threshold <= 255')
    try:
        rep = measure(load_rgba(args.chest), load_rgba(args.waist), load_rgba(args.head), args.alpha_threshold)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))

    print('画布 %dx%d，主体范围 %s' % (rep['canvas'][0], rep['canvas'][1], rep['subject_bbox']))
    for k, v in rep['layers'].items():
        print('%-5s 行 %s 不透明 %s 上渐变 %s 下渐变 %s' % (
            k, v['rows'], v['solid_rows'], v['top_ramp'], v['bottom_ramp']))
    for k, v in rep['overlaps'].items():
        print('重叠 %s: %s' % (k, v))
    print('胸层不透明段主体覆盖比例: waist=%s chest=%s' % (
        rep['waist_covers_chest_band'], rep['chest_covers_chest_band']))
    print('头层下缘接缝: %s' % rep['head_bottom_edge'])
    print('胸层下缘接缝: %s' % rep['chest_bottom_seam'])
    print('建议: --feather-chest %s，胸层下缘羽化 %s（%s）' % (
        rep['suggested']['feather_chest'], rep['suggested']['chest_bottom_feather'], rep['suggested']['note']))
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print('saved ' + args.json_out)


if __name__ == '__main__':
    main()
