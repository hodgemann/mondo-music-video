"""Storyboard review, timing, consent and renderer binding using temporary data and mock services."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from mmv import storyboard, passage_plans
from mmv.storage import Storage, read_json, write_json
from webapp.mondo_web import ProductionRequest, request_dict, create_app
import test_public_app as fixtures


class StoryboardTests(unittest.TestCase):
    def test_disabled_requests_and_prompt_context_are_unchanged(self):
        request = request_dict(ProductionRequest())
        self.assertNotIn('storyboard', request)
        self.assertNotIn('ident_all_references', request)
        self.assertEqual(storyboard.ident_notes('Original', None, 'a'), 'Original')
        self.assertIsNone(storyboard.writer_context(None, 'a'))
        self.assertIsNone(storyboard.align({}, []))

    def test_ordered_alignment_and_ident_multiple_beats_preserve_plan(self):
        segments = [SimpleNamespace(segment_id='a', song_start_frame=0, trim_frames=120,
                    shots=[SimpleNamespace(n=n, start_frame=(n-1)*30) for n in range(1, 5)])]
        board = {'enabled': True, 'mode': 'visual', 'panels': [{'direction': 'Walk'}, {'direction': 'Turn'}]}
        aligned = storyboard.align(board, segments)
        self.assertEqual([s['panel'] for s in aligned['passages']['a']], [1, 1, 2, 2])
        self.assertEqual([s['start_seconds'] for s in aligned['passages']['a']], [0, 1.25, 2.5, 3.75])
        self.assertIn('framing', storyboard.writer_context(aligned, 'a')['guidance'])
        ident = storyboard.align(board, segments, kind='ident')
        self.assertEqual([s['end_seconds'] for s in ident['passages']['a']], [2.5, 5])
        with self.assertRaises(ValueError):
            storyboard.align({**board, 'panels': board['panels'] * 3}, segments)
        self.assertEqual(len(segments[0].shots), 4)

    def test_blank_panel_direction_gets_the_friendly_message(self):
        with self.assertRaisesRegex(ValueError, 'Write a direction for each storyboard panel'):
            storyboard.Storyboard(enabled=True, panels=[{'direction': ''}])

    def test_untrusted_interpretation_is_bounded(self):
        good = {'panels': [{'image': 'a.png', 'direction': 'Walk forward'}]}
        self.assertEqual(storyboard.parse_response(json.dumps(good), ['a.png']), good['panels'])
        for bad in [[], {'panels': []}, {'panels': [None]}, {'panels': [{'image': 'x.png', 'direction': 'Walk'}]},
                    {'panels': [{'image': 'a.png', 'direction': 'x'*1201}]},
                    {'panels': [{'image': 'a.png', 'direction': ' '}]}, {'panels': good['panels'] * 25}]:
            with self.assertRaises(ValueError):
                storyboard.parse_response(json.dumps(bad), ['a.png'])
        with self.assertRaises(ValueError):
            ProductionRequest(storyboard={'mode': 'invented'})

    def test_humanize_storyboard_directions(self):
        sloppy = {'panels': [{'image': 'a.png', 'direction': 'In this shot, we see a delicate dance of shadow and light on the pavement, creating a sense of dread.'}]}
        # Default (humanize=False): unchanged
        self.assertEqual(storyboard.parse_response(json.dumps(sloppy), ['a.png'])[0]['direction'], sloppy['panels'][0]['direction'])
        # Opt-in (humanize=True): cleaned
        cleaned = storyboard.parse_response(json.dumps(sloppy), ['a.png'], humanize=True)
        self.assertEqual(cleaned[0]['direction'], 'Stark light and deep shadows on the pavement.')
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp), test_hosts=True)) as client:
            result = client.post('/api/storyboards/humanize', json=sloppy['panels'])
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), cleaned)
            self.assertEqual(client.post('/api/storyboards/humanize', json=[{'direction': 'x'}] * 25).status_code, 422)
            self.assertTrue(client.get('/api/thematic-worlds').json())

    def test_interpretation_and_result_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp)); (store.home / 'uploads' / 'a.png').write_bytes(fixtures.picture())
            directory = store.home / 'runs' / 'board'; directory.mkdir()
            request = request_dict(ProductionRequest(kind='storyboard', storyboard={'images': ['a.png']}))
            settings = {**store.settings(), 'vision_model': 'mock'}
            prepared = storyboard.prepare(store, request, settings)
            write_json(directory / 'request.json', request)
            write_json(directory / 'prepared.json', {**prepared, 'references': [str(p) for p in prepared['references']]})
            response = {'choices': [{'message': {'content': json.dumps({'panels': [{'image': 'a.png', 'direction': 'Walk'}]})}}]}
            with patch('mmv.render.request_json', return_value=response) as call:
                storyboard.interpret(store.home, directory)
            self.assertEqual(call.call_count, 1)
            with TestClient(create_app(store.home, test_hosts=True)) as client:
                self.assertEqual(client.get('/api/storyboards').json(), [{'run_id': 'board'}])
                self.assertEqual(client.get('/api/storyboards/board').json()['panels'][0]['direction'], 'Walk')
                self.assertEqual(client.get('/api/uploads/reference/a.png').status_code, 200)
                self.assertEqual(client.get('/api/storyboards/missing').status_code, 404)
                self.assertIn('Walk', client.get('/api/storyboards/board/response').json()['response'])
            with self.assertRaises(ValueError):
                storyboard.image_paths(store, ['../a.png'])

    def test_saved_alignment_binding_detects_tampering(self):
        prepared = {'storyboard': {'mode': 'narrative', 'passages': {'a': []}}}
        with self.assertRaises(ValueError):
            passage_plans.verify(prepared)
        prepared[passage_plans.KEY] = passage_plans.binding(prepared)
        self.assertTrue(passage_plans.verify(prepared))
        prepared['storyboard']['mode'] = 'visual'
        with self.assertRaises(ValueError):
            passage_plans.verify(prepared)


class StoryboardProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PublicAppTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.PublicAppTests.tearDownClass()

    def setUp(self):
        self.f = fixtures.PublicAppTests('test_version_matches_package_and_readme'); self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_ident_all_refs_and_storyboard_reach_writer_and_renderer(self):
        f = self.f
        refs = [f.client.post('/api/upload/reference', files={'file': (f'r{i}.png', fixtures.picture(), 'image/png')}).json()['file'] for i in range(2)]
        request = {'kind': 'ident', 'title': 'TITLE', 'direction': 'Letters move', 'references': refs,
                   'ident_all_references': True, 'ident_seconds': 4,
                   'storyboard': {'enabled': True, 'panels': [{'direction': 'Letters rise'}, {'direction': 'Letters turn'}]}}
        quote = f.client.post('/api/quote', json=request); quote.raise_for_status()
        self.assertEqual(quote.json()['segments'][0]['ref_image_slots'], 2)
        self.assertEqual(len(next(iter(quote.json()['storyboard']['passages'].values()))), 2)
        self.assertEqual(f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': False}).status_code, 400)
        started = f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True}); started.raise_for_status()
        status = f.wait(); self.assertEqual(status['state'], 'complete', status)
        run = f.home / 'runs' / status['id']
        self.assertTrue(passage_plans.verify(read_json(run / 'prepared.json')))
        passage_plans.verify_prompts(run, read_json(run / 'prepared.json'))
        calls = [b for p, b in fixtures.MockService.requests if p == '/chat/completions']
        self.assertIn('Letters turn', calls[0]['messages'][-1]['content'])
        graph = next(b['prompt'] for p, b in fixtures.MockService.requests if p == '/prompt')
        self.assertEqual(sum(n.get('class_type') == 'LoadImage' for n in graph.values()), 2)
        legacy = f.client.post('/api/quote', json={**request, 'ident_all_references': False, 'storyboard': {}})
        legacy.raise_for_status(); self.assertEqual(legacy.json()['segments'][0]['ref_image_slots'], 1)

    def test_video_board_job_and_prompt_binding(self):
        f = self.f
        request = {'song': f.song_upload(), 'storyboard': {'enabled': True, 'panels': [{'direction': 'Walk through mist'}]}}
        quote = f.client.post('/api/quote', json=request); quote.raise_for_status()
        f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True}).raise_for_status()
        status = f.wait(); self.assertEqual(status['state'], 'complete', status)
        run = f.home / 'runs' / status['id']
        jobs = list((run / 'writer_jobs').glob('*.json'))
        self.assertIn('Walk through mist', json.dumps(read_json(jobs[0])['storyboard']))
        passage_plans.verify_prompts(run, read_json(run / 'prepared.json'))

        from mmv.pipeline import prepare_resume
        saved_request = read_json(run / 'request.json')
        saved_request['storyboard']['panels'][0]['direction'] = 'Changed scene'
        with self.assertRaisesRegex(ValueError, 'Storyboard differs'):
            prepare_resume(f.store, saved_request, run)

    def test_interpretation_quote_start_and_fingerprint_use_normal_consent(self):
        f = self.f
        image = f.client.post('/api/upload/reference', files={'file': ('board.png', fixtures.picture(), 'image/png')}).json()['file']
        request = {'kind': 'storyboard', 'storyboard': {'images': [image]}}
        response = {'choices': [{'message': {'content': json.dumps({'panels': [{'image': image, 'direction': 'Walk'}]})}}]}
        def interpret_command(context, argv, **kwargs):
            self.assertIn('mmv.storyboard', argv)
            storyboard.interpret(f.home, context.log_path.parent)
        with patch('mmv.render.request_json', return_value=response) as call, patch('mmv.jobs.JobContext.command', interpret_command):
            quote = f.client.post('/api/quote', json=request); quote.raise_for_status()
            call.assert_not_called()
            self.assertEqual(f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': False}).status_code, 400)
            f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True}).raise_for_status()
            status = f.wait(); self.assertEqual(status['state'], 'complete', status)
            self.assertEqual(call.call_count, 1)
            result = f.client.get('/api/storyboards/' + status['id']); result.raise_for_status()
            self.assertEqual(result.json()['panels'][0]['direction'], 'Walk')
            quote = f.client.post('/api/quote', json=request); quote.raise_for_status()
            (f.home / 'uploads' / image).write_bytes(fixtures.picture() + b'changed')
            rejected = f.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True})
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(call.call_count, 1)
