"""Person 2 degradation API and standalone batch adapter; no work at import."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'configs/corruptions.json'
LEVELS = {
    'gaussian_blur': [0.6, 1.2, 2.4, 4, 6],
    'brightness_up': [1.2, 1.5, 1.9, 2.5, 3.2],
    'brightness_down': [0.8, 0.6, 0.4, 0.25, 0.12],
    'gaussian_noise': [5, 10, 20, 35, 50],
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path=DEFAULT_CONFIG):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if config.get('schema_version') != '1.0.0':
        raise ValueError('Unsupported schema_version')
    if type(config.get('base_seed')) is not int or config['base_seed'] < 0:
        raise ValueError('base_seed must be a nonnegative integer')
    levels = config.get('levels', {})
    if set(levels) != set(LEVELS):
        raise ValueError('Require exactly the four contract corruptions')
    for kind, values in levels.items():
        if len(values) != 5 or any(type(x) not in (int, float) or not np.isfinite(x) for x in values):
            raise ValueError(f'{kind}: require five finite levels')
        if kind == 'brightness_down':
            valid = all(0 < x < 1 for x in values) and all(a > b for a, b in zip(values, values[1:]))
        else:
            valid = all(x > (1 if kind == 'brightness_up' else 0) for x in values)
            valid = valid and all(a < b for a, b in zip(values, values[1:]))
        if not valid:
            raise ValueError(f'{kind}: invalid parameter range/severity ordering')
    return config


def _validator():
    # Load the shared validator lazily; importing the API performs no file I/O.
    scripts = str(ROOT / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from validate_contract import read_jsonl, validate_bundle
    return read_jsonl, validate_bundle


def inspect_inputs(manifest_path=None, config_path=DEFAULT_CONFIG, repo_root=ROOT):
    """Validate person 1's complete delivery without writing any output."""
    root = Path(repo_root).resolve()
    manifest = Path(manifest_path) if manifest_path else Path('data/manifests/originals.jsonl')
    manifest = manifest if manifest.is_absolute() else root / manifest
    config_path = Path(config_path)
    config_path = config_path if config_path.is_absolute() else root / config_path
    if not manifest.is_file():
        raise ValueError(f'Waiting for person 1: missing originals manifest {manifest}. '
                         'Provide original images and a contract-v1 originals.jsonl; image folders alone lack metadata/splits.')
    manifest_hash, config_hash = sha256(manifest), sha256(config_path)
    config = load_config(config_path)
    read_jsonl, validate_bundle = _validator()
    originals = read_jsonl(manifest)
    try:
        validate_bundle(originals)
    except Exception as exc:
        raise ValueError(f'Invalid person-1 manifest {manifest}: {exc}') from exc
    if any(row['corruption'] != 'original' for row in originals):
        raise ValueError('Person-1 input must contain only originals')
    sources, hashes = {}, {}
    for row in originals:
        sid = row['sample_id']
        source = _inside(root, row['image_path'])
        if not source.is_file():
            raise ValueError(f'Missing source for {sid}: {source}; keep image_path relative to repo root')
        try:
            prepared = prepare_image(source)
        except Exception as exc:
            raise ValueError(f'Cannot decode source for {sid}: {source}: {exc}') from exc
        if prepared.shape != (360, 640, 3) or prepared.dtype != np.uint8:
            raise ValueError(f'Cannot prepare RGB source: {sid}')
        digest = sha256(source)
        sources[sid] = {'path': row['image_path'], 'sha256': digest}
        hashes.setdefault(digest, []).append(sid)
    if sha256(manifest) != manifest_hash or sha256(config_path) != config_hash:
        raise ValueError('Input delivery changed during preflight; use a stable snapshot')
    duplicates = [ids for ids in hashes.values() if len(ids) > 1]
    warnings = []
    for name, predicate in _smoke_groups().items():
        if not any(predicate(row) for row in originals):
            warnings.append(f'No originals available for smoke group: {name}')
    if duplicates:
        warnings.append('Byte-identical sources detected; ask person 1 to review duplicate images')
    report = {
        'status': 'ready', 'original_count': len(originals),
        'expected_synthetic_count': len(originals) * 20,
        'expected_record_count': len(originals) * 21,
        'manifest': str(manifest.resolve()), 'config': str(config_path.resolve()),
        'manifest_sha256': manifest_hash, 'config_sha256': config_hash,
        'split_counts': dict(Counter(row['split'] for row in originals)),
        'timeofday_counts': dict(Counter(row['timeofday'] for row in originals)),
        'weather_counts': dict(Counter(row['weather'] for row in originals)),
        'duplicate_source_groups': duplicates, 'warnings': warnings,
    }
    return originals, config, sources, report


def _smoke_groups():
    return {
        'day_clear': lambda row: row['timeofday'] == 'daytime' and row['weather'] == 'clear',
        'night_clear': lambda row: row['timeofday'] == 'night' and row['weather'] == 'clear',
        'rainy': lambda row: row['weather'] == 'rainy',
    }


def select_smoke(originals, count=6):
    """Stable representative selection; report absent groups instead of inventing them."""
    if type(count) is not int or count <= 0:
        raise ValueError('Smoke count must be positive')
    selected, seen = [], set()
    candidates = sorted(originals, key=lambda row: row['sample_id'])
    for predicate in _smoke_groups().values():
        if any(predicate(row) for row in selected):
            continue
        for row in candidates:
            if len(selected) < count and row['sample_id'] not in seen and predicate(row):
                selected.append(row)
                seen.add(row['sample_id'])
                break
    for row in candidates:
        if len(selected) >= count:
            break
        if row['sample_id'] not in seen:
            selected.append(row)
            seen.add(row['sample_id'])
    return selected


def sample_seed(base_seed, parent_id, corruption, severity):
    """SHA256 of canonical UTF-8 JSON tuple; first 8 bytes, big endian."""
    payload = json.dumps([base_seed, parent_id, corruption, severity],
                         ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big')


def _degrade(image_rgb, corruption, severity, seed, levels):
    if not isinstance(image_rgb, np.ndarray) or image_rgb.dtype != np.uint8 or image_rgb.shape != (360, 640, 3):
        raise ValueError('Expected numpy RGB uint8 image of shape (360,640,3)')
    if corruption not in LEVELS:
        raise ValueError(f'Unsupported corruption: {corruption}')
    if type(severity) is not int or not 1 <= severity <= 5:
        raise ValueError('severity must be integer 1..5')
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    value = levels[corruption][severity - 1]
    if corruption == 'gaussian_blur':
        # Pillow approximates Gaussian convolution using extended box filters.
        return np.array(Image.fromarray(image_rgb).filter(ImageFilter.GaussianBlur(value)), copy=True)
    pixels = image_rgb.astype(np.float64)
    if corruption == 'gaussian_noise':
        pixels += np.random.default_rng(seed).normal(0, value, pixels.shape)
    else:
        pixels *= value
    return np.rint(np.clip(pixels, 0, 255)).astype(np.uint8)


def degrade(image_rgb, corruption, severity, seed):
    """Required four-argument API with the fixed default contract v1 levels."""
    return _degrade(image_rgb, corruption, severity, seed, LEVELS)


def prepare_image(path):
    with Image.open(path) as image:
        return np.array(image.convert('RGB').resize((640, 360), Image.Resampling.BILINEAR), copy=True)


def _inside(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes repository: {relative}')
    return target


def _contact_sheet(original, variants, levels, target):
    sheet = Image.new('RGB', (1440, 620), 'white')
    draw = ImageDraw.Draw(sheet)
    for row, kind in enumerate(LEVELS):
        for col in range(6):
            pixels = original if col == 0 else variants[(kind, col)]
            thumb = Image.fromarray(pixels).resize((240, 135), Image.Resampling.BILINEAR)
            sheet.paste(thumb, (col * 240, row * 155 + 20))
            label = 'original (resized)' if col == 0 else f'{kind} s{col}: {levels[kind][col-1]}'
            draw.text((col * 240 + 2, row * 155 + 3), label, fill='black')
    sheet.save(target)


def generate_batch(manifest_path, run_id, config_path=DEFAULT_CONFIG,
                   repo_root=ROOT, limit=None, sanity_count=6, smoke=False):
    """Owner-scoped adapter for person 5's runner; publish only complete bundles."""
    # Reuse the existing validator without editing person 5's files.
    _, validate_bundle = _validator()
    root = Path(repo_root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run_id: use letters, digits, underscore or hyphen')
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError('limit must be positive')
    if type(sanity_count) is not int or sanity_count < 0:
        raise ValueError('sanity_count must be nonnegative')
    originals, config, all_sources, input_report = inspect_inputs(manifest_path, config_path, root)
    manifest_path, config_path = input_report['manifest'], input_report['config']
    if smoke:
        originals = select_smoke(originals, limit or 6)
    elif limit is not None:
        originals = originals[:limit]
    output_dir = _inside(root, f'data/generated/{run_id}')
    output_manifest = _inside(root, f'data/manifests/augmented_{run_id}.jsonl')
    if output_dir.exists() or output_manifest.exists():
        raise FileExistsError('Output snapshot exists; choose a new run_id')
    ids = {row['sample_id'] for row in originals}
    sources = {row['sample_id']: all_sources[row['sample_id']] for row in originals}
    for row in originals:
        sid = row['sample_id']
        for kind in LEVELS:
            for severity in range(1, 6):
                child = f'{sid}_{kind}_s{severity}'
                if child in ids:
                    raise ValueError(f'Duplicate generated ID: {child}')
                ids.add(child)
    input_hash, config_hash = input_report['manifest_sha256'], input_report['config_sha256']
    output_dir.mkdir(parents=True, exist_ok=False)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / 'config_snapshot.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    result, image_hashes = list(originals), {}
    for index, row in enumerate(originals):
        sid = row['sample_id']
        try:
            original = prepare_image(_inside(root, row['image_path']))
            variants = {}
            for kind in LEVELS:
                for severity in range(1, 6):
                    seed = sample_seed(config['base_seed'], sid, kind, severity)
                    pixels = _degrade(original, kind, severity, seed, config['levels'])
                    child = f'{sid}_{kind}_s{severity}'
                    relative = f'data/generated/{run_id}/{child}.png'
                    destination = _inside(root, relative)
                    Image.fromarray(pixels).save(destination, format='PNG')
                    with Image.open(destination) as saved:
                        if saved.mode != 'RGB' or saved.size != (640, 360) or not np.array_equal(np.array(saved), pixels):
                            raise ValueError(f'PNG round-trip failed: {child}')
                    image_hashes[child] = sha256(destination)
                    parameter = 'sigma' if kind in ('gaussian_blur', 'gaussian_noise') else 'gain'
                    record = dict(row)
                    record.update(sample_id=child, parent_image_id=sid, image_path=relative,
                                  corruption=kind, severity=severity, seed=seed,
                                  parameters={parameter: config['levels'][kind][severity - 1]},
                                  label=None, label_source='unlabeled', label_rule_version=None)
                    result.append(record)
                    if index < sanity_count:
                        variants[(kind, severity)] = pixels
            if index < sanity_count:
                sanity = output_dir / 'sanity'
                sanity.mkdir(exist_ok=True)
                _contact_sheet(original, variants, config['levels'], sanity / f'{sid}.png')
        except Exception as exc:
            raise RuntimeError(f'Batch failed at {sid}; partial output retained at {output_dir}') from exc
    validation = validate_bundle(result)
    if len(result) != len(originals) * 21:
        raise ValueError('Incomplete output coverage')
    for sid, source in sources.items():
        if sha256(_inside(root, source['path'])) != source['sha256']:
            raise ValueError(f'Source changed during generation: {sid}')
    if sha256(manifest_path) != input_hash or sha256(config_path) != config_hash:
        raise ValueError('Input manifest/config changed during generation')
    with output_manifest.open('x', encoding='utf-8') as stream:
        for record in result:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
    summary = {
        'status': 'complete', 'run_id': run_id,
        'original_count': len(originals), 'synthetic_count': len(image_hashes),
        'record_count': len(result),
        'counts_per_corruption': {kind: len(originals) * 5 for kind in LEVELS},
        'manifest_path': output_manifest.relative_to(root).as_posix(),
        'input_manifest_sha256': input_hash, 'config_sha256': config_hash,
        'output_manifest_sha256': sha256(output_manifest), 'base_seed': config['base_seed'],
        'source_hashes': sources, 'generated_png_sha256': image_hashes,
        'versions': {'python': sys.version.split()[0], 'numpy': np.__version__, 'Pillow': PIL.__version__},
        'validation': validation,
        'input_delivery': input_report,
        'selected_original_ids': [row['sample_id'] for row in originals],
    }
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        summary['git_commit'] = commit.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        summary['git_commit'] = None
    # The commit alone cannot identify uncommitted implementation changes.
    summary['module_sha256'] = sha256(__file__)
    summary['config_snapshot_sha256'] = sha256(output_dir / 'config_snapshot.json')
    summary['invocation'] = {'argv': sys.argv, 'manifest': str(Path(manifest_path).resolve()),
                             'config': str(Path(config_path).resolve()),
                             'limit': limit, 'sanity_count': sanity_count}
    summary['invocation']['smoke'] = smoke
    (output_dir / 'run_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def verify_batch(run_id, repo_root=ROOT, replay=False):
    """Read-only acceptance check of a completed delivery, including actual files."""
    root = Path(repo_root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run_id')
    output = _inside(root, f'data/generated/{run_id}')
    summary = json.loads((output / 'run_summary.json').read_text(encoding='utf-8'))
    manifest = _inside(root, summary['manifest_path'])
    if sha256(manifest) != summary['output_manifest_sha256']:
        raise ValueError('Augmented manifest hash mismatch')
    snapshot = output / 'config_snapshot.json'
    if sha256(snapshot) != summary['config_snapshot_sha256']:
        raise ValueError('Config snapshot hash mismatch')
    config = load_config(snapshot)
    read_jsonl, validate_bundle = _validator()
    rows = read_jsonl(manifest)
    validate_bundle(rows)
    parents = {row['sample_id']: row for row in rows if row['corruption'] == 'original'}
    synthetic = [row for row in rows if row['corruption'] != 'original']
    if (len(parents) != summary['original_count'] or len(synthetic) != len(parents) * 20
            or len(rows) != summary['record_count'] or len(synthetic) != summary['synthetic_count']):
        raise ValueError('Delivery coverage/count mismatch')
    for sid, parent in parents.items():
        source = _inside(root, parent['image_path'])
        if sha256(source) != summary['source_hashes'][sid]['sha256']:
            raise ValueError(f'Source hash mismatch: {sid}')
    combinations = set()
    prepared = {}
    for row in synthetic:
        sid, kind, severity = row['sample_id'], row['corruption'], row['severity']
        parent = row['parent_image_id']
        key = (parent, kind, severity)
        if kind not in LEVELS or key in combinations:
            raise ValueError(f'Unexpected/duplicate corruption combination: {sid}')
        combinations.add(key)
        parameter = 'sigma' if kind in ('gaussian_blur', 'gaussian_noise') else 'gain'
        if row['parameters'] != {parameter: config['levels'][kind][severity - 1]}:
            raise ValueError(f'Parameter mismatch: {sid}')
        if row['seed'] != sample_seed(config['base_seed'], parent, kind, severity):
            raise ValueError(f'Seed mismatch: {sid}')
        if row['label'] is not None or row['label_source'] != 'unlabeled' or row['label_rule_version'] is not None:
            raise ValueError(f'Unexpected synthetic annotation: {sid}')
        path = _inside(root, row['image_path'])
        if sha256(path) != summary['generated_png_sha256'][sid]:
            raise ValueError(f'PNG hash mismatch: {sid}')
        with Image.open(path) as image:
            pixels = np.array(image)
            if image.format != 'PNG' or image.mode != 'RGB' or pixels.shape != (360, 640, 3) or pixels.dtype != np.uint8:
                raise ValueError(f'Invalid PNG mode/shape/dtype: {sid}')
        if replay:
            if parent not in prepared:
                # Cache one parent only; do not retain a full dataset in memory.
                prepared = {parent: prepare_image(_inside(root, parents[parent]['image_path']))}
            expected = _degrade(prepared[parent], kind, severity, row['seed'], config['levels'])
            if not np.array_equal(expected, pixels):
                raise ValueError(f'Replay pixel mismatch: {sid}')
    if len(combinations) != len(parents) * 20:
        raise ValueError('Missing parent/type/severity combinations')
    return {'status': 'verified', 'run_id': run_id, 'original_count': len(parents),
            'synthetic_count': len(synthetic), 'record_count': len(rows), 'replayed': replay}


def run_handoff(manifest_path=None, run_id=None, config_path=DEFAULT_CONFIG,
                repo_root=ROOT, sanity_count=6):
    """One command: preflight -> representative smoke -> full -> verify -> handoff."""
    root = Path(repo_root).resolve()
    if not run_id or not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Provide a safe run_id allocated by person 5')
    for name in (f'{run_id}_smoke', run_id):
        if (_inside(root, f'data/generated/{name}').exists()
                or _inside(root, f'data/manifests/augmented_{name}.jsonl').exists()):
            raise FileExistsError(f'Snapshot {name} already exists; use a new run_id')
    _, _, _, preflight = inspect_inputs(manifest_path, config_path, root)
    manifest_path, config_path = preflight['manifest'], preflight['config']
    smoke = generate_batch(manifest_path, f'{run_id}_smoke', config_path, root,
                           limit=6, sanity_count=6, smoke=True)
    smoke_verification = verify_batch(f'{run_id}_smoke', root, replay=True)
    full = generate_batch(manifest_path, run_id, config_path, root, sanity_count=sanity_count)
    if full['input_manifest_sha256'] != smoke['input_manifest_sha256'] or full['config_sha256'] != smoke['config_sha256']:
        raise ValueError('Smoke/full input snapshot differs; do not hand off this run')
    verification = verify_batch(run_id, root)
    handoff = {'status': 'ready_for_review', 'run_id': run_id,
               'manifest_path': full['manifest_path'], 'smoke_manifest_path': smoke['manifest_path'],
               'smoke_verification': smoke_verification, 'full_verification': verification,
               'warnings': preflight['warnings'], 'visual_review_required': True,
               'summary_path': f'data/generated/{run_id}/run_summary.json',
               'sanity_path': f'data/generated/{run_id}_smoke/sanity',
               'next_step': 'Person 3 reads every ID in manifest_path; do not glob generated PNGs.'}
    output = _inside(root, f'data/generated/{run_id}')
    (output / 'handoff.json').write_text(json.dumps(handoff, indent=2) + '\n', encoding='utf-8')
    example = next(row for row in _validator()[0](root / full['manifest_path']) if row['corruption'] != 'original')
    notes = (f'# Person 2 handoff: {run_id}\n\n'
             f'Status: ready for visual review; automatic checks passed.\n\n'
             f'Originals: {full["original_count"]}; synthetic: {full["synthetic_count"]}; records: {full["record_count"]}.\n\n'
             f'Person 3 input: `{full["manifest_path"]}`\n\n'
             f'Smoke contact sheets: `{handoff["sanity_path"]}`\n\n'
             f'Config SHA256: `{full["config_sha256"]}`\n\n'
             f'Manifest SHA256: `{full["output_manifest_sha256"]}`\n\n'
             f'Warnings: {json.dumps(preflight["warnings"])}\n\n'
             'Example synthetic record:\n\n```json\n' + json.dumps(example, indent=2) + '\n```\n\n'
             'Review contact sheets before acceptance. Synthetic severity is not a quality label. '
             'No training, detector AP or ADAS reliability claims. See docs/degradation_notes.md.\n')
    (output / 'handoff.md').write_text(notes, encoding='utf-8')
    return handoff


def image_smoke(image_dir, run_id, config_path=DEFAULT_CONFIG, repo_root=ROOT, count=6):
    """Diagnostic on real source images without inventing a pipeline manifest.

    Dataset-agnostic API verification; metadata, splits and manifest ownership
    stay with person 1. Output cannot be passed to the feature pipeline as a
    contract bundle. Existing upstream corruptions should not be used as sources.
    """
    root = Path(repo_root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run_id')
    if type(count) is not int or count <= 0:
        raise ValueError('Image smoke count must be positive')
    source_dir = _inside(root, image_dir)
    if not source_dir.is_dir():
        raise ValueError(f'Missing image directory: {source_dir}')
    config_path = Path(config_path)
    config_path = config_path if config_path.is_absolute() else root / config_path
    config_hash = sha256(config_path)
    config = load_config(config_path)
    candidates = sorted(path for path in source_dir.rglob('*')
                        if path.is_file() and path.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    if not candidates:
        raise ValueError(f'No source images in {source_dir}')
    # Spread across sorted source files rather than taking adjacent frames only.
    indices = np.linspace(0, len(candidates) - 1, min(count, len(candidates)), dtype=int)
    selected = [candidates[int(index)] for index in indices]
    prepared = []
    for path in selected:
        relative = path.relative_to(root).as_posix()
        _inside(root, relative)
        try:
            pixels = prepare_image(path)
        except Exception as exc:
            raise ValueError(f'Unreadable smoke image: {relative}') from exc
        prepared.append((relative, sha256(path), pixels))
    output = _inside(root, f'data/generated/{run_id}')
    if output.exists():
        raise FileExistsError('Image smoke output exists; choose a new run_id')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'images').mkdir()
    (output / 'sanity').mkdir()
    (output / 'config_snapshot.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    records, sources = [], []
    for index, (relative, source_hash, original) in enumerate(prepared):
        # Diagnostic ID, not a replacement for person 1's sample_id.
        image_id = 'smoke_' + hashlib.sha256(relative.encode('utf-8')).hexdigest()[:20]
        variants = {}
        for kind in LEVELS:
            for severity in range(1, 6):
                seed = sample_seed(config['base_seed'], image_id, kind, severity)
                pixels = _degrade(original, kind, severity, seed, config['levels'])
                replay = _degrade(original, kind, severity, seed, config['levels'])
                if not np.array_equal(pixels, replay):
                    raise ValueError(f'Image smoke replay failed: {relative}/{kind}/{severity}')
                name = f'{image_id}_{kind}_s{severity}.png'
                destination = output / 'images' / name
                Image.fromarray(pixels).save(destination, format='PNG')
                with Image.open(destination) as saved:
                    if saved.mode != 'RGB' or saved.size != (640, 360) or not np.array_equal(np.array(saved), pixels):
                        raise ValueError(f'Image smoke PNG roundtrip failed: {name}')
                parameter = 'sigma' if kind in ('gaussian_blur', 'gaussian_noise') else 'gain'
                records.append({'source_image': relative, 'diagnostic_image_id': image_id,
                                'corruption': kind, 'severity': severity, 'seed': seed,
                                'parameters': {parameter: config['levels'][kind][severity - 1]},
                                'image_path': destination.relative_to(root).as_posix(),
                                'png_sha256': sha256(destination)})
                variants[(kind, severity)] = pixels
        sheet = output / 'sanity' / f'{index:02d}_{image_id}.png'
        _contact_sheet(original, variants, config['levels'], sheet)
        if sha256(_inside(root, relative)) != source_hash:
            raise ValueError(f'Smoke source changed: {relative}')
        sources.append({'source_image': relative, 'source_sha256': source_hash,
                        'diagnostic_image_id': image_id, 'contact_sheet': sheet.relative_to(root).as_posix()})
    if sha256(config_path) != config_hash:
        raise ValueError('Image smoke config changed during run')
    report = {'status': 'diagnostic_passed', 'pipeline_ready': False,
              'manifest_generated': False, 'visual_review_required': True,
              'source_count': len(selected), 'synthetic_count': len(records),
              'source_candidates': len(candidates), 'sources': sources, 'images': records,
              'config_sha256': config_hash, 'module_sha256': sha256(__file__),
              'versions': {'python': sys.version.split()[0], 'numpy': np.__version__, 'Pillow': PIL.__version__},
              'invocation': sys.argv,
              'limitations': 'Diagnostic image-only run; no inferred dataset, weather, labels or splits. '
                             'Integrated augmented manifest awaits person 1 input and person 5 contract.'}
    (output / 'image_smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return {'status': report['status'], 'source_count': len(selected), 'synthetic_count': len(records),
            'pipeline_ready': False, 'report_path': (output / 'image_smoke.json').relative_to(root).as_posix()}


def self_check():
    """Executable acceptance checks on explicit non-BDD100K fixtures.

    Artifacts stay under ignored data/generated/ for inspection. Shared tests/
    remains owned by person 5; this check is local to the degradation module.
    """
    artifact_parent = ROOT / 'data/generated'
    artifact_parent.mkdir(parents=True, exist_ok=True)
    fixture_root = Path(tempfile.mkdtemp(prefix='degradation_fixture_', dir=artifact_parent))
    source_dir = fixture_root / 'data/raw'
    source_dir.mkdir(parents=True)
    yy, xx = np.indices((360, 640))
    gradient = np.stack(((xx * 255 / 639), (yy * 255 / 359), ((xx + yy) % 256)), axis=-1).astype(np.uint8)
    flat = np.full((360, 640, 3), 128, dtype=np.uint8)
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    for kind in LEVELS:
        for severity in range(1, 6):
            before = gradient.copy()
            state = np.random.get_state()
            output = degrade(gradient, kind, severity, 20261005)
            check(f'{kind}/s{severity}/shape-dtype', output.shape == gradient.shape and output.dtype == np.uint8)
            check(f'{kind}/s{severity}/input-preserved', np.array_equal(gradient, before))
            check(f'{kind}/s{severity}/reproducible', np.array_equal(output, degrade(gradient, kind, severity, 20261005)))
            after = np.random.get_state()
            check(f'{kind}/s{severity}/global-rng-preserved',
                  all(np.array_equal(a, b) for a, b in zip(state, after)))
            check(f'{kind}/s{severity}/new-array', not np.shares_memory(output, gradient))
    check('noise/different-seeds', not np.array_equal(degrade(flat, 'gaussian_noise', 3, 1), degrade(flat, 'gaussian_noise', 3, 2)))
    for kind, ascending in [('brightness_up', True), ('brightness_down', False)]:
        means = [float(degrade(flat, kind, severity, 1).mean()) for severity in range(1, 6)]
        check(f'{kind}/controlled-severity-response', all(a <= b if ascending else a >= b for a, b in zip(means, means[1:])))
    rms = [float(np.sqrt(np.mean((degrade(flat, 'gaussian_noise', s, 1).astype(float) - flat) ** 2))) for s in range(1, 6)]
    check('noise/controlled-rms-response', all(a < b for a, b in zip(rms, rms[1:])))
    checker = np.repeat((((xx // 4 + yy // 4) % 2) * 255).astype(np.uint8)[..., None], 3, axis=2)
    sharpness = []
    for severity in range(1, 6):
        blurred = degrade(checker, 'gaussian_blur', severity, 1).astype(float)
        sharpness.append(float(np.mean(np.abs(np.diff(blurred, axis=1)))))
    check('blur/controlled-edge-response', all(a >= b for a, b in zip(sharpness, sharpness[1:])))
    invalid = [(gradient.astype(float), 'gaussian_noise', 1, 1),
               (gradient[:10], 'gaussian_noise', 1, 1),
               (gradient, 'rain_overlay', 1, 1), (gradient, 'gaussian_blur', 0, 1),
               (gradient, 'gaussian_blur', True, 1), (gradient, 'gaussian_noise', 1, -1)]
    for index, args in enumerate(invalid):
        try:
            degrade(*args)
        except ValueError:
            checks.append(f'invalid-input-{index}/rejected')
        else:
            raise AssertionError(f'invalid-input-{index} accepted')
    rows = []
    for index in range(6):
        sid = f'fixture_{index:02d}'
        # Includes nonstandard dimensions and grayscale to test preparation.
        source = Image.fromarray(gradient if index % 2 == 0 else (gradient // 4))
        source = source.resize((800, 450))
        if index == 5:
            source = source.convert('L')
        path = source_dir / f'{sid}.png'
        source.save(path)
        rows.append(dict(schema_version='1.0.0', record_type='manifest', sample_id=sid,
                         parent_image_id=sid, sequence_id=sid, dataset='bdd100k',
                         source_split='train', image_path=f'data/raw/{sid}.png',
                         split=('train', 'val', 'test')[index % 3],
                         timeofday='daytime' if index % 2 == 0 else 'night',
                         weather='rainy' if index >= 4 else 'clear',
                         corruption='original', severity=0, seed=None, parameters={},
                         label=None, label_source='unlabeled', label_rule_version=None))
    manifest = fixture_root / 'fixture_originals.jsonl'
    manifest.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    (fixture_root / 'FIXTURE_ONLY.txt').write_text(
        'Artificial test images, NOT BDD100K data. dataset field only exercises the contract.\n', encoding='utf-8')
    first = generate_batch(manifest, 'repeat_a', repo_root=fixture_root)
    second = generate_batch(manifest, 'repeat_b', repo_root=fixture_root, sanity_count=0)
    check('batch/6-originals-120-synthetic-126-records', first['original_count'] == 6 and first['synthetic_count'] == 120 and first['record_count'] == 126)
    check('batch/png-hashes-reproduce', first['generated_png_sha256'] == second['generated_png_sha256'])
    generated = [json.loads(line) for line in (fixture_root / first['manifest_path']).read_text().splitlines()]
    check('batch/original-records-preserved', generated[:6] == rows)
    parents = {row['sample_id']: row for row in rows}
    for row in generated[6:]:
        parent = parents[row['parent_image_id']]
        check(f"{row['sample_id']}/metadata-labels", all(row[k] == parent[k] for k in
              ('dataset', 'sequence_id', 'source_split', 'split', 'timeofday', 'weather'))
              and row['label'] is None and row['label_source'] == 'unlabeled' and row['label_rule_version'] is None)
    # Compare saved samples to a fresh call on the prepared original. This
    # detects accidental cumulative application across severity/type loops.
    for row in generated[6:26]:
        prepared = prepare_image(fixture_root / parents[row['parent_image_id']]['image_path'])
        expected = degrade(prepared, row['corruption'], row['severity'], row['seed'])
        with Image.open(fixture_root / row['image_path']) as saved:
            check(f"{row['sample_id']}/direct-from-original", np.array_equal(np.array(saved), expected))
    one = generate_batch(manifest, 'smoke_limit', repo_root=fixture_root, limit=1, sanity_count=0)
    check('batch/limit-coverage', one['original_count'] == 1 and one['record_count'] == 21)
    reversed_manifest = fixture_root / 'reversed.jsonl'
    reversed_manifest.write_text(''.join(json.dumps(row) + '\n' for row in reversed(rows)), encoding='utf-8')
    reordered = generate_batch(reversed_manifest, 'reordered', repo_root=fixture_root, sanity_count=0)
    check('batch/order-independent-images', first['generated_png_sha256'] == reordered['generated_png_sha256'])
    bad_config = load_config()
    bad_config['levels']['brightness_down'][0] = 2
    bad_config_path = fixture_root / 'invalid_config.json'
    bad_config_path.write_text(json.dumps(bad_config), encoding='utf-8')
    try:
        generate_batch(manifest, 'bad_config', bad_config_path, repo_root=fixture_root)
    except ValueError:
        check('batch/invalid-config-no-output', not (fixture_root / 'data/generated/bad_config').exists())
    else:
        raise AssertionError('Invalid config accepted')
    try:
        generate_batch(manifest, 'repeat_a', repo_root=fixture_root)
    except FileExistsError:
        checks.append('batch/overwrite-rejected')
    else:
        raise AssertionError('Existing snapshot overwritten')
    for bad_run in ['../escape', '/absolute', 'with space']:
        try:
            generate_batch(manifest, bad_run, repo_root=fixture_root)
        except ValueError:
            checks.append('batch/unsafe-run-id-rejected')
        else:
            raise AssertionError('Unsafe run_id accepted')
    missing = dict(rows[0], image_path='data/raw/missing.png')
    missing_path = fixture_root / 'missing.jsonl'
    missing_path.write_text(json.dumps(missing) + '\n', encoding='utf-8')
    try:
        generate_batch(missing_path, 'missing_source', repo_root=fixture_root)
    except ValueError:
        check('batch/missing-source-no-output', not (fixture_root / 'data/generated/missing_source').exists())
    else:
        raise AssertionError('Missing source accepted')
    originals, _, _, ready = inspect_inputs(manifest, repo_root=fixture_root)
    check('preflight/full-input-count', ready['original_count'] == 6 and ready['expected_record_count'] == 126)
    selected = select_smoke(list(reversed(originals)), 3)
    check('smoke/representative-groups', all(any(predicate(row) for row in selected) for predicate in _smoke_groups().values()))
    check('smoke/stable-selection', selected == select_smoke(originals, 3))
    verification = verify_batch('repeat_a', fixture_root, replay=True)
    check('verify/pixel-replay', verification['replayed'] and verification['synthetic_count'] == 120)
    handoff = run_handoff(manifest, 'integration', repo_root=fixture_root, sanity_count=1)
    check('handoff/full-coverage', handoff['full_verification']['record_count'] == 126)
    check('handoff/smoke-replayed', handoff['smoke_verification']['replayed'])
    check('handoff/ready-for-visual-review', handoff['visual_review_required'] and handoff['status'] == 'ready_for_review')
    check('handoff/downstream-manifest-exists', (fixture_root / handoff['manifest_path']).is_file())
    check('handoff/markdown-exists', (fixture_root / 'data/generated/integration/handoff.md').is_file())
    # Tampering must be detected even when record schema still looks valid.
    tampered = fixture_root / generated[6]['image_path']
    original_bytes = tampered.read_bytes()
    tampered.write_bytes(original_bytes + b'tampered')
    try:
        verify_batch('repeat_a', fixture_root)
    except ValueError:
        checks.append('verify/tampered-png-rejected')
    else:
        raise AssertionError('Modified PNG accepted')
    finally:
        tampered.write_bytes(original_bytes)
    try:
        inspect_inputs('not_delivered.jsonl', repo_root=fixture_root)
    except ValueError as exc:
        check('preflight/missing-delivery-actionable', 'person 1' in str(exc))
    else:
        raise AssertionError('Missing delivery accepted')
    # Exercise the actual CLI on a fixture-root delivery.
    cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--preflight',
                          '--repo-root', str(fixture_root), '--manifest', str(manifest)],
                         capture_output=True, text=True)
    check('cli/preflight-success', cli.returncode == 0 and json.loads(cli.stdout)['status'] == 'ready')
    bad_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--preflight',
                              '--repo-root', str(fixture_root), '--manifest', 'absent.jsonl'],
                             capture_output=True, text=True)
    check('cli/missing-delivery-exit-2', bad_cli.returncode == 2 and 'person 1' in bad_cli.stderr)
    verified_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--verify',
                                  '--repo-root', str(fixture_root), '--run-id', 'integration'],
                                 capture_output=True, text=True)
    check('cli/verify-success', verified_cli.returncode == 0 and json.loads(verified_cli.stdout)['status'] == 'verified')
    handoff_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--handoff',
                                 '--repo-root', str(fixture_root), '--manifest', str(manifest),
                                 '--run-id', 'cli_integration', '--sanity-count', '1'],
                                capture_output=True, text=True)
    check('cli/handoff-success', handoff_cli.returncode == 0 and
          json.loads(handoff_cli.stdout)['full_verification']['record_count'] == 126)
    image_check = image_smoke('data/raw', 'image_api_check', repo_root=fixture_root, count=1)
    check('image-smoke/20-outputs', image_check['source_count'] == 1 and image_check['synthetic_count'] == 20)
    check('image-smoke/not-pipeline-manifest', not image_check['pipeline_ready'] and
          not (fixture_root / 'data/manifests/augmented_image_api_check.jsonl').exists())
    # A corrupt image must fail preflight without leaving a batch snapshot.
    corrupt_source = source_dir / 'corrupt.png'
    corrupt_source.write_bytes(b'not an image')
    corrupt_row = dict(rows[0], image_path='data/raw/corrupt.png')
    corrupt_manifest = fixture_root / 'corrupt.jsonl'
    corrupt_manifest.write_text(json.dumps(corrupt_row) + '\n', encoding='utf-8')
    try:
        generate_batch(corrupt_manifest, 'corrupt_source', repo_root=fixture_root)
    except ValueError as exc:
        check('preflight/corrupt-image-id-and-no-output', rows[0]['sample_id'] in str(exc)
              and not (fixture_root / 'data/generated/corrupt_source').exists())
    else:
        raise AssertionError('Corrupt source accepted')
    report = {'fixture_only': True, 'passed': len(checks), 'checks': checks,
              'artifacts': str(fixture_root), 'versions': first['versions']}
    (fixture_root / 'self_check.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest')
    parser.add_argument('--run-id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--self-check', action='store_true')
    mode.add_argument('--preflight', action='store_true', help='Validate the complete person-1 delivery; write nothing')
    mode.add_argument('--smoke', action='store_true', help='Select up to six representative day/night/rain originals')
    mode.add_argument('--handoff', action='store_true', help='Run preflight, representative smoke, full batch and verification')
    mode.add_argument('--verify', action='store_true', help='Read-only verification of an existing run')
    mode.add_argument('--image-smoke', action='store_true', help='Diagnostic API check on images without creating a contract manifest')
    parser.add_argument('--image-dir', help='With --image-smoke, directory of original images inside repo')
    parser.add_argument('--replay', action='store_true', help='With --verify, regenerate pixels to prove reproducibility')
    parser.add_argument('--repo-root', default=str(ROOT), help='Root used to resolve manifest image_path fields')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--sanity-count', type=int, default=6)
    args = parser.parse_args()
    if args.replay and not args.verify:
        parser.error('--replay requires --verify')
    if args.image_dir and not args.image_smoke:
        parser.error('--image-dir requires --image-smoke')
    if args.limit is not None and (args.handoff or args.preflight or args.verify):
        parser.error('--limit applies only to batch or --smoke; --handoff always runs the full delivery')
    try:
        if args.self_check:
            report = self_check()
            result = {key: report[key] for key in ('fixture_only', 'passed', 'artifacts', 'versions')}
        elif args.preflight:
            result = inspect_inputs(args.manifest, args.config, args.repo_root)[3]
        else:
            if not args.run_id:
                parser.error('--run-id is required to generate or verify a delivery')
            if args.image_smoke:
                if not args.image_dir:
                    parser.error('--image-smoke requires --image-dir')
                result = image_smoke(args.image_dir, args.run_id, args.config, args.repo_root,
                                     count=args.limit if args.limit is not None else 6)
            elif args.verify:
                result = verify_batch(args.run_id, args.repo_root, replay=args.replay)
            elif args.handoff:
                result = run_handoff(args.manifest, args.run_id, args.config, args.repo_root, args.sanity_count)
            else:
                manifest = args.manifest or 'data/manifests/originals.jsonl'
                summary = generate_batch(manifest, args.run_id, args.config, args.repo_root,
                                         limit=args.limit, sanity_count=args.sanity_count, smoke=args.smoke)
                result = {key: summary[key] for key in
                          ('status', 'run_id', 'original_count', 'synthetic_count', 'record_count', 'manifest_path')}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'Degradation error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
