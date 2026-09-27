"""Exercise the generated pagination script without a browser dependency."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from functools import partial
from pathlib import Path

from review_ingestion.play_pipeline import run_once
from review_ingestion.refresh_play import refresh


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the generated-page regression check')
class InspectionScriptTests(unittest.TestCase):
    def test_review_filters_do_not_hide_or_count_the_summary_table(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            health = refresh(apps=[dict(app_id='com.example.app', label='Example')], db=root/'db.sqlite3',
                             output=root/'out', pages=1, count=25, delay=0, retries=0,
                             collector=partial(run_once, fetcher=lambda **_: dict(records=[
                                 dict(reviewId=str(i), content='Useful', score=4, at='2026-09-27T00:00:00Z')
                                 for i in range(25)], cursor=None)))
            document = Path(health['snapshot']).read_text(encoding='utf-8')
            script = re.search(r'<script>(.*?)</script>', document, re.S)[1]
            # Two DOM table groups reproduce the regression: summary rows must
            # remain visible while review rows are filtered and paginated.
            groups = re.findall(r'<tbody>(.*?)</tbody>', document, re.S)
            def rows(group):
                result = []
                for attrs, body in re.findall(r'<tr([^>]*)>(.*?)</tr>', group, re.S):
                    app = re.search(r'data-app="([^"]+)"', attrs)
                    result.append(dict(dataset={'app': app[1]} if app else {}, hidden=False,
                                       textContent=re.sub('<[^>]+>', '', body)))
                return result
            fixture = {'summary': rows(groups[0]), 'reviews': rows(groups[1])}
            harness = r'''
const assert = require('node:assert/strict');
const fixture = JSON.parse(process.argv[1]);
const controls = {};
for(const id of ['app','search','count','previous','next','clear']) controls[id]={value:'',listeners:{},addEventListener(event,fn){this.listeners[event]=fn;}};
const document = {getElementById:id=>controls[id],querySelectorAll:selector=>selector==='#review-table tbody tr'?fixture.reviews:[...fixture.summary,...fixture.reviews]};
const window = {addEventListener(){}};
SCRIPT
assert.equal(controls.count.textContent,'1–20 of 25 matching reviews');
controls.next.listeners.click();
assert.equal(controls.count.textContent,'21–25 of 25 matching reviews');
controls.search.value='no-match';controls.search.listeners.input();
assert.equal(controls.count.textContent,'No matching reviews');
assert.ok(fixture.summary.every(row=>!row.hidden));
controls.clear.listeners.click();
assert.equal(controls.count.textContent,'1–20 of 25 matching reviews');
assert.equal(fixture.reviews.filter(row=>!row.hidden).length,20);
'''.replace('SCRIPT', script)
            checked = subprocess.run([shutil.which('node'), '-e', harness, json.dumps(fixture)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(checked.returncode, 0, checked.stderr)
