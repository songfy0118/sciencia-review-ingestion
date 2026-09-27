"""Exercise the generated review filters with actual exported records."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from functools import partial
from html import unescape
from pathlib import Path

from review_ingestion.play_pipeline import run_once
from review_ingestion.refresh_play import refresh


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the generated-page check')
class InspectionScriptTests(unittest.TestCase):
    def test_saved_review_filters_and_pagination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            health = refresh(apps=[dict(app_id='com.example.app', label='Example'),
                                   dict(app_id='com.example.other', label='Other')], db=root/'db.sqlite3',
                             output=root/'out', pages=1, count=25, delay=0, retries=0,
                             collector=partial(run_once, fetcher=lambda **request: dict(records=[
                                 dict(reviewId=str(i), content=f'Useful review {i}' if request['app_id']=='com.example.app' else f'Mention Example {i}',
                                      score=4 if i % 2 == 0 else 1,
                                      thumbsUpCount=10 if i >= 10 else 0,
                                      at='2026-09-27T00:00:00Z')
                                 for i in range(25)], cursor=None)))
            document = Path(health['snapshot']).read_text(encoding='utf-8')
            script = re.search(r'<script>(.*?)</script>', document, re.S)[1]
            cards = []
            for attributes, body in re.findall(r'<article class="review-card"([^>]*)>(.*?)</article>', document, re.S):
                def attribute(name):
                    return re.search(rf'data-{name}="([^"]+)"', attributes)[1]
                content = re.search(r'<p class="review-text">(.*?)</p>', body, re.S)[1]
                cards.append(dict(app=attribute('app'), name=attribute('name'), score=attribute('score'),
                                  helpful=attribute('helpful'), content=unescape(content)))
            self.assertEqual(len(cards), 50)
            self.assertIn('<summary>Record details</summary>', document)
            harness = r'''
const assert=require('node:assert/strict');
const fixture=JSON.parse(process.argv[1]);
const mockCards=fixture.map(c=>({dataset:c,hidden:false,querySelector:()=>({textContent:c.content})}));
const mockTiles=['','com.example.app','com.example.other'].map(app=>({dataset:{app},attrs:{},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v},addEventListener(){}}));
const controls={};
for(const id of ['app','search','rating','helpful','count','previous','next','clear','empty','browse-heading'])
 controls[id]={value:'',hidden:false,listeners:{},addEventListener(event,fn){this.listeners[event]=fn},scrollIntoView(){}};
const document={getElementById:id=>controls[id],querySelectorAll:selector=>
 selector==='#review-list .review-card'?mockCards:selector==='#app-tiles .app-tile'?mockTiles:[]};
const window={addEventListener(){}};
const location={protocol:'http:'};
SCRIPT
assert.equal(controls.count.textContent,'1–20 of 50 saved reviews');
controls.next.listeners.click();
assert.equal(controls.count.textContent,'21–40 of 50 saved reviews');
controls.app.value='com.example.app';controls.app.listeners.change();
controls.rating.value='high';controls.rating.listeners.change();
assert.equal(controls.count.textContent,'1–13 of 13 saved reviews');
controls.helpful.value='10';controls.helpful.listeners.change();
assert.equal(controls.count.textContent,'1–8 of 8 saved reviews');
controls.app.value='';controls.rating.value='';controls.helpful.value='';controls.search.value='Example';controls.search.listeners.input();
assert.equal(controls.count.textContent,'1–20 of 25 saved reviews');
assert.ok(mockCards.filter(card=>!card.hidden).every(card=>card.dataset.app==='com.example.app'));
controls.search.value='Mention';controls.search.listeners.input();
assert.equal(controls.count.textContent,'1–20 of 25 saved reviews');
assert.ok(mockCards.filter(card=>!card.hidden).every(card=>card.dataset.app==='com.example.other'));
controls.search.value='no-match';controls.search.listeners.input();
assert.equal(controls.count.textContent,'0 saved reviews');
assert.equal(controls.empty.hidden,false);
controls.clear.listeners.click();
assert.equal(controls.count.textContent,'1–20 of 50 saved reviews');
assert.equal(mockCards.filter(card=>!card.hidden).length,20);
'''.replace('SCRIPT', script)
            checked = subprocess.run([shutil.which('node'), '-e', harness, json.dumps(cards)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(checked.returncode, 0, checked.stderr)
