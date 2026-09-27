import unittest

from review_ingestion.probe_play import probe
from review_ingestion.play_pipeline import SourceError


class ProbeTests(unittest.TestCase):
    def test_same_ids_do_not_imply_verified_locale(self):
        calls = []

        def fetch(**kwargs):
            calls.append(kwargs)
            return {'records': [dict(reviewId='one', content='Good', score=4,
                                     at='2020-01-01T00:00:00Z')]}

        result = probe('com.example.app', fetcher=fetch, delay=0)
        self.assertEqual([c['country'] for c in calls], ['us', 'gb'])
        self.assertTrue(result['samples'][1]['same_ids_as_first_country'])
        self.assertIn('not verified', result['limitations'])

    def test_failure_is_recorded_and_next_country_is_tested(self):
        def fetch(**kwargs):
            if kwargs['country'] == 'us':
                raise SourceError('Source unavailable')
            return {'records': []}

        result = probe('com.example.app', fetcher=fetch, delay=0)
        self.assertEqual([s['status'] for s in result['samples']], ['failed', 'empty'])
        self.assertIn('Source unavailable', result['samples'][0]['error'])
