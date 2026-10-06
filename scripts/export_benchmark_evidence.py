"""Publish selected existing benchmark artifacts; never rerun or alter the run."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 'integration_20261006_01'
RUN = ROOT / 'reports/runs' / RUN_ID
DEST = ROOT / 'docs/evidence' / RUN_ID


def sha(data):
    return hashlib.sha256(data).hexdigest()


def portable(value):
    if isinstance(value, dict):
        return {portable(k): portable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [portable(v) for v in value]
    if isinstance(value, str):
        # Preserve commands, numbers, hashes and historical git state.
        for prefix in (str(ROOT) + '\\', ROOT.as_posix() + '/'):
            value = value.replace(prefix, '')
        return value
    return value


def selected():
    mapping = {}
    def add(src, dst):
        mapping[ROOT / src] = DEST / dst
    for name in ('curves.csv', 'groups.csv', 'samples.csv', 'split_totals.csv',
                 'score_increases.csv', 'member3_feature_summary.csv',
                 'severity_curves.png', 'score_distribution.png', 'original_degraded.png',
                 'provenance.json', 'selected_failure_explanation.json', 'review_findings.json',
                 'member3_feature_summary_provenance.json'):
        add(f'reports/runs/{RUN_ID}/evaluation/{name}', f'evaluation/{name}')
    for name in ('summary.json', 'phase_1.json', 'phase_2.json', 'phase_3.json',
                 'phase_4.json', 'phase_5.json', 'pixel_replay.json', 'feature_replay.json', 'report.md'):
        add(f'reports/runs/{RUN_ID}/evidence_20261006_01/{name}', f'audit/{name}')
    for name in ('features.jsonl', 'health_scores.jsonl', 'health_val.jsonl',
                 'references.json', 'references_draft.json', 'handoff.json'):
        add(f'data/features/{RUN_ID}/{name}', f'snapshots/{name}')
    for name in ('originals.jsonl', 'reference_ids.json', f'augmented_{RUN_ID}.jsonl'):
        add(f'data/manifests/{name}', f'snapshots/{name}')
    for name in ('run_summary.json', 'config_snapshot.json'):
        add(f'data/generated/{RUN_ID}/{name}', f'generation/{name}')
    add('data/raw/bdd100k/images/val/b329fe7d-f06455d3.jpg', 'images/b329fe7d-f06455d3.jpg')
    add(f'data/generated/{RUN_ID}/sanity/b1d22449-15fb948f.png', 'images/degradation_sanity.png')
    return mapping


def redirect_links(path, mapping):
    content = path.read_text(encoding='utf-8')
    def replace(match):
        label, target = match.group(1), match.group(2)
        if '://' in target or target.startswith('#'):
            return match.group(0)
        source = (path.parent / target).resolve()
        if source in mapping:
            dest = mapping[source]
            rel = os.path.relpath(dest, path.parent).replace('\\', '/')
            return f'[{label}]({rel})'
        if source.is_relative_to(ROOT / 'data') or source.is_relative_to(ROOT / 'reports/runs'):
            # Do not leave clickable GitHub links pointing to excluded artifacts.
            return f'{label} (artifact local: `{source.relative_to(ROOT).as_posix()}`)'
        return match.group(0)
    content = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', replace, content)
    return content


def export(update_docs=False):
    mapping = selected()
    for source in mapping:
        if not source.is_file():
            raise FileNotFoundError(source)
    records = []
    for source, target in mapping.items():
        original = source.read_bytes()
        published = original
        if source.suffix == '.json':
            obj = json.loads(original)
            converted = portable(obj)
            if obj != converted:
                published = (json.dumps(converted, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(published)
        records.append({'source': source.relative_to(ROOT).as_posix(),
                        'published': target.relative_to(DEST).as_posix(),
                        'source_sha256': sha(original), 'published_sha256': sha(published),
                        'byte_identical': original == published, 'bytes': len(published),
                        'transformation': 'none' if original == published else 'repository-root prefix removed from JSON strings/keys; JSON reserialized'})
    index = {'run_id': RUN_ID, 'kind': 'selected_existing_real_run_artifacts',
             'code_publication_commit': 'c29e8f994da629d935f95bb167e8073dfe58cc25',
             'run_git_commit': '0917990c809ed503ec29240ff6b61d29bbb8e4cc',
             'note': 'Run occurred with uncommitted integration code. Historical provenance is retained; this export is not a rerun. Relative image paths in manifests refer to separately obtained BDD100K images.',
             'artifacts': records}
    (DEST / 'export_index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if update_docs:
        paths = [ROOT / 'report.md', ROOT / 'docs/report_by_member.md', ROOT / 'docs/pitch_4_minutes.md']
        paths += list((ROOT / 'docs').glob('bao_cao_ca_nhan_*.md'))
        # The full local appendix is replaced by the public evidence entry.
        aliases = dict(mapping)
        aliases[RUN / 'report_detailed.md'] = DEST / 'README.md'
        for path in paths:
            content = redirect_links(path, aliases)
            content = content.replace('phần tích hợp đang uncommitted trên `feat/integration`',
                                      'tại thời điểm chạy, phần tích hợp còn uncommitted trên `feat/integration`')
            content = content.replace('File local/gitignored cần mang cùng thư mục khi trình bày; chỉ gửi report.md không đủ để mở ảnh/log.',
                                      'Các link CSV/ảnh failure/log ở trên dẫn tới bộ evidence được công bố; full dataset vẫn lưu local để chạy lại từ ảnh.')
            content = content.replace('[Phụ lục số liệu đầy đủ]', '[Bộ evidence công bố]')
            content = content.replace('phần người 5 chưa commit, nên dùng',
                                      'tại thời điểm chạy phần người 5 chưa commit, nên dùng')
            content = content.replace('code người 5 chưa commit nên dùng',
                                      'tại thời điểm chạy code người 5 chưa commit nên dùng')
            content = content.replace('Phần integration hiện nằm trên `feat/integration`, chưa commit/push tại thời điểm lập báo cáo. Dữ liệu/generated/run evidence được gitignore và phải bàn giao kèm thư mục local khi cần mở ảnh/log.',
                                      'Tại thời điểm chạy, integration nằm trên `feat/integration` và chưa commit; hiện code đã công bố trên main. Bộ evidence chọn lọc có link công khai bên dưới; full image replay vẫn cần dataset local.')
            content = content.replace('Data/log được gitignore và cần bàn giao kèm khi trình bày; các link local không đi theo Markdown nếu chỉ gửi riêng file báo cáo.',
                                      'Các link số đo/diagnostics đã chuyển sang bộ evidence công khai; full dataset vẫn local để image replay.')
            content = content.replace('Data/log/generated được gitignore, cần mang kèm khi trình bày; chỉ gửi Markdown không đủ mở ảnh/log.',
                                      'Full dataset/generated vẫn gitignore; bản evidence chọn lọc có link công khai bên dưới để người chấm mở CSV/plot/log.')
            note = ('\nBằng chứng công khai: [' + RUN_ID + '](' +
                    os.path.relpath(DEST / 'README.md', path.parent).replace('\\', '/') +
                    '). Code tích hợp đã công bố tại [commit c29e8f9](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/c29e8f994da629d935f95bb167e8073dfe58cc25). '
                    'Các ghi chú “chưa commit” mô tả trạng thái tại thời điểm chạy; provenance giữ nguyên lịch sử đó. '
                    'CSV/plot/log/snapshot chọn lọc mở được trên GitHub; full image replay cần dataset local.\n')
            if 'Bằng chứng công khai:' not in content:
                content = content.rstrip() + '\n' + note
            if 'buiquangvinh' in path.name and 'không thay thế evidence' not in content:
                content += '\nBộ công khai trên là lượt tích hợp nhóm `integration_20261006_01` do integrator chạy bằng scorer người 4; không thay thế evidence cho lượt riêng `p4_bdd100k_20261006_04` hoặc pilot nuScenes được mô tả ở trên. Các số đếm/action của những lượt riêng chưa được công bố trong bundle này.\n'
            path.write_text(content, encoding='utf-8')
    # Verify source snapshots still have their pre-export hashes.
    for row in records:
        if sha((ROOT / row['source']).read_bytes()) != row['source_sha256']:
            raise RuntimeError('Source changed during export: ' + row['source'])
    print(json.dumps({'artifacts': len(records), 'bytes': sum(r['bytes'] for r in records),
                      'source_unchanged': True, 'destination': DEST.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-docs', action='store_true')
    args = parser.parse_args()
    export(args.update_docs)
