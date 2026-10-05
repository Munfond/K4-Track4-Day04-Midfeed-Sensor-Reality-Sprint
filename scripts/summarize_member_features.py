"""Person 5: derive report evidence from the existing immutable feature bundle."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_contract import read_json, read_jsonl, validate_bundle


def summarize(run_id):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run ID')
    manifest_path = ROOT / 'data/manifests' / f'augmented_{run_id}.jsonl'
    feature_path = ROOT / 'data/features' / run_id / 'features.jsonl'
    metadata, features = read_jsonl(manifest_path), read_jsonl(feature_path)
    coverage = validate_bundle(metadata, features)
    index = {r['sample_id']: r['features'] for r in features}
    config_path = ROOT / 'data/generated' / run_id / 'config_snapshot.json'
    gains = [1.0] + read_json(config_path)['levels']['brightness_down']
    result = []
    selected_ids = {}
    for severity, gain in enumerate(gains):
        rows = [r for r in metadata if r['split'] == 'test' and r['timeofday'] == 'daytime'
                and r['severity'] == severity and r['corruption'] == ('original' if severity == 0 else 'brightness_down')]
        if not rows:
            raise ValueError(f'Missing benchmark group: severity {severity}')
        parents = {r['parent_image_id'] for r in rows}
        if severity == 0:
            baseline_parents = parents
        elif parents != baseline_parents:
            raise ValueError('Benchmark severity groups do not share original parents')
        value = {'split': 'test', 'timeofday': 'daytime', 'corruption': 'original' if severity == 0 else 'brightness_down',
                 'severity': severity, 'gain': gain, 'count': len(rows)}
        for key in index[rows[0]['sample_id']]:
            value[key + '_mean'] = mean(index[r['sample_id']][key] for r in rows)
        value['dark_ratio_pct_mean'] = 100 * value['dark_ratio_mean']
        result.append(value)
        selected_ids[str(severity)] = sorted(r['sample_id'] for r in rows)
    output = ROOT / 'reports/runs' / run_id / 'evaluation'
    target = output / 'member3_feature_summary.csv'
    with target.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = {'run_id': run_id, 'data_kind': 'real_originals_and_synthetic_derivatives',
                  'scope': 'test / metadata daytime / same original parents / brightness_down; means of per-frame features',
                  'coverage': coverage, 'selected_sample_ids': selected_ids,
                  'units': {'median_luminance_mean': 'mean of per-frame median grayscale intensity, 0..255',
                            'dark_ratio_pct_mean': 'mean fraction of Y<=5 pixels multiplied by 100, percent',
                            'log_laplacian_variance_mean': 'dimensionless, natural log', 'entropy_mean': 'bits'},
                  'input_sha256': {str(p.relative_to(ROOT)): digest(p) for p in (manifest_path, feature_path, config_path)},
                  'script_sha256': digest(Path(__file__)), 'csv_sha256': digest(target), 'command_argv': sys.argv}
    (output / 'member3_feature_summary_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    summarize(parser.parse_args().run_id)
