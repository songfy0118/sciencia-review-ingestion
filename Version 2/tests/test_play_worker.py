import json
import re
import unittest

from review_ingestion.play_worker import validate_response


PATTERN = re.compile(r"\)]}'\n\n([\s\S]+)")


def response(payload):
    return ")]}'\n\n" + json.dumps([['wrb.fr', 'oCPfdb', json.dumps(payload)]])


class WorkerResponseTests(unittest.TestCase):
    def test_observed_continuation_and_explicit_null_token_are_valid(self):
        for token in ('next-page', None):
            validate_response(response([[['review']], [None, token], []]), PATTERN)

    def test_missing_or_malformed_token_never_becomes_source_end(self):
        for payload in ([[]], [[], [], []], [[], None, []], [[], [None], []],
                        [[], [None, []], []], [[], [None, ''], []],
                        {'reviews': []}):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, 'source end is not confirmed'):
                validate_response(response(payload), PATTERN)

    def test_changed_or_invalid_envelope_is_diagnostic(self):
        for body in ('<html>Sign in</html>', ")]}'\n\ninvalid", ")]}'\n\n[]"):
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, 'Unrecognized Google Play'):
                validate_response(body, PATTERN)
