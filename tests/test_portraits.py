import pathlib
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from generate_breathing import alpha_apply, feather_factor, resolve_lines, save_bmp_alpha, split_layers
from measure_native import load_rgba, measure
from make_preview import BACKGROUNDS, main as preview_main
from pick_lines import pick
from verify_and_gif import alpha_deficit, load_bmp_rgba, read_bmp_header, render_frame
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'examples'))
from make_sample_portrait import make_portrait


class PortraitRegressionTests(unittest.TestCase):
    def test_json_lines_allow_independent_manual_overrides_and_output_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'lines.json'
            path.write_text(json.dumps({'portrait': {'chest_line': 300, 'leg_line': 700}}))
            for chest, leg, expected in [(None, None, (300, 700)), (400, None, (400, 700)),
                                          (None, 650, (300, 650)), (400, 650, (400, 650))]:
                with self.subTest(chest=chest, leg=leg):
                    args = SimpleNamespace(chest=chest, leg=leg, prefix='renamed', lines=str(path))
                    self.assertEqual(resolve_lines(args, 'portrait'), expected)

    def test_preview_cli_preserves_bmp_and_png_transparency(self):
        rgba = np.zeros((1024, 1024, 4), dtype=np.uint8)
        rgba[:, :, :3] = [200, 10, 20]
        rgba[10, 10, 3] = 128
        rgba[20, 20, 3] = 255
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bmp = root / 'portrait.BMP'
            png = root / 'portrait.png'
            save_bmp_alpha(str(bmp), rgba)
            Image.fromarray(rgba).save(png)
            for source in (bmp, png):
                out = root / source.suffix[1:]
                with patch.object(sys, 'argv', ['make_preview.py', str(source), '--out', str(out)]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    preview_main()
                for name, color in BACKGROUNDS.items():
                    with Image.open(out / ('portrait_on_%s.png' % name)) as preview:
                        self.assertEqual(preview.getpixel((0, 0)), color[:3])
                        expected = Image.alpha_composite(
                            Image.new('RGBA', (1, 1), color),
                            Image.new('RGBA', (1, 1), (200, 10, 20, 128))).getpixel((0, 0))[:3]
                        self.assertEqual(preview.getpixel((10, 10)), expected)
                        self.assertEqual(preview.getpixel((20, 20)), (200, 10, 20))

    def test_stable_leg_line_avoids_skirt_seam_at_every_phase(self):
        source = np.array(make_portrait())
        rows = (source[:, :, 3] > 40).sum(axis=1).astype(float)
        sm = np.convolve(rows, np.ones(15) / 15, mode='same')
        chest, leg = pick(sm, 70, 1023)
        self.assertLess(leg, 770)
        layers = split_layers(source, chest, leg, 7, 20)
        old_layers = split_layers(source, chest, 798, 7, 20)
        old = np.array(render_frame(*old_layers, chest, 1.5 * np.pi, (0, 0, 0, 0)))
        old_metric = alpha_deficit(source[760:811, :, 3], old[760:811, :, 3], 250)
        self.assertGreater(old_metric['pixels'], 1500)
        for i in range(16):
            frame = np.array(render_frame(*layers, chest, i / 16 * 2 * np.pi, (0, 0, 0, 0)))
            metric = alpha_deficit(source[760:811, :, 3], frame[760:811, :, 3], 250)
            self.assertEqual(metric['pixels'], 0, 'phase %d' % i)

    def test_alpha_deficit_reports_canvas_locations_and_ignores_soft_source(self):
        source = np.array([[255, 100], [255, 255]], dtype=np.uint8)
        frame = np.array([[127, 0], [255, 249]], dtype=np.uint8)
        self.assertEqual(alpha_deficit(source, frame, 250), {
            'pixels': 2, 'min_alpha': 127, 'bbox': [0, 0, 1, 1], 'rows': [[0, 1], [1, 1]]})
        self.assertEqual(alpha_deficit(source, source, 250), {
            'pixels': 0, 'min_alpha': None, 'bbox': None, 'rows': []})

    def test_zero_feather_is_hard_cut_without_nan(self):
        with np.errstate(all='raise'):
            np.testing.assert_array_equal(feather_factor(5, 2, 0, True), [0, 0, 1, 1, 1])
            np.testing.assert_array_equal(feather_factor(5, 2, 0, False), [1, 1, 1, 0, 0])

    def test_torso_excludes_old_head_and_legs(self):
        source = np.full((100, 2, 4), 255, dtype=np.uint8)
        chest, waist, head = split_layers(source, 30, 70, 7, 20)
        self.assertEqual(chest[0, 0, 3], 0)
        self.assertEqual(chest[99, 0, 3], 0)
        self.assertEqual(head[0, 0, 3], 255)
        self.assertEqual(waist[99, 0, 3], 255)
        self.assertTrue(np.all(chest[:, :, :3] == source[:, :, :3]))

    def test_preview_blends_partial_alpha_over_background(self):
        empty = np.zeros((4, 4, 4), dtype=np.uint8)
        head = empty.copy()
        head[0, 0] = [255, 0, 0, 128]
        frame = np.array(render_frame(empty, empty, head, 2, 0, (0, 0, 0, 255)))
        np.testing.assert_array_equal(frame[0, 0], [128, 0, 0, 255])

    def test_moving_head_leaves_no_copy_in_torso(self):
        source = np.zeros((100, 4, 4), dtype=np.uint8)
        source[10:20] = [255, 0, 0, 255]
        layers = split_layers(source, 30, 70, 7, 20)
        frame = np.array(render_frame(*layers, 30, np.pi / 2, (0, 0, 0, 0)))
        self.assertEqual(frame[19, 0, 3], 0)
        self.assertEqual(frame[8, 0, 3], 255)

    def test_measure_native_recovers_parameters_and_horizontal_seam(self):
        source = np.array(make_portrait())
        layers = split_layers(source, 330, 700, 7, 20)
        rep = measure(*layers)
        self.assertEqual(rep['canvas'], [1024, 1024])
        self.assertLess(rep['waist_covers_chest_band'], 0.5)
        self.assertEqual(rep['chest_covers_chest_band'], 1.0)
        self.assertEqual(rep['head_bottom_edge']['min_y'], 330)
        self.assertEqual(rep['head_bottom_edge']['max_y'], 330)
        self.assertEqual(rep['head_bottom_edge']['std'], 0.0)
        self.assertEqual(rep['head_bottom_edge']['ramp_median'], 7)
        self.assertGreater(rep['head_bottom_edge']['columns'], 50)
        self.assertEqual(rep['chest_bottom_seam']['min_y'], 700)
        self.assertEqual(rep['chest_bottom_seam']['max_y'], 700)
        self.assertEqual(rep['chest_bottom_seam']['std'], 0.0)
        self.assertEqual(rep['chest_bottom_seam']['ramp_median'], 20)
        self.assertEqual(rep['suggested']['feather_chest'], 7)
        self.assertEqual(rep['suggested']['chest_bottom_feather'], 20)
        self.assertTrue(rep['overlaps']['chest/waist'])

        # 模拟“底图覆盖全躯干+手臂，胸层仅抠胸口局部、下缘 30px 羽化”的原生结构
        h = source.shape[0]
        base_head = alpha_apply(source, feather_factor(h, 330, 7, False))
        base_waist = alpha_apply(source, feather_factor(h, 330, 7, True))
        base_chest = alpha_apply(
            source,
            feather_factor(h, 330, 7, True) * feather_factor(h, 700, 30, False),
        )
        base_chest[:, :360, 3] = 0
        base_chest[:, 664:, 3] = 0
        rep_base = measure(base_chest, base_waist, base_head)
        self.assertEqual(rep_base['waist_covers_chest_band'], 1.0)
        self.assertGreater(rep_base['chest_covers_chest_band'], 0.5)
        self.assertLess(rep_base['chest_covers_chest_band'], 0.95)
        self.assertEqual(rep_base['chest_bottom_seam']['ramp_median'], 30)
        self.assertEqual(rep_base['head_bottom_edge']['std'], 0.0)
        self.assertEqual(rep_base['suggested']['chest_bottom_feather'], 30)
        self.assertEqual(rep_base['suggested']['feather_chest'], 7)

    def test_measure_native_handles_hard_cut_and_curved_seam(self):
        source = np.array(make_portrait())
        hard = measure(*split_layers(source, 330, 700, 0, 0))
        self.assertEqual(hard['layers']['head']['bottom_ramp'], 0)
        self.assertEqual(hard['layers']['chest']['bottom_ramp'], 0)
        self.assertEqual(hard['head_bottom_edge']['ramp_median'], 0)
        self.assertEqual(hard['chest_bottom_seam']['ramp_median'], 0)
        self.assertEqual(hard['suggested']['feather_chest'], 0)
        self.assertEqual(hard['suggested']['chest_bottom_feather'], 0)

        # 弧线切口 + 统一 8px 垂直羽化，同时放一块悬空外轮廓（下方隔空气是肩膀）
        h, w = 120, 80
        head = np.zeros((h, w, 4), dtype=np.uint8)
        chest = np.zeros((h, w, 4), dtype=np.uint8)
        waist = np.zeros((h, w, 4), dtype=np.uint8)
        head[10:21, 5:16] = [200, 150, 120, 255]
        waist[50:81, 5:16] = [100, 120, 140, 255]
        for x in range(20, 61):
            y_cut = 30 + abs(x - 40) // 2
            head[10:y_cut + 1, x] = [200, 150, 120, 255]
            for d in range(1, 8):
                head[y_cut + d, x] = [200, 150, 120, int(255 * (1.0 - d / 8.0))]
            chest[y_cut:81, x] = [100, 120, 140, 255]
            waist[y_cut:101, x] = [100, 120, 140, 255]
        curved = measure(chest, waist, head)
        self.assertEqual(curved['head_bottom_edge']['columns'], 41)
        self.assertEqual(curved['head_bottom_edge']['min_y'], 30)
        self.assertEqual(curved['head_bottom_edge']['max_y'], 40)
        self.assertGreater(curved['head_bottom_edge']['std'], 2.0)
        self.assertEqual(curved['head_bottom_edge']['ramp_median'], 8)
        self.assertEqual(curved['suggested']['feather_chest'], 8)

    def test_measure_loader_reads_bitfield_bmp_png_and_rejects_invalid(self):
        rgba = np.zeros((4, 3, 4), dtype=np.uint8)
        rgba[1, 2] = [10, 20, 30, 128]
        bgra_bottom_up = rgba[::-1][:, :, [2, 1, 0, 3]].tobytes()
        bgra_top_down = rgba[:, :, [2, 1, 0, 3]].tobytes()
        off_v1 = 14 + 40 + 12
        hdr_v1 = struct.pack('<2sIHHI', b'BM', off_v1 + len(bgra_bottom_up), 0, 0, off_v1)
        dib_v1 = struct.pack('<IiiHHIIiiII', 40, 3, 4, 1, 32, 3, len(bgra_bottom_up), 0, 0, 0, 0)
        masks_rgb = struct.pack('<III', 0x00FF0000, 0x0000FF00, 0x000000FF)

        off_v4 = 14 + 108
        hdr_v4 = struct.pack('<2sIHHI', b'BM', off_v4 + len(bgra_top_down), 0, 0, off_v4)
        dib_v4_head = struct.pack('<IiiHHIIiiII', 108, 3, -4, 1, 32, 3, len(bgra_top_down), 0, 0, 0, 0)
        masks_rgba = struct.pack('<IIII', 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
        masks_xrgb = struct.pack('<IIII', 0x00FF0000, 0x0000FF00, 0x000000FF, 0x00000000)
        v4_tail = b'\x00' * 52

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bmp_v1 = root / 'v1.bmp'
            bmp_v1.write_bytes(hdr_v1 + dib_v1 + masks_rgb + bgra_bottom_up)
            np.testing.assert_array_equal(load_rgba(str(bmp_v1)), rgba)

            bmp_v4 = root / 'v4.bmp'
            bmp_v4.write_bytes(hdr_v4 + dib_v4_head + masks_rgba + v4_tail + bgra_top_down)
            np.testing.assert_array_equal(load_rgba(str(bmp_v4)), rgba)

            png = root / 'n.png'
            Image.fromarray(rgba).save(png)
            np.testing.assert_array_equal(load_rgba(str(png)), rgba)

            # 60 字节截断的 BI_BITFIELDS BMP 必须抛 ValueError 而不是 struct.error
            trunc = root / 'trunc.bmp'
            trunc.write_bytes(hdr_v1 + dib_v1 + b'\x00' * 6)
            with self.assertRaises(ValueError):
                load_rgba(str(trunc))

            # V4 位域 alpha_mask == 0（无透明通道 XRGB）必须拒绝
            xrgb = root / 'xrgb.bmp'
            xrgb.write_bytes(hdr_v4 + dib_v4_head + masks_xrgb + v4_tail + bgra_top_down)
            with self.assertRaises(ValueError):
                load_rgba(str(xrgb))

            # 非标准 RGB 掩码拒绝
            bad_mask = root / 'bad_mask.bmp'
            bad_mask.write_bytes(
                hdr_v1 + dib_v1 + struct.pack('<III', 0x000000FF, 0x0000FF00, 0x00FF0000) + bgra_bottom_up
            )
            with self.assertRaises(ValueError):
                load_rgba(str(bad_mask))

            # 无 alpha 的 RGB PNG 拒绝
            rgb_png = root / 'rgb.png'
            Image.fromarray(rgba[:, :, :3], 'RGB').save(rgb_png)
            with self.assertRaises(ValueError):
                load_rgba(str(rgb_png))

        # 尺寸不一致与全透明边界
        with self.assertRaises(ValueError):
            measure(rgba, rgba, np.zeros((2, 2, 4), dtype=np.uint8))
        empty = np.zeros((8, 8, 4), dtype=np.uint8)
        empty_rep = measure(empty, empty, empty)
        self.assertIsNone(empty_rep['subject_bbox'])
        self.assertIsNone(empty_rep['head_bottom_edge'])
        self.assertIsNone(empty_rep['waist_covers_chest_band'])

    def test_short_subject_has_nonempty_leg_search(self):
        for height in (1, 2, 10, 50, 900):
            chest, leg = pick(np.ones(1024), 20, 20 + height)
            self.assertLess(chest, leg)
            self.assertLessEqual(leg, 20 + height)

    def test_bmp_roundtrip_and_reject_corrupt_input(self):
        rgba = np.zeros((1024, 1024, 4), dtype=np.uint8)
        rgba[10, 20] = [30, 70, 110, 128]
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / 'test.bmp')
            save_bmp_alpha(path, rgba)
            self.assertTrue(read_bmp_header(path)[0])
            np.testing.assert_array_equal(load_bmp_rgba(path), rgba)
            data = pathlib.Path(path).read_bytes()
            for invalid in (b'BM', data[:-1], data[:18] + struct.pack('<i', -1024) + data[22:]):
                pathlib.Path(path).write_bytes(invalid)
                with self.assertRaises(ValueError):
                    read_bmp_header(path)


if __name__ == '__main__':
    unittest.main()
