"""Integration acceptance on generated software fixtures, never BDD benchmark."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image
from jsonschema import ValidationError
from src import baseline, corruptions, evaluate, run_pipeline
from scripts import run_health
from scripts.validate_contract import read_json, read_jsonl
from scripts.validate_health import validate_health

REPO = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        for folder in ('src', 'scripts', 'schemas', 'configs'):
            shutil.copytree(REPO / folder, cls.root / folder, ignore=shutil.ignore_patterns('__pycache__'))
        rows = []
        rng = np.random.default_rng(41)
        for sid, split, time, brightness in (('day', 'train', 'daytime', 120), ('night', 'train', 'night', 30),
                                           ('val', 'val', 'daytime', 100), ('test', 'test', 'undefined', 40)):
            pixels = np.clip(rng.normal(brightness, 10, (360, 640, 3)), 0, 255).astype(np.uint8)
            Image.fromarray(pixels).save(cls.root / f'{sid}.png')
            rows.append({'schema_version': '1.0.0', 'record_type': 'manifest', 'sample_id': sid,
                         'parent_image_id': sid, 'sequence_id': sid, 'dataset': 'bdd100k', 'source_split': 'train',
                         'image_path': f'{sid}.png', 'split': split, 'timeofday': time, 'weather': 'clear',
                         'corruption': 'original', 'severity': 0, 'seed': None, 'parameters': {},
                         'label': None, 'label_source': 'unlabeled', 'label_rule_version': None})
        cls.manifest = cls.root / 'originals.jsonl'
        cls.manifest.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        cls.ids = cls.root / 'ids.json'
        cls.ids.write_text(json.dumps(['day', 'night']), encoding='utf-8')
        cls.patches = [patch.object(module, 'ROOT', cls.root) for module in (corruptions, run_health, evaluate, run_pipeline)]
        cls.patches.append(patch.object(run_health.subprocess, 'check_output', return_value='fixture_git'))
        for p in cls.patches:
            p.start()
        try:
            args = SimpleNamespace(run_id='fixture_integration', manifest=str(cls.manifest), reference_ids=str(cls.ids),
                                   corruption_config=str(cls.root / 'configs/corruptions.json'),
                                   health_config=str(cls.root / 'configs/health.json'), data_kind='fixture')
            run_pipeline.prepare(args)
            cls.folder = cls.root / 'data/features/fixture_integration'
            cls.val = read_jsonl(cls.folder / 'health_val.jsonl')
            cls.draft = read_json(cls.folder / 'references_draft.json')
            run_pipeline.finalize(SimpleNamespace(run_id=args.run_id, validation_note='Fixture val software review',
                                                 reference_review_note='Synthetic fixture references', data_kind='fixture'))
            cls.images = read_jsonl(cls.root / 'data/manifests/augmented_fixture_integration.jsonl')
            cls.features = read_jsonl(cls.folder / 'features.jsonl')
            cls.scores = read_jsonl(cls.folder / 'health_scores.jsonl')
            cls.refs = read_json(cls.folder / 'references.json')
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):
            p.stop()
        cls.temp.cleanup()

    def validate(self, scores=None, refs=None, features=None):
        return validate_health(self.images, features or self.features, scores or self.scores, refs or self.refs)

    def test_end_to_end_and_artifacts(self):
        self.assertEqual(len(self.images), 84)
        self.assertEqual(self.validate()['test'], 21)
        self.assertEqual(len(self.val), 21)
        report = self.root / 'reports/runs/fixture_integration'
        for name in ('report.md', 'evaluation/groups.csv', 'evaluation/curves.csv',
                     'evaluation/severity_curves.png', 'evaluation/original_degraded.png', 'evaluation/provenance.json'):
            self.assertTrue((report / name).is_file(), name)
        self.assertIn('fixture', (report / 'report.md').read_text(encoding='utf-8'))
        with self.assertRaises(FileExistsError):
            evaluate.evaluate(self.root / 'data/manifests/augmented_fixture_integration.jsonl', self.folder / 'features.jsonl', self.folder / 'health_scores.jsonl',
                              self.folder / 'references.json', report)

    def test_missing_duplicate_and_wrong_score_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(scores=self.scores[:-1])
        with self.assertRaises(ValueError):
            self.validate(scores=self.scores + [self.scores[0]])
        wrong = copy.deepcopy(self.scores)
        wrong[0]['camera_weight'] = .123456
        with self.assertRaises(ValueError):
            self.validate(scores=wrong)

    def test_wrong_mode_policy_action_rejected(self):
        for key, value in (('mode', 'night'), ('policy_id', 'wrong'), ('action', 'wrong')):
            wrong = copy.deepcopy(self.scores)
            wrong[0][key] = value
            with self.assertRaises((ValueError, ValidationError)):
                self.validate(scores=wrong)

    def test_fallback_reason_required(self):
        wrong = copy.deepcopy(self.scores)
        row = next(r for r in wrong if r['mode'] == 'fixed_fallback')
        del row['fallback_reason']
        with self.assertRaises(ValidationError):
            self.validate(scores=wrong)

    def test_draft_cannot_evaluate_test(self):
        with self.assertRaisesRegex(ValueError, 'frozen'):
            self.validate(refs=self.draft)

    def test_frozen_val_feature_tampering_rejected(self):
        wrong = copy.deepcopy(self.features)
        row = next(r for r in wrong if r['sample_id'] == 'val')
        row['features']['contrast'] += .01
        with self.assertRaisesRegex(ValueError, 'validation features'):
            self.validate(features=wrong)


class EvaluationStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.images = [dict(sample_id=sid, parent_image_id='parent', split='test', timeofday='night',
                            weather='rainy', corruption=kind, severity=severity)
                       for sid, kind, severity in (('parent', 'original', 0), ('s1', 'gaussian_noise', 1),
                                                  ('s2', 'gaussian_noise', 2))]
        self.scores = [dict(sample_id=sid, health_fixed=fixed, health_adaptive=adaptive, action='normal')
                       for sid, fixed, adaptive in (('s2', 50, 60), ('parent', 80, 90), ('s1', 40, 50))]

    def test_paired_join_uses_ids_with_shuffled_records(self):
        rows = evaluate.summarize(self.images, self.scores)
        severity_two = next(r for r in rows if r['severity'] == 2)
        self.assertEqual(severity_two['fixed_paired_delta_mean'], -30)
        self.assertEqual(severity_two['adaptive_paired_delta_mean'], -30)
        self.assertEqual(severity_two['adaptive_minus_fixed_mean'], 10)

    def test_nonmonotonic_curve_detected_even_below_parent(self):
        findings = evaluate.score_increases(self.images, self.scores)
        self.assertEqual(len(findings), 2)
        self.assertEqual({r['comparison'] for r in findings}, {'previous_severity'})
        self.assertEqual({r['delta'] for r in findings}, {10})


if __name__ == '__main__':
    unittest.main()
