"""Packaged-executable self-test for the no-OCR assistant edition (synthetic documents only, never client data).

Usage: python native/smoke_nocr.py <ContractOCR.exe>   (any command that starts the service also works)
Checks: digital PDF text layer, Word (.docx) upload and 补充 Word 版, images / scanned PDFs saved without
text, the OCR endpoint disabled, analysis and backup still working.
"""
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def make_docx(paragraphs, table=None):
    def p(text):
        return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    body = ''.join(p(t) for t in paragraphs)
    if table:
        rows = ''.join('<w:tr>' + ''.join(f'<w:tc>{p(c)}</w:tc>' for c in row) + '</w:tr>' for row in table)
        body += f'<w:tbl>{rows}</w:tbl>'
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', document)
    return buffer.getvalue()


def main():
    from PIL import Image, ImageDraw
    skip_pdf = os.environ.get('SMOKE_SKIP_PDF') == '1'   # developer machines without PyMuPDF only; never set for the EXE
    if not skip_pdf:
        import pymupdf as fitz
    command = shlex.split(sys.argv[1]) if len(sys.argv) > 1 and ' ' in sys.argv[1] else [str(Path(sys.argv[1]).resolve())]
    port = os.environ.get('CONTRACT_OCR_PORT', '18765')
    with tempfile.TemporaryDirectory() as temporary:
        env = {**os.environ, 'CONTRACT_OCR_DATA_DIR': str(Path(temporary) / 'data'), 'CONTRACT_OCR_DIAGNOSTICS': '1', 'CONTRACT_OCR_WORKERS': '2', 'CONTRACT_OCR_CLOUD_DEFAULT': ''}
        process = subprocess.Popen(command + ['--no-browser'], env=env)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        origin = f'http://127.0.0.1:{port}'

        def request(path, data=None, headers=None):
            return opener.open(urllib.request.Request(origin + path, data=data, headers=headers or {}), timeout=120).read()

        try:
            for _ in range(120):
                try:
                    if json.loads(request('/api/health'))['application'] == 'ContractOCR':
                        break
                except OSError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('Executable exited during startup')
                time.sleep(.5)
            else:
                raise RuntimeError('Service did not start')
            html = request('/').decode('utf-8')
            token = json.loads(re.search(r'window\.__LOCAL_OCR_TOKEN=("[^"\\]*");', html)[1])
            assert 'myContracts' in html and 'id="ocrMode"' not in html and 'wordFileInput' in html
            api = {'Origin': origin, 'X-OCR-Token': token}

            def upload(name, data):
                job_id = json.loads(request('/api/jobs', data=data, headers={**api, 'Content-Type': 'application/octet-stream', 'X-Filename': name, 'X-OCR-Mode': 'balanced'}))['id']
                for _ in range(480):
                    job = json.loads(request('/api/jobs/' + job_id))
                    if job['status'] in ('done', 'error'):
                        assert job['status'] == 'done', (name, job.get('error'))
                        return job['result']
                    time.sleep(.25)
                raise RuntimeError(name + ' did not finish')

            try:
                request('/api/ocr', data=b'x', headers={**api, 'Content-Type': 'application/octet-stream'}); raise AssertionError('OCR endpoint must be off')
            except urllib.error.HTTPError as error:
                assert error.code == 400 and '不含 OCR' in error.read().decode('utf-8'), error.code
            # 1) digital PDF: text layer
            expected = 5 if not skip_pdf else 2
            if not skip_pdf:
                pdf = fitz.open(); page = pdf.new_page(width=595, height=842)
                page.insert_text((60, 80), 'AUDIT CONTRACT ITGC SOX 2025-09-11', fontsize=14)
                text_pdf = pdf.tobytes(); pdf.close()
                for result in [upload('synthetic-text.pdf', text_pdf) for _ in range(2)]:
                    assert 'AUDIT CONTRACT' in result['rawText'] and result['textSource'] == 'pdf-text' and not result['textMissing'] and not result.get('ocrModel'), result
            # 2) Word upload: paragraphs + table
            docx = make_docx(['信息系统审计服务协议', '服务内容：开展信息系统一般控制（ITGC）测试和渗透测试。'], [['序号', '系统名称'], ['1', '订单管理系统']])
            word = upload('synthetic.docx', docx)
            assert word['textSource'] == 'word' and not word['textMissing'] and 'ITGC' in word['rawText'] and '订单管理系统' in word['rawText'], word['rawText']
            # 3) image and scanned PDF: saved without text, with the Word hint
            image = Image.new('RGB', (1000, 600), 'white'); ImageDraw.Draw(image).rectangle([100, 100, 900, 140], fill='black')
            buffer = io.BytesIO(); image.save(buffer, format='PNG')
            picture = upload('scan.png', buffer.getvalue())
            checked = [picture]
            if not skip_pdf:
                scanned_pdf = fitz.open(); page = scanned_pdf.new_page(width=595, height=842); page.insert_image(page.rect, stream=buffer.getvalue()); checked.append(upload('scan.pdf', scanned_pdf.tobytes())); scanned_pdf.close()
            for result in checked:
                assert result['textMissing'] and not result['rawText'].strip() and any('Word' in n['message'] for n in result['reviewNotes']), result
            # 4) 补充 Word 版: text only, nothing stored
            filled = json.loads(request('/api/docx-text', data=docx, headers={**api, 'Content-Type': 'application/octet-stream'}))
            assert 'ITGC' in filled['text'] and filled['lines'] >= 3
            try:
                request('/api/docx-text', data=b'not a docx', headers={**api, 'Content-Type': 'application/octet-stream'}); raise AssertionError('bad docx accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 422
            # 5) contracts saved, analysis completes, backup complete
            contracts = json.loads(request('/api/contracts'))
            assert len(contracts) == expected, len(contracts)
            for _ in range(240):
                states = [c.get('analysisStatus') for c in json.loads(request('/api/contracts'))]
                if all(s in ('done', 'error') for s in states):
                    break
                time.sleep(.25)
            assert 'error' not in states, states
            backup = request('/api/backup', data=b'', headers=api)
            with zipfile.ZipFile(io.BytesIO(backup)) as archive:
                assert archive.testzip() is None
                assert len([n for n in archive.namelist() if n.startswith('contracts/')]) == expected
            Path('packaged-validation.json').write_text(json.dumps({'edition': 'assistant-no-ocr', 'syntheticOnly': True, 'contracts': 5}, ensure_ascii=False), encoding='utf-8')
            print('PASS no-OCR edition: PDF text layer, Word upload / 补充 Word 版, scans saved without text, OCR off, analysis, backup')
        finally:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    main()
