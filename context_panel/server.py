"""Loopback-only local app. Run: python3 -m context_panel.server."""
import argparse
import copy
import math
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import tempfile
import time
from urllib.parse import urlparse, parse_qs
import uuid

from .core import CodexStore, DEFAULTS, DEFAULTS_EN, JevHTTPError, build_request, context_windows, call_jev, decide, export_markdown, read_key, redact, validate_settings, review_enabled

STATIC = Path(__file__).parent / 'web'
RETRY_DELAYS = (1.0, 2.0)
RETRYABLE_HTTP = {502, 503, 504}


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.chmod(0o600)
    temp.replace(path)


class MissingKeyError(ValueError):
    pass


class App:
    def __init__(self, home, data, env_file=None):
        self.store = CodexStore(home)
        self.data = Path(data).expanduser()
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.env_file = env_file
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.runs = {}
        self.previews = {}
        self.appearance = {'theme': 'fresh', 'language': 'zh'}
        try:
            appearance = json.loads((self.data / 'appearance.json').read_text())
            if isinstance(appearance, dict) and appearance.get('theme') in ('colorful', 'fresh', 'tech', 'plain'):
                self.appearance = {'theme': appearance['theme'], 'language': appearance.get('language') if appearance.get('language') in ('zh', 'en') else 'zh'}
        except (OSError, ValueError):
            pass
        self.settings = copy.deepcopy(DEFAULTS)
        settings_file = self.data / 'settings.json'
        if settings_file.exists():
            self.settings = validate_settings(json.loads(settings_file.read_text()))
        # Rehydrate the most recent local reports, never resume paid requests automatically.
        files = sorted((p for p in self.data.glob('*.json') if len(p.stem) == 32), key=lambda p: p.stat().st_mtime)[-20:]
        for path in files:
            try:
                run = json.loads(path.read_text())
                run.update(events=[], cancel=False)
                if run['status'] in ('reading', 'running'):
                    run.update(status='failed', error='服务已重启，未自动恢复调用；未处理内容保留')
                    for segment in run['segments']:
                        if segment['status'] in ('queued', 'evaluating'):
                            segment.update(status='review' if review_enabled(run['settings']) else 'keep', reason='服务重启，保留')
                self.runs[run['id']] = run
                self.event(run, 'snapshot', {k: v for k, v in run.items() if k not in ('events', 'cancel')})
                self.event(run, 'done', {'status': run['status'], 'error': run.get('error')})
            except (ValueError, KeyError, OSError):
                continue

    def get_key(self):
        with self.lock:
            try:
                key = json.loads((self.data / 'credentials.json').read_text()).get('api_key', '')
                if isinstance(key, str) and key.strip():
                    return key.strip()
            except (OSError, ValueError, AttributeError):
                pass
            return read_key(self.env_file)

    def key_status(self):
        return {'key_configured': bool(self.get_key())}

    def set_key(self, value):
        key = value.get('api_key') if isinstance(value, dict) else None
        if not isinstance(key, str) or not 16 <= len(key.strip()) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key.strip()):
            raise ValueError('请填写有效的 Vercel AI Gateway Key（16–4096 字符，不含空白）')
        key = key.strip()
        with self.lock:
            # Create with owner-only permissions before writing any secret bytes.
            fd, name = tempfile.mkstemp(prefix='.credentials-', dir=self.data)
            try:
                with os.fdopen(fd, 'w') as handle:
                    json.dump({'api_key': key}, handle)
                os.replace(name, self.data / 'credentials.json')
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            # Previews may have been redacted using an older key.
            self.previews.clear()
        return self.key_status()

    def set_appearance(self, value):
        if not isinstance(value, dict):
            raise ValueError('配置必须是对象')
        with self.lock:
            appearance = {**self.appearance, **value}
            if appearance.get('theme') not in ('colorful', 'fresh', 'tech', 'plain'):
                raise ValueError('请选择有效的外观主题')
            if appearance.get('language') not in ('zh', 'en'):
                raise ValueError('请选择中文或英文')
            appearance = {k: appearance[k] for k in ('theme', 'language')}
            save_json(self.data / 'appearance.json', appearance)
            self.appearance = appearance
            return dict(appearance)

    def event(self, run, kind, data):
        with self.lock:
            event = {'seq': len(run['events']), 'type': kind, 'data': copy.deepcopy(data), 'at': time.time()}
            run['events'].append(event)
            self.changed.notify_all()

    def persist(self, run):
        snapshot = {k: v for k, v in run.items() if k not in ('cancel', 'events')}
        save_json(self.data / (run['id'] + '.json'), snapshot)
        path = self.data / (run['id'] + '.md')
        path.write_text(export_markdown(run))
        path.chmod(0o600)

    def preview(self, thread_id):
        settings = copy.deepcopy(self.settings)
        extracted = self.store.extract(thread_id, settings['include_tools'], self.get_key(),
                                       classify_user_messages=settings['classify_user_messages'], skip_patterns=settings['skip_patterns'])
        segments = extracted['segments']
        messages = {(s['source_file'], s['line']) for s in segments if s['role'] != 'tool'}
        tool_records = {(s['source_file'], s['line']) for s in segments if s['role'] == 'tool'}
        model_count = sum(not s['protected'] for s in segments)
        now = time.time()
        result = {'id': uuid.uuid4().hex, 'thread_id': thread_id, 'messages': len(messages),
                  'tool_records': len(tool_records), 'segments': len(segments),
                  'protected': len(segments) - model_count, 'model_segments': model_count,
                  'regex_skipped': sum(bool(s.get('regex_skipped')) for s in segments),
                  'regex_skipped_messages': len({(s['source_file'], s['line']) for s in segments if s.get('regex_skipped')}),
                  'characters': sum(len(s['text']) for s in segments),
                  'requests': math.ceil(model_count / settings['batch_size']), 'concurrency': settings['concurrency'],
                  'context_window_size': settings.get('context_window_size', 3),
                  'manual_review': settings['manual_review'], 'classify_user_messages': settings['classify_user_messages'], 'snapshot_at': now,
                  'expires_at': now + 300}
        with self.lock:
            self.previews = {k: v for k, v in self.previews.items() if v['summary']['expires_at'] > now}
            while len(self.previews) >= 3:
                self.previews.pop(next(iter(self.previews)))
            self.previews[result['id']] = {'summary': result, 'settings': settings, 'extracted': extracted}
        return result

    def decide_segment(self, run_id, segment_id, status):
        with self.lock:
            run = self.runs[run_id]
            if run['status'] in ('running', 'reading'):
                raise ValueError('请先完成或停止整理再复核')
            if status not in (('keep', 'drop', 'review') if review_enabled(run['settings']) else ('keep', 'drop')):
                raise ValueError('未知决定')
            segment = next((s for s in run['segments'] if s['id'] == segment_id), None)
            if segment is None or segment['protected']:
                raise ValueError('受保护段落不能在此省略')
            segment.update(status=status, reason='用户手动复核')
            run['revision'] = run.get('revision', 0) + 1
            run['applied'] = None
            self.persist(run)
            return {'segment': segment.copy(), 'revision': run['revision'], 'applied': None}

    def apply_run(self, run_id, revision, confirmed, language='zh'):
        with self.lock:
            run = self.runs[run_id]
            if run['status'] in ('reading', 'running') or not run['segments']:
                raise ValueError('请先完成整理并复核结果')
            if confirmed is not True or revision != run.get('revision', 0):
                raise ValueError('复核内容已变化，请重新打开预览后确认应用')
            if run.get('applied') and run['applied']['revision'] == revision:
                return run['applied']
            name = f"{run_id}-r{revision}.applied.md"
            target = self.data / name
            target.write_text(export_markdown(run, language))
            target.chmod(0o600)
            run['applied'] = {'revision': revision, 'at': time.time(), 'file': name,
                              'mode': 'new_context_copy', 'language': language if language in ('en', 'zh') else 'zh'}
            self.persist(run)
            return run['applied']

    def approved_export(self, run, language='zh'):
        with self.lock:
            if not run.get('applied') or run['applied']['revision'] != run.get('revision', 0):
                raise ValueError('请先复核并确认应用，再导出或用于新任务')
            return export_markdown(run, language)

    def start(self, thread_id, goal=None, preview_id=None):
        with self.lock:
            if any(r['status'] in ('reading', 'running') for r in self.runs.values()):
                raise ValueError('已有整理任务运行中，请完成或停止后再开始')
            if not self.get_key():
                raise MissingKeyError('请先配置 API Key，再开始整理')
            settings = copy.deepcopy(self.settings)
            if goal is not None:
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 6000:
                    raise ValueError('请填写本次整理目标（1–6000字符）')
                settings['goal'] = goal.strip()
            preview = self.previews.get(preview_id) if preview_id else None
            if not preview or preview['summary']['thread_id'] != thread_id or preview['summary']['expires_at'] < time.time():
                raise ValueError('会话预览已过期，请刷新条数后再开始')
            if preview['settings'] != settings:
                raise ValueError('提示词配置已变化，请刷新条数后再开始')
            if not preview['summary']['segments']:
                raise ValueError('该会话没有可整理的消息')
            extracted = copy.deepcopy(preview['extracted'])
            thread = extracted['thread']
            run = {'id': uuid.uuid4().hex, 'thread': thread, 'settings': settings,
                   'status': 'reading', 'segments': [], 'events': [], 'cancel': False,
                   'preview': preview['summary'], 'revision': 0, 'applied': None,
                   'started_at': time.time(), 'usage': {'input_tokens': 0, 'output_tokens': 0}, 'requests': 0}
            self.runs[run['id']] = run
            threading.Thread(target=self.work, args=(run, extracted), daemon=True).start()
            return run['id']

    def work(self, run, extracted):
        key = ''
        try:
            key = self.get_key()
            run.update(extracted)
            run.update(status='running', batch_stats=[], retry_count=0, retry_pending=0, retry_exhausted=0)
            self.event(run, 'snapshot', {k: v for k, v in run.items() if k not in ('events', 'cancel')})
            candidates = [s for s in run['segments'] if not s['protected']]
            windows = context_windows(run['segments'], run['settings'].get('context_window_size', 3))
            count = run['settings']['batch_size']
            queue = [{'batch': candidates[i:i + count], 'number': i // count + 1, 'attempt': 1, 'ready_at': 0}
                     for i in range(0, len(candidates), count)]
            parallel = run['settings'].get('concurrency', 2)
            fatal = False
            last_persist = 0

            def publish_usage():
                run['retry_pending'] = sum(job['attempt'] > 1 for job in queue)
                self.event(run, 'usage', {k: copy.deepcopy(run[k]) for k in
                                        ('requests', 'usage', 'batch_stats', 'retry_count', 'retry_pending', 'retry_exhausted')})

            with ThreadPoolExecutor(max_workers=parallel, thread_name_prefix='jev-request') as pool:
                pending = {}

                def submit_next():
                    if run['cancel'] or fatal:
                        return False
                    # Failed jobs go to the tail. Cooling-down jobs never occupy a worker
                    # or block ready jobs behind them.
                    index = next((i for i, job in enumerate(queue) if job['ready_at'] <= time.monotonic()), None)
                    if index is None:
                        return False
                    job = queue.pop(index)
                    for segment in job['batch']:
                        segment.update(status='evaluating', retry_waiting=False)
                        self.event(run, 'segment', segment.copy())
                    request = build_request(run['settings'], job['batch'], windows=windows)
                    run['requests'] += 1
                    if job['attempt'] > 1:
                        run['retry_count'] += 1
                    pending[pool.submit(call_jev, request, key)] = (job, time.perf_counter(), run['requests'])
                    publish_usage()
                    return True

                while pending or (queue and not fatal and not run['cancel']):
                    while len(pending) < parallel and submit_next():
                        pass
                    if not pending:
                        if queue and not fatal and not run['cancel']:
                            delay = max(0, min(job['ready_at'] for job in queue) - time.monotonic())
                            with self.changed:
                                self.changed.wait(timeout=min(delay, .25))
                        continue
                    finished, _ = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
                    for future in finished:
                        job, started, index = pending.pop(future)
                        batch, attempt = job['batch'], job['attempt']
                        elapsed = round(time.perf_counter() - started, 3)
                        stat = {'batch': job['number'], 'request': index, 'attempt': attempt,
                                'segments': len(batch), 'seconds': elapsed, 'status': 'completed'}
                        try:
                            result = future.result()
                            answers = result['answers']
                            decisions = {s['id']: decide(answers.get(s['id']), run['settings']['drop_threshold'], review_enabled(run['settings'])) for s in batch}
                            for name in run['usage']:
                                run['usage'][name] += (result.get('usage') or {}).get(name, 0)
                            for segment in batch:
                                status, reason = decisions[segment['id']]
                                segment.update(status=status, reason=reason, answer=answers[segment['id']], seconds=elapsed)
                                self.event(run, 'segment', segment.copy())
                        except Exception as exc:
                            retryable = isinstance(exc, JevHTTPError) and exc.status in RETRYABLE_HTTP
                            if isinstance(exc, JevHTTPError):
                                stat['http_status'] = exc.status
                            if retryable and attempt <= len(RETRY_DELAYS) and not run['cancel'] and not fatal:
                                delay = RETRY_DELAYS[attempt - 1]
                                queue.append({**job, 'attempt': attempt + 1, 'ready_at': time.monotonic() + delay})
                                stat.update(status='retry_queued', retry_delay=delay)
                                for segment in batch:
                                    segment.update(status='queued', retry_waiting=True,
                                                   reason=f'HTTP {exc.status}，已放回队尾，等待第 {attempt} 次重试')
                                    self.event(run, 'segment', segment.copy())
                            else:
                                stat['status'] = 'failed'
                                if retryable and attempt > len(RETRY_DELAYS):
                                    # Exhausting one batch does not prevent other batches from completing.
                                    run['retry_exhausted'] += 1
                                    reason = '重试次数已用完，自动保留'
                                else:
                                    fatal = True
                                    reason = '请求失败，自动保留'
                                run.setdefault('error', redact(str(exc), key)[:1000])
                                for segment in batch:
                                    segment.update(status='review' if review_enabled(run['settings']) else 'keep', retry_waiting=False, reason=reason)
                                    self.event(run, 'segment', segment.copy())
                        run['batch_stats'].append(stat)
                        publish_usage()
                    if time.perf_counter() - last_persist > 1:
                        self.persist(run)
                        last_persist = time.perf_counter()
            run['status'] = 'cancelled' if run['cancel'] else 'failed' if fatal or run['retry_exhausted'] else 'completed'
        except Exception as exc:
            run['status'] = 'failed'
            run['error'] = redact(str(exc), key)[:1000]
        finally:
            for segment in run['segments']:
                if segment['status'] in ('queued', 'evaluating'):
                    segment.update(status='review' if review_enabled(run['settings']) else 'keep', retry_waiting=False, reason='未完成评估，自动保留')
                    self.event(run, 'segment', segment.copy())
            run['retry_pending'] = 0
            run['finished_at'] = time.time()
            self.persist(run)
            self.event(run, 'done', {'status': run['status'], 'error': run.get('error'), 'requests': run['requests'],
                                    'usage': run['usage'], 'batch_stats': run.get('batch_stats', []),
                                    'retry_count': run.get('retry_count', 0), 'retry_pending': 0,
                                    'retry_exhausted': run.get('retry_exhausted', 0)})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def reply(self, value, code=200, mime='application/json; charset=utf-8'):
        raw = json.dumps(value, ensure_ascii=False).encode() if mime.startswith('application/json') else value.encode() if isinstance(value, str) else value
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        expected = '127.0.0.1:' + str(self.server.server_port)
        if self.headers.get('Host') != expected:
            self.reply({'error': 'Host rejected'}, 403); return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected:
            self.reply({'error': 'Origin rejected'}, 403); return False
        if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.app.token):
            self.reply({'error': '请通过启动器打开面板，访问凭证无效或已过期'}, 401); return False
        return True

    def body(self):
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size <= 100_000:
            raise ValueError('请求大小无效')
        return json.loads(self.rfile.read(size))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not path.startswith('/api/'):
                name = {'/': 'index.html', '/app.js': 'app.js', '/flow.js': 'flow.js', '/i18n.js': 'i18n.js', '/style.css': 'style.css'}.get(path)
                if not name:
                    return self.reply({'error': 'Not found'}, 404)
                mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
                return self.reply((STATIC / name).read_bytes(), mime=mime + '; charset=utf-8')
            if not self.allowed():
                return
            if path == '/api/status':
                return self.reply({**self.app.key_status(), 'data_dir': str(self.app.data)})
            if path == '/api/appearance':
                return self.reply(self.app.appearance)
            if path == '/api/settings':
                return self.reply({'settings': self.app.settings, 'defaults': DEFAULTS, 'defaults_en': DEFAULTS_EN})
            if path == '/api/threads':
                query = parse_qs(parsed.query)
                return self.reply(self.app.store.threads(query.get('q', [''])[0], int(query.get('limit', ['300'])[0])))
            if path == '/api/runs':
                return self.reply([{'id': r['id'], 'title': r['thread']['title'], 'status': r['status']} for r in reversed(list(self.app.runs.values()))])
            parts = path.strip('/').split('/')
            if len(parts) >= 3 and parts[:2] == ['api', 'runs']:
                run = self.app.runs.get(parts[2])
                if not run:
                    return self.reply({'error': '运行不存在'}, 404)
                if len(parts) == 4 and parts[3] == 'events':
                    return self.stream(run, int(parse_qs(parsed.query).get('after', ['-1'])[0]))
                if len(parts) == 4 and parts[3] == 'event-batch':
                    cursor = int(parse_qs(parsed.query).get('after', ['-1'])[0])
                    with self.app.changed:
                        if parse_qs(parsed.query).get('wait') == ['1']:
                            self.app.changed.wait_for(lambda: len(run['events']) > cursor + 1, timeout=1)
                        batch = run['events'][cursor + 1:]
                        terminal = bool(run['events'] and run['events'][-1]['type'] == 'done')
                    return self.reply({'events': batch, 'terminal': terminal})
                if len(parts) == 4 and parts[3] == 'draft':
                    return self.reply(export_markdown(run, parse_qs(parsed.query).get('language', ['zh'])[0]), mime='text/markdown; charset=utf-8')
                if len(parts) == 4 and parts[3] == 'export':
                    return self.reply(self.app.approved_export(run, parse_qs(parsed.query).get('language', ['zh'])[0]), mime='text/markdown; charset=utf-8')
                return self.reply({k: v for k, v in run.items() if k not in ('cancel', 'events')})
            self.reply({'error': 'Not found'}, 404)
        except (ValueError, OSError, KeyError) as exc:
            self.reply({'error': redact(str(exc))}, 400)

    def stream(self, run, cursor):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            while True:
                with self.app.lock:
                    batch = run['events'][cursor + 1:]
                for event in batch:
                    self.wfile.write(('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())
                    self.wfile.flush()
                    cursor = event['seq']
                    if event['type'] == 'done':
                        return
                if not batch:
                    self.wfile.write(b': heartbeat\n\n'); self.wfile.flush()
                with self.app.changed:
                    self.app.changed.wait_for(lambda: len(run['events']) > cursor + 1, timeout=8)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if not self.allowed():
            return
        try:
            value = self.body()
            if self.path == '/api/credentials':
                return self.reply(self.app.set_key(value))
            if self.path == '/api/appearance':
                return self.reply(self.app.set_appearance(value))
            if self.path == '/api/settings':
                with self.app.lock:
                    self.app.settings = validate_settings(value)
                    save_json(self.app.data / 'settings.json', self.app.settings)
                return self.reply(self.app.settings)
            if self.path == '/api/preview':
                return self.reply(self.app.preview(value['thread_id']))
            if self.path == '/api/runs':
                return self.reply({'id': self.app.start(value['thread_id'], value.get('goal'), value.get('preview_id'))}, 201)
            parts = self.path.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api', 'runs']:
                run = self.app.runs.get(parts[2])
                if not run:
                    raise ValueError('运行不存在')
                if parts[3] == 'cancel':
                    with self.app.changed:
                        run['cancel'] = True
                        self.app.changed.notify_all()
                    return self.reply({'ok': True})
                if parts[3] == 'decision':
                    return self.reply(self.app.decide_segment(run['id'], value.get('id'), value.get('status')))
                if parts[3] == 'apply':
                    return self.reply(self.app.apply_run(run['id'], value.get('revision'), value.get('confirmed'), value.get('language', 'zh')))
            self.reply({'error': 'Not found'}, 404)
        except MissingKeyError as exc:
            self.reply({'error': str(exc), 'code': 'KEY_NOT_CONFIGURED'}, 400)
        except (ValueError, KeyError, OSError) as exc:
            self.reply({'error': redact(str(exc))}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--codex-home', default=os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    parser.add_argument('--data-dir', default=str(Path.home() / 'Library/Application Support/JevContext'))
    parser.add_argument('--env-file', default=os.environ.get('JEV_ENV_FILE'))
    args = parser.parse_args()
    app = App(args.codex_home, args.data_dir, args.env_file)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.app = app
    save_json(app.data / 'runtime.json', {'url': 'http://127.0.0.1:' + str(args.port), 'token': app.token, 'pid': os.getpid()})
    print('JevClean listening on http://127.0.0.1:' + str(args.port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
