import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from .launch import reload_services


class ReloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'runtime.json').write_text(json.dumps({'pid': 101, 'url': 'http://127.0.0.1:8766', 'token': 'fixture'}))
        (self.root / 'bridge-runtime.json').write_text(json.dumps({'pid': 102}))

    def tearDown(self):
        self.temp.cleanup()

    def test_active_run_blocks_reload(self):
        opener = MagicMock()
        opener.open.return_value = io.BytesIO(b'[{"status":"running"}]')
        with patch('context_panel.launch.reachable', return_value=True), patch('context_panel.launch.urllib.request.build_opener', return_value=opener), patch('context_panel.launch.os.kill') as kill:
            with self.assertRaises(SystemExit):
                reload_services(self.root)
            kill.assert_not_called()

    def test_stale_pid_never_stops_unrelated_process(self):
        with patch('context_panel.launch.reachable', return_value=False), patch('context_panel.launch.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout='/Applications/ChatGPT.app/Contents/MacOS/ChatGPT')), patch('context_panel.launch.os.kill') as kill:
            with self.assertRaises(SystemExit):
                reload_services(self.root)
            kill.assert_not_called()

    def test_reload_only_signals_verified_bridge_and_service(self):
        process_results = [subprocess.CompletedProcess([], 0, stdout='node /project/context_panel/cdp.mjs'), subprocess.CompletedProcess([], 0, stdout='python3 -m context_panel.server')]
        signals = []
        def kill(pid, sig):
            if sig == 0:
                raise ProcessLookupError()
            signals.append((pid, sig))
        with patch('context_panel.launch.reachable', return_value=False), patch('context_panel.launch.subprocess.run', side_effect=process_results), patch('context_panel.launch.os.kill', side_effect=kill):
            reload_services(self.root)
        self.assertEqual(signals, [(102, signal.SIGINT), (101, signal.SIGTERM)])
