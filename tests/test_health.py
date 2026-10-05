"""Verify health handoff compatibility, input integrity and validation freeze."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src import baseline

ROOT = Path(__file__).resolve().parents[1]


def feature(sid, luminance=100):
    return {'schema_version': '1.0.0', 'record_type': 'features', 'sample_id': sid,
            'feature_version': '1.0.0', 'width': 640, 'height': 360,
            'features': {'log_laplacian_variance': 5.0, 'saturation_ratio': 0.01,
                         'dark_ratio': 0.05, 'entropy': 6.0, 'noise_residual': 4.0,
                         'median_luminance': luminance, 'contrast': 30.0}}


def metadata(sid, split, timeofday='daytime'):
    return {'schema_version': '1.0.0', 'record_type': 'manifest', 'sample_id': sid,
            'parent_image_id': sid, 'sequence_id': 'seq_' + sid, 'split': split,
            'timeofday': timeofday, 'corruption': 'original', 'severity': 0}


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.config = baseline.prepare_config(json.loads((ROOT / 'configs/health.json').read_text()))
        self.images = [metadata('day', 'train'), metadata('night', 'train', 'night'),
                       metadata('val', 'val'), metadata('test', 'test')]
        self.features = [feature('day'), feature('night', 30), feature('val'), feature('test')]
        self.refs = baseline.calibrate(self.features[:2], self.images, self.config)

    def test_enriched_reference_delivery_and_legacy_forms(self):
        value = {'day': ['day'], 'night': ['night'], 'fixed': ['night', 'day'],
                 'visual_review': 'pending', 'manifest_path': 'data/manifests/originals.jsonl'}
        self.assertEqual(baseline._select_reference_ids(value), ['day', 'night'])
        self.assertEqual(baseline._select_reference_ids(['day', 'night']), ['day', 'night'])
        self.assertEqual(baseline._select_reference_ids({'day': ['day'], 'night': ['night']}),
                         ['day', 'night'])

    def test_duplicate_and_inconsistent_fixed_ids_fail(self):
        for value in ({'day': ['day'], 'night': ['day']},
                      {'day': ['day'], 'night': ['night'], 'fixed': ['day']},
                      {'day': [], 'night': ['night']}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                baseline._select_reference_ids(value)

    def test_source_hash_and_original_snapshot_are_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'originals.jsonl'
            source.write_text('\n'.join(json.dumps(row) for row in self.images), encoding='utf-8')
            handoff = {'manifest_path': 'originals.jsonl',
                       'manifest_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
            images = baseline._metadata_index(self.images)
            self.assertIn('source_manifest_sha256', baseline._validate_reference_source(handoff, images, root))
            changed = copy.deepcopy(images)
            changed['day']['timeofday'] = 'night'
            with self.assertRaisesRegex(ValueError, 'differ'):
                baseline._validate_reference_source(handoff, changed, root)
            source.write_text(source.read_text() + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                baseline._validate_reference_source(handoff, images, root)

    def test_val_allowed_but_test_and_all_blocked_before_freeze(self):
        self.assertEqual(len(baseline.score_bundle(self.features, self.images, self.refs,
                                                 self.refs['config'], 'val')), 1)
        for split in ('test', None):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, 'frozen'):
                baseline.score_bundle(self.features, self.images, self.refs, self.refs['config'], split)

    def test_freeze_then_score_test_and_weight(self):
        frozen = baseline.freeze_references(self.refs, [self.features[2]], [self.images[2]],
                                            self.refs['config'], 'Reviewed val fixtures')
        rows = baseline.score_bundle(self.features, self.images, frozen, frozen['config'], 'test')
        self.assertEqual(len(rows), 1)
        self.assertEqual(frozen['config']['validation']['sample_ids'], ['val'])
        self.assertAlmostEqual(rows[0]['camera_weight'], (rows[0]['health_score'] / 100) ** 2)
        self.assertFalse(self.refs['config']['frozen'])

    def test_reference_sequence_change_is_rejected(self):
        changed = copy.deepcopy(self.images)
        changed[0]['sequence_id'] = 'replacement'
        with self.assertRaisesRegex(ValueError, 'Reference.*changed'):
            baseline.score_bundle(self.features, changed, self.refs, self.refs['config'], 'val')

    def test_train_only_and_validation_sequence_leakage(self):
        changed = copy.deepcopy(self.images)
        changed[0]['split'] = 'val'
        with self.assertRaisesRegex(ValueError, 'original.*train'):
            baseline.calibrate(self.features[:2], changed, self.config)
        changed = copy.deepcopy(self.images)
        changed[3]['sequence_id'] = changed[2]['sequence_id']
        with self.assertRaisesRegex(ValueError, 'sequence split leakage'):
            baseline.score_bundle(self.features, changed, self.refs, self.refs['config'], 'val')

    def test_feature_coverage_and_tampered_reference_fail(self):
        with self.assertRaisesRegex(ValueError, 'cover exactly'):
            baseline.score_bundle(self.features[:-1], self.images, self.refs, self.refs['config'], 'val')
        changed = copy.deepcopy(self.refs)
        changed['groups']['day']['median']['noise_residual'] += 1
        with self.assertRaisesRegex(ValueError, 'summary'):
            baseline.score_health(self.features[2], 'daytime', changed, self.refs['config'])

    def test_fallback_and_explanation_preserve_score(self):
        explanation = baseline.explain_health(self.features[2], 'dawn/dusk', self.refs, self.refs['config'])
        row = explanation['health_record']
        self.assertEqual(row['mode'], 'fixed_fallback')
        self.assertEqual(row['health_fixed'], row['health_adaptive'])
        self.assertEqual(row['fallback_reason'], 'timeofday=dawn/dusk')
        self.assertAlmostEqual(row['health_score'], 100 - sum(explanation['adaptive']['penalty_points'].values()))


if __name__ == '__main__':
    unittest.main()
