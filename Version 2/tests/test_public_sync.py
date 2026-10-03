import contextlib
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

from review_ingestion.play_pipeline import run_once

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_seed', ROOT / 'web/seed.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class PublicSyncTests(unittest.TestCase):
    def test_merge_updates_older_retains_newer_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as folder:
            db, sql = Path(folder) / 'local.sqlite3', Path(folder) / 'sync.sql'
            rows = [dict(reviewId=key, content="An app's review", score=4,
                         userName='PRIVATE AUTHOR', at='2026-10-01T00:00:00Z')
                    for key in ('update', 'keep', 'add')]
            run_once(db_path=db, apps=[dict(app_id='com.example.app', label='Example')],
                     pages=1, delay=0, fetcher=lambda **_: dict(records=rows, cursor=None))
            self.assertEqual(seed.export(db, sql), 3)
            script = sql.read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE AUTHOR', script)
            self.assertNotIn('author_name', script)
            with contextlib.closing(sqlite3.connect(':memory:')) as c:
                c.executescript((ROOT / 'web/schema.sql').read_text())
                c.execute("INSERT INTO apps VALUES('com.example.app','Example','2000-01-01T00:00:00Z')")
                for key, text, date in (('update', 'old', '2000-01-01T00:00:00Z'),
                                        ('keep', 'newer online', '2099-01-01T00:00:00Z'),
                                        ('online-only', 'retain me', '2026-01-01T00:00:00Z')):
                    c.execute('INSERT INTO reviews(app_id,review_id,content,score,thumbs_up_count,review_at,collected_at) VALUES(?,?,?,?,?,?,?)',
                              ('com.example.app', key, text, 4, 0, date, date))
                c.commit()
                c.executescript(script)
                result = c.execute('SELECT review_id,content,collected_at FROM reviews ORDER BY review_id').fetchall()
                self.assertEqual(len(result), 4)
                self.assertEqual(dict((r[0],r[1]) for r in result),
                                 {'update': "An app's review", 'keep': 'newer online',
                                  'add': "An app's review", 'online-only': 'retain me'})
                c.executescript(script)
                self.assertEqual(c.execute('SELECT review_id,content,collected_at FROM reviews ORDER BY review_id').fetchall(), result)
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            with self.assertRaisesRegex(ValueError, 'distinct files'):
                seed.export(db, db)


if __name__ == '__main__':
    unittest.main()
