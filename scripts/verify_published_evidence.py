"""Check published artifact hashes, health recomputation and benchmark curves without images."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_contract import read_json, read_jsonl
from scripts.validate_health import validate_health


def verify():
    evidence = ROOT / 'docs/evidence/integration_20261006_01'
    index = read_json(evidence / 'export_index.json')
    for artifact in index['artifacts']:
        path = (evidence / artifact['published']).resolve()
        if not path.is_relative_to(evidence.resolve()):
            raise ValueError('Artifact path escapes evidence directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact['published_sha256']:
            raise ValueError('Published hash mismatch: ' + artifact['published'])
    snap = evidence / 'snapshots'
    manifest = read_jsonl(snap / 'augmented_integration_20261006_01.jsonl')
    features = read_jsonl(snap / 'features.jsonl')
    health = read_jsonl(snap / 'health_scores.jsonl')
    result = validate_health(manifest, features, health, read_json(snap / 'references.json'))
    health_index = {r['sample_id']: r for r in health}
    samples = list(csv.DictReader((evidence / 'evaluation/samples.csv').open(encoding='utf-8')))
    if len(samples) != len(health) or {r['sample_id'] for r in samples} != set(health_index):
        raise ValueError('Samples CSV coverage mismatch')
    for row in samples:
        for metric in ('health_fixed', 'health_adaptive', 'camera_weight'):
            if not math.isclose(float(row[metric]), health_index[row['sample_id']][metric], abs_tol=1e-9):
                raise ValueError('Samples CSV health mismatch')
    curves = list(csv.DictReader((evidence / 'evaluation/curves.csv').open(encoding='utf-8')))
    checked = 0
    for row in curves:
        if row['split'] != 'test' or row['corruption'] != 'brightness_down':
            continue
        severity = int(row['severity'])
        selected = [s for s in samples if s['split'] == 'test' and s['timeofday'] == row['timeofday']
                    and int(s['severity']) == severity
                    and s['corruption'] == ('original' if severity == 0 else 'brightness_down')]
        if len(selected) != int(row['count']):
            raise ValueError('Curve count mismatch')
        for mode in ('fixed', 'adaptive'):
            if not math.isclose(mean(float(s['health_' + mode]) for s in selected),
                                float(row[mode + '_mean']), abs_tol=1e-9):
                raise ValueError('Curve mean mismatch')
        checked += 1
    if checked != 12:
        raise ValueError('Expected 12 day/night brightness-down groups')
    return {'status': 'passed', 'artifact_hashes': len(index['artifacts']), **result,
            'main_curve_groups_recomputed': checked,
            'scope': 'Published snapshots only; no image reextraction or pixel replay in this command. Historical image replay is recorded in audit/.'}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
