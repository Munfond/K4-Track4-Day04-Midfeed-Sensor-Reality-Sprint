"""Person 5: validate heuristic records separately from the frozen ML contract."""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jsonschema import Draft202012Validator
from src import baseline
from scripts.validate_contract import read_json, read_jsonl, validate_bundle, finite, require

SCHEMA = read_json(ROOT / 'schemas/heuristic_health.schema.json')
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)


def validate_health(manifest, features, scores, references, split=None):
    validate_bundle(manifest, features)
    config = references['config']
    metadata = {r['sample_id']: r for r in manifest}
    for row in references['reference_rows']:
        image = metadata.get(row['sample_id'])
        require(image is not None and image['split'] == 'train' and image['corruption'] == 'original',
                f'Reference missing from train originals: {row["sample_id"]}')
    expected = baseline.score_bundle(features, manifest, references, config, split=split)
    expected = {row['sample_id']: row for row in expected}
    actual = {}
    for row in scores:
        finite(row)
        VALIDATOR.validate(row)
        sid = row['sample_id']
        require(sid not in actual, f'Duplicate health ID: {sid}')
        actual[sid] = row
    require(set(actual) == set(expected), 'Health coverage must exactly match selected manifest IDs')
    for sid, row in actual.items():
        for key, value in expected[sid].items():
            valid = (math.isclose(row[key], value, rel_tol=1e-9, abs_tol=1e-7)
                     if type(value) in (int, float) else row.get(key) == value)
            require(valid, f'Health {key} mismatch: {sid}')
    # Recheck freeze evidence against actual validation input, not only hash shape.
    if config['frozen']:
        evidence = config['validation']
        val_images = sorted((r for r in manifest if r['split'] == 'val'), key=lambda r: r['sample_id'])
        val_ids = {r['sample_id'] for r in val_images}
        require(val_ids == set(evidence['sample_ids']), 'Frozen validation coverage mismatch')
        val_features = sorted((r for r in features if r['sample_id'] in val_ids), key=lambda r: r['sample_id'])
        require(baseline._hash(val_features) == evidence['features_sha256'], 'Frozen validation features changed')
        metadata = [{key: r[key] for key in ('sample_id', 'split', 'timeofday', 'sequence_id')} for r in val_images]
        require(baseline._hash(metadata) == evidence['metadata_sha256'], 'Frozen validation metadata changed')
        val_scores = baseline.score_bundle(features, manifest, references, config, split='val')
        require(baseline._hash(val_scores) == evidence['health_sha256'], 'Frozen validation health changed')
    return {'health': len(actual), 'test': sum(r['split'] == 'test' and r['sample_id'] in actual for r in manifest),
            'frozen': config['frozen'], 'policy_id': config['policy_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'features', 'health', 'references'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_health(read_jsonl(args.manifest), read_jsonl(args.features),
                                   read_jsonl(args.health), read_json(args.references))))


if __name__ == '__main__':
    main()
