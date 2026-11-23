"""Build-time check for the Tesseract edition: the bundled Tesseract runs and reads Chinese contract text.

Uses a synthetic printed contract snippet only (no client data). Verifies:
  * tesseract.exe is found (bundle folder, CONTRACT_OCR_TESSERACT, PATH or the default install) and is version 5+
  * chi_sim and eng language data are present
  * every recognition mode reads a date and an amount correctly through engine.recognize_image
"""
import io
import json
from pathlib import Path
import re
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402

command = engine.tesseract_command()
version = engine.tesseract_version()
if not re.match(r'^(\d+)', version) or int(re.match(r'^(\d+)', version)[1]) < 5:
    raise SystemExit(f'Tesseract 5 or newer is required, found {version!r} at {command}')
import pytesseract  # noqa: E402
languages = set(pytesseract.get_languages(config=''))
missing = {'chi_sim', 'eng'} - languages
if missing:
    raise SystemExit('Tesseract language data missing: ' + ', '.join(sorted(missing)) + f' (have: {sorted(languages)})')

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
fonts = [Path(p) for p in ('C:/Windows/Fonts/simsun.ttc', 'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf', '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc')]
font_path = next((path for path in fonts if path.exists()), None)
if not font_path:
    raise SystemExit('No Chinese font found to draw the synthetic check image')
font = ImageFont.truetype(str(font_path), 44, index=2 if 'Noto' in font_path.name else 0)
lines, expected = ['签订日期：2026年11月6日', '合同金额：人民币180,000.25元', '服务内容：信息系统一般控制测试'], ['2026年11月6日', '180,000.25', '信息系统一般控制']
image = Image.new('RGB', (1200, 360), 'white')
draw = ImageDraw.Draw(image)
for index, line in enumerate(lines):
    draw.text((40, 40 + index * 100), line, fill='black', font=font)
buffer = io.BytesIO(); image.save(buffer, format='PNG')

report = {'tesseract': command, 'version': version, 'languages': sorted(languages)}
for mode in ('fast', 'balanced', 'fine'):
    result = engine.recognize_image(buffer.getvalue(), mode)
    compact = re.sub(r'\s+', '', result['text'])
    report[mode] = {'model': result['ocrModel'], 'text': result['text'], 'seconds': result['seconds']}
    for item in expected:
        if item not in compact:
            raise SystemExit(f'{mode} ({result["ocrModel"]}) misread {item!r}: {result["text"]!r}')
print(json.dumps(report, ensure_ascii=False, indent=1))
print('Tesseract OCR check passed.')
