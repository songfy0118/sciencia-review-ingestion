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
            pages=2, status='paused',
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

    def test_real_intervals_and_missing_days(self):
        result = summarize([report('a', '2026-10-07T20:00:00Z'),
                            report('b', '2026-10-08T05:00:00Z'),
                            report('c', '2026-10-10T05:00:00Z')])['coverage'][0]
        self.assertEqual([i['hours'] for i in result['intervals']], [9, 48])
        self.assertEqual(result['missing_days_utc'], ['2026-10-09'])
        self.assertFalse(result['near_daily_intervals'])

    def test_chronology_uses_instants_not_timezone_strings(self):
        result = summarize([report('later', '2026-10-08T01:00:00-05:00'),
                            report('earlier', '2026-10-08T05:00:00Z')])
        self.assertEqual([r['run_id'] for r in result['rows']], ['earlier', 'later'])
        self.assertEqual(result['coverage'][0]['intervals'][0]['hours'], 1)

    def test_missing_evidence_and_conflicting_counts_fail_closed(self):
        for field, value in [('pages', 1), ('status', 'failed'),
                             ('unique_reviews_in_run', 101), ('newest_returned_review', None)]:
            item = report('a', '2026-10-07T10:00:00Z')
            item['runs'][0]['evaluation']['apps'][0][field] = value
            self.assertFalse(summarize([item])['rows'][0]['valid_collection'])

    def test_negative_counts_cannot_cancel_each_other(self):
        item = report('a', '2026-10-07T10:00:00Z')
        item['runs'][0]['apps'][0].update(new_records=101, repeated_records=-1,
                                         changed_records=-1)
        self.assertFalse(summarize([item])['rows'][0]['accounting_ok'])

    def test_no_overlap_is_separate_from_storage_success(self):
        item = report('a', '2026-10-07T10:00:00Z')
        evidence = item['runs'][0]['evaluation']['apps'][0]
        evidence.update(warnings=[], comparison={'shared_ids_in_window': 0})
        row = summarize([item])['rows'][0]
        self.assertTrue(row['valid_collection'])
        self.assertFalse(row['source_quality_ok'])
        self.assertTrue(any('continuity' in w for w in row['warnings']))
        evidence['comparison']['shared_ids_in_window'] = 1
        self.assertTrue(summarize([item])['rows'][0]['source_quality_ok'])

    def test_overlap_mode_and_duplicate_apps(self):
        first = report('a', '2026-10-07T10:00:00Z')
        second = report('b', '2026-10-08T10:00:00Z')
        second['runs'][0]['config']['overlap_run'] = 'a'
        self.assertEqual(len(summarize([first, second])['coverage']), 2)
        first['runs'][0]['apps'] *= 2
        with self.assertRaises(ValueError):
            summarize([first])

    def test_invalid_naive_or_future_review_date_does_not_count(self):
        for newest in ('not-a-date', '2026-09-27T00:00:00',
                       '2026-10-08T00:00:00Z', 123):
            item = report('a', '2026-10-07T10:00:00Z')
            item['runs'][0]['evaluation']['apps'][0]['newest_returned_review'] = newest
            result = summarize([item])
            self.assertFalse(result['rows'][0]['valid_collection'])
            self.assertEqual(result['coverage'][0]['valid_days_utc'], [])

    def test_duplicate_evaluation_app_rejected(self):
        item = report('a', '2026-10-07T10:00:00Z')
        item['runs'][0]['evaluation']['apps'] *= 2
        with self.assertRaisesRegex(ValueError, 'within evaluation'):
            summarize([item])
