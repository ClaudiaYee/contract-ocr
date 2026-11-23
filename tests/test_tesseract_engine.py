"""Tesseract edition engine: interface, Chinese word joining, confusions, stamp removal. Synthetic images only."""
import io
from pathlib import Path
import shutil
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
import engine


class TesseractEngineTests(unittest.TestCase):
    def test_interface_matches_pipeline(self):
        self.assertFalse(engine.server_available()); self.assertFalse(engine.date_vote_available()); self.assertIsNone(engine.int8_detector())
        self.assertEqual(engine.KEY_LINES, {'fast': 0, 'balanced': 0, 'fine': 0})
        for name in ('recognize_image', 'read_crops', 'recognize_lines', 'pixmap_array', 'initialize_engine', 'model_tag'):
            self.assertTrue(callable(getattr(engine, name)))
        self.assertEqual(engine.recognize_lines([]), [])

    def test_chinese_words_joined_latin_and_columns_spaced(self):
        self.assertEqual(engine.join_words(['信', '息', '系', '统']), '信息系统')
        self.assertEqual(engine.join_words(['SOC', '2', '类型', '二']), 'SOC 2类型二')
        boxes = [(0, 0, 60, 20), (62, 0, 60, 20), (300, 0, 80, 20)]   # third word after a column gap
        self.assertEqual(engine.join_words(['订单', '管理', '华南'], boxes), '订单管理 华南')

    def test_letter_digit_confusions_fixed_without_touching_codes(self):
        cases = {'提供S0C2类型二报告': '提供SOC2类型二报告', 'IS027001': 'ISO27001', '人民币18O,000.00元': '人民币180,000.00元', '180.000.00元': '180,000.00元',
                 'XBar V50 Kit, W70, B8650': 'XBar V50 Kit, W70, B8650', 'ISO 27001：2022': 'ISO 27001:2022', '第1，2条': '第1，2条'}
        for raw, expected in cases.items():
            self.assertEqual(engine.fix_confusables(raw), expected, raw)

    def test_missing_tesseract_has_a_clear_message(self):
        saved = (engine._CMD, engine.MODEL_ROOT)
        try:
            engine._CMD = None; engine.MODEL_ROOT = Path('/nonexistent')
            with unittest.mock.patch.dict('os.environ', {'CONTRACT_OCR_TESSERACT': ''}), unittest.mock.patch('shutil.which', return_value=None), \
                 unittest.mock.patch('engine.Path.is_file', return_value=False):
                with self.assertRaisesRegex(RuntimeError, '未找到 Tesseract'):
                    engine.tesseract_command()
        finally:
            engine._CMD, engine.MODEL_ROOT = saved

    @unittest.skipUnless(shutil.which('tesseract'), 'Tesseract not installed on this machine')
    def test_reads_synthetic_contract_lines_and_removes_seal(self):
        from PIL import Image, ImageDraw, ImageFont
        fonts = [Path('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'), Path('C:/Windows/Fonts/simsun.ttc')]
        font_path = next((p for p in fonts if p.exists()), None)
        if not font_path:
            self.skipTest('no Chinese font')
        font = ImageFont.truetype(str(font_path), 40, index=2 if 'Noto' in font_path.name else 0)
        image = Image.new('RGB', (1654, 900), 'white'); draw = ImageDraw.Draw(image)
        draw.text((80, 100), '服务内容：信息系统一般控制测试', font=font, fill='black')
        draw.text((80, 200), '合同金额：人民币180,000.25元', font=font, fill='black')
        draw.ellipse([900, 60, 1260, 420], outline=(215, 40, 40), width=8)
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        result = engine.recognize_image(buffer.getvalue(), 'balanced')
        compact = result['text'].replace(' ', '')
        self.assertIn('信息系统一般控制', compact); self.assertIn('180,000.25', compact)
        self.assertEqual(result['stampsRemoved'], 1); self.assertEqual(result['ocrModel'], engine.TESSERACT_LABEL)
        self.assertTrue(all({'text', 'score', 'x0', 'y0', 'x1', 'y1'} <= set(line) for line in result['lines']))
        self.assertTrue(engine.model_tag('balanced').startswith('tesseract-5'))


import unittest.mock  # noqa: E402

if __name__ == '__main__':
    unittest.main()
