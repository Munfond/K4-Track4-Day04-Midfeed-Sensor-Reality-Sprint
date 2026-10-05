"""Validate JSONL contracts and cross-record invariants, without ML dependencies."""
import argparse
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/camera_health.schema.json').read_text(encoding='utf-8'))
CONTRACT = json.loads((ROOT / 'configs/contract.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'Non-finite number is forbidden')
    elif isinstance(value, dict):
        for v in value.values(): finite(v)
    elif isinstance(value, list):
        for v in value: finite(v)

def validate_record(row, kind):
    finite(row)
    VALIDATOR.validate(row)
    require(row['record_type'] == kind, f'Expected {kind} record')

def index(rows, kind):
    result = {}
    for row in rows:
        validate_record(row, kind)
        sid = row['sample_id']
        require(sid not in result, f'Duplicate sample_id: {sid}')
        result[sid] = row
    return result

def validate_bundle(manifest, features=None, predictions=None, model=None):
    images = index(manifest, 'manifest')
    require(bool(images), 'Manifest cannot be empty')
    sequences = {}
    for sid, row in images.items():
        seq = row['sequence_id']
        require(seq not in sequences or sequences[seq] == row['split'], f'Sequence leakage: {seq}')
        sequences[seq] = row['split']
        parent = images.get(row['parent_image_id'])
        require(parent is not None, f'Missing original parent: {sid}')
        require(parent['corruption'] == 'original', f'Parent is not original: {sid}')
        if row['corruption'] == 'original':
            require(row['sample_id'] == row['parent_image_id'], f'Original must reference itself: {sid}')
        else:
            require(row['sample_id'] != row['parent_image_id'], f'Corrupted record must have a new ID: {sid}')
        for field in ('sequence_id', 'split', 'dataset', 'source_split', 'timeofday', 'weather'):
            require(row[field] == parent[field], f'Parent {field} mismatch: {sid}')
        params = row['parameters']; kind = row['corruption']
        if kind in ('gaussian_blur', 'gaussian_noise'):
            require(set(params) == {'sigma'} and params['sigma'] > 0, f'{kind} requires positive sigma: {sid}')
        elif kind in ('brightness_up', 'brightness_down'):
            require(set(params) == {'gain'}, f'{kind} requires gain: {sid}')
            require(params['gain'] > 1 if kind == 'brightness_up' else 0 < params['gain'] < 1, f'Invalid gain: {sid}')
        elif kind == 'rain_overlay':
            require(set(params) == {'streak_count', 'veil_alpha'}, f'Invalid rain parameters: {sid}')
            require(params['streak_count'] > 0 and params['streak_count'] == int(params['streak_count']) and 0 <= params['veil_alpha'] <= 1, f'Invalid rain values: {sid}')
    feature_index = None
    if features is not None:
        feature_index = index(features, 'features')
        require(set(feature_index) == set(images), 'Features must cover exactly the supplied manifest IDs')
    if model is not None:
        validate_record(model, 'model_metadata')
        require(model['feature_order'] == CONTRACT['feature_order'], 'Feature order mismatch')
        require(model['class_order'] == CONTRACT['class_order'], 'Class order mismatch')
    if predictions is not None:
        require(model is not None, 'Predictions require model metadata')
        output = index(predictions, 'prediction')
        require(bool(output), 'Predictions cannot be empty')
        for sid, row in output.items():
            require(sid in images, f'Unknown prediction ID: {sid}')
            require(row['model_id'] == model['model_id'], f'Model ID mismatch: {sid}')
            probs = row['probabilities']
            require(abs(sum(probs.values()) - 1) <= 1e-6, f'Probabilities do not sum to 1: {sid}')
            expected = max(CONTRACT['class_order'], key=lambda k: probs[k])
            require(row['predicted_label'] == expected, f'Predicted class mismatch: {sid}')
            score = 100 * (probs['good'] + .5 * probs['degraded'])
            require(abs(row['health_score'] - score) <= 1e-6, f'Health formula mismatch: {sid}')
            require(abs(row['camera_weight'] - (score / 100)**2) <= 1e-6, f'Camera weight mismatch: {sid}')
            action = 'normal' if score >= 75 else 'down_weight' if score >= 45 else 'strong_down_weight'
            require(row['action'] == action, f'Action mismatch: {sid}')
    return {'manifest':len(images), 'features':len(features) if features is not None else None,
            'predictions':len(predictions) if predictions is not None else None}

def reject_constant(value):
    raise ValueError(f'Invalid JSON constant: {value}')

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject_constant)

def read_jsonl(path):
    rows = []
    for line_no, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if line.strip():
            try: rows.append(json.loads(line, parse_constant=reject_constant))
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f'{path}:{line_no}: {exc}') from exc
    return rows

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--features'); ap.add_argument('--predictions'); ap.add_argument('--model')
    ap.add_argument('--check-files', action='store_true', help='Check manifest image paths under repository root')
    args = ap.parse_args()
    manifest = read_jsonl(args.manifest)
    result = validate_bundle(manifest, read_jsonl(args.features) if args.features else None,
                             read_jsonl(args.predictions) if args.predictions else None,
                             read_json(args.model) if args.model else None)
    if args.check_files:
        for row in manifest:
            target = (ROOT / row['image_path']).resolve()
            require(target.is_relative_to(ROOT), f'Image path escapes repository: {row["sample_id"]}')
            require(target.is_file(), f'Missing image file: {target}')
    print('Contract valid: ' + json.dumps(result))

if __name__ == '__main__': main()
