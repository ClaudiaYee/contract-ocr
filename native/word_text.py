"""Read the text of a Word (.docx) contract without OCR, using only the standard library.

Paragraphs become lines; table rows become one line with cells separated by two spaces, so the
same keyword rules as for PDFs apply. Headers/footers, comments and tracked deletions are skipped.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MAX_XML = 60 * 1024 * 1024   # uncompressed word/document.xml limit (zip-bomb guard)


class WordError(ValueError):
    pass


def _deleted_ids(root):
    return {id(t) for d in root.iter(W + 'del') for t in d.iter(W + 't')}


def docx_lines(data: bytes) -> list[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise WordError('不是有效的 Word（.docx）文件；旧版 .doc 请先另存为 .docx')
    with archive:
        try:
            info = archive.getinfo('word/document.xml')
        except KeyError:
            raise WordError('Word 文件缺少正文（word/document.xml）')
        if info.file_size > MAX_XML:
            raise WordError('Word 正文过大，请拆分后上传')
        root = ET.fromstring(archive.read(info))
    deleted = _deleted_ids(root)
    body = root.find(W + 'body')
    if body is None:
        return []
    lines: list[str] = []

    def text_of(node):
        parts = []
        for el in node.iter():
            if el.tag == W + 't' and el.text and id(el) not in deleted:
                parts.append(el.text)
            elif el.tag == W + 'tab':
                parts.append(' ')
            elif el.tag in (W + 'br', W + 'cr'):
                parts.append('\n')
        return ''.join(parts)

    def walk(container):
        for child in container:
            if child.tag == W + 'p':
                lines.extend(text_of(child).split('\n'))
            elif child.tag == W + 'tbl':
                for row in child.iter(W + 'tr'):
                    cells = [' '.join(text_of(p).strip() for p in cell.iter(W + 'p')).strip() for cell in row.findall(W + 'tc')]
                    if any(cells):
                        lines.append('  '.join(c for c in cells if c))
            elif child.tag == W + 'sdt':     # content controls wrap paragraphs / tables
                content = child.find(W + 'sdtContent')
                if content is not None:
                    walk(content)
    walk(body)
    return [line.rstrip() for line in lines if line.strip()]
