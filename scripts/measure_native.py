# -*- coding: utf-8 -*-
"""量取一组原生呼吸图（胸、腰、头三张）的 alpha 分层参数，用来校准默认值。

本脚本只读取你自己导出的文件，仓库不附带也不接受任何游戏素材。
PK 版数据块 8 中每名武将三帧的顺序按社区资料为 胸、腰、头，参数也按这个顺序传入。

输出（打印 + 可选 JSON），坐标均为该图画布像素：
  - 画布尺寸、三层合并后的主体范围（可判断原生图是 1024 画布还是 633x900 有效区）；
  - 每层逐行最大 alpha 的上下渐变宽度（从全透明行到 >=阈值 行的距离）及完全不透明的行段；
  - 两两层之间同时有 alpha 的重叠行段；
  - 胸层完全不透明行段内，腰层对主体的覆盖率（判断“底图是否带胸、手臂”）；
  - 头层下缘逐列高度的离散度（判断下缘是水平线还是弧线）；
  - 建议参数：--overlap、--feather-chest 的近似值。

用法：
  python measure_native.py 胸.bmp 腰.bmp 头.bmp [--json native_alpha.json]
"""
import argparse
import json
import struct

import numpy as np
from PIL import Image


def load_rgba(path):
    """读 32 位 BMP（BI_RGB 或标准 BGRA 位域）或 PIL 能读的带透明图为 RGBA 数组。"""
    with open(path, 'rb') as f:
        d = f.read()
    if d[:2] == b'BM' and len(d) >= 54:
        off = struct.unpack_from('<I', d, 10)[0]
        dib = struct.unpack_from('<I', d, 14)[0]
        w = struct.unpack_from('<i', d, 18)[0]
        h_signed = struct.unpack_from('<i', d, 22)[0]
        bpp = struct.unpack_from('<H', d, 28)[0]
        comp = struct.unpack_from('<I', d, 30)[0]
        h = abs(h_signed)
        if bpp == 32 and comp in (0, 3):
            if comp == 3:
                masks = struct.unpack_from('<III', d, 54 if dib == 40 else 14 + 40)
                if masks != (0x00FF0000, 0x0000FF00, 0x000000FF):
                    raise ValueError('不支持的 BMP 位域掩码: %s' % path)
            if w <= 0 or h == 0 or off + w * h * 4 > len(d):
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
        # 渐变宽度 = 不透明段边缘到第一行全透明之间的距离，与生成脚本的羽化参数同义
        top_ramp, bottom_ramp = s0 - top + 1, bottom - s1 + 1
        solid_rows = [s0, s1]
    else:
        top_ramp = bottom_ramp = None
        solid_rows = None
    return {'rows': [top, bottom], 'solid_rows': solid_rows,
            'top_ramp': top_ramp, 'bottom_ramp': bottom_ramp}


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

    # 胸层完全不透明行段内，腰层覆盖了多少主体像素：接近 1 说明底图带胸/手臂
    solid = report['layers']['chest']['solid_rows']
    if solid:
        band = slice(solid[0], solid[1] + 1)
        subject = union[band] >= threshold
        covered = subject & (layers['waist'][band] >= threshold)
        report['waist_covers_chest_band'] = round(float(covered.sum()) / max(int(subject.sum()), 1), 4)
    else:
        report['waist_covers_chest_band'] = None

    # 头层下缘：逐列最后一个 alpha>=阈值 的行，离散度大说明是弧线而不是水平线
    hs = layers['head'] >= threshold
    cols = np.flatnonzero(hs.any(axis=0))
    if len(cols):
        last = np.array([np.flatnonzero(hs[:, c])[-1] for c in cols])
        report['head_bottom_edge'] = {'min_y': int(last.min()), 'max_y': int(last.max()),
                                      'std': round(float(last.std()), 2)}
    else:
        report['head_bottom_edge'] = None

    report['suggested'] = {
        'overlap': report['layers']['chest']['bottom_ramp'],
        'feather_chest': report['layers']['head']['bottom_ramp'],
        'note': '按该图画布像素；若原生有效区不是 1024 高，需要按比例换算后再传给 generate_breathing.py',
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
    print('腰层覆盖胸层不透明段主体比例: %s' % rep['waist_covers_chest_band'])
    print('头层下缘: %s' % rep['head_bottom_edge'])
    print('建议: --overlap %s --feather-chest %s（%s）' % (
        rep['suggested']['overlap'], rep['suggested']['feather_chest'], rep['suggested']['note']))
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print('saved ' + args.json_out)


if __name__ == '__main__':
    main()
