import io
import urllib.error
from unittest.mock import patch
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .core import JevHTTPError, call_jev, CodexStore, DEFAULTS, DEFAULTS_EN, LEGACY_DEFAULTS, LEGACY_DEFAULTS_EN, build_request, context_windows, decide, redact, validate_settings


def record(payload, kind='response_item', ordinal=None):
    data = {'type': kind, 'payload': payload}
    if ordinal is not None:
        data['ordinal'] = ordinal
    return (json.dumps(data) + '\n').encode()


def message(text, role='assistant'):
    return record({'type': 'message', 'role': role, 'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': text}]})


class FilteringTests(unittest.TestCase):
    def test_http_error_preserves_status_for_retry_without_leaking_key(self):
        error = urllib.error.HTTPError('https://example.invalid', 503, 'unavailable', {}, io.BytesIO(b'fixture-secret'))
        with patch('context_panel.core.urllib.request.urlopen', side_effect=error):
            with self.assertRaises(JevHTTPError) as caught:
                call_jev({}, 'fixture-secret')
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn('fixture-secret', str(caught.exception))

    def test_thread_search_partial_words_rank_and_recent_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            with sqlite3.connect(Path(folder) / 'state_5.sqlite') as conn:
                conn.execute('CREATE TABLE threads (id TEXT,title TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER)')
                conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?)', [
                    ('a', 'Jev 上下文整理', '/work/tools', 1, 0),
                    ('b', '上下文压缩', '/work/tools', 4, 0),
                    ('c', 'JEV 接入指南', '/work/docs', 3, 0),
                    ('d', '天气分析', '/work/loop', 2, 0),
                ])
            store = CodexStore(folder)
            self.assertEqual([t['id'] for t in store.threads(limit=3)], ['b', 'c', 'd'])
            self.assertEqual([t['id'] for t in store.threads('@jev 上下')], ['a', 'b', 'c'])
            self.assertEqual([t['id'] for t in store.threads('整理')], ['a'])
            self.assertEqual([t['id'] for t in store.threads('LOOP')], ['d'])
            self.assertEqual(store.threads('不存在'), [])

    def test_thread_picker_uses_visible_name_recency_and_excludes_subagents(self):
        with tempfile.TemporaryDirectory() as folder:
            with sqlite3.connect(Path(folder) / 'state_5.sqlite') as conn:
                conn.execute('CREATE TABLE threads (id TEXT,title TEXT,name TEXT,cwd TEXT,updated_at INTEGER,recency_at INTEGER,archived INTEGER,thread_source TEXT,source TEXT)')
                conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)', [
                    ('a', 'original user message', 'Jev 面板', '/tools', 100, 1, 0, 'user', 'vscode'),
                    ('b', 'another prompt', '最近聊的任务', '/tools', 2, 2, 0, 'user', 'vscode'),
                    ('c', 'internal approval transcript', 'Jev 内部检查', '/tools', 300, 3, 0, 'subagent', 'exec'),
                    ('d', 'archived prompt', 'Jev 已归档', '/tools', 400, 4, 1, 'user', 'vscode'),
                ])
            store = CodexStore(folder)
            self.assertEqual([t['id'] for t in store.threads()], ['b', 'a'])
            self.assertEqual([t['title'] for t in store.threads('面板')], ['Jev 面板'])
            self.assertEqual([t['id'] for t in store.threads('jev')], ['d', 'a'])

    def test_optional_review_changes_request_classes_and_uncertain_decision(self):
        settings = validate_settings({})
        self.assertFalse(settings['manual_review'])
        self.assertEqual(settings['concurrency'], 2)
        request = build_request(settings, [{'id': 's1', 'text': 'fact', 'role': 'assistant'}], [])
        self.assertEqual(set(request['questions']['s1']['criteria']), {'keep', 'drop'})
        answer = {'choice': 'drop', 'probabilities': {'keep': .4, 'drop': .6}}
        self.assertEqual(decide(answer, .9, False)[0], 'keep')
        settings['manual_review'] = True
        request = build_request(settings, [{'id': 's1', 'text': 'fact', 'role': 'assistant'}], [])
        self.assertEqual(set(request['questions']['s1']['criteria']), {'keep', 'drop', 'review'})
        for value in [{'manual_review': 'false'}, {'concurrency': 0}, {'concurrency': 5}, {'concurrency': True}]:
            with self.assertRaises(ValueError):
                validate_settings(value)

    def test_unknown_response_cannot_delete(self):
        for answer in [None, {'choice': 'drop'}, {'choice': 'drop', 'probabilities': {'keep': 0, 'drop': 2, 'review': 0}}]:
            with self.assertRaises(ValueError):
                decide(answer, .9)

    def test_drop_threshold_uses_probability_not_confidence(self):
        answer = {'choice': 'drop', 'confidence': .99, 'probabilities': {'drop': .55, 'keep': .4, 'review': .05}}
        self.assertEqual(decide(answer, .9)[0], 'review')

    def test_redaction(self):
        text = 'vck_' + 'x' * 40 + ' /Users/example/secret key=fixture-key'
        cleaned = redact(text, 'fixture-key')
        self.assertNotIn('example', cleaned)
        self.assertNotIn('fixture-key', cleaned)
        self.assertNotIn('vck_', cleaned)
        self.assertIn('/Users/example/', redact(text, 'fixture-key', anonymize_paths=False))
        for prefix in ['vck_', 'vck\\_', 'vck\\\\_']:
            self.assertNotIn('x' * 40, redact('测试' + prefix + 'x' * 40))

    def test_inconsistent_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            decide({'choice': 'drop', 'probabilities': {'keep': .99, 'drop': .95, 'review': .5}}, .9)
        with self.assertRaises(ValueError):
            decide({'choice': 'drop', 'probabilities': {'keep': .95, 'drop': .04, 'review': .01}}, .9)

    def test_config_validation(self):
        for value in [{'drop_threshold': 0}, {'batch_size': 40}, {'prompt': ' '}, {'include_tools': 'false'}, {'classify_user_messages': 'false'}]:
            with self.assertRaises(ValueError):
                validate_settings(value)

    def test_request_contains_target_text(self):
        request = build_request(DEFAULTS, [{'id': 's1', 'role': 'assistant', 'text': 'unique fact'}], [])
        self.assertIn('unique fact', request['state'])
        self.assertIn('s1', request['questions'])

    def test_single_prompt_needs_no_placeholder_and_attaches_data(self):
        settings = validate_settings({'prompt': '只保留尚未完成的工作。'})
        segments = [{'id': 's017', 'role': 'user', 'text': '还有登录页未完成'}]
        request = build_request(settings, segments, ['用户目标'])
        state = json.loads(request['state'])
        self.assertEqual(state['instructions'], settings['prompt'])
        self.assertEqual(state['segments'], segments)
        self.assertEqual(state['user_context'], ['用户目标'])
        self.assertIn('s017', request['questions']['s017']['instructions'])
        self.assertNotIn('{id}', request['questions']['s017']['instructions'])
        self.assertNotIn('question', settings)

    def test_context_window_validation_and_edges(self):
        self.assertEqual(validate_settings({})['context_window_size'], 3)
        for bad in [0, 2, 22, True, '3', 3.0]:
            with self.assertRaises(ValueError):
                validate_settings({'context_window_size': bad})
        segments = [{'id': 's'+str(i), 'role': 'assistant', 'text': str(i)} for i in range(7)]
        windows = context_windows(segments, 3)
        self.assertEqual([s['id'] for s in windows['s3']], ['s2', 's3', 's4'])
        self.assertEqual([s['id'] for s in windows['s0']], ['s0', 's1'])
        self.assertEqual([s['id'] for s in windows['s6']], ['s5', 's6'])
        self.assertEqual(context_windows(segments, 1)['s3'], [segments[3]])
        self.assertEqual(len(context_windows(segments, 5)['s3']), 5)

    def test_request_windows_cross_batches_and_deduplicate_neighbors(self):
        segments = [{'id': 's'+str(i), 'role': 'assistant', 'text': str(i)} for i in range(7)]
        segments[2]['protected'] = True
        segments[4]['text'] = 'vck_' + 'x' * 40
        request = build_request(DEFAULTS, segments[3:5], windows=context_windows(segments, 3))
        state = json.loads(request['state'])
        self.assertEqual(state['windows'], {'s3':['s2','s3','s4'], 's4':['s3','s4','s5']})
        self.assertEqual([s['id'] for s in state['segments']], ['s2','s3','s4','s5'])
        self.assertEqual(set(request['questions']), {'s3','s4'})
        self.assertNotIn('user_context', state)
        self.assertNotIn('vck_', request['state'])

    def test_custom_criteria_are_structured_parameters_not_parsed_prompt_headings(self):
        custom = {'keep': '仅保留待办事项', 'drop': '省略已完成事项', 'review': '日期无法确定'}
        settings = validate_settings({'prompt': '任意标题，不包含分类字段名', 'criteria': custom,
                                      'manual_review': True})
        batch = [{'id': 's1', 'text': 'fact', 'role': 'assistant'}]
        request = build_request(settings, batch, [])
        self.assertEqual(request['questions']['s1']['criteria'], custom)
        self.assertEqual(json.loads(request['state'])['instructions'], settings['prompt'])
        settings['manual_review'] = False
        for _ in range(2):
            criteria = build_request(settings, batch, [])['questions']['s1']['criteria']
            self.assertNotIn('review', criteria)
            self.assertEqual(criteria['drop'], custom['drop'])
            self.assertTrue(criteria['keep'].startswith(custom['keep']))
        self.assertEqual(settings['criteria'], custom)
        self.assertEqual(validate_settings({'prompt': '已有单一提示词'})['criteria'], DEFAULTS['criteria'])
        for bad in [None, {'keep': 'missing others'}, dict(custom, drop=''), dict(custom, keep=1)]:
            with self.assertRaises(ValueError):
                validate_settings({'criteria': bad})

    def test_legacy_prompt_migration_preserves_custom_rules(self):
        self.assertEqual(validate_settings(LEGACY_DEFAULTS)['prompt'], DEFAULTS['prompt'])
        self.assertEqual(validate_settings(LEGACY_DEFAULTS_EN)['prompt'], DEFAULTS_EN['prompt'])
        old = dict(LEGACY_DEFAULTS, goal='只整理开发事项', question='判断 {id}，优先保留接口约定',
                   criteria=dict(LEGACY_DEFAULTS['criteria'], keep='保留未解决的测试失败'))
        migrated = validate_settings(old)
        for text in ['只整理开发事项', '优先保留接口约定']:
            self.assertIn(text, migrated['prompt'])
        self.assertNotIn('保留未解决的测试失败', migrated['prompt'])
        self.assertEqual(migrated['criteria'], old['criteria'])
        self.assertNotIn('{id}', migrated['prompt'])
        self.assertEqual(validate_settings(migrated), migrated)
        self.assertEqual(validate_settings(dict(old, prompt='新的单一规则'))['prompt'], '新的单一规则')

    def test_existing_settings_default_to_classifying_users(self):
        self.assertTrue(validate_settings({})['classify_user_messages'])
        self.assertFalse(validate_settings({'classify_user_messages': False})['classify_user_messages'])

    def test_shared_history_excludes_parent_later_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); sessions = root / 'sessions'; sessions.mkdir()
            base_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
            base = sessions / ('rollout-' + base_id + '.jsonl')
            old = record({'id': base_id}, 'session_meta', 0) + record({'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'old retained fact'}]}, ordinal=1)
            base.write_bytes(old + message('must not leak from future parent'))
            current = sessions / 'child.jsonl'
            current.write_bytes(record({'history_base': {'thread_id': base_id, 'end_byte_offset': len(old), 'end_ordinal_exclusive': 2}}, 'session_meta', 2) + record({'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'explicit user goal'}]}, ordinal=3) + record({'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': 'not exported'}]}, ordinal=4))
            with sqlite3.connect(root / 'state_5.sqlite') as conn:
                conn.execute('CREATE TABLE threads (id TEXT,title TEXT,cwd TEXT,rollout_path TEXT)')
                conn.execute('INSERT INTO threads VALUES (?,?,?,?)', ('child', 'test', folder, str(current)))
            result = CodexStore(root).extract('child')
            texts = [s['text'] for s in result['segments']]
            self.assertEqual(texts, ['old retained fact', 'explicit user goal'])
            self.assertFalse(result['segments'][1]['protected'])
            self.assertEqual(len(result['source_files']), 2)
            current.write_bytes(current.read_bytes().replace(b'"end_ordinal_exclusive": 2', b'"end_ordinal_exclusive": 9'))
            with self.assertRaises(ValueError):
                CodexStore(root).extract('child')

    def test_malformed_and_partial_history_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'broken.jsonl'
            for content in [b'{"type":', b'invalid\n']:
                p.write_bytes(content)
                with self.assertRaises(ValueError):
                    list(CodexStore(folder).history(p))


if __name__ == '__main__':
    unittest.main()
