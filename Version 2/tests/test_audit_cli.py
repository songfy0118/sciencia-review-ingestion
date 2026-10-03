import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from review_ingestion.audit_play import main


class AuditCliTests(unittest.TestCase):
    def test_report_cannot_replace_database_or_hardlink(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'database.sqlite3'
            db.write_bytes(b'preserve existing database')
            alias = Path(folder) / 'alias.json'
            os.link(db, alias)
            for destination in (db, alias):
                with self.subTest(destination=destination), patch('sys.argv', [
                        'audit', '--db', str(db), '--report', str(destination)]), patch(
                        'review_ingestion.audit_play.audit') as check, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        main()
                    self.assertEqual(result.exception.code, 2)
                    check.assert_not_called()
                self.assertEqual(db.read_bytes(), b'preserve existing database')
                self.assertEqual(alias.read_bytes(), b'preserve existing database')


if __name__ == '__main__':
    unittest.main()
