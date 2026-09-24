import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from .server import App
from .core import JevHTTPError, DEFAULTS, validate_settings, context_windows, build_request, match_skip_patterns
from .test_core import message


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'conversation.jsonl'
        self.source.write_bytes(message('保留目标和决定', 'user') + message('A' * 1300 + '\n\n' + 'B' * 1300))
        with sqlite3.connect(self.root / 'state_5.sqlite') as c:
            c.execute('CREATE TABLE threads (id TEXT,title TEXT,cwd TEXT,rollout_path TEXT)')
            c.execute('INSERT INTO threads VALUES (?,?,?,?)', ('one', 'Fixture', str(self.root), str(self.source)))
        self.key_patch = patch('context_panel.server.read_key', return_value='fixture-key')
        self.key_patch.start()
        self.app = App(self.root, self.root / 'reports')

    def tearDown(self):
        self.key_patch.stop()
        self.temp.cleanup()

    def test_regex_defaults_validation_and_explicit_disable(self):
        self.assertEqual(validate_settings({})['skip_patterns'], ['key', 'apikey'])
        self.assertEqual(validate_settings({'skip_patterns': []})['skip_patterns'], [])
        self.assertEqual(match_skip_patterns(['KEY', 'apikey', 'API_KEY', 'keyboard', '普通消息'], DEFAULTS['skip_patterns']), {0, 1, 2, 3})
        self.assertEqual(match_skip_patterns(['KEY'], []), set())
        for value in ('key', ['['], [''], ['x'] * 21, ['x' * 501], [1]):
            with self.assertRaises(ValueError):
                validate_settings({'skip_patterns': value})
        with self.assertRaisesRegex(ValueError, '超时'):
            match_skip_patterns(['a' * 5000 + '!'], ['(a+)+$'], timeout=0.15)

    def test_regex_skips_whole_message_before_redaction_and_excludes_neighbors(self):
        self.source.write_bytes(message('ordinary left') + message('fixture-key' + 'A' * 1400 + '\n\n' + 'B' * 1400, 'user') + message('ordinary right'))
        original = self.source.read_bytes()
        summary = self.app.preview('one')
        self.assertEqual(summary['regex_skipped_messages'], 1)
        self.assertEqual(summary['regex_skipped'], 2)
        self.assertEqual(summary['model_segments'], 2)
        segments = self.app.previews[summary['id']]['extracted']['segments']
        skipped = [s for s in segments if s['regex_skipped']]
        self.assertTrue(all(s['protected'] and s['status'] == 'keep' for s in skipped))
        # The original matching token was removed by redaction, but still caused the skip.
        self.assertNotIn('fixture-key', skipped[0]['text'])
        batch = [s for s in segments if not s['protected']]
        windows = context_windows(segments, 3)
        self.assertEqual([s['id'] for s in windows[batch[0]['id']]], [batch[0]['id']])
        request = build_request(self.app.settings, batch, windows=windows)
        state = json.loads(request['state'])
        self.assertEqual({s['id'] for s in state['segments']}, {s['id'] for s in batch})
        self.assertEqual(set(request['questions']), {s['id'] for s in batch})
        # Even a caller-supplied window cannot reintroduce a skipped message.
        direct = build_request(self.app.settings, batch, windows={s['id']: segments for s in batch})
        self.assertEqual(len(json.loads(direct['state'])['segments']), 2)
        with self.assertRaises(ValueError):
            build_request(self.app.settings, skipped)
        self.assertEqual(self.source.read_bytes(), original)
        self.app.settings = validate_settings({**self.app.settings, 'skip_patterns': []})
        fresh = self.app.preview('one')
        self.assertEqual(fresh['regex_skipped'], 0)
        self.assertEqual(fresh['model_segments'], 4)
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            self.app.start('one', preview_id=summary['id'])

    def test_all_regex_skipped_run_makes_no_model_calls(self):
        self.source.write_bytes(message('APIKEY setup', 'user') + message('key configured'))
        preview = self.app.preview('one')
        self.assertEqual(preview['requests'], 0)
        extracted = self.app.previews[preview['id']]['extracted']
        with patch('context_panel.server.threading.Thread'):
            run_id = self.app.start('one', preview_id=preview['id'])
        run = self.app.runs[run_id]
        with patch('context_panel.server.call_jev') as call:
            self.app.work(run, extracted)
            call.assert_not_called()
        self.assertEqual(run['status'], 'completed')
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))

    def test_appearance_persists_without_changing_preview_or_rules(self):
        summary = self.app.preview('one')
        rules = copy.deepcopy(self.app.settings)
        for theme in ('colorful', 'fresh', 'tech', 'plain'):
            self.assertEqual(self.app.set_appearance({'theme': theme, 'language': 'zh'}), {'theme': theme, 'language': 'zh'})
        restored = App(self.root, self.root / 'reports')
        self.assertEqual(restored.appearance, {'theme': 'plain', 'language': 'zh'})
        self.assertEqual(self.app.settings, rules)
        with patch('context_panel.server.threading.Thread'):
            run_id = self.app.start('one', preview_id=summary['id'])
        self.assertEqual(self.app.runs[run_id]['settings'], rules)
        for invalid in (None, [], {'theme': 'unknown'}, {'theme': ['fresh']}):
            with self.assertRaises(ValueError):
                self.app.set_appearance(invalid)
        self.assertEqual(self.app.appearance, {'theme': 'plain', 'language': 'zh'})

    def test_language_updates_preserve_theme_prompts_and_snapshot(self):
        summary = self.app.preview('one')
        rules = copy.deepcopy(self.app.settings)
        self.app.set_appearance({'theme': 'tech'})
        self.assertEqual(self.app.set_appearance({'language': 'en'}), {'theme': 'tech', 'language': 'en'})
        self.assertEqual(self.app.set_appearance({'theme': 'plain'}), {'theme': 'plain', 'language': 'en'})
        for value in ('fr', None, [], ''):
            with self.assertRaises(ValueError):
                self.app.set_appearance({'language': value})
        restored = App(self.root, self.root / 'reports')
        self.assertEqual(restored.appearance, {'theme': 'plain', 'language': 'en'})
        self.assertEqual(restored.settings, rules)
        with patch('context_panel.server.threading.Thread'):
            self.app.start('one', preview_id=summary['id'])

    def test_localized_export_keeps_content_and_approval_gate(self):
        run = self.completed()
        with self.assertRaises(ValueError):
            self.app.approved_export(run, 'en')
        self.app.apply_run(run['id'], run['revision'], True, 'en')
        english = self.app.approved_export(run, 'en')
        chinese = self.app.approved_export(run, 'zh')
        self.assertIn('# Compact conversation', english)
        self.assertIn('# 精简会话', chinese)
        for segment in run['segments']:
            if segment['status'] != 'drop':
                self.assertIn(segment['text'], english)
                self.assertIn(segment['text'], chinese)
        self.assertEqual((self.app.data / run['applied']['file']).read_text(), english)
        self.assertEqual(run['applied']['language'], 'en')

    def test_user_classification_default_toggle_and_long_segment_protection(self):
        self.source.write_bytes(message('user question', 'user') + message('assistant answer') +
                                message('U' * 6001, 'user') + message('A' * 6001))
        enabled = self.app.preview('one')
        self.assertTrue(self.app.settings['classify_user_messages'])
        self.assertEqual((enabled['protected'], enabled['model_segments']), (2, 2))
        self.app.settings['classify_user_messages'] = False
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            self.app.start('one', preview_id=enabled['id'])
        disabled = self.app.preview('one')
        self.assertEqual((disabled['protected'], disabled['model_segments']), (3, 1))
        segments = self.app.previews[disabled['id']]['extracted']['segments']
        self.assertTrue(all(s['protected'] for s in segments if s['role'] == 'user'))

    def test_window_passes_neighboring_completion_across_request_boundary(self):
        self.source.write_bytes(message('deploy request', 'user') + message('deploy pending') + message('deploy completed'))
        self.app.settings.update(batch_size=1, concurrency=1, classify_user_messages=False)
        summary = self.app.preview('one')
        self.assertEqual(summary['context_window_size'], 3)
        self.app.settings['context_window_size'] = 5
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            self.app.start('one', preview_id=summary['id'])
        self.app.settings['context_window_size'] = 3
        with patch('context_panel.server.threading.Thread'):
            run_id = self.app.start('one', preview_id=summary['id'])
        requests = []
        def classify(request, key):
            requests.append(request)
            return {'answers': {sid: {'choice':'keep','probabilities':{'keep':.99,'drop':.01}}
                                for sid in request['questions']}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(self.app.runs[run_id], self.app.previews[summary['id']]['extracted'])
        self.assertEqual(len(requests), 2)
        state = json.loads(requests[0]['state'])
        self.assertEqual([s['text'] for s in state['segments']], ['deploy request','deploy pending','deploy completed'])
        self.assertEqual(len(requests[0]['questions']), 1)
        self.assertNotIn('user_context', state)

    def test_single_role_compact_copies_are_text_and_source_is_unchanged(self):
        self.source.write_bytes(message('question marker', 'user') + message('answer marker'))
        original = self.source.read_bytes()
        for kept_role in ('user', 'assistant'):
            with self.subTest(kept_role=kept_role):
                summary = self.app.preview('one')
                with patch('context_panel.server.threading.Thread'):
                    run_id = self.app.start('one', preview_id=summary['id'])
                run = self.app.runs[run_id]
                extracted = copy.deepcopy(self.app.previews[summary['id']]['extracted'])
                seen_roles = set()
                def classify(request, key):
                    segments = json.loads(request['state'])['segments']
                    seen_roles.update(s['role'] for s in segments)
                    return {'answers': {s['id']: {'choice': 'keep' if s['role'] == kept_role else 'drop',
                             'probabilities': {'keep': .99 if s['role'] == kept_role else .01,
                                               'drop': .01 if s['role'] == kept_role else .99}} for s in segments}}
                with patch('context_panel.server.call_jev', side_effect=classify):
                    self.app.work(run, extracted)
                self.assertEqual(seen_roles, {'user', 'assistant'})
                self.assertEqual(run['status'], 'completed')
                self.assertTrue(all(s['role'] == kept_role for s in run['segments'] if s['status'] == 'keep'))
                self.app.apply_run(run_id, run['revision'], True)
                text = self.app.approved_export(run)
                self.assertIsInstance(text, str)
                self.assertIn('question marker' if kept_role == 'user' else 'answer marker', text)
                self.assertNotIn('answer marker' if kept_role == 'user' else 'question marker', text)
                self.assertEqual(self.source.read_bytes(), original)

    def completed(self):
        self.app.settings['classify_user_messages'] = False
        summary = self.app.preview('one')
        with patch('context_panel.server.threading.Thread'):
            run_id = self.app.start('one', preview_id=summary['id'])
        run = self.app.runs[run_id]
        extracted = copy.deepcopy(self.app.previews[summary['id']]['extracted'])
        def classify(request, key):
            return {'answers': {sid: {'choice': 'drop', 'probabilities': ({'keep': .02, 'drop': .96, 'review': .02} if 'review' in question['criteria'] else {'keep': .04, 'drop': .96})} for sid, question in request['questions'].items()}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(run, extracted)
        return run

    def prepared(self, count=6):
        self.source.write_bytes(message('user goal', 'user') + b''.join(message('fact ' + str(i)) for i in range(count)))
        self.app.settings.update(batch_size=1, concurrency=2, manual_review=False, classify_user_messages=False)
        summary = self.app.preview('one')
        with patch('context_panel.server.threading.Thread'):
            run_id = self.app.start('one', preview_id=summary['id'])
        return self.app.runs[run_id], copy.deepcopy(self.app.previews[summary['id']]['extracted'])

    def test_bounded_parallel_requests_and_immutable_snapshot(self):
        run, extracted = self.prepared()
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        active = peak = total = 0
        def classify(request, key):
            nonlocal active, peak, total
            with lock:
                active += 1
                total += 1
                peak = max(peak, active)
            barrier.wait(timeout=2)
            time.sleep(.01)
            with lock:
                active -= 1
            return {'answers': {sid: {'choice': 'keep', 'probabilities': {'keep': .99, 'drop': .01}} for sid in request['questions']}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(run, extracted)
        self.assertEqual(run['status'], 'completed')
        self.assertEqual((peak, total, run['requests']), (2, 6, 6))
        self.assertEqual(run['events'][0]['data']['segments'][1]['status'], 'queued')
        self.assertEqual(run['segments'][1]['status'], 'keep')
        self.assertEqual(run['events'][-1]['type'], 'done')

    def test_failure_stops_new_batches_and_binary_mode_auto_keeps_remaining(self):
        run, extracted = self.prepared()
        barrier = threading.Barrier(2)
        def classify(request, key):
            barrier.wait(timeout=2)
            if 's0002' in request['questions']:
                raise JevHTTPError(400, 'invalid request')
            time.sleep(.04)  # Keep the successful in-flight call pending until failure is observed.
            return {'answers': {sid: {'choice': 'keep', 'probabilities': {'keep': .99, 'drop': .01}} for sid in request['questions']}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(run, extracted)
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['requests'], 2)
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))
        with self.assertRaises(ValueError):
            self.app.decide_segment(run['id'], 's0002', 'review')

    def test_transient_failure_requeues_identical_batch_after_other_work(self):
        run, extracted = self.prepared(count=3)
        run['settings']['concurrency'] = 1
        calls = []
        def classify(request, key):
            calls.append(copy.deepcopy(request))
            if len(calls) == 1:
                raise JevHTTPError(503, 'unavailable')
            return {'answers': {sid: {'choice': 'drop', 'probabilities': {'keep': .01, 'drop': .99}} for sid in request['questions']}}
        with patch('context_panel.server.call_jev', side_effect=classify), patch('context_panel.server.RETRY_DELAYS', (0, 0)):
            self.app.work(run, extracted)
        self.assertEqual([next(iter(r['questions'])) for r in calls], ['s0002', 's0003', 's0004', 's0002'])
        self.assertEqual(calls[0], calls[-1])
        self.assertEqual((run['status'], run['requests'], run['retry_count'], run['retry_pending']), ('completed', 4, 1, 0))
        self.assertNotIn('error', run)
        self.assertTrue(all(s['status'] == 'drop' for s in run['segments'][1:]))
        self.assertEqual(run['batch_stats'][0]['status'], 'retry_queued')
        self.assertEqual(run['batch_stats'][-1]['attempt'], 2)
        self.assertTrue(any(e['type'] == 'segment' and e['data'].get('retry_waiting') for e in run['events']))

    def test_exhausted_batch_is_preserved_and_other_batches_finish(self):
        for manual in (False, True):
            with self.subTest(manual=manual):
                run, extracted = self.prepared(count=3)
                run['settings'].update(concurrency=1, manual_review=manual)
                calls = []
                def classify(request, key):
                    sid = next(iter(request['questions']))
                    calls.append(sid)
                    if sid == 's0002':
                        raise JevHTTPError(503, 'unavailable')
                    probs = {'keep': .01, 'drop': .99, **({'review': 0} if manual else {})}
                    return {'answers': {sid: {'choice': 'drop', 'probabilities': probs}}}
                with patch('context_panel.server.call_jev', side_effect=classify), patch('context_panel.server.RETRY_DELAYS', (0, 0)):
                    self.app.work(run, extracted)
                self.assertEqual(calls, ['s0002', 's0003', 's0004', 's0002', 's0002'])
                self.assertEqual((run['status'], run['retry_count'], run['retry_exhausted']), ('failed', 2, 1))
                self.assertEqual([s['status'] for s in run['segments']], ['keep', 'review' if manual else 'keep', 'drop', 'drop'])
                self.assertEqual(run['events'][-1]['data']['retry_pending'], 0)

    def test_parallel_retries_stay_within_concurrency_limit(self):
        run, extracted = self.prepared(count=4)
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        calls, active, peak = {}, 0, 0
        def classify(request, key):
            nonlocal active, peak
            sid = next(iter(request['questions']))
            with lock:
                calls[sid] = calls.get(sid, 0) + 1
                attempt = calls[sid]
                active += 1
                peak = max(peak, active)
            try:
                if sid in ('s0002', 's0003') and attempt == 1:
                    barrier.wait(timeout=2)
                    raise JevHTTPError(503, 'unavailable')
                time.sleep(.01)
                return {'answers': {sid: {'choice': 'keep', 'probabilities': {'keep': .99, 'drop': .01}}}}
            finally:
                with lock:
                    active -= 1
        with patch('context_panel.server.call_jev', side_effect=classify), patch('context_panel.server.RETRY_DELAYS', (0, 0)):
            self.app.work(run, extracted)
        self.assertEqual((peak, run['requests'], run['retry_count']), (2, 6, 2))
        self.assertEqual(run['status'], 'completed')
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))

    def test_retry_backoff_and_max_attempts(self):
        run, extracted = self.prepared(count=1)
        calls = []
        def fail(request, key):
            calls.append(time.monotonic())
            raise JevHTTPError(504, 'unavailable')
        with patch('context_panel.server.call_jev', side_effect=fail), patch('context_panel.server.RETRY_DELAYS', (.02, .03)):
            self.app.work(run, extracted)
        self.assertEqual(len(calls), 3)
        self.assertGreaterEqual(calls[1] - calls[0], .02)
        self.assertGreaterEqual(calls[2] - calls[1], .03)
        self.assertEqual(run['retry_exhausted'], 1)

    def test_cancel_during_backoff_never_submits_retry(self):
        run, extracted = self.prepared(count=1)
        def fail(request, key):
            raise JevHTTPError(502, 'unavailable')
        with patch('context_panel.server.call_jev', side_effect=fail) as call, patch('context_panel.server.RETRY_DELAYS', (10, 20)):
            worker = threading.Thread(target=self.app.work, args=(run, extracted))
            worker.start()
            with self.app.changed:
                queued = self.app.changed.wait_for(lambda: run.get('retry_pending') == 1, timeout=2)
                run['cancel'] = True
                self.app.changed.notify_all()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertTrue(queued)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(run['status'], 'cancelled')
        self.assertEqual(run['retry_pending'], 0)
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))

    def test_cancel_waits_for_inflight_and_does_not_schedule_more(self):
        run, extracted = self.prepared()
        barrier = threading.Barrier(2)
        def classify(request, key):
            barrier.wait(timeout=2)
            run['cancel'] = True
            return {'answers': {sid: {'choice': 'keep', 'probabilities': {'keep': .99, 'drop': .01}} for sid in request['questions']}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(run, extracted)
        self.assertEqual(run['status'], 'cancelled')
        self.assertEqual(run['requests'], 2)
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))

    def test_invalid_batch_does_not_apply_partial_drop(self):
        run, extracted = self.prepared(count=2)
        run['settings'].update(batch_size=2)
        def classify(request, key):
            return {'answers': {'s0002': {'choice': 'drop', 'probabilities': {'keep': .01, 'drop': .99}}, 's0003': None}}
        with patch('context_panel.server.call_jev', side_effect=classify):
            self.app.work(run, extracted)
        self.assertEqual(run['status'], 'failed')
        self.assertTrue(all(s['status'] == 'keep' for s in run['segments']))

    def test_preview_counts_messages_separately_from_segments_without_model_call(self):
        with patch('context_panel.server.call_jev') as call:
            result = self.app.preview('one')
        call.assert_not_called()
        self.assertEqual((result['messages'], result['segments'], result['protected'], result['requests']), (2, 3, 0, 1))

    def test_start_uses_preview_snapshot_even_if_history_grows(self):
        summary = self.app.preview('one')
        self.source.write_bytes(self.source.read_bytes() + message('added after preview', 'user'))
        with patch('context_panel.server.threading.Thread') as thread:
            self.app.start('one', preview_id=summary['id'])
        extracted = thread.call_args.kwargs['args'][1]
        self.assertEqual(len(extracted['segments']), 3)
        self.assertNotIn('added after preview', json.dumps(extracted))

    def test_expired_or_changed_config_preview_cannot_start(self):
        summary = self.app.preview('one')
        self.app.settings['include_tools'] = True
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            self.app.start('one', preview_id=summary['id'])
        self.app.settings['include_tools'] = False
        self.app.previews[summary['id']]['summary']['expires_at'] = 0
        with self.assertRaisesRegex(ValueError, '预览已过期'):
            self.app.start('one', preview_id=summary['id'])

    def test_apply_requires_confirmation_and_keeps_original_bytes(self):
        run = self.completed()
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            self.app.approved_export(run)
        with self.assertRaises(ValueError):
            self.app.apply_run(run['id'], 0, False)
        applied = self.app.apply_run(run['id'], 0, True)
        self.assertTrue((self.app.data / applied['file']).exists())
        exported = self.app.approved_export(run)
        self.assertIn('保留目标和决定', exported)
        self.assertNotIn('A' * 100, exported)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.app.apply_run(run['id'], 0, True), applied)

    def test_manual_revision_invalidates_apply_and_review_stays_in_copy(self):
        self.app.settings['manual_review'] = True
        run = self.completed()
        applied = self.app.apply_run(run['id'], 0, True)
        candidate = next(s for s in run['segments'] if not s['protected'])
        change = self.app.decide_segment(run['id'], candidate['id'], 'review')
        self.assertEqual(change['revision'], 1)
        with self.assertRaises(ValueError):
            self.app.apply_run(run['id'], 0, True)
        with self.assertRaises(ValueError):
            self.app.approved_export(run)
        with self.assertRaises(ValueError):
            self.app.decide_segment(run['id'], run['segments'][0]['id'], 'drop')
        self.app.apply_run(run['id'], 1, True)
        self.assertIn(candidate['text'], self.app.approved_export(run))
        self.assertTrue((self.app.data / applied['file']).exists())


if __name__ == '__main__':
    unittest.main()
