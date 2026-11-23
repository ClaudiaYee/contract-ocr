"""Red seals are removed before OCR; red body text, small red marks and dark text under the seal are kept. Synthetic images only."""
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
from stamp_removal import red_mask, remove_stamps

RED = (215, 40, 40)


def page():
    return Image.new('RGB', (1654, 2339), 'white')


def bgr(img):
    return np.asarray(img)[:, :, ::-1].copy()


class StampRemovalTests(unittest.TestCase):
    def test_round_square_and_oval_seals_are_removed_but_text_under_them_kept(self):
        img = page(); d = ImageDraw.Draw(img)
        d.rectangle([150, 400, 1200, 430], fill=(20, 20, 20))            # black text line under the seal
        d.ellipse([500, 250, 860, 610], outline=RED, width=7); d.regular_polygon((680, 430, 40), 5, fill=RED)
        for i in range(10):
            d.rectangle([560 + i * 25, 300, 575 + i * 25, 330], fill=RED)  # seal characters along the ring
        d.rectangle([1000, 900, 1260, 1160], outline=RED, width=8)          # square seal
        d.ellipse([200, 1400, 600, 1660], outline=RED, width=7)            # oval seal
        array = bgr(img)
        out, removed = remove_stamps(array)
        self.assertEqual(removed, 3)
        self.assertEqual(int(red_mask(out).sum()), 0)
        dark = array.max(axis=2) < 90
        self.assertTrue(np.array_equal(out[dark], array[dark]), 'black text under the seal is untouched')
        self.assertGreater(int(red_mask(array).sum()), 0, 'input not modified')

    def test_red_body_text_and_small_marks_are_kept(self):
        img = page(); d = ImageDraw.Draw(img)
        d.rectangle([150, 150, 1450, 185], fill=RED)                        # red revision line
        for i in range(4):
            d.rectangle([150, 260 + i * 52, 1400, 290 + i * 52], fill=(200, 30, 30))  # red paragraph
        d.rectangle([150, 560, 175, 585], fill=RED)                         # small red tick
        array = bgr(img)
        out, removed = remove_stamps(array)
        self.assertEqual(removed, 0)
        self.assertTrue(np.array_equal(out, array))

    def test_solid_red_block_and_dark_red_are_not_seals(self):
        img = page(); d = ImageDraw.Draw(img)
        d.rectangle([300, 300, 600, 600], fill=RED)                         # filled logo / highlight
        d.ellipse([800, 300, 1150, 650], outline=(90, 10, 10), width=8)     # dark red: treated as text colour
        out, removed = remove_stamps(bgr(img))
        self.assertEqual(removed, 0)

    def test_page_without_red_is_returned_as_is(self):
        array = bgr(page())
        out, removed = remove_stamps(array)
        self.assertIs(out, array); self.assertEqual(removed, 0)


if __name__ == '__main__':
    unittest.main()
