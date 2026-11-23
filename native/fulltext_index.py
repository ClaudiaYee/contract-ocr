"""Encrypted full-text search index stored next to the shared master table.

The master table only has short columns (keywords, tags…), so a word that appears only in a
contract's body (e.g. 「消费」) could not be found by colleagues who do not have that contract
locally. This module stores, per contract, a Bloom filter of keyed hashes (HMAC-SHA256) of every
1–3 character fragment of the normalised full text:

* any word can be searched (a longer word must have all of its 3-character fragments present);
* the file holds only bits — no text, no word list, no contract ID in clear;
* results are "probably contains": false positives are rare (about 1 in 2000 per contract per word).

Limits: someone who has this tool can test whether a chosen word occurs in a contract (that is the
purpose of search); the text itself cannot be read back from the index.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import struct
import tempfile
import unicodedata
from pathlib import Path

KEY = b'contract-ocr/fulltext-index/v1/7f3c1e9a5b2d4c8e'
MAGIC = b'COIX1'
MAX_GRAM = 3
BITS_PER_ITEM = 16
HASHES = 11
MIN_BITS = 1 << 15
_CACHE: dict[str, tuple[float, int, int, int, bytes]] = {}


def normalize(text: str) -> str:
    """Same idea as the search box: case/width-insensitive, ignore spaces and punctuation (OCR inserts both)."""
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', str(text or '')).casefold())


def _grams(text: str) -> set[str]:
    out = set()
    for size in range(1, MAX_GRAM + 1):
        for i in range(0, max(0, len(text) - size + 1)):
            out.add(text[i:i + size])
    return out


def _positions(gram: str, bits: int, hashes: int) -> list[int]:
    digest = hmac.new(KEY, gram.encode('utf-8'), hashlib.sha256).digest()
    a, b = struct.unpack_from('<QQ', digest)
    return [(a + i * b) % bits for i in range(hashes)]


def build(text: str) -> bytes:
    grams = _grams(normalize(text))
    bits = MIN_BITS
    while bits < len(grams) * BITS_PER_ITEM:
        bits <<= 1
    array = bytearray(bits // 8)
    for gram in grams:
        for p in _positions(gram, bits, HASHES):
            array[p >> 3] |= 1 << (p & 7)
    return MAGIC + struct.pack('<IB', bits, HASHES) + bytes(array)


def _parse(blob: bytes) -> tuple[int, int, bytes]:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 5:
        raise ValueError('not a full-text index')
    bits, hashes = struct.unpack_from('<IB', blob, len(MAGIC))
    data = blob[len(MAGIC) + 5:]
    if len(data) * 8 != bits:
        raise ValueError('damaged full-text index')
    return bits, hashes, data


def contains(blob_or_parsed, term: str) -> bool:
    bits, hashes, data = _parse(blob_or_parsed) if isinstance(blob_or_parsed, (bytes, bytearray)) else blob_or_parsed
    t = normalize(term)
    if not t:
        return False
    pieces = [t] if len(t) <= MAX_GRAM else [t[i:i + MAX_GRAM] for i in range(len(t) - MAX_GRAM + 1)]
    return all(all(data[p >> 3] >> (p & 7) & 1 for p in _positions(piece, bits, hashes)) for piece in pieces)


def index_dir(master: Path) -> Path:
    return master.with_name(master.stem + '.检索索引')


def file_for(folder: Path, contract_id: str) -> Path:
    # The file name is a keyed hash of the contract ID, so the folder does not list contract IDs either.
    return folder / (hmac.new(KEY, ('id:' + contract_id).encode('utf-8'), hashlib.sha256).hexdigest()[:32] + '.idx')


def write(master: Path, contract_id: str, text: str) -> None:
    folder = index_dir(master)
    folder.mkdir(exist_ok=True)
    target = file_for(folder, contract_id)
    handle, temporary = tempfile.mkstemp(prefix='.idx-', dir=folder)
    try:
        with os.fdopen(handle, 'wb') as file:
            file.write(build(text))
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(master: Path, contract_id: str):
    """Parsed index for a contract, or None when that contract has no index yet. Cached by file mtime/size."""
    path = file_for(index_dir(master), contract_id)
    try:
        stat = path.stat()
    except OSError:
        return None
    key = str(path)
    cached = _CACHE.get(key)
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2:]
    try:
        parsed = _parse(path.read_bytes())
    except (OSError, ValueError):
        return None
    _CACHE[key] = (stat.st_mtime, stat.st_size, *parsed)
    return parsed
