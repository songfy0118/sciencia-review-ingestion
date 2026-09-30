import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from review_ingestion.google_play_cli import main
from review_ingestion.play_pipeline import run_once


class ControlledCliTests(unittest.TestCase):
    def test_output_cannot_overwrite_database_or_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'apps.json'
            config.write_text('[{"app_id":"com.example.app"}]')
            database = root / 'db.sqlite3'
            database.write_bytes(b'preserve database')
            for destination in (config, database):
                with self.subTest(destination=destination), patch('sys.argv', [
                        'collect', '--input', str(config), '--db', str(database), '--report', str(destination)]), patch(
                        'review_ingestion.google_play_cli.run_once') as collect, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        main()
                    self.assertEqual(result.exception.code, 2)
                    collect.assert_not_called()
            self.assertEqual(database.read_bytes(), b'preserve database')
            self.assertEqual(config.read_text(), '[{"app_id":"com.example.app"}]')

    def invoke_with_check_failure(self, check, error):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'apps.json'
            config.write_text(json.dumps([dict(app_id='com.example.app', label='Example')]))
            destination = root / 'report.json'
            database = root / 'db.sqlite3'

            def collect(**kwargs):
                return run_once(**kwargs, fetcher=lambda **_: dict(records=[dict(
                    reviewId='one', content='Good', score=4, at='2026-09-28T00:00:00Z')], cursor=None))

            argv = ['collect', '--input', str(config), '--db', str(database),
                    '--report', str(destination), '--pages', '1', '--delay', '0']
            with patch('sys.argv', argv), patch('review_ingestion.google_play_cli.run_once', side_effect=collect), patch(
                    'review_ingestion.google_play_cli.' + check, side_effect=error), contextlib.redirect_stdout(io.StringIO()):
                if isinstance(error, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        main()
                else:
                    self.assertEqual(main(), 1)
            report = json.loads(destination.read_text())['runs'][0]
            with contextlib.closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT status FROM collection_runs').fetchone()[0], report['status'])
            return report

    def test_audit_exception_preserves_collection_and_failure_report(self):
        report = self.invoke_with_check_failure('audit', sqlite3.DatabaseError('audit unavailable'))
        self.assertEqual(report['verification_status'], 'failed')
        self.assertIn('audit unavailable', report['verification_errors']['storage_audit'])
        self.assertIn('evaluation', report)

    def test_evaluation_exception_does_not_skip_audit(self):
        report = self.invoke_with_check_failure('evaluate', ValueError('invalid snapshot'))
        self.assertEqual(report['verification_status'], 'failed')
        self.assertTrue(report['storage_audit']['storage_checks_passed'])

    def test_interruption_leaves_pending_report_not_success(self):
        report = self.invoke_with_check_failure('evaluate', KeyboardInterrupt())
        self.assertEqual(report['verification_status'], 'pending')
        self.assertEqual(report['unique_reviews_in_database'], 1)

    def test_three_rounds_report_real_database_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'apps.json'
            config.write_text(json.dumps([dict(app_id='com.example.app', label='Example')]))
            report = root / 'report.json'
            rounds = iter([
                [('one', 'original'), ('two', 'same')],
                [('one', 'edited'), ('two', 'same'), ('three', 'new')],
                [('one', 'edited'), ('two', 'same'), ('three', 'new')],
            ])

            def collect(**kwargs):
                records = [dict(reviewId=key, content=text, score=4, at='2026-09-28T00:00:00Z')
                           for key, text in next(rounds)]
                return run_once(**kwargs, fetcher=lambda **_: dict(records=records, cursor=None))

            argv = ['collect', '--input', str(config), '--db', str(root / 'db.sqlite3'),
                    '--report', str(report), '--runs', '3', '--pages', '1', '--count', '100',
                    '--delay', '0', '--interval', '0']
            with patch('sys.argv', argv), patch('review_ingestion.google_play_cli.run_once', side_effect=collect), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            runs = json.loads(report.read_text())['runs']
            self.assertEqual([r['unique_reviews_in_database'] for r in runs], [2, 3, 3])
            self.assertTrue(all(r['storage_audit']['storage_checks_passed'] for r in runs))
            self.assertEqual(runs[1]['apps'][0]['changed_records'], 1)
            self.assertEqual(runs[2]['apps'][0]['unchanged_records'], 3)
            self.assertEqual(runs[2]['evaluation']['apps'][0]['comparison']['id_jaccard'], 1)


if __name__ == '__main__':
    unittest.main()
