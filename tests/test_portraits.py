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
from generate_breathing import feather_factor, resolve_lines, save_bmp_alpha, split_layers
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
        layers = split_layers(source, chest, leg, 7, 20, 'legacy')
        old_layers = split_layers(source, chest, 798, 7, 20, 'legacy')
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
        chest, waist, head = split_layers(source, 30, 70, 7, 20, 'legacy')
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
        for model in ('legacy', 'base'):
            with self.subTest(model=model):
                layers = split_layers(source, 30, 70, 7, 20, model)
                frame = np.array(render_frame(*layers, 30, np.pi / 2, (0, 0, 0, 0), model == 'base'))
                self.assertEqual(frame[19, 0, 3], 0)
                self.assertEqual(frame[8, 0, 3], 255)

    def test_base_model_waist_is_full_body_under_moving_layers(self):
        source = np.full((100, 2, 4), 255, dtype=np.uint8)
        chest, waist, head = split_layers(source, 30, 70, 7, 20, 'base', 10)
        # 底图从胸线起完全不透明，包括胸段和手臂所在行
        self.assertTrue(np.all(waist[30:, :, 3] == 255))
        self.assertEqual(waist[22, 0, 3], 0)
        # 胸层上缘只羽化 7px（不带进头部），下缘向外 10px 重叠羽化
        self.assertEqual(chest[23, 0, 3], 0)
        self.assertGreater(chest[25, 0, 3], 0)
        self.assertGreater(chest[75, 0, 3], 0)
        self.assertEqual(chest[81, 0, 3], 0)
        self.assertEqual(head[0, 0, 3], 255)

    def test_base_model_has_no_body_gap_even_on_old_hem_line(self):
        source = np.array(make_portrait())
        rows = (source[:, :, 3] > 40).sum(axis=1).astype(float)
        sm = np.convolve(rows, np.ones(15) / 15, mode='same')
        chest, _ = pick(sm, 70, 1023)
        for leg in (798, 700):
            layers = split_layers(source, chest, leg, 7, 20, 'base', 30)
            for i in range(16):
                with self.subTest(leg=leg, phase=i):
                    frame = np.array(render_frame(*layers, chest, i / 16 * 2 * np.pi, (0, 0, 0, 0), True))
                    metric = alpha_deficit(source[chest:, :, 3], frame[chest:, :, 3], 250)
                    self.assertEqual(metric['pixels'], 0)

    def test_split_layers_rejects_unknown_model_and_negative_overlap(self):
        source = np.zeros((10, 1, 4), dtype=np.uint8)
        with self.assertRaises(ValueError):
            split_layers(source, 3, 6, 1, 1, 'arc')
        with self.assertRaises(ValueError):
            split_layers(source, 3, 6, 1, 1, 'base', -1)

    def test_measure_native_recovers_generated_parameters(self):
        source = np.array(make_portrait())
        layers = split_layers(source, 330, 700, 7, 20, 'base', 30)
        rep = measure(*layers)
        self.assertEqual(rep['canvas'], [1024, 1024])
        self.assertEqual(rep['waist_covers_chest_band'], 1.0)
        self.assertEqual(rep['layers']['head']['bottom_ramp'], 7)
        self.assertEqual(rep['suggested'], {'overlap': 30, 'feather_chest': 7, 'note': rep['suggested']['note']})
        self.assertTrue(rep['overlaps']['chest/waist'])
        legacy = measure(*split_layers(source, 330, 700, 7, 20, 'legacy'))
        self.assertLess(legacy['waist_covers_chest_band'], 0.5)

    def test_measure_loader_reads_bitfield_bmp_and_png(self):
        rgba = np.zeros((4, 3, 4), dtype=np.uint8)
        rgba[1, 2] = [10, 20, 30, 128]
        bgra = rgba[::-1][:, :, [2, 1, 0, 3]].tobytes()
        off = 14 + 40 + 12
        header = struct.pack('<2sIHHI', b'BM', off + len(bgra), 0, 0, off)
        dib = struct.pack('<IiiHHIIiiII', 40, 3, 4, 1, 32, 3, len(bgra), 0, 0, 0, 0)
        masks = struct.pack('<III', 0x00FF0000, 0x0000FF00, 0x000000FF)
        with tempfile.TemporaryDirectory() as tmp:
            bmp = pathlib.Path(tmp) / 'n.bmp'
            bmp.write_bytes(header + dib + masks + bgra)
            np.testing.assert_array_equal(load_rgba(str(bmp)), rgba)
            png = pathlib.Path(tmp) / 'n.png'
            Image.fromarray(rgba).save(png)
            np.testing.assert_array_equal(load_rgba(str(png)), rgba)

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

