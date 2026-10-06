"""Exercise the complete health runner and reject changes after validation."""
import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from scripts import run_health

REPO = Path(__file__).resolve().parents[1]


class HealthRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ('src/baseline.py', 'src/features.py', 'scripts/run_health.py'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, path)
        rows = []
        for sid, split, timeofday, color in (('day', 'train', 'daytime', 120),
                                           ('night', 'train', 'night', 30),
                                           ('val', 'val', 'daytime', 100),
                                           ('test', 'test', 'night', 40)):
            path = self.root / f'{sid}.png'
            Image.new('RGB', (640, 360), (color, color, color)).save(path)
            rows.append({'schema_version': '1.0.0', 'record_type': 'manifest', 'sample_id': sid,
                         'parent_image_id': sid, 'sequence_id': sid, 'dataset': 'bdd100k',
                         'source_split': 'train', 'image_path': f'{sid}.png', 'split': split,
                         'timeofday': timeofday, 'weather': 'clear', 'corruption': 'original',
                         'severity': 0, 'seed': None, 'parameters': {}, 'label': None,
                         'label_source': 'unlabeled', 'label_rule_version': None})
        self.manifest = self.root / 'originals.jsonl'
        self.manifest.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
        self.ids = self.root / 'ids.json'
        self.ids.write_text(json.dumps(['day', 'night']), encoding='utf-8')
        self.output = self.root / 'data/features/fixture_health'
        self.root_patch = patch.object(run_health, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        args = argparse.Namespace(manifest=str(self.manifest), reference_ids=str(self.ids),
                                  config=str(REPO / 'configs/health.json'), features=None,
                                  run_id='fixture_health')
        with patch.object(run_health, 'subprocess', SimpleNamespace(check_output=Mock(return_value='fixture_commit'))), contextlib.redirect_stdout(io.StringIO()):
            run_health.prepare(args)

    def finalize(self):
        args = argparse.Namespace(run_dir=str(self.output), validation_note='Reviewed fixture val',
                                  reference_review_note='Reviewed synthetic software-test references')
        with contextlib.redirect_stdout(io.StringIO()):
            run_health.finalize(args)

    def test_complete_flow_and_no_overwrite(self):
        val = run_health.read_jsonl(self.output / 'health_val.jsonl')
        self.assertEqual([row['sample_id'] for row in val], ['val'])
        self.assertFalse((self.output / 'health_scores.jsonl').exists())
        self.finalize()
        final = run_health.read_jsonl(self.output / 'health_scores.jsonl')
        self.assertEqual(len(final), 4)
        frozen = json.loads((self.output / 'references.json').read_text())
        self.assertTrue(frozen['config']['frozen'])
        with self.assertRaises(FileExistsError):
            self.finalize()

    def test_feature_change_after_review_is_rejected(self):
        path = self.output / 'features.jsonl'
        path.write_text(path.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'features changed'):
            self.finalize()
        self.assertFalse((self.output / 'references.json').exists())

    def test_code_change_after_review_is_rejected(self):
        path = self.root / 'src/baseline.py'
        path.write_text(path.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'baseline.py changed'):
            self.finalize()


if __name__ == '__main__':
    unittest.main()
