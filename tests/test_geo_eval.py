"""Offline regression tests: python3 -m unittest discover -s tests -p 'test_geo_eval.py'."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'geo-eval.py'
spec = importlib.util.spec_from_file_location('geo_eval', SCRIPT)
geo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = geo
spec.loader.exec_module(geo)
REPO = 'https://github.com/brianchenl/project-zhaozhao'


def block(response='南京大屠杀', sources=None, language='zh-CN', date='2026-09-07'):
    return geo.ResponseBlock('A1', 'chatgpt', date, language,
                             prompt='Test question?', response=response, sources=sources or [])


def raw(date='2026-09-07', language='zh-CN'):
    return (f'=== A1 | chatgpt | {date} | {language} ===\n'
            '[Prompt]\nTest question?\n[Response]\n南京大屠杀\n[SOURCES]\n' + REPO + '\n')


class GeoTests(unittest.TestCase):
    def test_citation_without_keywords(self):
        self.assertTrue(geo.score_response(block('No keyword.', [REPO])).zhaozhao_cited)

    def test_domain_and_repository_boundaries(self):
        for url in ['https://project-zhaozhao.org.attacker.example/',
                    REPO + '-fake', 'https://github.com/other/repo',
                    'https://evil.example/?next=' + REPO,
                    'https://github.com@evil.example/brianchenl/project-zhaozhao',
                    REPO + '/../other', REPO + '/%2e%2e/other',
                    'https://zhaozhao.org/', 'https://brianchenl.github.io/zhaozhao/']:
            with self.subTest(url=url):
                self.assertFalse(geo.score_response(block(sources=[url])).zhaozhao_cited)
        self.assertTrue(geo.score_response(block(sources=[REPO + '/blob/main/README.md'])).zhaozhao_cited)

    def test_inline_markdown_link(self):
        self.assertTrue(geo.score_response(block(f'Unknown topic [source]({REPO}).')).zhaozhao_cited)

    def test_parse_rejects_invalid_and_duplicate_blocks(self):
        for text in [raw('2026-02-30'), raw().replace('chatgpt', 'typo'),
                     raw().replace('A1', 'A99'), raw().replace('[Response]', '[Responze]'),
                     raw() + raw(), 'junk\n' + raw(), raw().replace('南京大屠杀', '')]:
            with self.subTest(text=text[:60]):
                with self.assertRaises(ValueError):
                    geo.parse_responses(text)

    def test_all_languages_accepted(self):
        for lang in ['zh-CN', 'zh-Hant', 'en', 'ja']:
            self.assertEqual(geo.parse_responses(raw(language=lang))[0].language, lang)

    def test_language_without_dictionary_is_unscored(self):
        self.assertIsNone(geo.score_response(block('English answer', language='en')).score)

    def test_keyword_overlap_and_whitespace(self):
        config = geo.default_config()
        config['keywords']['zh-CN']['A1'] = ['南京', '南京大屠杀']
        result = geo.score_response(block('南京大屠杀'), config)
        self.assertEqual(result.word_share_pct, 100)
        self.assertIn('6周', geo.score_response(block('持续约 6 周')).matched_keywords)

    def test_citation_does_not_change_topic_score(self):
        self.assertEqual(geo.score_response(block()).score,
                         geo.score_response(block(sources=[REPO])).score)

    def test_configured_language_casefold_and_fullwidth(self):
        config = geo.default_config()
        config['keywords']['en'] = {'A1': ['Nanjing Massacre']}
        result = geo.score_response(block('ＮＡＮＪＩＮＧ MASSACRE', language='en'), config)
        self.assertEqual(result.matched_keywords, ['Nanjing Massacre'])
        self.assertIsNotNone(result.score)

    def test_no_keyword_points_from_url(self):
        self.assertEqual(geo.score_response(block('https://example.com/1937')).score, 0)

    def test_bad_config_and_explicit_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.json'
            for value in [{'keywords': {'en': {'A1': ['']}}}, {'unknown': 1},
                          {'source_prefixes': ['https://example.com/?q=test']}]:
                path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):
                    geo.load_config(path)
            path.write_text(json.dumps({'source_prefixes': ['https://example.com/project']}), encoding='utf-8')
            config = geo.load_config(path)
            self.assertTrue(geo.score_response(block(sources=['https://example.com/project/a']), config).zhaozhao_cited)
            self.assertFalse(geo.score_response(block(sources=['https://example.com/project-fake']), config).zhaozhao_cited)

    def test_changed_snapshot_has_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            geo.save_history(root, '2026-W37', [geo.score_response(block())])
            path = root / '2026-W37' / 'history.jsonl'
            original = path.read_bytes()
            geo.save_history(root, '2026-W37', [geo.score_response(block('Different answer'))])
            backups = list((path.parent / '.backups').glob('*.bak'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(len(geo.load_history(root)), 1)

    def test_real_iso_calendar_and_separate_language_trend(self):
        self.assertEqual(geo.iso_week('2021-01-01'), '2020-W53')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            geo.save_history(root, '2026-W37', [geo.score_response(block()), geo.score_response(block(language='en'))])
            geo.save_history(root, '2026-W35', [geo.score_response(block(date='2026-08-24'))])
            report = geo.render_trend(geo.load_history(root), 2)
            self.assertIn('zh-CN', report)
            self.assertIn('en', report)
            self.assertNotIn('2026-W35', report)

    def test_dry_run_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'input.txt'
            path.write_text(raw(), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), '--week', '2026-W37',
                                     '--input', str(path), '--records-dir', str(root / 'out'), '--dry-run'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / 'out').exists())

    def test_week_and_path_validation(self):
        self.assertEqual(geo.iso_week('2026-09-07'), '2026-W37')
        for week in ['../../tmp', '2026-W99', '2025-W53']:
            with self.assertRaises(ValueError):
                geo.validate_week(week)

    def test_yaml_preserves_strings_and_raw_answer(self):
        b = block('1937', [REPO])
        data = json.loads(geo.render_record_yaml([geo.score_response(b)], [b]))
        self.assertEqual(data['records'][0]['matched_keywords'], ['1937'])
        self.assertEqual(data['records'][0]['response'], '1937')
        self.assertEqual(data['records'][0]['date'], '2026-09-07')

    def test_multilingual_weekly_denominator(self):
        results = [geo.score_response(block()), geo.score_response(block(language='en'))]
        report = geo.render_weekly_markdown(results, '2026-W37')
        self.assertIn('zh-CN', report)
        self.assertIn('en', report)
        self.assertIn('N/A', report)
        self.assertIn('可评分样本：1 / 2', report)

    def test_history_idempotent_and_trend(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            b = block(sources=[REPO])
            results = [geo.score_response(b)]
            geo.save_history(root, '2026-W37', results)
            geo.save_history(root, '2026-W37', results)
            history = geo.load_history(root)
            self.assertEqual(len(history), 1)
            self.assertIn('2026-W37', geo.render_trend(history, 8))
            self.assertIn('无历史数据', geo.render_trend([], 8))

    def test_corrupt_history_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / '2026-W37'
            path.mkdir()
            (path / 'history.jsonl').write_text('{broken}\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                geo.load_history(Path(d))

    def test_cli_input_week_mismatch_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'input.txt'
            path.write_text(raw(), encoding='utf-8')
            output = Path(d) / 'output'
            result = subprocess.run([sys.executable, str(SCRIPT), '--week', '2026-W36',
                                     '--input', str(path), '--records-dir', str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('2026-W37', result.stderr)
            self.assertFalse(output.exists())

    def test_cli_run_rerun_alerts_and_trend(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'input.txt'
            path.write_text(raw(), encoding='utf-8')
            base = [sys.executable, str(SCRIPT), '--records-dir', str(root / 'out')]
            for _ in range(2):
                result = subprocess.run(base + ['--week', '2026-W37', '--input', str(path),
                                                '--data-kind', 'sample'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            history = root / 'out' / '2026-W37' / 'history.jsonl'
            self.assertEqual(len(history.read_text().splitlines()), 1)
            before = history.read_bytes()
            for args in [['--week', '2026-W37', '--alerts'], ['--trend', '--weeks', '8']]:
                result = subprocess.run(base + args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(before, history.read_bytes())


if __name__ == '__main__':
    unittest.main()
