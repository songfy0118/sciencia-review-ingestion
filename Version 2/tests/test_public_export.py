import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from review_ingestion.play_pipeline import run_once

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_export', ROOT / 'web/export_public.py')
public_export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_export)


class PublicExportTests(unittest.TestCase):
    def test_contacts_and_secret_patterns_are_removed(self):
        text, count = public_export.redact('email me@sample.com or +1 (312) 555-1234 ghp_' + 'a' * 30)
        self.assertEqual(count, 3)
        self.assertNotIn('sample.com', text)
        self.assertNotIn('555-1234', text)
        self.assertNotIn('ghp_', text)

    def test_export_omits_authors_and_has_repeatable_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            db, output = Path(folder) / 'reviews.sqlite3', Path(folder) / 'public'
            run_once(db_path=db, apps=[dict(app_id='com.example.app', label='Example')], pages=1,
                     delay=0, fetcher=lambda **_: {'records': [dict(reviewId='one', content='Contact me@sample.com',
                         userName='PRIVATE AUTHOR', score=4, at='2026-10-01T00:00:00Z')], 'cursor': None})
            metadata = public_export.export(db, output)
            first = (output / 'reviews.json.gz').read_bytes()
            rows = json.loads(gzip.decompress(first))
            self.assertEqual(metadata['reviews'], 1)
            self.assertNotIn('author_name', rows[0])
            self.assertNotIn('PRIVATE AUTHOR', gzip.decompress(first).decode())
            self.assertEqual(rows[0]['content'], 'Contact [REDACTED CONTACT]')
            self.assertEqual(metadata['quality'][0]['quality_status'], 'unassessed')
            public_export.export(db, output)
            self.assertEqual((output / 'reviews.json.gz').read_bytes(), first)


if __name__ == '__main__':
    unittest.main()
