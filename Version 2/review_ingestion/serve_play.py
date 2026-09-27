"""Local control panel for bounded Google Play collection. No extra dependencies."""
from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .google_play import utc_now, validate_app_id
from .google_play_cli import load_apps
from .refresh_play import read_health, refresh


ICON_DIRECTORY = Path(__file__).with_name('app_icons')
ICON_FILES = {path.name for path in ICON_DIRECTORY.glob('*') if path.suffix in ('.png', '.jpg')}


def icon_url(app_id):
    for extension in ('.png', '.jpg'):
        name = app_id + extension
        if name in ICON_FILES:
            return '/icons/' + name
    return None


def parse_app(value: str) -> str:
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError('Enter a Google Play app ID or product link.')
    value = value.strip()
    if '://' in value:
        url = urlsplit(value)
        if url.scheme != 'https' or url.netloc != 'play.google.com' or url.path != '/store/apps/details':
            raise ValueError('Use a https://play.google.com/store/apps/details?id=... link.')
        ids = parse_qs(url.query).get('id', [])
        if len(ids) != 1:
            raise ValueError('The Google Play link must contain one app ID.')
        value = ids[0]
    return validate_app_id(value)


class Collector:
    def __init__(self, db: Path, output: Path, apps: list[dict], runner=refresh):
        self.db, self.output, self.apps, self.runner = db, output, apps, runner
        self.lock = threading.Lock()
        self.active = False
        self.message = None
        self.thread = None
        self.started_at = None

    def prepare(self, request):
        if not isinstance(request, dict):
            raise ValueError('Request must be an object.')
        pages, count = request.get('pages', 1), request.get('count', 50)
        if type(pages) is not int or not 1 <= pages <= 5 or type(count) is not int or count not in (25, 50, 100):
            raise ValueError('Use 1–5 pages per app and 25, 50 or 100 reviews per page.')
        resume = request.get('resume')
        if resume:
            if not isinstance(resume, str) or len(resume) > 100 or not self.db.is_file():
                raise ValueError('Saved run not found.')
            with closing(sqlite3.connect(self.db.resolve().as_uri() + '?mode=ro', uri=True)) as c:
                row = c.execute('SELECT report_json FROM collection_runs WHERE run_id=?', (resume,)).fetchone()
                can_resume = c.execute("SELECT count(*) FROM play_jobs WHERE run_id=? AND status IN ('pending','paused','failed')", (resume,)).fetchone()[0]
            if not row or not can_resume:
                raise ValueError('This run has no resumable checkpoint. Start a new collection.')
            config = json.loads(row[0])['config']
            return dict(apps=config['apps'], pages=pages, count=config['count'],
                        country=config['country'], lang=config['lang'], resume=resume)
        values = request.get('apps', [])
        if not isinstance(values, list):
            raise ValueError('Choose apps from the list or add a Google Play link.')
        values = list(values)
        extra = request.get('extra_app', '')
        extra_name = request.get('extra_name', '')
        if not isinstance(extra, str) or not isinstance(extra_name, str) or len(extra_name) > 80:
            raise ValueError('Use a Google Play link and an app name of at most 80 characters.')
        extra = extra.strip()
        if extra:
            values.append(extra)
        if not isinstance(values, list) or not 1 <= len(values) <= 5:
            raise ValueError('Choose between one and five apps.')
        ids = [parse_app(value) for value in values]
        if len(set(ids)) != len(ids):
            raise ValueError('An app appears more than once. Remove the duplicate.')
        labels = {a['app_id']: a['label'] for a in self.apps}
        if self.db.is_file():
            with closing(sqlite3.connect(self.db.resolve().as_uri() + '?mode=ro', uri=True)) as c:
                for app_id, label in c.execute('SELECT app_id, label FROM apps'):
                    labels.setdefault(app_id, label)
        if extra and extra_name.strip() and ids[-1] not in labels:
            labels[ids[-1]] = extra_name.strip()
        return dict(apps=[dict(app_id=i, label=labels.get(i, i)) for i in ids], pages=pages, count=count)

    def start(self, request):
        options = self.prepare(request)
        with self.lock:
            if self.active:
                raise RuntimeError('A collection is already running. Wait for it to finish.')
            self.active, self.message = True, 'Collecting reviews and checking the saved data…'
            self.started_at = utc_now()
        self.thread = threading.Thread(target=self._run, args=(options,), daemon=False)
        try:
            self.thread.start()
        except Exception:
            with self.lock:
                self.active = False
            raise

    def _run(self, options):
        try:
            result = self.runner(db=self.db, output=self.output, **options, timeout=20, retries=1, delay=2)
            message = {'ready': 'Collection finished. Data checks passed.',
                       'warning': 'Collection finished. Review the source quality notes below.',
                       'needs_attention': 'Collection saved with issues. Check the results before continuing.',
                       'failed': 'Collection could not finish. See the failure details below.'}[result['status']]
        except Exception as exc:
            message = f'Collection could not finish: {type(exc).__name__}: {exc}'
        with self.lock:
            self.active, self.message = False, message

    def state(self):
        with self.lock:
            result = dict(active=self.active, message=self.message,
                          apps=[dict(app, icon=icon_url(app['app_id'])) for app in self.apps],
                          started_at=self.started_at)
        cycles, errors = [], []
        for path in self.output.glob('*/health.json'):
            if len(path.parent.name) != 32 or any(c not in '0123456789abcdef' for c in path.parent.name):
                continue
            try:
                health = read_health(path)
                cycles.append(dict(cycle_id=path.parent.name, started_at=health['started_at'],
                                   status=health['status'], issues=health['issues'],
                                   unique_reviews=health.get('unique_reviews'),
                                   result_url=f'/results/{path.parent.name}/index.html' if health.get('snapshot') else None))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'Cannot read saved result {path.parent.name}: {type(exc).__name__}')
        result['cycles'] = sorted(cycles, key=lambda r: r['started_at'], reverse=True)[:20]
        result['errors'], result['runs'], result['stored_reviews'] = errors, [], 0
        if self.db.exists():
            try:
                with closing(sqlite3.connect(self.db.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as c:
                    c.row_factory = sqlite3.Row
                    result['stored_reviews'] = c.execute('SELECT count(*) FROM reviews').fetchone()[0]
                    for run in c.execute('SELECT run_id,started_at FROM collection_runs ORDER BY started_at DESC LIMIT 10'):
                        jobs = [dict(j) for j in c.execute('SELECT label,pages,status,error FROM play_jobs WHERE run_id=? ORDER BY app_id', (run['run_id'],))]
                        result['runs'].append(dict(run_id=run['run_id'], started_at=run['started_at'], jobs=jobs,
                                                   can_resume=any(j['status'] in ('paused','pending','failed') for j in jobs)))
            except sqlite3.Error as exc:
                errors.append(f'Database status unavailable: {exc}')
        return result


FILES = {'index.html': 'text/html; charset=utf-8', 'health.json': 'application/json',
         'run.json': 'application/json', 'audit.json': 'application/json',
         'evaluation.json': 'application/json', 'reviews.json': 'application/json',
         'reviews.sqlite3': 'application/vnd.sqlite3'}


def make_server(collector, port=8768):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, content_type='application/json', download=None):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def json(self, code, value):
            self.send(code, json.dumps(value).encode())

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.json(403, {'error': 'Use the local 127.0.0.1 address.'})
            path = urlsplit(self.path).path
            if path in ('/', '/results/index.html'):
                return self.send(200, Path(__file__).with_name('play_dashboard.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/state':
                return self.json(200, collector.state() | {'token': token})
            if path.startswith('/icons/'):
                name = path.removeprefix('/icons/')
                if name in ICON_FILES:
                    icon = ICON_DIRECTORY / name
                    return self.send(200, icon.read_bytes(), 'image/png' if name.endswith('.png') else 'image/jpeg')
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[0] == 'results' and len(parts[1]) == 32 and all(c in '0123456789abcdef' for c in parts[1]) and parts[2] in FILES:
                file = (collector.output / parts[1] / parts[2]).resolve()
                if file.is_relative_to(collector.output.resolve()) and file.is_file():
                    return self.send(200, file.read_bytes(), FILES[parts[2]], parts[2] if parts[2] != 'index.html' else None)
            return self.json(404, {'error': 'Result not found.'})

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != origin or self.headers.get('X-Collection-Token') != token:
                return self.json(403, {'error': 'Open the local control panel to start collection.'})
            if self.path != '/api/collect':
                return self.json(404, {'error': 'Action not found.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    raise ValueError('Request is empty or too large.')
                collector.start(json.loads(self.rfile.read(size)))
            except (ValueError, TypeError) as exc:
                return self.json(400, {'error': str(exc)})
            except RuntimeError as exc:
                return self.json(409, {'error': str(exc)})
            except (sqlite3.Error, KeyError) as exc:
                return self.json(500, {'error': f'Cannot load the checkpoint: {exc}'})
            self.json(202, {'message': 'Collection started. You can keep browsing saved results.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('config/google_play_apps.example.json'))
    parser.add_argument('--db', type=Path, default=Path('data/google_play_v2.sqlite3'))
    parser.add_argument('--output', type=Path, default=Path('data/inspection'))
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    collector = Collector(args.db, args.output, load_apps(args.input))
    server = make_server(collector, args.port)
    print(f'Open http://127.0.0.1:{server.server_port}/ — local use only.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if collector.thread and collector.thread.is_alive():
            print('Waiting for the bounded collection to finish saving.', flush=True)
            collector.thread.join()


if __name__ == '__main__':
    main()
