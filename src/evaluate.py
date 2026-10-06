"""Person 5 evaluation: ID joins, paired responses, plots and reproducibility."""
import argparse
import csv
import importlib.metadata
import json
import math
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_contract import read_json, read_jsonl
from scripts.validate_health import validate_health
from scripts.run_health import digest

CODE_NAMES = ('src/run_pipeline.py', 'src/evaluate.py', 'src/corruptions.py', 'src/features.py',
              'src/baseline.py', 'scripts/validate_health.py', 'scripts/run_health.py',
              'scripts/validate_contract.py', 'schemas/heuristic_health.schema.json', 'configs/contract.json')
SOURCE_SNAPSHOT = {name: digest(ROOT / name) for name in CODE_NAMES}


def contact_sheet(path, selected, metadata, scores):
    from PIL import Image, ImageDraw
    images = {r['sample_id']: r for r in metadata}
    width, height, columns = 320, 250, 4
    sheet = Image.new('RGB', (columns * width, math.ceil(len(selected) / columns) * height), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, sid in enumerate(selected):
        x, y = index % columns * width, index // columns * height
        with Image.open(ROOT / images[sid]['image_path']) as source:
            sheet.paste(source.convert('RGB').resize((width, 180), Image.Resampling.BILINEAR), (x, y))
        for line, part in enumerate(textwrap.wrap(sid, width=40)[:2]):
            draw.text((x + 3, y + 183 + 13 * line), part, fill='black')
        row, score = images[sid], scores[sid]
        draw.text((x + 3, y + 212), f"{row['split']} / {row['timeofday']} / s{row['severity']}", fill='black')
        draw.text((x + 3, y + 228), f"fixed={score['health_fixed']:.1f} adaptive={score['health_adaptive']:.1f}", fill='black')
    sheet.save(path)


def summarize(manifest, scores):
    images = {r['sample_id']: r for r in manifest}
    health = {r['sample_id']: r for r in scores}
    groups = defaultdict(list)
    for sid, row in health.items():
        image = images[sid]
        groups[(image['split'], image['timeofday'], image['weather'], image['corruption'], image['severity'])].append(row)
    result = []
    for keys, rows in sorted(groups.items()):
        value = dict(zip(('split', 'timeofday', 'weather', 'corruption', 'severity'), keys))
        value['count'] = len(rows)
        for mode in ('fixed', 'adaptive'):
            values = [r['health_' + mode] for r in rows]
            for name, fn in (('mean', mean), ('median', median), ('std', pstdev), ('min', min), ('max', max)):
                value[f'{mode}_{name}'] = fn(values)
        value['adaptive_minus_fixed_mean'] = mean(r['health_adaptive'] - r['health_fixed'] for r in rows)
        for mode in ('fixed', 'adaptive'):
            value[f'{mode}_paired_delta_mean'] = mean(r['health_' + mode] - health[images[r['sample_id']]['parent_image_id']]['health_' + mode] for r in rows)
        value.update(Counter(r['action'] for r in rows))
        for action in ('normal', 'down_weight', 'strong_down_weight'):
            value.setdefault(action, 0)
        result.append(value)
    return result


def score_increases(manifest, scores):
    images = {r['sample_id']: r for r in manifest}
    health = {r['sample_id']: r for r in scores}
    variants = defaultdict(list)
    for image in manifest:
        variants[(image['parent_image_id'], image['corruption'])].append(image)
    result = []
    for sid, score in health.items():
        image = images[sid]
        if image['corruption'] == 'original':
            continue
        for mode in ('fixed', 'adaptive'):
            previous = [r for r in variants[(image['parent_image_id'], image['corruption'])]
                        if r['severity'] < image['severity'] and r['sample_id'] in health]
            prior = max(previous, key=lambda r: r['severity']) if previous else images[image['parent_image_id']]
            for comparison, reference in (('parent', images[image['parent_image_id']]), ('previous_severity', prior)):
                delta = score['health_' + mode] - health[reference['sample_id']]['health_' + mode]
                if delta > 1e-7:
                    result.append({'sample_id': sid, 'reference_id': reference['sample_id'], 'mode': mode,
                                   'comparison': comparison, 'delta': delta, 'corruption': image['corruption'],
                                   'severity': image['severity'], 'split': image['split']})
    return result


def write_csv(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate(manifest_path, features_path, health_path, references_path, output, split=None, data_kind='real', extra_inputs=()):
    if ROOT == Path(__file__).resolve().parents[1]:
        for name, expected_hash in SOURCE_SNAPSHOT.items():
            if digest(ROOT / name) != expected_hash:
                raise ValueError(f'Code changed after import: {name}; start a fresh evaluation process')
    paths = [Path(p).resolve() for p in (manifest_path, features_path, health_path, references_path)]
    hashes = {str(p): digest(p) for p in paths}
    manifest, features, scores = (read_jsonl(p) for p in paths[:3])
    references = read_json(paths[3])
    validation = validate_health(manifest, features, scores, references, split=split)
    output = Path(output)
    if (output / 'report.md').exists() or (output / 'evaluation').exists():
        raise FileExistsError(f'Evaluation snapshot exists: {output}')
    output.mkdir(parents=True, exist_ok=True)
    evaluation = output / 'evaluation'
    evaluation.mkdir()
    selected = {r['sample_id'] for r in scores}
    images = [r for r in manifest if r['sample_id'] in selected]
    summary = summarize(images, scores)
    increases = score_increases(images, scores)
    write_csv(evaluation / 'groups.csv', summary)
    write_csv(evaluation / 'score_increases.csv', increases)
    health = {r['sample_id']: r for r in scores}
    joined = [{**{k: r[k] for k in ('sample_id', 'parent_image_id', 'split', 'timeofday', 'weather', 'corruption', 'severity')},
               **{k: s[k] for k in ('health_fixed', 'health_adaptive', 'camera_weight', 'action')}}
              for r in images for s in [health[r['sample_id']]]]
    write_csv(evaluation / 'samples.csv', joined)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    curves = defaultdict(list)
    health = {r['sample_id']: r for r in scores}
    for r in images:
        if r['corruption'] != 'original':
            curves[(r['split'], r['timeofday'], r['corruption'], r['severity'])].append(health[r['sample_id']])
    curve_rows = []
    for (lab_split, time, kind, severity), values in sorted(curves.items()):
        curve_rows.append({'split': lab_split, 'timeofday': time, 'corruption': kind, 'severity': severity,
                           'count': len(values), 'fixed_mean': mean(v['health_fixed'] for v in values),
                           'adaptive_mean': mean(v['health_adaptive'] for v in values)})
    for lab_split, time, kind in sorted({key[:3] for key in curves}):
        parent_values = [health[r['sample_id']] for r in images if r['corruption'] == 'original'
                         and r['split'] == lab_split and r['timeofday'] == time]
        curve_rows.append({'split': lab_split, 'timeofday': time, 'corruption': kind, 'severity': 0,
                           'count': len(parent_values), 'fixed_mean': mean(v['health_fixed'] for v in parent_values),
                           'adaptive_mean': mean(v['health_adaptive'] for v in parent_values)})
    curve_rows.sort(key=lambda r: (r['split'], r['timeofday'], r['corruption'], r['severity']))
    write_csv(evaluation / 'curves.csv', curve_rows)
    kinds = sorted({r['corruption'] for r in curve_rows})
    if kinds:
        splits = sorted({r['split'] for r in curve_rows})
        fig, axes = plt.subplots(len(splits), len(kinds), figsize=(5 * len(kinds), 4 * len(splits)), squeeze=False)
        for row_index, lab_split in enumerate(splits):
            for ax, kind in zip(axes[row_index], kinds):
                times = sorted({r['timeofday'] for r in curve_rows if r['split'] == lab_split})
                for time, color in zip(times, ('tab:blue', 'tab:orange', 'tab:green', 'tab:red')):
                    values = [r for r in curve_rows if (r['corruption'], r['split'], r['timeofday']) == (kind, lab_split, time)]
                    for mode, style in (('fixed', '--'), ('adaptive', '-')):
                        ax.plot([r['severity'] for r in values], [r[mode + '_mean'] for r in values], style,
                                color=color, label=f'{time}/{mode}', linewidth=1.5)
                ax.set(title=f'{lab_split}: {kind}', xlabel='Synthetic severity (proxy)', ylabel='Mean health', ylim=(0, 101))
                ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(evaluation / 'severity_curves.png', dpi=150)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for mode in ('fixed', 'adaptive'):
        ax.hist([r['health_' + mode] for r in scores], bins=20, range=(0, 100), alpha=.5, label=mode)
    ax.set(xlabel='Heuristic health', ylabel='Frame count', title=f'{data_kind}: selected split {split or "all"}')
    ax.legend()
    fig.tight_layout()
    fig.savefig(evaluation / 'score_distribution.png', dpi=150)
    plt.close(fig)
    originals = [r for r in images if r['corruption'] == 'original']
    selections = {
        'lowest_originals': sorted(originals, key=lambda r: health[r['sample_id']]['health_adaptive'])[:8],
        'real_rain': sorted((r for r in originals if r['weather'] == 'rainy'), key=lambda r: health[r['sample_id']]['health_adaptive'])[:8],
        'noise_increases': [next(r for r in images if r['sample_id'] == sid) for sid in
                            list(dict.fromkeys(r['sample_id'] for r in increases if r['corruption'] == 'gaussian_noise'))[:8]],
    }
    noisy = selections['noise_increases'][:4]
    paired_noise = []
    image_index = {r['sample_id']: r for r in images}
    for row in noisy:
        paired_noise.extend([image_index[row['parent_image_id']], row])
    selections['noise_increases'] = paired_noise
    for name, rows in selections.items():
        if rows:
            contact_sheet(evaluation / (name + '.png'), [r['sample_id'] for r in rows], manifest, health)
    # One parent and its twenty variants for visual degradation sanity review.
    if originals:
        parent = originals[0]['sample_id']
        paired = sorted((r for r in images if r['parent_image_id'] == parent),
                        key=lambda r: (r['corruption'] != 'original', r['corruption'], r['severity']))
        contact_sheet(evaluation / 'original_degraded.png', [r['sample_id'] for r in paired], manifest, health)
    provenance = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                  'data_kind': data_kind, 'validation': validation, 'input_sha256': hashes,
                  'extra_input_sha256': {str(Path(p).resolve()): digest(p) for p in extra_inputs},
                  'module_sha256': {name: digest(ROOT / name) for name in CODE_NAMES},
                  'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'git_status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
                  'versions': {name: importlib.metadata.version(name) for name in ('numpy', 'Pillow', 'jsonschema', 'matplotlib')},
                  'python': sys.version, 'command_argv': sys.argv,
                  'reference_sha256': references['reference_sha256'], 'config_sha256': references['config_sha256'],
                  'synthetic_seed_count': len({r['seed'] for r in images if r['corruption'] != 'original'}),
                  'scored_frames': len(scores), 'split_counts': dict(Counter(r['split'] for r in images))}
    for p in paths:
        if digest(p) != hashes[str(p)]:
            raise ValueError(f'Input changed during evaluation: {p}')
    (evaluation / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    totals = []
    for lab_split in sorted({r['split'] for r in images}):
        for kind in ('original', 'synthetic'):
            values = [health[r['sample_id']] for r in images if r['split'] == lab_split
                      and (r['corruption'] == 'original') == (kind == 'original')]
            if values:
                totals.append({'split': lab_split, 'source': kind, 'count': len(values),
                               'fixed_mean': mean(v['health_fixed'] for v in values),
                               'adaptive_mean': mean(v['health_adaptive'] for v in values),
                               'adaptive_median': median(v['health_adaptive'] for v in values),
                               'adaptive_std': pstdev(v['health_adaptive'] for v in values)})
    write_csv(evaluation / 'split_totals.csv', totals)
    lines = ['# Báo cáo tích hợp camera health', '', f'Nguồn: **{data_kind}**. Thực chạy {len(scores)} frames; split={split or "all"}.',
             f'Coverage: {validation}. Original: {len(originals)}; synthetic: {len(images)-len(originals)}.',
             f'Config frozen: {references["config"]["frozen"]}; policy: `{references["config"]["policy_id"]}`.', '',
             '| Split | Source | N | Fixed mean | Adaptive mean | Adaptive median | Adaptive std |',
             '|---|---|---:|---:|---:|---:|---:|']
    for r in totals:
        lines.append('| {split} | {source} | {count} | {fixed_mean:.2f} | {adaptive_mean:.2f} | {adaptive_median:.2f} | {adaptive_std:.2f} |'.format(**r))
    lines += ['',
             '| Split | Time | Weather | Corruption | Severity | N | Fixed mean | Adaptive mean | Adaptive std | Paired delta |',
             '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append('| {split} | {timeofday} | {weather} | {corruption} | {severity} | {count} | {fixed_mean:.2f} | {adaptive_mean:.2f} | {adaptive_std:.2f} | {adaptive_paired_delta_mean:.2f} |'.format(**r))
    lines += ['', f'Score tăng: {len(increases)} findings, đếm riêng fixed/adaptive và parent/previous severity; xem CSV để tránh coi là số frame độc lập.',
              f'Mưa thật: {sum(r["weather"] == "rainy" for r in originals)} originals; metadata weather không phải quality label.',
              'Contact sheets trong evaluation là ảnh cần review, không tự động chứng minh false alarm hoặc chất lượng reference.',
              '', '![Phân bố](evaluation/score_distribution.png)', '']
    if kinds:
        lines.append('![Severity](evaluation/severity_curves.png)')
    for name, rows in selections.items():
        if rows:
            lines += ['', f'![{name}](evaluation/{name}.png)']
    lines += ['', 'Giới hạn: chưa train model; chưa có nhãn quality để tính F1/false alarm, chưa chạy detector/AP/fusion; health chưa kiểm chứng ADAS.',
              'Synthetic severity là proxy. Noise/texture có thể làm sharpness/entropy tăng; original có thể vốn xấu. Không loại ngoại lệ khỏi report.',
              'Bảng là số tự đo của run; không dùng fixture hoặc paper claims làm kết quả BDD100K.',
              'Reproduction: xem evaluation/provenance.json (argv, hashes, versions, git dirty state) và config snapshot trong references.json.',
              '', 'Pitch: pipeline đo bảy feature, tham chiếu train-only, so sánh fixed/day-night sau val review và config freeze; báo coverage và failure trước khi diễn giải ứng dụng.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'features', 'health', 'references', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--data-kind', choices=('real', 'fixture'), default='real')
    parser.add_argument('--split', choices=('train', 'val', 'test'), help='Exact coverage of this scoring split')
    args = parser.parse_args()
    evaluate(args.manifest, args.features, args.health, args.references, args.output, split=args.split, data_kind=args.data_kind)


if __name__ == '__main__':
    main()
