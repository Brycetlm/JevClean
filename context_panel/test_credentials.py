"""Credential persistence and authenticated API contract; no model calls."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from .server import App, Handler, MissingKeyError

KEY = 'fixture-private-key-123456789'


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fallback = patch('context_panel.server.read_key', return_value='')
        self.fallback.start()
        self.app = App(self.root, self.root / 'data')

    def tearDown(self):
        self.fallback.stop()
        self.temp.cleanup()

    def test_persist_priority_permissions_and_no_echo(self):
        with patch('context_panel.server.read_key', return_value='environment-fixture'):
            self.assertEqual(self.app.get_key(), 'environment-fixture')
            self.app.previews['old'] = {}
            self.assertEqual(self.app.set_key({'api_key': '  ' + KEY + '  '}), {'key_configured': True})
            self.assertFalse(self.app.previews)
            self.assertEqual(self.app.get_key(), KEY)
            restored = App(self.root, self.root / 'data')
            self.assertEqual(restored.get_key(), KEY)
            path = self.root / 'data' / 'credentials.json'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())['api_key'], KEY)
            self.assertNotIn(KEY, json.dumps(restored.settings))
            self.assertNotIn(KEY, json.dumps(restored.key_status()))
            self.assertFalse(list(path.parent.glob('.credentials-*')))

    def test_invalid_input_does_not_replace_key(self):
        self.app.set_key({'api_key': KEY})
        for value in (None, [], {}, {'api_key': 4}, {'api_key': ''}, {'api_key': 'short'},
                      {'api_key': 'A' * 4097}, {'api_key': 'A' * 20 + '\nSECRET'}, {'api_key': '中文' * 20}):
            with self.assertRaises(ValueError) as err:
                self.app.set_key(value)
            self.assertNotIn(KEY, str(err.exception))
            self.assertEqual(self.app.get_key(), KEY)

    def test_failed_save_preserves_old_credential_and_cleans_temp(self):
        self.app.set_key({'api_key': KEY})
        with patch('context_panel.server.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.app.set_key({'api_key': 'replacement-fixture-key-12345'})
        self.assertEqual(self.app.get_key(), KEY)
        self.assertFalse(list(self.app.data.glob('.credentials-*')))

    def test_missing_key_blocks_before_thread_or_model_start(self):
        with patch('context_panel.server.threading.Thread') as worker, patch('context_panel.server.call_jev') as call:
            with self.assertRaises(MissingKeyError):
                self.app.start('anything')
            worker.assert_not_called()
            call.assert_not_called()
            self.assertFalse(self.app.runs)

    def test_http_auth_status_and_missing_key_code(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None, auth=True, origin=None):
            connection = HTTPConnection('127.0.0.1', server.server_port)
            headers = {'Content-Type': 'application/json'}
            if auth:
                headers['Authorization'] = 'Bearer ' + self.app.token
            if origin:
                headers['Origin'] = origin
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        try:
            self.assertEqual(request('POST', '/api/credentials', {'api_key': KEY}, auth=False)[0], 401)
            self.assertEqual(request('POST', '/api/credentials', {'api_key': KEY}, origin='http://evil.test')[0], 403)
            self.assertFalse(self.app.get_key())
            status, body = request('POST', '/api/runs', {'thread_id': 'anything'})
            self.assertEqual(status, 400)
            self.assertEqual(body['code'], 'KEY_NOT_CONFIGURED')
            self.assertEqual(request('POST', '/api/credentials', {'api_key': KEY}), (200, {'key_configured': True}))
            for path in ('/api/status', '/api/settings', '/api/runs', '/api/credentials'):
                status, body = request('GET', path)
                self.assertNotIn(KEY, json.dumps(body))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
