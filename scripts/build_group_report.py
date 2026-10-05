"""Build the five-section group report from immutable benchmark evidence."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.baseline import explain_health
from scripts.validate_contract import read_json, read_jsonl


def build(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Invalid run ID')
    run = ROOT / 'reports/runs' / run_id
    evaluation = run / 'evaluation'
    provenance = read_json(evaluation / 'provenance.json')
    evidence = run / 'evidence_20261006_01'
    audit = read_json(evidence / 'summary.json')
    curves = list(csv.DictReader((evaluation / 'curves.csv').open(encoding='utf-8')))
    totals = list(csv.DictReader((evaluation / 'split_totals.csv').open(encoding='utf-8')))
    refs = read_json(ROOT / 'data/features' / run_id / 'references.json')
    rows = read_jsonl(ROOT / 'data/features' / run_id / 'features.jsonl')
    sid = 'b329fe7d-f06455d3'
    failure_feature = next(r for r in rows if r['sample_id'] == sid)
    failure = explain_health(failure_feature, 'daytime', refs, refs['config'])
    diag = evaluation / 'selected_failure_explanation.json'
    if diag.exists() and read_json(diag) != failure:
        raise ValueError('Existing failure diagnostics differ')
    if not diag.exists():
        diag.write_text(json.dumps(failure, indent=2) + '\n', encoding='utf-8')
    fixed = failure['health_record']['health_fixed']
    adaptive = failure['health_record']['health_adaptive']
    weight = failure['health_record']['camera_weight']
    gains = [1.0, .8, .6, .4, .25, .12]
    table = ['| Severity | Gain (× cường độ RGB) | Day: N | Fixed baseline (điểm) | Adaptive day (điểm) | Night: N | Fixed baseline (điểm) | Adaptive night (điểm) |',
             '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for severity in range(6):
        chosen = [next(r for r in curves if r['split'] == 'test' and r['corruption'] == 'brightness_down'
                       and int(r['severity']) == severity and r['timeofday'] == mode) for mode in ('daytime', 'night')]
        day, night = chosen
        table.append(f'| {severity} | {gains[severity]:g} | {day["count"]} | {float(day["fixed_mean"]):.2f} | '
                     f'{float(day["adaptive_mean"]):.2f} | {night["count"]} | {float(night["fixed_mean"]):.2f} | {float(night["adaptive_mean"]):.2f} |')
    test_original = next(r for r in totals if r['split'] == 'test' and r['source'] == 'original')
    test_synthetic = next(r for r in totals if r['split'] == 'test' and r['source'] == 'synthetic')
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def render(target):
        # Relative links resolve both in root report.md and in the run report.
        import os
        def link(path):
            return os.path.relpath(path, target.parent).replace('\\', '/')
        ev = lambda name: link(evaluation / name)
        data = lambda name: link(ROOT / name)
        evidence_link = lambda name: link(evidence / name)
        source = '[paper v3](https://arxiv.org/abs/2112.05456v3)'
        lines = [f'# Báo cáo nhóm — Camera Degradation Health Score', '',
                 f'Ngày 06/10/2026 · Run `{run_id}` · Bản báo cáo `group-five-sections-v1`.',
                 'Năm mục theo rubric người dùng cung cấp; mọi số benchmark dưới đây là số nhóm tự đo, trừ câu ghi rõ nguồn paper/repo.', '',
                 '## 1. Problem', '',
                 'Nền tảng là prototype Python chạy offline trên Windows, hướng tới giám sát camera cho ADAS/robot mặt đất. Sensor đầu vào là ảnh RGB camera đường phố BDD100K; nhóm chưa đo một camera vật lý hoặc triển khai trên xe/drone.',
                 'Tính năng là đo trạng thái ảnh và xuất health/camera_weight/action để hỗ trợ một bộ giám sát downstream. Thiếu sáng làm mất chi tiết vùng tối; blur làm mất cạnh; noise và clipping làm sai tín hiệu ảnh. Tác động tới detector là giả thuyết kỹ thuật, chưa được đo AP trong sprint.',
                 f'Failure thực tế được phân tích duy nhất: ảnh `{sid}` nhìn giống cảnh đêm nhưng metadata nguồn ghi daytime, khiến reference ngày chấm thấp mạnh. Vấn đề bao gồm độ tin cậy metadata khi cảnh camera thiếu sáng, không chỉ chất lượng pixel.', '',
                 '## 2. Method', '',
                 f'**Nguồn paper/repo:** Wischow và cộng sự, {source}, IEEE T-ITS 2023; [repo tác giả](https://github.com/MaikWischow/Camera-Condition-Monitoring). Paper nghiên cứu giám sát blur/noise theo tác vụ và mô tả quan hệ input–output có thể phi tuyến, không đơn điệu. Đây là kết luận của paper, không phải số đo detector của nhóm.',
                 '**Thuật toán nhóm:** pipeline heuristic tự triển khai; không chạy lại estimator ML hoặc bộ điều khiển của paper. Input là RGB uint8 640×360 và metadata nguồn. Original được resize Pillow BILINEAR trước corruption; synthetic không resize lại. Bảy feature gồm log Laplacian variance, bright-clipping ratio, dark ratio, entropy, median-filter residual, median luminance và contrast.',
                 'Reference lấy median/MAD từ 20 original train (10 day, 10 night). Baseline fixed dùng cả 20; adaptive dùng nhóm theo metadata. Penalty được chuẩn hóa bằng MAD/scale floor, có deadband và chặn [0,1]. Exposure lấy max của dark/clipping/luminance penalties.',
                 '`H = 100 × (1 − 0.3P_sharpness − 0.3P_exposure − 0.3P_noise − 0.1P_entropy)`, chặn [0,100]. Output gồm fixed/adaptive H, `camera_weight=(H/100)^2` và action: ≥75 normal, 45–<75 down_weight, <45 strong_down_weight. Weight là hệ số tương đối, chưa phải fusion weight được kiểm chứng.',
                 'Giả định: metadata day/night đáng tin và reference train đại diện cho điều kiện cần so sánh. Reference đêm có glare/vùng tối/nhòe; chưa có quality labels. Chọn giữ config trên val rồi freeze trước test; ngưỡng 75/45 là mặc định mô tả, chưa tối ưu bằng nhãn. Unknown/dawn/dusk dùng fixed_fallback hiện có.',
                 f'**Truy vết code:** [repo nhóm](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint), [HEAD `{provenance["git_commit"][:7]}`](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/{provenance["git_commit"]}); phần tích hợp đang uncommitted trên `feat/integration`, nên HEAD không đủ tái hiện: dùng [source hashes/runtime/argv]({ev("provenance.json")}). Contract/feature v1.0.0; formula weighted_reference_penalties_v1; policy `{refs["config"]["policy_id"]}`; reference hash `{refs["reference_sha256"]}`.',
                 f'Runtime thực chạy: Python 3.12.14, NumPy {provenance["versions"]["numpy"]}, Pillow {provenance["versions"]["Pillow"]}, jsonschema {provenance["versions"]["jsonschema"]}, matplotlib {provenance["versions"]["matplotlib"]}. [Contract/công thức]({data("docs/contracts.md")}), [config frozen]({data(f"data/features/{run_id}/references.json")}).',
                 f'Lệnh đọc lại phương pháp cho đúng failure (chỉ đọc, có thể chạy lại):', '', '```powershell',
                 rf'.\.venv\Scripts\python.exe src/baseline.py explain --manifest data/manifests/augmented_{run_id}.jsonl --features data/features/{run_id}/features.jsonl --references data/features/{run_id}/references.json --sample-id {sid}',
                 '```', '',
                 '## 3. Benchmark', '',
                 '**Dữ liệu:** [BDD100K toolkit/dataset](https://github.com/bdd100k/bdd100k). Local metadata export có 10.000 mẫu; subset đã bàn giao có 300 ảnh thật, source_split=val, lab split train/val/test=180/60/60 theo sequence_id được cung cấp. Day/night=159/141; clear/rainy=200/100. Sequence metadata chưa được xác minh độc lập; code/config prepare_data của người 1 chưa có để replay selection.',
                 'Bốn corruption synthetic trên ảnh thật × năm mức tạo 6.000 PNG: Gaussian blur σ=0.6/1.2/2.4/4/6 pixel; brightness_up gain=1.2/1.5/1.9/2.5/3.2; brightness_down gain=0.8/0.6/0.4/0.25/0.12; Gaussian noise σ=5/10/20/35/50 mức RGB 8-bit. Seed gốc 20261005; seed từng mẫu lưu manifest. Corruption là proxy, không mô phỏng đầy đủ sensor/ISP; ảnh mưa thật không phải rain overlay.',
                 '**Bảng chính — nhóm tự benchmark, split test, brightness_down.** Severity 0 là original baseline ảnh, gain=1. Mỗi mức giữ cùng 34 parents metadata daytime và 26 parents night; ảnh severity 1–5 là synthetic từ các ảnh đó. Fixed baseline là policy tham chiếu chung; adaptive là policy tham chiếu theo metadata. Health là **điểm 0–100**, không phải % accuracy hoặc confidence.', '',
                 *table, '',
                 f'**Nguồn số đo ngay cạnh bảng:** [curves.csv]({ev("curves.csv")}), [groups.csv (mean/median/population std)]({ev("groups.csv")}), [manifest]({data(f"data/manifests/augmented_{run_id}.jsonl")}), [provenance]({ev("provenance.json")}). Dòng bảng được lấy từ CSV, làm tròn hai chữ số; không chép số từ paper.',
                 'Ở metadata daytime, adaptive giảm 84,54→30,00 điểm từ original đến gain 0,12; ở night giảm 84,01→30,15. Bảng thể hiện phản ứng với giảm sáng có kiểm soát; không chứng minh adaptive chính xác hơn fixed khi chưa có nhãn quality.',
                 f'Toàn test: 60 original có adaptive mean {float(test_original["adaptive_mean"]):.2f}, median {float(test_original["adaptive_median"]):.2f}, std {float(test_original["adaptive_std"]):.2f}; 1.200 synthetic có mean {float(test_synthetic["adaptive_mean"]):.2f}, median {float(test_synthetic["adaptive_median"]):.2f}, std {float(test_synthetic["adaptive_std"]):.2f}. Coverage full=6.300/6.300, test=1.260/1.260. Đây là độ phủ, không phải accuracy.',
                 f'Evidence chạy được: [log generate (count/seed/source/PNG hashes)]({data(f"data/generated/{run_id}/run_summary.json")}), [handoff health/freeze]({data(f"data/features/{run_id}/handoff.json")}), [audit 5 phase]({evidence_link("report.md")}). Pixel replay 120 variants khớp; 145 feature records tính lại sai khác tối đa 0; recalibration 20 reference và 6.300 health khớp; năm CSV evaluation byte-equal. 32 unittest đạt; tests fixture được phân biệt với benchmark ảnh thật.',
                 f'Lệnh đã dùng để tạo batch: `python src/run_pipeline.py prepare --run-id {run_id}` rồi `finalize` với review notes; argv đầy đủ của finalize ở [provenance]({ev("provenance.json")}). Snapshot tồn tại được bảo vệ; chạy pipeline lần mới phải đổi run_id và review val trước freeze. Lệnh audit đã chạy; để lặp, đổi evidence_id mới:', '', '```powershell',
                 rf'.\.venv\Scripts\python.exe scripts/audit_real_run.py --run-id {run_id} --evidence-id evidence_pitch_review_01',
                 '```',
                 f'Lệnh tái dựng báo cáo này từ CSV/evidence: `python scripts/build_group_report.py --run-id {run_id}`. Report-builder SHA256 `{script_hash}`. Không cần sinh lại dataset để sửa nội dung báo cáo.',
                 'Giới hạn benchmark: chưa train classifier, chưa có F1/false alarm, chưa chạy detector AP, fusion hoặc đo latency/ADAS reliability. Các curve corruption khác nằm trong report chi tiết; giữ ngoại lệ score tăng trong CSV.', '',
                 '## 4. Failure case', '',
                 f'**Một tình huống duy nhất:** test original `{sid}`, đường ảnh `{data(f"data/raw/bdd100k/images/val/{sid}.jpg")}`. Không có corruption synthetic áp vào frame này trong failure analysis.',
                 f'![Ảnh failure thật]({data(f"data/raw/bdd100k/images/val/{sid}.jpg")})',
                 'Ảnh có trời tối và đèn đường/đèn xe nhưng timeofday=daytime. Đối chiếu local metadata nguồn xác nhận handoff khớp nguồn; đây là nghi vấn về nhãn so với nội dung ảnh, chưa chứng minh người 1 xử lý sai.',
                 f'**Số đo nhóm:** median luminance={failure["feature_values"]["median_luminance"]:.0f}/255; dark_ratio={100*failure["feature_values"]["dark_ratio"]:.2f}% pixel. Fixed={fixed:.2f}, adaptive day={adaptive:.2f}, chênh lệch={adaptive-fixed:.2f} điểm. Day reference median luminance={failure["adaptive"]["reference_median"]["median_luminance"]:.0f}/255; exposure penalty trừ {failure["adaptive"]["penalty_points"]["exposure"]:.2f} điểm, driven by median_luminance.',
                 f'Adaptive action là strong_down_weight và camera_weight={weight:.4f}; nếu chỉ dùng fixed thì action theo ngưỡng hiện tại sẽ normal. Reference có thể đổi quyết định dù pixel giống nhau. Chưa có quality label hoặc kết quả detector để kết luận action nào đúng.',
                 f'Nguyên nhân hỗ trợ bởi diagnostics: scorer chọn reference day theo metadata và so cảnh tối với baseline sáng hơn; cả sharpness/entropy penalties cũng thay đổi. [JSON giải thích từng penalty]({ev("selected_failure_explanation.json")}), [samples.csv]({ev("samples.csv")}), [audit đối chiếu nguồn metadata]({evidence_link("phase_1.json")}). Không sửa test metadata/score sau freeze.', '',
                 '## 5. Engineering decision', '',
                 '**Quyết định từ failure:** coi độ tin cậy metadata là điều kiện để dùng adaptive score làm tín hiệu downstream. Giữ nguyên run frozen làm bằng chứng; không tune theo test và không xem health là lệnh điều khiển xe.',
                 '**Đã có:** log sample_id, input/config/reference/source hashes, mode, fixed/adaptive score, camera_weight/action và diagnostics cho frame trên. Fallback hiện tại chỉ xử lý dawn/dusk/undefined bằng fixed_fallback; nó không phát hiện daytime label có nội dung giống night.',
                 '**Một cải tiến đề xuất, chưa triển khai:** thêm metadata-quality gate trước adaptive routing ở run mới. Owner 1 review provenance và gán trạng thái metadata đã kiểm tra; nếu chưa đáng tin thì phát cờ uncertainty ở log ngoài health schema và yêu cầu bộ giám sát xử lý, giữ fixed làm đối chiếu. Không tự đổi day/night từ luminance và không coi fixed là fallback an toàn đã được chứng minh. Owner 4/5 cần chốt contract và validate gate trước deployment.',
                 'Dữ liệu tiếp theo cần có là metadata/reference đã review, nhãn quality độc lập và đo tác vụ detector trên cùng cảnh tối. Owner 1 bàn giao code/config selection; owner 4 chọn policy trên val mới; owner 5 giữ test độc lập và báo mức giảm coverage khi gate từ chối adaptive.',
                 '**Trade-off:** heuristic nhẹ, dễ giải thích và phù hợp thăm dò offline/chẩn đoán camera. Chưa đo runtime nên không khẳng định real-time. Gate có thể giảm routing sai nhưng tăng số frame uncertain và công review. Không dùng score đơn lẻ cho phanh/steering, sensor fusion robot hoặc điều khiển drone trước khi có task-level validation và supervisor.',
                 f'**Năm mục cho từng người:** [bản câu ngắn theo thành viên]({data("docs/report_by_member.md")}); đây là bản integrator tổng hợp từ evidence chung, không thay báo cáo cá nhân của owner.',
                 '**Nhịp pitch 4 phút (kịch bản phân vai, chưa ghi âm một buổi tập):** 0:00–0:35 Problem/người 1; 0:35–1:30 Method/người 2–3; 1:30–2:35 Benchmark/người 4; 2:35–3:20 Failure/người 5; 3:20–4:00 Decision và trade-off/cả nhóm. Chỉ trình chiếu bảng chính; mở ảnh và JSON khi hỏi nguyên nhân.',
                 f'**Đường mở demo đã kiểm tra:** [bảng CSV]({ev("curves.csv")}) → [ảnh failure]({data(f"data/raw/bdd100k/images/val/{sid}.jpg")}) → [penalty log]({ev("selected_failure_explanation.json")}) → [audit summary]({evidence_link("summary.json")}). File local/gitignored cần mang cùng thư mục khi trình bày; chỉ gửi report.md không đủ để mở ảnh/log.',
                 '**Tự đối chiếu rubric:** benchmark/demo 40% có code, batch log, CSV và replay; failure 25% có một frame, nguyên nhân và tác động action; thuật toán 20% có input/output/công thức/giả định/nguồn; trade-off 15% có gate, uncertainty/coverage và giới hạn ADAS/robot/drone. Đây là checklist đáp ứng yêu cầu, không tự chấm điểm giảng viên.',
                 f'[Phụ lục số liệu đầy đủ]({link(run / "report_detailed.md")}) và [tiến độ/phân công/evidence]({data("docs/integration_status.md")}).']
        spaced, in_code = [], False
        for line in lines:
            spaced.append(line)
            if line.startswith('```'):
                in_code = not in_code
            elif line and not in_code and not line.startswith(('#', '|')):
                spaced.append('')
        return '\n'.join(spaced) + '\n'

    detailed = run / 'report_detailed.md'
    if not detailed.exists():
        shutil.copyfile(run / 'report.md', detailed)
    for target in (ROOT / 'report.md', run / 'report.md'):
        target.write_text(render(target), encoding='utf-8')
    return [ROOT / 'report.md', run / 'report.md']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    for path in build(args.run_id):
        print(path)


if __name__ == '__main__':
    main()
