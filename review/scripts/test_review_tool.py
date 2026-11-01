"""Protocol tests for review_tool: parsing, SRT conversion, validation, docx rendering."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
import zipfile

import review_tool as app

SAMPLE = app.ROOT / 'examples' / 'sample'


class ReviewToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def sample(self):
        target = self.root / 'sample'
        shutil.copytree(SAMPLE, target, ignore=shutil.ignore_patterns('*.docx'))
        return target / 'transcript.md', target / 'review.json'

    def test_parse_sample_and_old_transcript_without_marker(self):
        transcript, _ = self.sample()
        data = app.parse_transcript(transcript)
        self.assertEqual(data['marker'], 'v1')
        self.assertEqual(len(data['segments']), 10)
        old = self.root / 'old.md'
        old.write_text('# 旧稿\n\n[00:00:00.000 --> 00:00:01.000] 你好\n', encoding='utf-8')
        data = app.parse_transcript(old)
        self.assertIsNone(data['marker'])
        self.assertTrue(data['warnings'])
        bad = self.root / 'bad.md'
        bad.write_text('<!-- transcript-format: v9 -->\n# x\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            app.parse_transcript(bad)
        plain = self.root / 'plain.md'
        plain.write_text('# x\n\n没有时间戳的一行\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            app.parse_transcript(plain)

    def test_srt_converts_to_transcript_beside_it(self):
        srt = self.root / '课程.srt'
        srt.write_text('1\n00:00:01,200 --> 00:00:04,500\n第一句\n第一句续\n\n2\n00:00:05,000 --> 00:00:06,000\nsecond\n', encoding='utf-8')
        path, data = app.normalize_one(srt)
        self.assertEqual(path, self.root / 'transcript.md')
        text = path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(app.FORMAT_MARKER + '\n# 课程\n'))
        self.assertIn('[00:00:01.200 --> 00:00:04.500] 第一句 第一句续', text)
        self.assertEqual(data['segments'][1]['text'], 'second')
        path.write_text('edited', encoding='utf-8')
        with self.assertRaises(ValueError):
            app.normalize_one(srt)

    def test_discover_skips_work_dirs_and_non_transcripts(self):
        (self.root / 'video-a-1234' ).mkdir()
        (self.root / 'video-a-1234' / 'transcript.md').write_text('# a\n\n[00:00:00.000 --> 00:00:01.000] x\n', encoding='utf-8')
        (self.root / '.work' / 'k').mkdir(parents=True)
        (self.root / '.work' / 'k' / 'transcript.md').write_text('# w\n\n[00:00:00.000 --> 00:00:01.000] x\n', encoding='utf-8')
        (self.root / 'README.md').write_text('# readme\n\nprose\n', encoding='utf-8')
        found = [p.relative_to(self.root).as_posix() for p in app.discover(self.root)]
        self.assertEqual(found, ['video-a-1234/transcript.md'])

    def test_validation_rejects_bad_findings(self):
        transcript, findings = self.sample()
        data = app.parse_transcript(transcript)
        good = json.loads(findings.read_text(encoding='utf-8'))
        self.assertEqual(len(app.validate_findings(data, good)), 2)
        cases = {
            'unknown timestamp': dict(good['findings'][0], start='00:00:30.000'),
            'end before start': dict(good['findings'][0], start='00:00:39.400', end='00:00:30.100'),
            'bad type': dict(good['findings'][0], risk_type='合规'),
            'empty advice': dict(good['findings'][0], advice=' '),
            'multiline': dict(good['findings'][0], risk='a\nb'),
            'extra field': dict(good['findings'][0], note='x'),
        }
        for name, row in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                app.validate_findings(data, dict(findings=[row]))
        overlap = dict(good['findings'][0], end='00:00:56.000')
        with self.assertRaises(ValueError):
            app.validate_findings(data, dict(findings=[overlap, good['findings'][1]]))
        with self.assertRaises(ValueError):
            app.validate_findings(data, dict(findings=[], extra=1))
        for risk_type in app.RISK_TYPES:
            app.validate_findings(data, dict(findings=[dict(good['findings'][0], risk_type=risk_type)]))

    def test_conclusion_required_exactly_when_findings_empty(self):
        transcript, findings = self.sample()
        data = app.parse_transcript(transcript)
        good = json.loads(findings.read_text(encoding='utf-8'))
        for bad in (dict(findings=[]), dict(findings=[], conclusion=' '), dict(findings=[], conclusion='a\nb'),
                    dict(good, conclusion='通过')):
            with self.subTest(bad), self.assertRaises(ValueError):
                app.validate_findings(data, bad)
        passed = dict(findings=[], conclusion=' 未发现风险 ')
        self.assertEqual(app.validate_findings(data, passed), [])
        self.assertEqual(app.validate_conclusion(passed), '未发现风险')
        self.assertIsNone(app.validate_conclusion(good))

    def test_legal_scope_reads_chapter_headings(self):
        names = app.legal_scope()
        self.assertIn('诈骗罪', names)
        self.assertTrue(any(n.startswith('互联网信息内容规范（《') for n in names))
        standards = self.root / 'standards.md'
        standards.write_text('# 清单\n\n## 判断总则\n\n1. x\n\n## 一、甲罪（风险类型：刑事）\n\n**法条**：x\n\n'
                             '## 二、乙规范（风险类型：民事）\n\n**（一）《丙办法》**（2020 年）\n\n**（二）《丁规定》**\n\n'
                             '## 三、写法\n\n**（一）《不是法》**\n', encoding='utf-8')
        self.assertEqual(app.legal_scope(standards), ['甲罪', '乙规范（《丙办法》《丁规定》）'])
        (self.root / 'none.md').write_text('# 空\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            app.legal_scope(self.root / 'none.md')

    def test_render_pass_opinion_from_clean_example(self):
        source = app.ROOT / 'examples' / 'clean'
        shutil.copytree(source, self.root / 'clean', ignore=shutil.ignore_patterns('*.docx'))
        transcript = self.root / 'clean' / 'transcript.md'
        data = app.parse_transcript(transcript)
        findings = json.loads((self.root / 'clean' / 'review.json').read_text(encoding='utf-8'))
        resolved = app.validate_findings(data, findings)
        conclusion = app.validate_conclusion(findings)
        target = app.report_path(transcript, data['title'])
        app.render_docx(data, resolved, target, conclusion, scope=['甲罪', '乙规范'])
        xml = zipfile.ZipFile(target).read('word/document.xml').decode('utf-8')
        self.assertNotIn('w:color', xml)
        text = re.sub(r'<[^>]+>', '', xml)
        self.assertIn(app.CONCLUSION_HEADING + conclusion + app.SCOPE_PREFIX + '甲罪、乙规范。', text)
        self.assertNotIn('复核', text)
        paragraphs = re.findall(r'<w:p/>|<w:p>.*?</w:p>|<w:p .*?</w:p>', xml, re.S)
        self.assertEqual(len(paragraphs), 1 + len(data['segments']) + 1 + 3)   # title, segments, blank, heading+body+scope
        self.assertIn('<w:b/>', [p for p in paragraphs if app.CONCLUSION_HEADING in p][0])

    def test_render_colors_problem_spans_and_advice(self):
        transcript, findings = self.sample()
        data = app.parse_transcript(transcript)
        resolved = app.validate_findings(data, json.loads(findings.read_text(encoding='utf-8')))
        target = app.report_path(transcript, data['title'])
        app.render_docx(data, resolved, target)
        self.assertEqual(target.name, '星盘与人生规划入门课（虚构样例）-审查报告.docx')
        xml = zipfile.ZipFile(target).read('word/document.xml').decode('utf-8')
        paragraphs = re.findall(r'<w:p>.*?</w:p>|<w:p .*?</w:p>', xml, re.S)
        # title + 10 segments + 2 opinion lines
        self.assertEqual(len(paragraphs), 13)
        red = [p for p in paragraphs if f'w:val="{app.COLOR_PROBLEM}"' in p]
        self.assertEqual(len(red), 4 + 2)
        for p in paragraphs:
            if '[00:00:14.200' in p or '[00:00:48.700' in p:
                self.assertNotIn('w:color', p)
        opinion = [p for p in paragraphs if '风险提示' in p]
        self.assertEqual(len(opinion), 2)
        for p in opinion:
            self.assertIn(f'w:val="{app.COLOR_ADVICE}"', p)
            text = re.sub(r'<[^>]+>', '', p)
            self.assertTrue(text.startswith('（风险提示：【刑事】') and text.endswith('）'))
            self.assertIn('；处理意见：', text)
        self.assertIn(f'w:eastAsia="{app.FONT_EAST_ASIAN}"', xml)

    def test_render_without_findings_and_without_speech(self):
        transcript, findings = self.sample()
        data = app.parse_transcript(transcript)
        target = self.root / 'clean.docx'
        app.render_docx(data, [], target)
        xml = zipfile.ZipFile(target).read('word/document.xml').decode('utf-8')
        self.assertNotIn('w:color', xml)
        silent = self.root / 'silent.md'
        silent.write_text(app.FORMAT_MARKER + '\n# 静音\n\n' + app.NO_SPEECH + '\n', encoding='utf-8')
        data = app.parse_transcript(silent)
        self.assertEqual(data['segments'], [])
        app.render_docx(data, [], self.root / 'silent.docx')
        self.assertIn(app.NO_SPEECH, zipfile.ZipFile(self.root / 'silent.docx').read('word/document.xml').decode('utf-8'))

    def test_chunks_carry_context(self):
        segments = [dict(index=i, start=f'00:00:{i:02d}.000', end=f'00:00:{i + 1:02d}.000', text='字' * 10) for i in range(10)]
        self.assertEqual(list(app.chunk_ranges(segments, limit=35)), [(0, 3), (3, 6), (6, 9), (9, 10)])
        shown = app.show_chunk(dict(title='t', segments=segments), 1, limit=35)
        self.assertIn('[00:00:01.000', shown)   # context before
        self.assertIn('[00:00:06.000', shown)   # context after
        self.assertNotIn('[00:00:00.000', shown)
        self.assertNotIn('[00:00:08.000', shown)


if __name__ == '__main__':
    unittest.main()
