"""No-OCR assistant edition: Word text, images saved without text, no OCR runtime loaded. Synthetic files only."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
import documents
from word_text import docx_lines, WordError
from smoke_nocr import make_docx, W_NS


class WordTextTests(unittest.TestCase):
    def test_paragraphs_and_table_rows(self):
        data = make_docx(['信息系统审计服务协议', '服务内容：开展 ITGC 测试。'], [['序号', '系统名称', '用途'], ['1', '订单管理系统', '订单审批']])
        self.assertEqual(docx_lines(data), ['信息系统审计服务协议', '服务内容：开展 ITGC 测试。', '序号  系统名称  用途', '1  订单管理系统  订单审批'])

    def test_tracked_deletions_are_not_text(self):
        doc = (f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>保留</w:t></w:r><w:del><w:r><w:delText>删除</w:delText></w:r></w:del>'
               f'<w:del><w:r><w:t>旧文字</w:t></w:r></w:del></w:p></w:body></w:document>')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', doc)
        self.assertEqual(docx_lines(buffer.getvalue()), ['保留'])

    def test_bad_files(self):
        with self.assertRaises(WordError):
            docx_lines(b'not a zip')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('other.xml', '<x/>')
        with self.assertRaises(WordError):
            docx_lines(buffer.getvalue())


class NoOcrDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.assertFalse(documents.OCR_ENABLED, 'this branch ships without OCR')

    def run_doc(self, name, data):
        path = self.root / name; path.write_bytes(data)
        return documents.recognize_document(str(path), name, 'balanced', str(self.root / (name + '.progress.json')))

    def test_word_contract_has_text_for_keyword_analysis(self):
        result = self.run_doc('合同.docx', make_docx(['服务内容：开展信息系统一般控制（ITGC）测试和渗透测试。']))
        self.assertEqual(result['textSource'], 'word'); self.assertFalse(result['textMissing']); self.assertFalse(result['ocrUsed'])
        self.assertIn('ITGC', result['rawText']); self.assertEqual(result['layoutPages'][0]['rawEnd'], len(result['rawText']))
        json.dumps(result)

    def test_image_is_saved_without_text_and_asks_for_word(self):
        from PIL import Image
        buffer = io.BytesIO(); Image.new('RGB', (800, 600), 'white').save(buffer, format='PNG')
        result = self.run_doc('scan.png', buffer.getvalue())
        self.assertTrue(result['textMissing']); self.assertEqual(result['rawText'], '')
        self.assertIn('Word', result['reviewNotes'][0]['message']); self.assertIn('不含 OCR', result['reviewNotes'][0]['message'])
        self.assertNotIn('rapidocr_onnxruntime', sys.modules, 'no OCR runtime is loaded')
        self.assertNotIn('onnxruntime', sys.modules)


if __name__ == '__main__':
    unittest.main()
