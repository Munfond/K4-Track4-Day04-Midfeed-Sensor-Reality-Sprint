"""Person 1: select a BDD100K subset, check images, split by sequence, export originals manifest + reference IDs.

Usage (from repo root):
    python src/prepare_data.py --config configs/data.json [--download] [--contact-sheet PATH]
"""
import argparse
import ast
import hashlib
import json
import random
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = '1.0.0'
PREPARED_SIZE = (640, 360)
SPLITS = ('train', 'val', 'test')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def _field(value):
    """FiftyOne samples.json stores nested docs as Python-literal strings."""
    if isinstance(value, str) and value.startswith('{'):
        value = ast.literal_eval(value)
    return value.get('label') if isinstance(value, dict) else value


def load_metadata(path, fmt):
    """Return {image_name: {'timeofday', 'weather'}} from FiftyOne or official BDD100K label JSON."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    meta = {}
    if fmt == 'fiftyone':
        for s in data['samples']:
            name = Path(s['filepath']).name
            meta[name] = {'timeofday': _field(s.get('timeofday')) or 'undefined',
                          'weather': _field(s.get('weather')) or 'undefined'}
    elif fmt == 'bdd100k':
        for s in data:
            attrs = s.get('attributes') or {}
            meta[s['name']] = {'timeofday': attrs.get('timeofday', 'undefined'),
                               'weather': attrs.get('weather', 'undefined')}
    else:
        raise ValueError(f'Unknown metadata_format: {fmt}')
    return meta


def sequence_of(name, mode):
    stem = Path(name).stem
    # BDD100K names are <video-prefix>-<suffix>; frames sharing the prefix are grouped conservatively.
    return stem.split('-')[0] if mode == 'name_prefix' else stem


def prepared_luma(img):
    rgb = img.convert('RGB').resize(PREPARED_SIZE, Image.Resampling.BILINEAR)
    return np.asarray(rgb.convert('L'), dtype=np.float64)


def quality_stats(y):
    lap = (y[:-2, 1:-1] + y[2:, 1:-1] + y[1:-1, :-2] + y[1:-1, 2:] - 4 * y[1:-1, 1:-1])
    return {'median_luminance': float(np.median(y)),
            'dark_ratio': float(np.mean(y <= 5)),
            'saturation_ratio': float(np.mean(y >= 250)),
            'log_laplacian_variance': float(np.log1p(lap.var()))}


def check_image(path, expected_size):
    """Fail-soft image check; returns (stats, reason)."""
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            if img.format != 'JPEG' and path.suffix.lower() in ('.jpg', '.jpeg'):
                return None, f'format {img.format}'
            if list(img.size) != list(expected_size):
                return None, f'size {img.size}'
            if img.mode not in ('RGB', 'L', 'P', 'RGBA', 'CMYK', 'YCbCr'):
                return None, f'mode {img.mode}'
            return quality_stats(prepared_luma(img)), None
    except Exception as exc:  # noqa: BLE001 - report any decode failure by ID
        return None, f'unreadable: {exc}'


def download(name, base_url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + '.part')
    urllib.request.urlretrieve(f'{base_url.rstrip("/")}/{name}', tmp)
    tmp.replace(dst)


def select(meta, cfg, image_dir, allow_download, log):
    """Pick `count` valid, unique images per group in deterministic seeded order."""
    seed, src = cfg['seed'], cfg['source']
    taken, hashes, rejected = {}, {}, []
    for group, rule in cfg['groups'].items():
        candidates = sorted(n for n, m in meta.items()
                            if m['timeofday'] in rule['timeofday'] and m['weather'] in rule['weather'] and n not in taken)
        random.Random(f'{seed}:{group}').shuffle(candidates)
        picked = 0
        for name in candidates:
            if picked == rule['count']:
                break
            path = image_dir / name
            if not path.is_file():
                if not allow_download:
                    rejected.append((name, 'missing file')); continue
                try:
                    download(name, src['download_base_url'], path)
                except Exception as exc:  # noqa: BLE001
                    rejected.append((name, f'download failed: {exc}')); continue
            stats, reason = check_image(path, cfg['expected_size'])
            if reason is None:
                digest = sha256_file(path)
                if digest in hashes:
                    reason = f'duplicate of {hashes[digest]}'
            if reason:
                rejected.append((name, reason)); continue
            hashes[digest] = name
            taken[name] = {'group': group, 'stats': stats, 'sha256': digest, **meta[name]}
            picked += 1
        if picked < rule['count']:
            log(f'WARNING: group {group} has only {picked}/{rule["count"]} valid images')
    return taken, rejected


def assign_splits(taken, cfg):
    """Sequence-level split, stratified by each sequence's majority group."""
    seqs = defaultdict(list)
    for name, row in taken.items():
        seqs[sequence_of(name, cfg['sequence_grouping'])].append(name)
    by_group = defaultdict(list)
    for seq, names in seqs.items():
        major = Counter(taken[n]['group'] for n in names).most_common(1)[0][0]
        by_group[major].append(seq)
    ratios = cfg['split_ratios']
    seq_split = {}
    for group in sorted(by_group):
        group_seqs = sorted(by_group[group])
        random.Random(f'{cfg["seed"]}:split:{group}').shuffle(group_seqs)
        total = sum(len(seqs[s]) for s in group_seqs)
        counts = dict.fromkeys(SPLITS, 0)
        for seq in group_seqs:
            deficit = {s: ratios[s] * total - counts[s] for s in SPLITS}
            split = max(SPLITS, key=lambda s: (deficit[s], -SPLITS.index(s)))
            seq_split[seq] = split
            counts[split] += len(seqs[seq])
    return {n: seq_split[sequence_of(n, cfg['sequence_grouping'])] for n in taken}


def manifest_rows(taken, splits, cfg, image_dir):
    rows = []
    for name in sorted(taken):
        row = taken[name]
        sid = Path(name).stem
        rows.append({
            'schema_version': SCHEMA_VERSION, 'record_type': 'manifest', 'sample_id': sid,
            'parent_image_id': sid, 'sequence_id': sequence_of(name, cfg['sequence_grouping']),
            'dataset': 'bdd100k', 'source_split': cfg['source']['source_split'],
            'image_path': rel(image_dir / name), 'split': splits[name],
            'timeofday': row['timeofday'], 'weather': row['weather'],
            'corruption': 'original', 'severity': 0, 'seed': None, 'parameters': {},
            'label': None, 'label_source': 'unlabeled', 'label_rule_version': None})
    return rows


def pick_references(taken, splits, cfg):
    ref_cfg = cfg['reference']
    refs, screened = {}, {}
    for mode, group in ref_cfg['groups'].items():
        qc = ref_cfg['qc'][mode]
        lo, hi = qc['median_luminance']
        ok = [n for n, r in taken.items()
              if r['group'] == group and splits[n] == 'train'
              and lo <= r['stats']['median_luminance'] <= hi
              and r['stats']['dark_ratio'] <= qc['dark_ratio_max']
              and r['stats']['saturation_ratio'] <= qc['saturation_ratio_max']
              and r['stats']['log_laplacian_variance'] >= qc['log_laplacian_variance_min']]
        # Prefer the most typical frames: closest to the group median sharpness/luminance.
        med = {k: float(np.median([taken[n]['stats'][k] for n in ok])) for k in ('median_luminance', 'log_laplacian_variance')} if ok else {}
        ok.sort(key=lambda n: (abs(taken[n]['stats']['median_luminance'] - med['median_luminance']) / 255
                               + abs(taken[n]['stats']['log_laplacian_variance'] - med['log_laplacian_variance']) / 10, n))
        refs[mode] = [Path(n).stem for n in ok[:ref_cfg['per_mode']]]
        screened[mode] = len(ok)
        if len(refs[mode]) < ref_cfg['per_mode']:
            raise SystemExit(f'Not enough QC-passing train references for {mode}: {len(refs[mode])}')
    return refs, screened


def contact_sheet(names, image_dir, out, cols=5):
    tw, th = 256, 144
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * tw, rows * th))
    for i, name in enumerate(names):
        with Image.open(image_dir / name) as img:
            sheet.paste(img.convert('RGB').resize((tw, th), Image.Resampling.BILINEAR), ((i % cols) * tw, (i // cols) * th))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default='configs/data.json')
    ap.add_argument('--download', action='store_true', help='Fetch missing selected images from download_base_url')
    ap.add_argument('--contact-sheet', help='Optional PNG of reference images for visual review')
    args = ap.parse_args()

    config_path = ROOT / args.config
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    src = cfg['source']
    image_dir = ROOT / src['image_dir']
    log = lambda msg: print(msg, file=sys.stderr)

    meta = load_metadata(ROOT / src['metadata_path'], src['metadata_format'])
    log(f'Metadata: {len(meta)} images')
    taken, rejected = select(meta, cfg, image_dir, args.download, log)
    splits = assign_splits(taken, cfg)
    rows = manifest_rows(taken, splits, cfg, image_dir)

    out_manifest = ROOT / cfg['output']['manifest']
    write_jsonl(out_manifest, rows)
    refs, screened = pick_references(taken, splits, cfg)
    for mode, ids in refs.items():
        assert all(splits[i + '.jpg'] == 'train' for i in ids)
    reference = {
        'data_version': cfg['data_version'],
        'manifest_path': rel(out_manifest), 'manifest_sha256': sha256_file(out_manifest),
        'config_path': rel(config_path), 'config_sha256': sha256_file(config_path),
        'selection': 'train originals passing QC thresholds, closest to group median luminance/sharpness',
        'qc_thresholds': cfg['reference']['qc'], 'qc_passing_train_candidates': screened,
        'visual_review': 'pending',
        'day': refs['day'], 'night': refs['night'],
        'fixed': sorted(refs['day'] + refs['night']),
    }
    out_refs = ROOT / cfg['output']['reference_ids']
    out_refs.write_text(json.dumps(reference, indent=2) + '\n', encoding='utf-8')
    if args.contact_sheet:
        contact_sheet([i + '.jpg' for i in refs['day'] + refs['night']], image_dir, Path(args.contact_sheet))

    dist = Counter((taken[r['sample_id'] + '.jpg']['group'], r['split']) for r in rows)
    print(json.dumps({
        'manifest': rel(out_manifest), 'records': len(rows),
        'sequences': len({r['sequence_id'] for r in rows}),
        'group_split': {g: {s: dist[(g, s)] for s in SPLITS} for g in cfg['groups']},
        'split_total': dict(Counter(r['split'] for r in rows)),
        'timeofday_weather': {f'{k[0]}/{k[1]}': v for k, v in sorted(Counter((r['timeofday'], r['weather']) for r in rows).items())},
        'rejected': len(rejected), 'rejected_reasons': dict(Counter(r.split(':')[0] for _, r in rejected)),
        'references': {k: len(v) for k, v in refs.items() if k != 'fixed'},
    }, indent=2))


if __name__ == '__main__':
    main()
