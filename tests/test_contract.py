import copy
import sys
import unittest
from pathlib import Path
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_contract import read_json, read_jsonl, validate_bundle

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.man = read_jsonl(ROOT/'examples/manifest.jsonl')
        self.feat = read_jsonl(ROOT/'examples/features.jsonl')
        self.pred = read_jsonl(ROOT/'examples/predictions.jsonl')
        self.model = read_json(ROOT/'examples/model_metadata.json')

    def test_valid_examples(self):
        self.assertEqual(validate_bundle(self.man, self.feat, self.pred, self.model)['manifest'], 4)

    def test_parent_split_leakage(self):
        self.man[-1]['split'] = 'test'
        with self.assertRaisesRegex(ValueError, 'leakage|mismatch'): validate_bundle(self.man)

    def test_sequence_leakage(self):
        self.man[1]['sequence_id'] = self.man[0]['sequence_id']
        with self.assertRaisesRegex(ValueError, 'leakage'): validate_bundle(self.man)

    def test_missing_parent(self):
        self.man[-1]['parent_image_id'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'parent'): validate_bundle(self.man)

    def test_feature_coverage(self):
        with self.assertRaisesRegex(ValueError, 'cover exactly'): validate_bundle(self.man, self.feat[:-1])

    def test_feature_order(self):
        self.model['feature_order'].reverse()
        with self.assertRaises((ValidationError, ValueError)): validate_bundle(self.man, model=self.model)

    def test_nan(self):
        self.feat[0]['features']['entropy'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Non-finite'): validate_bundle(self.man, self.feat)

    def test_invalid_parameter(self):
        self.man[-1]['parameters'] = {'sigma': -1}
        with self.assertRaisesRegex(ValueError, 'sigma'): validate_bundle(self.man)

    def test_probability_sum(self):
        self.pred[0]['probabilities']['good'] = .9
        with self.assertRaisesRegex(ValueError, 'sum'): validate_bundle(self.man, predictions=self.pred, model=self.model)

    def test_health_formula(self):
        self.pred[0]['health_score'] = 95
        with self.assertRaisesRegex(ValueError, 'Health'): validate_bundle(self.man, predictions=self.pred, model=self.model)

    def test_extra_feature_forbidden(self):
        self.feat[0]['features']['severity'] = 5
        with self.assertRaises(ValidationError): validate_bundle(self.man, self.feat)

    def test_invalid_unlabeled_record(self):
        self.man[0]['label_source'] = 'unlabeled'
        with self.assertRaises(ValidationError): validate_bundle(self.man)

if __name__ == '__main__': unittest.main()
