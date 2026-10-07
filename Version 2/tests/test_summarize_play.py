import copy
import unittest

from review_ingestion.summarize_play import summarize


def report(key, at, count=100):
    return {'runs': [dict(run_id=key, status='bounded_success', verification_status='passed',
        config=dict(lang='en', country='us', count=count, sort='NEWEST', adapter='strict', package='1.2.7'),
        apps=[dict(app_id='com.example.app', label='Example', status='paused', pages=2,
                   new_records=99, repeated_records=1, changed_records=1, unchanged_records=0,
                   stale_records=0, accepted_records=100, unclassified_pages=0)],
        evaluation={'apps': [dict(app_id='com.example.app', sample_collected_at=at,
            unique_reviews_in_run=100, newest_returned_review='2026-09-27T00:00:00Z',
            newest_review_age_days_at_collection=10, warnings=['stale source'])]})]}


class SummaryTests(unittest.TestCase):
    def test_same_day_is_not_multiple_days(self):
        result = summarize([report('a', '2026-10-07T10:00:00Z'), report('b', '2026-10-07T20:00:00Z')])
        self.assertEqual(result['coverage'][0]['longest_consecutive_days'], 1)
        self.assertEqual(result['rows'][0]['warnings'], ['stale source'])

    def test_gap_and_parameter_change_break_streak(self):
        result = summarize([report('a', '2026-10-07T10:00:00Z'), report('b', '2026-10-08T10:00:00Z'),
                            report('c', '2026-10-10T10:00:00Z'), report('d', '2026-10-09T10:00:00Z', 50)])
        self.assertEqual(sorted(g['longest_consecutive_days'] for g in result['coverage']), [1, 2])

    def test_failed_or_unverified_runs_do_not_count(self):
        for field, value in [('status', 'needs_attention'), ('verification_status', 'failed')]:
            bad = report('a', '2026-10-07T10:00:00Z')
            bad['runs'][0][field] = value
            self.assertEqual(summarize([bad])['coverage'][0]['valid_days_utc'], [])

    def test_accounting_mismatch_does_not_count(self):
        bad = report('a', '2026-10-07T10:00:00Z')
        bad['runs'][0]['apps'][0]['changed_records'] = 2
        self.assertFalse(summarize([bad])['rows'][0]['accounting_ok'])
        self.assertEqual(summarize([bad])['coverage'][0]['longest_consecutive_days'], 0)

    def test_duplicate_run_rejected(self):
        item = report('a', '2026-10-07T10:00:00Z')
        with self.assertRaises(ValueError):
            summarize([item, copy.deepcopy(item)])

    def test_date_uses_observation_and_utc_not_generation(self):
        item = report('a', '2026-10-07T23:30:00-05:00')
        item['runs'][0]['generated_at'] = '2026-10-20T00:00:00Z'
        self.assertEqual(summarize([item])['rows'][0]['day_utc'], '2026-10-08')

    def test_naive_date_rejected_instead_of_using_machine_timezone(self):
        with self.assertRaises(ValueError):
            summarize([report('a', '2026-10-07T10:00:00')])
