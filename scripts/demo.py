"""Synthetic screenshot server: no Codex files, credentials or model requests."""
import argparse
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_panel.core import DEFAULTS, DEFAULTS_EN
from context_panel.server import App, Handler, STATIC


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=['zh', 'en'], default='zh')
    parser.add_argument('--port', type=int, default=8777)
    args = parser.parse_args()
    english = args.language == 'en'
    with tempfile.TemporaryDirectory(prefix='jevclean-demo-') as directory:
        root = Path(directory)
        app = App(root / 'empty-codex', root / 'data')
        app.token = 'demo-only'
        app.get_key = lambda: ''  # Demo never reads environment credentials.
        app.settings = copy.deepcopy(DEFAULTS_EN if english else DEFAULTS)
        app.appearance = {'theme': 'fresh', 'language': args.language}
        samples = ([
            ('user', 'Build a reading-list app. Keep keyboard navigation and offline access.', 'keep'),
            ('assistant', 'The first build failed because the icon import was missing.', 'drop'),
            ('assistant', 'The import is fixed. The app now builds successfully.', 'drop'),
            ('user', 'Keep the local SQLite storage decision. No cloud account is required.', 'keep'),
            ('assistant', 'Saved articles use an id, title, URL and reading status. This is the current schema.', 'keep'),
            ('user', 'The loading indicator looks good. This visual task is accepted.', 'drop'),
            ('assistant', 'I will check the button spacing next.', 'drop'),
            ('assistant', 'Button spacing is fixed and the screenshot has been reviewed.', 'drop'),
            ('user', 'Next: add export to Markdown and preserve the article order.', 'keep'),
            ('assistant', 'The export path is still unfinished. Add coverage for empty lists and Unicode titles.', 'keep'),
            ('user', 'Use the existing app theme. Export must also work offline.', 'keep'),
            ('assistant', 'The earlier dependency installation is complete.', 'drop'),
        ] if english else [
            ('user', '做一个阅读清单应用，保留键盘导航和离线使用能力。', 'keep'),
            ('assistant', '首次构建失败，原因是缺少图标导入。', 'drop'),
            ('assistant', '图标导入已经修复，构建通过。', 'drop'),
            ('user', '继续使用本地 SQLite 存储，不要求用户注册云端账户。', 'keep'),
            ('assistant', '文章包含编号、标题、链接和阅读状态，这是当前生效的数据结构。', 'keep'),
            ('user', '加载效果已经验收，这项视觉需求完成了。', 'drop'),
            ('assistant', '我接下来检查按钮的间距。', 'drop'),
            ('assistant', '按钮间距已经修复，截图也检查过了。', 'drop'),
            ('user', '下一步增加 Markdown 导出，保留文章原有顺序。', 'keep'),
            ('assistant', '导出功能尚未完成，还需要验证空清单和中文标题。', 'keep'),
            ('user', '沿用当前主题，导出在离线时也必须能用。', 'keep'),
            ('assistant', '前面的依赖安装已经完成。', 'drop'),
        ])
        now = time.time()
        thread = {'id': '11111111-1111-4111-8111-111111111111', 'title': 'Reading list · next iteration' if english else '阅读清单 · 下一轮迭代', 'cwd': '/demo/reading-list', 'updated_at': now}
        segments = [{'id': 's%04d' % (i + 1), 'role': role, 'text': text, 'line': i + 1, 'source_file': 'synthetic-demo.jsonl', 'protected': False, 'status': status, 'reason': 'Jev 分类', 'answer': {'choice': status, 'probabilities': {'keep': .97 if status == 'keep' else .03, 'drop': .97 if status == 'drop' else .03}}} for i, (role, text, status) in enumerate(samples)]
        preview = {'id': 'demo-preview', 'thread_id': thread['id'], 'messages': 12, 'segments': 12, 'characters': sum(len(s['text']) for s in segments), 'protected': 0, 'model_segments': 12, 'requests': 3, 'concurrency': 2, 'context_window_size': 3, 'regex_skipped': 0, 'regex_skipped_messages': 0, 'snapshot_at': now, 'expires_at': now + 3600}
        app.runs['demo'] = {'id': 'demo', 'thread': thread, 'settings': app.settings, 'preview': preview, 'status': 'completed', 'segments': segments, 'events': [], 'cancel': False, 'revision': 0, 'applied': None, 'requests': 0, 'usage': {}, 'retry_count': 0}
        app.store.threads = lambda *a, **kw: [thread]

        class DemoHandler(Handler):
            def do_GET(self):
                if self.path.split('?', 1)[0] == '/':
                    html = (STATIC / 'index.html').read_text()
                    banner = 'DEMO · Synthetic data · No model requests' if english else '演示模式 · 合成数据 · 不调用模型'
                    html = html.replace('<body>', '<body><div style="text-align:center;padding:7px;background:#e8f3ef;color:#396d5b;font-size:11px">' + banner + '</div><script>sessionStorage.setItem("jev-run","demo");</script>')
                    return self.reply(html, mime='text/html; charset=utf-8')
                return super().do_GET()

            def do_POST(self):
                # Only local UI preferences are mutable in screenshot mode.
                if self.path not in ('/api/appearance', '/api/settings'):
                    if self.allowed():
                        self.reply({'error': 'Demo only; model calls and credentials are disabled.'}, 400)
                    return
                return super().do_POST()

        server = ThreadingHTTPServer(('127.0.0.1', args.port), DemoHandler)
        server.app = app
        print('Synthetic demo: http://127.0.0.1:%s/#token=demo-only' % args.port, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
