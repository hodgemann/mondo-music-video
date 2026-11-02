"""Golden parity and failure checks for the extracted music-video engine."""
from dataclasses import asdict
import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mmv.engine.analyze import ScoreMap
from mmv.engine.plan import plan
from mmv.engine.backends import get_backend
from mmv.engine.schema import WriterResponse, assemble_prompt, validate_prompt
from mmv.engine.validators.laya_semantic import LayaSemanticValidator

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path(__file__).parent/'fixtures'

class OriginalEngineTests(unittest.TestCase):
    def test_original_golden_plan(self):
        score=ScoreMap.from_json(FIXTURES/'score.json')
        actual=plan(score,width=1024,height=576,vocab=json.loads((FIXTURES/'vocab-legacy.json').read_text(encoding='utf-8')),
                    seed=17,cast_size=3,ref_policy='all',bars_per_phrase=2,backend=get_backend('local_h3'))
        self.assertEqual(asdict(actual),json.loads((FIXTURES/'plan.json').read_text()))

    def test_expanded_vocabulary_golden_plan(self):
        score = ScoreMap.from_json(FIXTURES / 'score.json')
        vocab = json.loads((ROOT / 'mmv/engine/config/vocab.json').read_text(encoding='utf-8'))
        actual = plan(score, width=1024, height=576, vocab=vocab, seed=17, cast_size=3,
                      ref_policy='all', bars_per_phrase=2, backend=get_backend('local_h3'))
        self.assertEqual(asdict(actual), json.loads((FIXTURES / 'plan-expanded.json').read_text(encoding='utf-8')))

    def test_expanded_vocabulary_preserves_timing_and_casting(self):
        from mmv.engine.casting import assign
        legacy = json.loads((FIXTURES / 'vocab-legacy.json').read_text(encoding='utf-8'))
        expanded = json.loads((ROOT / 'mmv/engine/config/vocab.json').read_text(encoding='utf-8'))
        roster = [{'actor_id': f'actor_{index}', 'display_name': f'Actor {index}',
                   'sheet': f'actor_{index}.png', 'sheet_path': f'/temporary/actor_{index}.png'} for index in range(3)]
        def structure(p):
            data = asdict(p)
            for segment in data['segments']:
                for key in ('thematic_anchor', 'footage_anchor', 'practical_effects'):
                    segment.pop(key)
                for shot in segment['shots']:
                    for key in ('camera', 'shot_scale', 'vocab'):
                        shot.pop(key)
            return data
        for backend in ('local_h3', 'wavespeed', 'seedance_2', 'seedance_2_5'):
            for seed in (0, 1, 17):
                with self.subTest(backend=backend, seed=seed):
                    plans = [plan(ScoreMap.from_json(FIXTURES / 'score.json'), width=1024, height=576,
                                  vocab=vocab, seed=seed, cast_size=3, ref_policy='all',
                                  bars_per_phrase=2, backend=get_backend(backend)) for vocab in (legacy, expanded)]
                    self.assertEqual(structure(plans[0]), structure(plans[1]))
                    for policy in ('random', 'rotate', 'section'):
                        casts = [assign(p, roster, policy=policy, seed=seed, ref_policy='all') for p in plans]
                        self.assertEqual(casts[0], casts[1])

    def test_expanded_rotation_pools_are_sfw_unique_and_traceable(self):
        from mmv.engine.plan import VocabSampler
        import re
        path = ROOT / 'mmv/engine/config/vocab.json'
        vocab = json.loads(path.read_text(encoding='utf-8'))
        legacy = json.loads((FIXTURES / 'vocab-legacy.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'docs/SOURCE_EXTRACTION.json').read_text(encoding='utf-8'))
        record = next(entry for entry in manifest if entry['public'] == 'mmv/engine/config/vocab.json')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['published_sha256'])
        self.assertEqual(vocab['camera_by_energy'], legacy['camera_by_energy'])
        self.assertEqual(vocab['shot_scales'], legacy['shot_scales'])
        self.assertEqual(vocab['rigging'], legacy['rigging'])
        sampler = VocabSampler(vocab, seed=17)
        for table, minimum in [('settings', 250), ('subject_types', 200), ('mechanisms', 250),
                               ('costume', 30), ('tonal_registers', 180), ('lighting', 220),
                               ('footage_anchors', 65), ('practical_effects', 100)]:
            with self.subTest(table=table):
                pool = vocab[table]
                self.assertGreaterEqual(len(pool), minimum)
                self.assertEqual(len(pool), len(set(pool)))
                self.assertEqual(len(pool), record['counts'][table]['published'])
                for _ in range(2):
                    draws = [sampler.pick(table) for _ in pool]
                    self.assertEqual(set(draws), set(pool))
                    self.assertEqual(len(draws), len(set(draws)))
                for value in pool:
                    self.assertIsNone(re.search(r'\b(nude|naked|erotic|pornographic|bawdy|translucent)\b', value, re.I), value)
        self.assertFalse({'gasping', 'panting', 'yawning', 'sighing'}.intersection(vocab['mechanisms']))

    def test_unchanged_original_source_hashes(self):
        manifest=json.loads((ROOT/'docs/SOURCE_EXTRACTION.json').read_text())
        unchanged=[entry for entry in manifest if entry['adaptation']=='none']
        self.assertGreaterEqual(len(unchanged),10)
        for entry in unchanged:
            self.assertEqual(hashlib.sha256((ROOT/entry['public']).read_bytes()).hexdigest(),entry['sha256'],
                             entry['public']+' is part of the protected prompting scheme and changed. Do NOT update the hash to make this pass: warn the person you work for that this can make videos worse and read docs/PROMPT_SCHEME_PROTECTION.md.')

    def test_hosted_phrase_shrinks_on_original_musical_edges(self):
        vocab=json.loads((ROOT/'mmv/engine/config/vocab.json').read_text(encoding='utf-8'))
        for name in ('local_h3','wavespeed','seedance_2','seedance_2_5'):
            score=ScoreMap.from_json(FIXTURES/'score.json');backend=get_backend(name)
            result=plan(score,width=1024,height=576,vocab=vocab,seed=17,cast_size=1,ref_policy='all',backend=backend)
            self.assertEqual(result.segments[0].song_start_frame,0)
            self.assertEqual(sum(s.trim_frames for s in result.segments),score.duration_frames)
            for seg in result.segments:
                self.assertLessEqual(seg.gen_frames,backend.max_gen_frames)
                self.assertGreaterEqual(seg.gen_frames,seg.trim_frames)
                if seg.song_start_frame:self.assertIn(seg.song_start_frame,score.downbeat_frames)

    def test_laya_rejects_and_formats_original_corrective_note(self):
        validator=LayaSemanticValidator()
        clip={'state':{'shot_count':4},'questions':[]}
        problems=validator.decide({'answers':{'visual_density':{'expected_level':1,'confidence':.9},
            'structural_completeness':{'selected':'missing_action'},'restriction_adherence':{'selected':'safe','confidence':.9}}},clip)
        self.assertTrue(problems)
        self.assertIn('Give every shot a concrete action',validator.format_retry_feedback(problems))
        self.assertEqual(validator.decide({'answers':{'visual_density':{'expected_level':1,'confidence':.01}}},clip),[])

    def test_no_nsfw_workflow_or_controls(self):
        workflows=list((ROOT/'mmv/engine/workflows').glob('*.json'))
        self.assertIn('h3_ref2video_audionodeadded.json',{w.name for w in workflows})
        for workflow in workflows:
            graph=json.loads(workflow.read_text())
            self.assertFalse(any('lora' in n.get('class_type','').lower() for n in graph.values()),workflow.name)
        for file in ('webapp/index.html','webapp/mondo_web.py'):
            self.assertNotIn('nsfw_local',(ROOT/file).read_text(encoding='utf-8'))

    def test_laya_device_fallback_when_device_unavailable(self):
        import sys
        from unittest.mock import MagicMock
        from mmv.storage import Storage
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / 'model.safetensors').touch()
            (p / 'rl_agent_config.json').touch()
            (p / 'tokenizer').mkdir()
            (p / 'encoder').mkdir()
            (p / 'encoder/config.json').touch()
            mock_mod = MagicMock()
            mock_agent_cls = MagicMock()
            mock_agent_cls.return_value.cfg = {}
            mock_mod.RLAgent = mock_agent_cls
            with patch.dict(sys.modules, {'rl_agent_api': mock_mod}):
                # Test cuda_or_cpu fallback when cuda unavailable
                with patch.object(Storage, 'settings', return_value={'laya_device': 'cuda_or_cpu', 'laya_model_dir': str(p)}), \
                     patch('torch.cuda.is_available', return_value=False):
                    v = LayaSemanticValidator()
                    v._load_agent()
                    mock_agent_cls.assert_called_with(str(p), device='cpu')
                # Test mps_or_cpu fallback when mps unavailable
                with patch.object(Storage, 'settings', return_value={'laya_device': 'mps_or_cpu', 'laya_model_dir': str(p)}):
                    v = LayaSemanticValidator()
                    v._load_agent()
                    mock_agent_cls.assert_called_with(str(p), device='cpu')

    def test_normalize_h3_prompt(self):
        from mmv.engine.backends.local_h3 import normalize_h3_prompt
        prompt = (
            "subject_definitions:\n"
            "<Subject 1> is Bob, an alien figure.\n"
            "<Audio 1> is the rhythm.\n\n"
            "detailed_description:\n"
            "[Shot 1] Bob walks forward as Bob's coat rustles.\n"
            "[Shot 2] The camera holds as Bob pauses.\n"
        )
        cast = [{"slot": 0, "picture_tag": "<Picture 1>", "actor_id": "bob", "display_name": "Bob"}]
        normalized = normalize_h3_prompt(prompt, cast)
        self.assertIn("<Subject 1> is <Picture 1>, Bob", normalized)
        self.assertIn("[Shot 1] <Subject 1> walks forward as <Subject 1>'s coat rustles.", normalized)
        self.assertIn("[Shot 2] The camera holds as <Subject 1> pauses.", normalized)
        self.assertEqual(normalize_h3_prompt(normalized, cast), normalized)
        self.assertEqual(normalize_h3_prompt(prompt, []), prompt)

    def test_normalize_h3_prompt_keeps_scene_colours_and_longest_names(self):
        from mmv.engine.backends.local_h3 import h3_cast_kwargs, normalize_h3_prompt
        prompt = ("subject_definitions:\n<Subject 1> is Red.\n<Subject 2> is <Picture 1>, wrong.\n\n"
                  "detailed_description:\n[Shot 1] Red lighting hits Ann Marie beside Ann.\n")
        cast = [{"actor_id": "ann", "display_name": "Ann"}, {"actor_id": "ann_marie", "display_name": "Ann Marie"},
                {"actor_id": "red", "display_name": "Red"}]
        out = normalize_h3_prompt(prompt, cast)
        self.assertIn("Red lighting hits", out)
        self.assertIn("hits <Subject 2> beside <Subject 1>.", out)
        self.assertIn("<Subject 1> is <Picture 1>, Red.", out)
        self.assertIn("<Subject 2> is <Picture 1>, wrong.", out)
        self.assertEqual(h3_cast_kwargs({}, "local_h3", cast), {})
        self.assertEqual(h3_cast_kwargs({"h3_tag_normalizer": True}, "wavespeed", cast), {})
        self.assertEqual(h3_cast_kwargs({"h3_tag_normalizer": True}, "local_h3", cast), {"cast": cast})

    def test_python_311_syntax(self):
        for directory in ('mmv','webapp'):
            for path in (ROOT/directory).rglob('*.py'):
                ast.parse(path.read_text(),filename=str(path),feature_version=(3,11))

if __name__=='__main__':unittest.main()
