import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from review_ingestion.storage import write_json


class ReportStorageTests(unittest.TestCase):
    def test_replace_failure_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            write_json(path, {'round': 1})
            with patch('review_ingestion.storage.os.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    write_json(path, {'round': 2})
            self.assertEqual(json.loads(path.read_text()), {'round': 1})
            self.assertEqual(list(path.parent.iterdir()), [path])
            write_json(path, {'round': 2})
            self.assertEqual(json.loads(path.read_text()), {'round': 2})

    def test_serialization_failure_does_not_truncate_old_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            write_json(path, {'round': 1})
            with self.assertRaises(TypeError):
                write_json(path, {'invalid': object()})
            self.assertEqual(json.loads(path.read_text()), {'round': 1})


if __name__ == '__main__':
    unittest.main()
