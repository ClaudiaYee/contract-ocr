"""OCR engine for the Tesseract edition (小秘书 Tesseract 版), in an importable module for frozen multiprocessing.

Pages and images are read by Tesseract 5 (LSTM, chi_sim + eng) through pytesseract, the OCR route of the
PDF skill. The public functions keep the PP-OCR engine's interface, so the document pipeline, checkpoints,
cache keys and stamp removal work unchanged:

* Tesseract puts spaces between Chinese characters; they are removed (spaces stay only between Latin
  letters / digits), otherwise keyword rules would not match (信 息 系 统 -> 信息系统).
* There is no second recognizer, so the fine-mode key-line review and the three-model date vote are off
  (server_available() / date_vote_available() return False).
* Measured on the synthetic 6-page contract set: 92.6% character accuracy vs 99.6% for PP-OCRv4 with
  stamp removal; dates, amounts and table cells are the most frequent misses. Check key fields.
"""
from pathlib import Path
import io
import os
import re
import shutil
import sys
import time

LANG = 'chi_sim+eng'
TESSERACT_LABEL = 'Tesseract 5 (chi_sim+eng)'
ENGINES = {}           # kept for interface compatibility
FILES = {}             # no model files of our own: Tesseract brings its tessdata
MODEL_ROOT = Path(sys._MEIPASS) / 'tesseract' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent / 'models' / 'tesseract'
INT8_DET = None
KEY_LINES = {'fast': 0, 'balanced': 0, 'fine': 0}
LABELS = {'tesseract': TESSERACT_LABEL, 'v4': TESSERACT_LABEL, 'v5-server': TESSERACT_LABEL, 'date-vote': TESSERACT_LABEL}
TEXT_SCORE = 0.15
UNCERTAIN = 0.7       # Tesseract word confidences run lower than PP-OCR scores
_CMD = None


def int8_detector():
    return None


def server_available():
    return False


def date_vote_available():
    return False


def tesseract_command():
    """Bundled tesseract.exe (packaged app) > CONTRACT_OCR_TESSERACT > PATH > default Windows install."""
    global _CMD
    if _CMD:
        return _CMD
    candidates = [MODEL_ROOT / ('tesseract.exe' if os.name == 'nt' else 'tesseract'), os.environ.get('CONTRACT_OCR_TESSERACT'),
                  shutil.which('tesseract'), r'C:\Program Files\Tesseract-OCR\tesseract.exe']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            _CMD = str(candidate)
            tessdata = Path(_CMD).parent / 'tessdata'
            if (tessdata / 'chi_sim.traineddata').is_file():
                os.environ['TESSDATA_PREFIX'] = str(tessdata)
            return _CMD
    raise RuntimeError('未找到 Tesseract OCR 引擎（tesseract.exe）。请重新安装本程序，或联系管理员。')


def _pytesseract():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tesseract_command()
    os.environ['OMP_THREAD_LIMIT'] = str(thread_count())   # Tesseract's own threads per worker process
    return pytesseract


def tesseract_version():
    try:
        return str(_pytesseract().get_tesseract_version())
    except Exception:
        return 'unknown'


def model_tag(mode):
    """Model set a mode uses on this installation; part of cache/checkpoint keys."""
    return 'tesseract-' + re.sub(r'[^0-9A-Za-z.]+', '', tesseract_version()) + '-' + LANG


def engine_for(mode):
    return 'tesseract', _pytesseract()


def initialize_engine():
    _pytesseract().get_tesseract_version()


def thread_count():
    try:
        value = int(os.environ.get('CONTRACT_OCR_THREADS', '0'))
    except ValueError:
        value = 0
    return value if 1 <= value <= 8 else max(1, min(2, (os.cpu_count() or 2) // 2))


# Letter/digit confusions inside one Latin/number token, e.g. S0C2 -> SOC2, IS0 -> ISO,
# 18O,000 -> 180,000, Page 1l -> Page 11, 180.000.00 -> 180,000.00.
def fix_confusables(text):
    def token(match):
        value = match.group(0)
        if sum(ch.isalpha() for ch in value) >= 2:
            value = re.sub(r'(?<=[A-Za-z])0(?=[A-Za-z]|$)', 'O', value)
        value = re.sub(r'(?<=\d)[Oo](?=[\d,.]|$)', '0', value)
        value = re.sub(r'(?<=\d)[lI](?=\d|$)', '1', value)
        return value
    text = re.sub(r'[A-Za-z0-9]+', token, str(text))
    text = re.sub(r'(?<![A-Za-z])IS0(?=\s?\d{4,5})', 'ISO', text)
    text = re.sub(r'(?<!\d)(\d{1,3})((?:\.\d{3})+)\.(\d{2})(?!\d)', lambda m: m.group(1) + m.group(2).replace('.', ',') + '.' + m.group(3), text)
    text = re.sub(r'(?<=\d)[Oo](?=[,.]\d)|(?<=[\d,])[Oo](?=\d)', '0', text)
    text = re.sub(r'(?<=\d)：(?=\d)', ':', text)
    return re.sub(r'(?<=\d)，(?=\d{3}(?!\d))', ',', text)


_LATIN = re.compile(r'[A-Za-z0-9]')


def join_words(words, boxes=None):
    """Join Tesseract words of one line: a space between two Latin/number words, or where there is a
    real gap (table columns, label/value); Chinese characters of one phrase are joined without spaces."""
    out = ''
    for i, word in enumerate(words):
        if out:
            gap = False
            if boxes:
                (px, _, pw, ph), (x, _, _, h) = boxes[i - 1], boxes[i]
                gap = x - (px + pw) > 0.9 * max(ph, h)
            if gap or (_LATIN.match(word[0]) and _LATIN.match(out[-1])):
                out += ' '
        out += word
    return out


def _lines_from_data(data, scale=1.0):
    groups = {}
    for i, word in enumerate(data['text']):
        word = str(word).strip()
        try:
            conf = float(data['conf'][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 0:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        x, y, w, h = (data[k][i] / scale for k in ('left', 'top', 'width', 'height'))
        g = groups.setdefault(key, {'words': [], 'boxes': [], 'confs': [], 'x0': x, 'y0': y, 'x1': x + w, 'y1': y + h})
        g['words'].append(word); g['boxes'].append((x, y, w, h)); g['confs'].append(conf)
        g['x0'] = min(g['x0'], x); g['y0'] = min(g['y0'], y); g['x1'] = max(g['x1'], x + w); g['y1'] = max(g['y1'], y + h)
    items = []
    for g in groups.values():
        raw = join_words(g['words'], g['boxes'])
        if not raw.strip():
            continue
        score = sum(g['confs']) / len(g['confs']) / 100
        if score < TEXT_SCORE:
            continue
        fixed = fix_confusables(raw)
        items.append({'text': fixed, **({'ocrRaw': raw} if fixed != raw else {}), 'score': round(score, 4), 'x0': g['x0'], 'y0': g['y0'], 'x1': g['x1'], 'y1': g['y1']})
    return items


def _to_rgb_image(content):
    import numpy as np
    from PIL import Image, ImageOps
    if isinstance(content, np.ndarray):
        if content.shape[0] * content.shape[1] > 32_000_000:
            raise ValueError('图片超过3200万像素，请降低分辨率')
        return content
    Image.MAX_IMAGE_PIXELS = 32_000_000
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > 32_000_000:
            raise ValueError('图片超过3200万像素，请降低分辨率')
        image = ImageOps.exif_transpose(source).convert('RGB')
        return np.asarray(image)[:, :, ::-1].copy()   # BGR, like PyMuPDF pages


def recognize_image(content, mode: str):
    import numpy as np
    from PIL import Image
    tess = _pytesseract()
    started = time.perf_counter()
    array = _to_rgb_image(content)
    # 去除红色公章 / 合同专用章（只处理印章形状的红色区域，红色正文保留）
    from stamp_removal import remove_stamps
    array, stamps_removed = remove_stamps(array)
    image = Image.fromarray(np.ascontiguousarray(array[:, :, ::-1]))
    data = tess.image_to_data(image, lang=LANG, config='--oem 1 --psm 3', output_type=tess.Output.DICT)
    items = _lines_from_data(data)
    from layout_quality import group_rows
    rows = group_rows(items)
    items = [item for row in rows for item in row]
    return {'text': '\n'.join(' '.join(item['text'] for item in row) for row in rows), 'lines': items, 'items': items,
            'seconds': round(time.perf_counter() - started, 3), 'engine': 'native', 'ocrModel': TESSERACT_LABEL, 'stampsRemoved': stamps_removed,
            'uncertain': [item for item in items if item['score'] < UNCERTAIN]}


def read_crops(tag, crops):
    """Single-line crops (BGR arrays) -> [(text, score)] with Tesseract's single-line mode."""
    if not crops:
        return []
    import numpy as np
    from PIL import Image
    tess = _pytesseract()
    out = []
    for crop in crops:
        data = tess.image_to_data(Image.fromarray(np.ascontiguousarray(crop[:, :, ::-1])), lang=LANG, config='--oem 1 --psm 7', output_type=tess.Output.DICT)
        items = _lines_from_data(data)
        out.append((join_words([i['text'] for i in items]), sum(i['score'] for i in items) / len(items) if items else 0.0))
    return out


def recognize_lines(crops):
    return read_crops('tesseract', crops)


def pixmap_array(pixmap):
    """RGB PyMuPDF pixmap -> BGR array without PNG/PPM encoding and decoding."""
    import numpy as np
    channels = pixmap.n
    rows = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.stride)
    array = rows[:, :pixmap.width * channels].reshape(pixmap.height, pixmap.width, channels)
    if channels == 1:
        array = np.repeat(array, 3, axis=2)
    return np.ascontiguousarray(array[:, :, 2::-1])
