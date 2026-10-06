"""Person 5: reproducible per-phase evidence audit of an immutable real run."""
import argparse
import copy
import csv
import json
import math
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import baseline, corruptions, features
from src.evaluate import evaluate
from scripts.run_health import digest
from scripts.validate_contract import read_json, read_jsonl, validate_bundle
from scripts.validate_health import validate_health


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def audit(run_id, evidence_id):
    import re
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+', value) for value in (run_id, evidence_id)):
        raise ValueError('Invalid run/evidence ID')
    run = ROOT / 'reports/runs' / run_id
    output = run / evidence_id
    output.mkdir(parents=True, exist_ok=False)
    folder = ROOT / 'data/features' / run_id
    state = read_json(folder / 'state.json')
    originals_path = ROOT / 'data/manifests/originals.jsonl'
    ids_path = Path(state['reference_ids'])
    manifest_path, feature_path = Path(state['manifest']), Path(state['features'])
    refs_path, health_path = folder / 'references.json', folder / 'health_scores.jsonl'
    original_report = run / 'evaluation'
    summary_path = ROOT / 'data/generated' / run_id / 'run_summary.json'
    source_path = ROOT / 'data/raw/bdd100k_hf/samples.json'
    protected = [originals_path, ids_path, manifest_path, feature_path, refs_path, health_path,
                 folder / 'health_val.jsonl', folder / 'references_draft.json', folder / 'handoff.json',
                 summary_path, ROOT / 'configs/corruptions.json', ROOT / 'configs/health.json',
                 ROOT / 'src/corruptions.py', ROOT / 'src/features.py', ROOT / 'src/baseline.py', source_path]
    before = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    manifest, saved_features, scores = map(read_jsonl, (manifest_path, feature_path, health_path))
    refs, ids = read_json(refs_path), read_json(ids_path)
    feature_index = {r['sample_id']: r for r in saved_features}
    images = {r['sample_id']: r for r in manifest}
    stages = []

    def record(person, phase, evidence):
        evidence.update({'person': person, 'phase': phase, 'data_kind': 'real_bdd100k',
                         'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
        write_json(output / f'phase_{person}.json', evidence)
        stages.append(evidence)
        print(json.dumps({'phase': person, 'status': evidence['status']}), flush=True)

    started = time.perf_counter()
    originals, _, _, delivery = corruptions.inspect_inputs(originals_path)
    reference_ids = baseline._select_reference_ids(ids)
    baseline._validate_reference_source(ids, baseline._metadata_index(originals))
    for mode in ('day', 'night'):
        if any(images[sid]['split'] != 'train' or baseline.TIME_MODES.get(images[sid]['timeofday']) != mode for sid in ids[mode]):
            raise ValueError('Reference split/group mismatch')
    source = read_json(source_path)['samples']
    source_index = {Path(row['filepath']).stem: row for row in source}
    mismatches, missing = [], []
    for row in originals:
        original = source_index.get(row['sample_id'])
        if original is None:
            missing.append(row['sample_id'])
            continue
        for field in ('timeofday', 'weather'):
            value = original.get(field, {}).get('label')
            if row[field] != value:
                mismatches.append({'sample_id': row['sample_id'], 'field': field,
                                   'manifest': row[field], 'source': value})
    if missing or mismatches:
        raise ValueError(f'Metadata handoff mismatch: missing={missing}, mismatches={mismatches}')
    record(1, 'data_handoff_audit', {'status': 'delivery_verified_preparation_not_replayed',
           'delivery': delivery, 'reference_count': len(reference_ids), 'reference_visual_review': ids.get('visual_review'),
           'source_metadata_records': len(source), 'matched_original_metadata': len(originals),
           'metadata_mismatches': mismatches, 'missing_source_metadata': missing,
           'missing_preparation_files': [name for name in ('src/prepare_data.py', 'configs/data.json', 'docs/data_notes.md')
                                         if not (ROOT / name).exists()],
           'limitations': 'Cannot replay person1 preparation without its code/config. Sequence IDs checked as supplied, not independently verified. Visual daytime/night flags also occur in local source metadata.',
           'seconds': time.perf_counter() - started})

    # Six original parents spanning every lab split and both metadata time groups.
    selected = []
    for i, split in enumerate(('train', 'val', 'test')):
        for j, timeofday in enumerate(('daytime', 'night')):
            candidates = sorted((r for r in originals if r['split'] == split and r['timeofday'] == timeofday),
                                key=lambda r: r['sample_id'])
            preferred_weather = 'rainy' if (i + j) % 2 else 'clear'
            candidates.sort(key=lambda r: r['weather'] != preferred_weather)
            if not candidates:
                raise ValueError(f'Missing audit stratum: {split}/{timeofday}')
            selected.append(candidates[0])
    selected_ids = {r['sample_id'] for r in selected}
    replay_rows = [r for r in manifest if r['parent_image_id'] in selected_ids and r['corruption'] != 'original']
    started = time.perf_counter()
    verification = corruptions.verify_batch(run_id, repo_root=ROOT, replay=False)
    config = corruptions.load_config(ROOT / 'data/generated' / run_id / 'config_snapshot.json')
    prepared = {r['sample_id']: corruptions.prepare_image(ROOT / r['image_path']) for r in selected}
    pixel_checks = []
    for row in replay_rows:
        actual = features._load_manifest_image(row, ROOT)
        expected = corruptions._degrade(prepared[row['parent_image_id']], row['corruption'], row['severity'], row['seed'], config['levels'])
        if not np.array_equal(actual, expected):
            raise ValueError(f'Real-image pixel replay mismatch: {row["sample_id"]}')
        pixel_checks.append({'sample_id': row['sample_id'], 'seed': row['seed'], 'pixel_equal': True})
    if len(pixel_checks) != 120:
        raise ValueError('Expected 6 parents x 4 corruptions x 5 severity levels')
    write_json(output / 'pixel_replay.json', pixel_checks)
    record(2, 'degradation_verification_and_pixel_replay', {'status': 'passed', 'full_batch': verification,
           'pixel_replay_count': len(pixel_checks), 'selection': selected,
           'replay_scope': 'Full hashes/format/seeds/parameters/coverage checked on 6000 synthetic frames; pixel regeneration on stratified 120 real variants only.',
           'seconds': time.perf_counter() - started})

    started = time.perf_counter()
    feature_ids = {r['sample_id'] for r in replay_rows} | selected_ids | set(reference_ids)
    feature_checks, reextracted = [], {}
    for sid in sorted(feature_ids):
        values = features.extract_features(features._load_manifest_image(images[sid], ROOT))
        expected = feature_index[sid]['features']
        difference = max(abs(values[key] - expected[key]) for key in features.FEATURE_ORDER)
        if difference > 1e-12 or not all(math.isfinite(v) for v in values.values()):
            raise ValueError(f'Feature replay mismatch: {sid}')
        row = copy.deepcopy(feature_index[sid])
        row['features'] = values
        reextracted[sid] = row
        feature_checks.append({'sample_id': sid, 'max_absolute_difference': difference})
    write_json(output / 'feature_replay.json', feature_checks)
    record(3, 'feature_coverage_and_image_reextraction', {'status': 'passed',
           'full_bundle': validate_bundle(manifest, saved_features), 'image_reextraction_count': len(feature_checks),
           'max_absolute_difference': max(r['max_absolute_difference'] for r in feature_checks),
           'replay_scope': 'All 6300 records checked for schema/finite/range/coverage; image computation replay on selected 6 parents, all their variants and all 20 train references.',
           'seconds': time.perf_counter() - started})

    started = time.perf_counter()
    draft = copy.deepcopy(refs['config'])
    draft.update(frozen=False, reference_sha256=None, validation=None)
    draft = baseline.prepare_config(draft)
    recalibrated = baseline.calibrate([reextracted[sid] for sid in reference_ids], manifest, draft)
    if recalibrated['reference_sha256'] != refs['reference_sha256']:
        raise ValueError('Recalibration from real reference images differs from frozen references')
    health_validation = validate_health(manifest, saved_features, scores, refs)
    val_replayed = baseline.score_bundle(saved_features, manifest, refs, refs['config'], split='val')
    if val_replayed != read_jsonl(folder / 'health_val.jsonl'):
        raise ValueError('Validation health no longer matches pre-freeze snapshot')
    record(4, 'reference_recalibration_and_full_health_recomputation', {'status': 'passed',
           'recalibrated_real_train_images': len(reference_ids), 'reference_sha256': recalibrated['reference_sha256'],
           'full_health': health_validation, 'pre_freeze_val_records_equal': len(val_replayed),
           'frozen_config_sha256': refs['config_sha256'],
           'limitations': 'Same unchanged heuristic policy; replay proves implementation reproducibility, not optimal thresholds, clean reference labels or ADAS reliability.',
           'seconds': time.perf_counter() - started})

    started = time.perf_counter()
    reproduction = output / 'evaluation_replay'
    provenance = evaluate(manifest_path, feature_path, health_path, refs_path, reproduction,
                          data_kind='real', extra_inputs=(ids_path, summary_path))
    csv_matches = {}
    for name in ('groups.csv', 'samples.csv', 'curves.csv', 'score_increases.csv', 'split_totals.csv'):
        csv_matches[name] = digest(reproduction / 'evaluation' / name) == digest(original_report / name)
    if not all(csv_matches.values()):
        raise ValueError(f'Evaluation CSV replay differs: {csv_matches}')
    record(5, 'evaluation_report_reproduction', {'status': 'passed', 'evaluated_frames': provenance['scored_frames'],
           'split_counts': provenance['split_counts'], 'csv_byte_equal': csv_matches,
           'report': str((reproduction / 'report.md').relative_to(ROOT)), 'seconds': time.perf_counter() - started})

    after = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    if before != after:
        raise ValueError('Protected input/owner code changed during evidence audit')
    final = {'status': 'complete', 'run_id': run_id, 'evidence_id': evidence_id,
             'command_argv': sys.argv, 'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'audit_script_sha256': digest(__file__), 'protected_sha256': before, 'protected_unchanged': True,
             'phases': [{'person': r['person'], 'phase': r['phase'], 'status': r['status']} for r in stages]}
    write_json(output / 'summary.json', final)
    lines = ['# Evidence theo phase trên BDD100K thật', '', f'Run: `{run_id}`. Evidence: `{evidence_id}`.', '',
             '| Người | Phase | Kết quả |', '|---|---|---|']
    lines += [f'| {r["person"]} | {r["phase"]} | {r["status"]} |' for r in stages]
    lines += ['', 'Phase 1: audit delivery 300 ảnh và đối chiếu metadata nguồn local; chưa replay bước chuẩn bị data vì thiếu code/config người 1.',
              'Phase 2: kiểm tra full 6.000 synthetic; tái sinh pixel 120 variants của 6 parents đủ train/val/test, ngày/đêm và clear/rainy.',
              f'Phase 3: validate 6.300 features; tính lại từ ảnh {len(feature_checks)} records, gồm toàn bộ 20 reference. Sai khác tối đa 0.',
              'Phase 4: recalibrate từ 20 train ảnh thật; reference hash khớp; recompute 6.300 scores và evidence freeze/val khớp.',
              'Phase 5: tái xuất report; năm CSV có byte/hash giống run đã nghiệm thu. Xem evaluation_replay/report.md.',
              '', 'Inputs, owner code/config và output bàn giao không đổi. Mỗi phase có JSON, timestamp UTC, thời gian, số record và scope rõ ràng.',
              'Không gọi sample replay là full image-computation replay. Full integration run trước đó đã tính tất cả 6.300 frames từ ảnh thật.',
              'Reference review và visual metadata flags vẫn là limitations; hai daytime flags khớp metadata nguồn local, chưa chứng minh lỗi xử lý người 1.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'complete', 'evidence': str(output)}), flush=True)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--evidence-id', required=True)
    args = parser.parse_args()
    audit(args.run_id, args.evidence_id)


if __name__ == '__main__':
    main()
