"""Person 5 orchestrator; invoke owner adapters without changing their logic."""
import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import corruptions
from scripts import run_health
from src.evaluate import evaluate
from scripts.validate_contract import read_json


def prepare(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id):
        raise ValueError('Invalid run_id')
    for target in (ROOT / 'data/features' / args.run_id, ROOT / 'reports/runs' / args.run_id):
        if target.exists():
            raise FileExistsError(f'Snapshot exists: {target}; choose a new run_id')
    # Validate reference provenance before expensive image generation.
    originals, _, _, delivery = corruptions.inspect_inputs(args.manifest, args.corruption_config, repo_root=ROOT)
    from src import baseline
    ids_file = read_json(args.reference_ids)
    ids = baseline._select_reference_ids(ids_file)
    metadata = baseline._metadata_index(originals)
    baseline._validate_reference_source(ids_file, metadata)
    for sid in ids:
        if sid not in metadata or metadata[sid]['split'] != 'train' or metadata[sid]['corruption'] != 'original':
            raise ValueError(f'Invalid train reference: {sid}')
    if isinstance(ids_file, dict):
        for mode in ('day', 'night'):
            if any(baseline.TIME_MODES.get(metadata[sid]['timeofday']) != mode for sid in ids_file[mode]):
                raise ValueError(f'Reference group does not match source metadata: {mode}')
    if not {'train', 'val', 'test'} <= {r['split'] for r in originals}:
        raise ValueError('Full integration requires train, val and test originals')
    print(json.dumps({'stage': 'data_ready', **delivery}), flush=True)
    generated = corruptions.generate_batch(args.manifest, args.run_id, args.corruption_config, repo_root=ROOT)
    manifest = str(ROOT / generated['manifest_path'])
    run_health.prepare(SimpleNamespace(manifest=manifest, reference_ids=args.reference_ids,
                                      config=args.health_config, features=None, run_id=args.run_id))
    folder = ROOT / 'data/features' / args.run_id
    evaluate(manifest, folder / 'features.jsonl', folder / 'health_val.jsonl', folder / 'references_draft.json',
             ROOT / 'reports/runs' / args.run_id / 'validation', split='val', data_kind=args.data_kind,
             extra_inputs=(args.reference_ids, args.corruption_config, args.health_config))
    print('Review validation report and reference contact sheets, then finalize with review notes.', flush=True)


def finalize(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id):
        raise ValueError('Invalid run_id')
    folder = ROOT / 'data/features' / args.run_id
    # Owner 2 verifies source hashes, generated coverage, seeds and parameters.
    corruptions.verify_batch(args.run_id, repo_root=ROOT)
    final_report = ROOT / 'reports/runs' / args.run_id
    if (final_report / 'report.md').exists() or (final_report / 'evaluation').exists():
        raise FileExistsError('Final report exists')
    if not (folder / 'references.json').exists():
        run_health.finalize(SimpleNamespace(run_dir=str(folder), validation_note=args.validation_note,
                                           reference_review_note=args.reference_review_note))
    state = read_json(folder / 'state.json')
    for name in ('manifest', 'features', 'reference_ids'):
        if run_health.digest(state[name]) != state[name + '_sha256']:
            raise ValueError(f'{name} changed since validation')
    result = evaluate(state['manifest'], state['features'], folder / 'health_scores.jsonl', folder / 'references.json',
                      final_report, data_kind=args.data_kind,
                      extra_inputs=(state['reference_ids'], ROOT / 'data/generated' / args.run_id / 'run_summary.json'))
    print(json.dumps({'stage': 'evaluation_complete', 'frames': result['scored_frames'], 'report': str(final_report / 'report.md')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    draft = commands.add_parser('prepare')
    draft.add_argument('--manifest', default=str(ROOT / 'data/manifests/originals.jsonl'))
    draft.add_argument('--reference-ids', default=str(ROOT / 'data/manifests/reference_ids.json'))
    draft.add_argument('--corruption-config', default=str(ROOT / 'configs/corruptions.json'))
    draft.add_argument('--health-config', default=str(ROOT / 'configs/health.json'))
    final = commands.add_parser('finalize')
    final.add_argument('--validation-note', required=True)
    final.add_argument('--reference-review-note', required=True)
    for command in (draft, final):
        command.add_argument('--run-id', required=True)
        command.add_argument('--data-kind', choices=('real', 'fixture'), default='real')
    args = parser.parse_args()
    try:
        (prepare if args.command == 'prepare' else finalize)(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'Integration error: {exc}\n')


if __name__ == '__main__':
    main()
