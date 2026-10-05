"""Prepare person 4's validation review, then finalize an immutable health run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import baseline
from src.features import extract_manifest
from scripts.validate_contract import read_jsonl, validate_bundle


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    baseline._write_new(path, value)


def summary(rows, metadata):
    images = {row['sample_id']: row for row in metadata}
    scores = {row['sample_id']: row for row in rows}
    groups = defaultdict(list)
    for row in rows:
        image = images[row['sample_id']]
        groups[(image['split'], row['mode'], image['corruption'], image['severity'])].append(row)
    result = []
    for (split, mode, kind, severity), values in sorted(groups.items()):
        paired = [row['health_adaptive'] - scores[images[row['sample_id']]['parent_image_id']]['health_adaptive']
                  for row in values]
        result.append({'split': split, 'mode': mode, 'corruption': kind, 'severity': severity,
                       'count': len(values), 'fixed_mean': mean(row['health_fixed'] for row in values),
                       'adaptive_mean': mean(row['health_adaptive'] for row in values),
                       'adaptive_median': median(row['health_adaptive'] for row in values),
                       'paired_delta_mean': mean(paired),
                       'normal': sum(row['action'] == 'normal' for row in values),
                       'down_weight': sum(row['action'] == 'down_weight' for row in values),
                       'strong_down_weight': sum(row['action'] == 'strong_down_weight' for row in values)})
    return result


def write_summary(output, rows, metadata, title):
    values = summary(rows, metadata)
    write_json(output / 'summary.json', values)
    with (output / 'summary.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)
    increases = baseline.find_score_increases(rows, metadata)
    write_json(output / 'score_increases.json', increases)
    lines = [f'# {title}', '', f'Records: {len(rows)}. Actions: {dict(Counter(row["action"] for row in rows))}.',
             f'Score-increase findings against original parents: {len(increases)} (fixed/adaptive counted separately).', '',
             '| Split | Mode | Corruption | Severity | N | Fixed mean | Adaptive mean | Paired delta |',
             '|---|---|---|---:|---:|---:|---:|---:|']
    for value in values:
        lines.append('| {split} | {mode} | {corruption} | {severity} | {count} | {fixed_mean:.2f} | '
                     '{adaptive_mean:.2f} | {paired_delta_mean:.2f} |'.format(**value))
    lines += ['', 'Synthetic severity is a proxy, not a human quality label. Thresholds are descriptive.',
              'No classifier training, F1, detector AP, fusion benefit or ADAS safety claim.']
    with (output / 'review.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')


def contact_sheet(path, selected, metadata, scores=None):
    from PIL import Image, ImageDraw
    images = {row['sample_id']: row for row in metadata}
    columns, width, height = 4, 320, 220
    sheet = Image.new('RGB', (columns * width, math.ceil(len(selected) / columns) * height), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, sid in enumerate(selected):
        x, y = index % columns * width, index // columns * height
        with Image.open(ROOT / images[sid]['image_path']) as image:
            sheet.paste(image.convert('RGB').resize((width, 180), Image.Resampling.BILINEAR), (x, y))
        draw.text((x + 3, y + 183), sid, fill='black')
        caption = images[sid]['timeofday'] + ' / ' + images[sid]['corruption']
        if scores:
            caption += f" / health {scores[sid]['health_adaptive']:.1f}"
        draw.text((x + 3, y + 200), caption, fill='black')
    sheet.save(path)


def prepare(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id):
        raise ValueError('run-id must contain only letters, digits, underscore or hyphen')
    manifest = Path(args.manifest).resolve()
    reference_path = Path(args.reference_ids).resolve()
    images = read_jsonl(manifest)
    validate_bundle(images)
    references_file = baseline._read_json(reference_path)
    ids = baseline._select_reference_ids(references_file)
    metadata = baseline._metadata_index(images)
    provenance = baseline._validate_reference_source(references_file, metadata)
    if not set(ids) <= set(metadata):
        raise ValueError('Reference IDs are missing from the manifest')
    if isinstance(references_file, dict):
        for mode in ('day', 'night'):
            if any(baseline.TIME_MODES.get(metadata[sid]['timeofday']) != mode for sid in references_file[mode]):
                raise ValueError(f'Reference IDs mislabeled as {mode}')
    output = ROOT / 'data/features' / args.run_id
    output.mkdir(parents=True, exist_ok=False)
    feature_path = Path(args.features).resolve() if args.features else output / 'features.jsonl'
    if not args.features:
        extract_manifest(manifest, feature_path, image_root=ROOT)
    features = read_jsonl(feature_path)
    validate_bundle(images, features)
    indexed = {row['sample_id']: row for row in features}
    config = baseline.prepare_config(baseline._read_json(args.config))
    refs = baseline.calibrate([indexed[sid] for sid in ids], images, config)
    provenance.update({'manifest_sha256': digest(manifest), 'features_sha256': digest(feature_path),
                       'reference_ids_sha256': digest(reference_path),
                       'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                       'runtime': sys.version, 'packages': {name: importlib.metadata.version(name)
                                                          for name in ('numpy', 'Pillow', 'jsonschema')},
                       'module_sha256': {name: digest(ROOT / name) for name in
                                         ('src/baseline.py', 'src/features.py', 'scripts/run_health.py')}})
    refs['provenance'] = provenance
    write_json(output / 'references_draft.json', refs)
    val = baseline.score_bundle(features, images, refs, refs['config'], split='val')
    baseline._write_new(output / 'health_val.jsonl', val, jsonl=True)
    review = output / 'validation'
    review.mkdir()
    val_images = [row for row in images if row['split'] == 'val']
    write_summary(review, val, val_images, 'Validation review before config freeze')
    val_scores = {row['sample_id']: row for row in val}
    originals = [row for row in val if metadata[row['sample_id']]['corruption'] == 'original']
    selected = [row['sample_id'] for row in sorted(originals, key=lambda row: row['health_adaptive'])[:8]]
    contact_sheet(review / 'lowest_originals.png', selected, images, val_scores)
    diagnostics = [baseline.explain_health(indexed[sid], metadata[sid]['timeofday'], refs, refs['config'])
                   for sid in selected]
    write_json(review / 'explanations.json', diagnostics)
    for mode in ('day', 'night'):
        selected_refs = [sid for sid in ids if baseline.TIME_MODES.get(metadata[sid]['timeofday']) == mode]
        contact_sheet(review / f'references_{mode}.png', selected_refs, images)
    state = {'run_id': args.run_id, 'manifest': str(manifest), 'features': str(feature_path),
             'reference_ids': str(reference_path), 'manifest_sha256': digest(manifest),
             'features_sha256': digest(feature_path), 'reference_ids_sha256': digest(reference_path),
             'validation_scores_sha256': digest(output / 'health_val.jsonl'),
             'draft_sha256': digest(output / 'references_draft.json')}
    write_json(output / 'state.json', state)
    print(json.dumps({'stage': 'validation_ready', 'run_id': args.run_id, 'val_count': len(val),
                      'review': str(review), 'next_step': 'Review references and validation, then finalize.'}))


def finalize(args):
    output = Path(args.run_dir).resolve()
    state = baseline._read_json(output / 'state.json')
    if (output / 'references.json').exists() or (output / 'health_scores.jsonl').exists():
        raise FileExistsError('Final output already exists; prepare a new run')
    if not args.validation_note.strip() or not args.reference_review_note.strip():
        raise ValueError('Both review notes must be nonempty')
    for name in ('manifest', 'features', 'reference_ids'):
        if digest(state[name]) != state[name + '_sha256']:
            raise ValueError(f'{name} changed since validation; prepare a new run')
    if digest(output / 'references_draft.json') != state['draft_sha256']:
        raise ValueError('Draft reference/config changed since validation')
    if digest(output / 'health_val.jsonl') != state['validation_scores_sha256']:
        raise ValueError('Validation scores changed since review')
    images, features = read_jsonl(state['manifest']), read_jsonl(state['features'])
    validate_bundle(images, features)
    refs = baseline._read_json(output / 'references_draft.json')
    for name, expected_hash in refs['provenance']['module_sha256'].items():
        if digest(ROOT / name) != expected_hash:
            raise ValueError(f'{name} changed since validation; prepare a new run')
    val_ids = {row['sample_id'] for row in images if row['split'] == 'val'}
    frozen = baseline.freeze_references(refs, [row for row in features if row['sample_id'] in val_ids],
                                       [row for row in images if row['sample_id'] in val_ids],
                                       refs['config'], args.validation_note)
    frozen['provenance']['reference_review_note'] = args.reference_review_note
    frozen['provenance']['validation_review_note'] = args.validation_note
    scores = baseline.score_bundle(features, images, frozen, frozen['config'])
    baseline._require(len(scores) == len(images), 'Final health coverage mismatch')
    for row in scores:
        baseline._require(all(math.isfinite(row[key]) and 0 <= row[key] <= 100 for key in
                              ('health_fixed', 'health_adaptive', 'health_score')), 'Invalid health score')
        baseline._require(math.isclose(row['camera_weight'], (row['health_score'] / 100) ** 2),
                          'Camera weight mismatch')
    write_json(output / 'references.json', frozen)
    baseline._write_new(output / 'health_scores.jsonl', scores, jsonl=True)
    review = output / 'final_review'
    review.mkdir()
    write_summary(review, scores, images, 'Frozen health run: all splits')
    write_json(output / 'handoff.json', {'run_id': state['run_id'], 'status': 'complete',
               'record_count': len(scores), 'split_counts': dict(Counter(row['split'] for row in images)),
               'manifest': state['manifest'], 'features': state['features'],
               'reference_ids': state['reference_ids'],
               'references': str(output / 'references.json'), 'health_scores': str(output / 'health_scores.jsonl'),
               'reference_sha256': frozen['reference_sha256'], 'config_sha256': frozen['config_sha256'],
               'health_file_sha256': digest(output / 'health_scores.jsonl'), 'policy_id': frozen['config']['policy_id'],
               'validation_note': args.validation_note, 'reference_review_note': args.reference_review_note,
               'limitations': 'Heuristic only; synthetic severity is not a quality label. No model training.'})
    print(json.dumps({'stage': 'complete', 'run_id': state['run_id'], 'score_count': len(scores),
                      'test_count': sum(row['split'] == 'test' for row in images), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    draft = commands.add_parser('prepare', help='Extract features, calibrate and score val only')
    draft.add_argument('--manifest', required=True)
    draft.add_argument('--reference-ids', default=str(ROOT / 'data/manifests/reference_ids.json'))
    draft.add_argument('--config', default=str(ROOT / 'configs/health.json'))
    draft.add_argument('--features', help='Reuse an existing immutable feature file')
    draft.add_argument('--run-id', required=True)
    frozen = commands.add_parser('finalize', help='Record reviews, freeze config and score all splits')
    frozen.add_argument('--run-dir', required=True)
    frozen.add_argument('--validation-note', required=True)
    frozen.add_argument('--reference-review-note', required=True)
    args = parser.parse_args()
    try:
        (prepare if args.command == 'prepare' else finalize)(args)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f'Health run error: {error}\n')


if __name__ == '__main__':
    main()
