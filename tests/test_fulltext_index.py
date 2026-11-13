"""Encrypted full-text index: colleagues can search words that occur only in a contract's body, without the text being stored on the share. Synthetic text only."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
import excel_table as e
import fulltext_index as f

TEXT = '服务内容：对示例客户消费电子业务的信息系统一般控制进行评估，包括逻辑访问管理、变更管理。本次评估不包括内部审计。SOC 2 类型二。'


class FullTextIndexTests(unittest.TestCase):
    def test_finds_words_and_ignores_spacing_and_punctuation(self):
        index = f.build(TEXT)
        for word in ['消费', '消费电子', '逻辑 访问管理', '信息系统一般控制', 'soc2', 'SOC 2 类型二', '变更管理。']:
            self.assertTrue(f.contains(index, word), word)
        for word in ['零售', '供应链', '财务报表审计', 'ITGC']:
            self.assertFalse(f.contains(index, word), word)
        self.assertFalse(f.contains(index, '  '))

    def test_index_holds_no_readable_text(self):
        index = f.build(TEXT)
        for word in ['消费', '逻辑访问', '示例客户', 'SOC']:
            for encoding in ('utf-8', 'utf-16-le', 'gb18030'):
                self.assertNotIn(word.encode(encoding), index)
                self.assertNotIn(word.lower().encode(encoding), index)

    def test_file_name_hides_contract_id_and_damaged_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            master = Path(folder) / e.MASTER_NAME
            f.write(master, 'job_secret_id', TEXT)
            names = [p.name for p in f.index_dir(master).iterdir()]
            self.assertEqual(len(names), 1); self.assertNotIn('secret', names[0])
            self.assertTrue(f.contains(f.load(master, 'job_secret_id'), '消费'))
            self.assertIsNone(f.load(master, 'unknown'))
            f.file_for(f.index_dir(master), 'job_secret_id').write_bytes(b'garbage')
            self.assertIsNone(f.load(master, 'job_secret_id'))

    def test_cloud_search_uses_index_for_words_outside_the_table(self):
        with tempfile.TemporaryDirectory() as folder:
            e.merge_into_master(folder, [{'项目名称': '他人项目', '上传者ID': '同事乙', '原始关键词': 'ITGC', '合同ID': 'remote-1'},
                                         {'项目名称': '没有索引的项目', '合同ID': 'remote-2'}])
            f.write(e.master_path(folder), 'remote-1', TEXT)
            rows = e.search_master(folder, '消费', {}, None, set(), set())['rows']
            self.assertEqual([r['row']['合同ID'] for r in rows], ['remote-1'])
            self.assertEqual(rows[0]['textTerms'], ['消费'])
            both = e.search_master(folder, 'ITGC 消费', {}, None, set(), set())['rows']
            self.assertEqual(both[0]['textTerms'], ['消费'], 'table hits are not reported as full-text hits')
            self.assertEqual(e.search_master(folder, '消费 零售', {}, None, set(), set())['rows'], [])
            self.assertEqual(len(e.search_master(folder, '消费 零售', {}, None, set(), set(), True)['rows']), 1)


if __name__ == '__main__':
    unittest.main()
