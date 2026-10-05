# T1 — Camera Degradation Health Score

Shared contract and collaboration starter for a five-person BDD100K lab.

**Bắt đầu:** đọc [contract v1](docs/contracts.md), [ownership 5 người](docs/team_ownership.md) và [nhiệm vụ chi tiết](docs/sprint_assignments.md). Sprint hiện tại tập trung data, degradation, feature, health heuristic và evaluation; **train model tạm hoãn**. Các module corruption/features/health và runner/evaluator đã có; dữ liệu người 1 bàn giao local, code chuẩn bị data chưa được commit. Xem [tiến độ và bàn giao người 5](docs/integration_status.md).

## Kiểm tra schema

Python 3.12, chạy từ repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/validate_contract.py --manifest examples/manifest.jsonl --features examples/features.jsonl --predictions examples/predictions.jsonl --model examples/model_metadata.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Trên Linux/macOS thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`.

- Schema máy đọc: [schemas/camera_health.schema.json](schemas/camera_health.schema.json).
- Thứ tự feature/class, preprocessing và policy: [configs/contract.json](configs/contract.json).
- Ví dụ các record: [examples/](examples/). **Toàn bộ là fixture giả lập, không phải ảnh/nhãn BDD100K thật hoặc prediction đã chạy.**
- Validator phát hiện schema sai, duplicate ID, thiếu ảnh gốc trong manifest, leakage sequence/parent, thiếu feature, probability hoặc health formula sai.
- Thêm `--check-files` khi dùng dữ liệu thật. Ví dụ không có ảnh nên không dùng flag này với fixtures.
- GitHub Actions chạy validator và tests trên push/PR.

## Mục tiêu triển khai

```text
BDD100K manifest → degradation → features → health heuristic → evaluation
```

Người 4 triển khai calibration train-only và health heuristic; so sánh fixed/day-night reference, chọn config trên val, đóng băng trước test. Record health tạm thời và output paths được chốt trong nhiệm vụ chi tiết. Schema model/prediction và fixtures ML hiện có dành cho giai đoạn sau; không dùng chúng để giả lập health heuristic hoặc kết quả model đã train.

## Chạy tích hợp (người 5)

Runner gọi các adapter của người 2/3/4, không thay đổi công thức của owner. Mỗi run_id là snapshot mới, không ghi đè data bàn giao. Cần `data/manifests/originals.jsonl`, ảnh nguồn và `reference_ids.json` có reference day/night thuộc train.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe src/run_pipeline.py prepare --run-id integration_20261006_01
```

`prepare` tạo degradation, feature, reference draft và chỉ score val. Review `reports/runs/<run_id>/validation/report.md`, các contact sheet ở `data/features/<run_id>/validation/` (đặc biệt reference day/night), rồi lưu quyết định review:

```powershell
.\.venv\Scripts\python.exe src/run_pipeline.py finalize --run-id integration_20261006_01 --validation-note "Nội dung review val và quyết định giữ/chọn config" --reference-review-note "Nội dung kiểm tra ảnh reference"
```

`finalize` xác minh batch, hash/code/input sau review, freeze config trước scoring test và xuất `reports/runs/<run_id>/report.md` cùng `evaluation/`: CSV groups/samples/curves/score_increases, biểu đồ, contact sheets và provenance. Không tự tune thresholds; nếu val cho thấy cần đổi công thức/config, gửi owner 4 và chạy run_id mới. Ghi note đúng bằng chứng, không coi lời gọi freeze là xác nhận nhãn người thật.

Đánh giá riêng một handoff frozen bằng `python src/evaluate.py --manifest <augmented.jsonl> --features <features.jsonl> --health <health_scores.jsonl> --references <references.json> --output <new-report-dir>`. Dữ liệu fixture phải thêm `--data-kind fixture`.

Heuristic có schema độc lập [heuristic_health.schema.json](schemas/heuristic_health.schema.json), không thay schema ML v1. Kiểm tra với `python scripts/validate_health.py --manifest <manifest> --features <features> --health <health> --references <references>`: coverage, train reference, freeze/val evidence hashes, score/mode/weight/action theo đúng config. Không báo classification metric khi thiếu nhãn quality.

## Evidence riêng theo phase

Khi full run đã frozen và có báo cáo, dùng audit độc lập để lưu nghiệm thu từng người trong thư mục report mới:

```powershell
.\.venv\Scripts\python.exe scripts/audit_real_run.py --run-id integration_20261006_01 --evidence-id evidence_20261006_01
```

Audit đối chiếu data với metadata nguồn local, kiểm tra full batch, replay pixel trên 120 variants phân tầng, tính lại feature từ ảnh thật gồm toàn bộ reference, recalibrate reference và recompute toàn bộ health, rồi tái xuất evaluation và so sánh năm CSV. `phase_1.json`–`phase_5.json`, `summary.json` và `report.md` nằm trong `reports/runs/<run_id>/<evidence_id>/`. Output đã tồn tại bị từ chối; chọn evidence_id mới khi lặp. Audit giữ nguyên data/code/config của owner và xác nhận hashes trước/sau. Phase 1 chỉ audit delivery khi code/config chuẩn bị data chưa có; sample replay được ghi rõ, không gọi là replay toàn bộ ảnh.

## Báo cáo nhóm và pitch

[report.md](report.md) là bản nhóm theo đúng năm mục Problem → Method → Benchmark → Failure case → Engineering decision. Chọn bảng giảm sáng trên test làm benchmark chính; số liệu lấy từ CSV thực chạy, nguồn/version/commands đặt cạnh Method/Benchmark. [Bản theo từng thành viên](docs/report_by_member.md) và [kịch bản pitch 4 phút](docs/pitch_4_minutes.md) dùng chung một failure case.

Tái dựng báo cáo từ evidence hiện có: `.\.venv\Scripts\python.exe scripts/build_group_report.py --run-id integration_20261006_01`, sau đó `python scripts/export_benchmark_evidence.py --update-docs` để cập nhật link công khai. Script giữ báo cáo số liệu dài trong `reports/runs/<run_id>/report_detailed.md`; không chạy lại benchmark hoặc sửa output tính toán/owner code. [Bộ evidence công khai](docs/evidence/integration_20261006_01/README.md) gồm CSV, plot, log audit, snapshot feature/health và một failure case. Full dataset/generated vẫn local gitignored.

Tải ảnh cùng detection labels/metadata từ [nguồn BDD100K](https://github.com/bdd100k/bdd100k). Chọn subset khoảng 300 ảnh; giữ ảnh gốc và mọi bản degraded cùng split. Weather/timeofday không phải nhãn quality. Nhãn synthetic là proxy và phải báo cáo riêng với nhãn người thật. Nhãn detection chưa được chuyển thành health labels.

Lưu dữ liệu trong `data/raw/`, ảnh generated trong `data/generated/`; các đường này đã gitignore. Model binary trong `models/`; báo cáo lần chạy trong `reports/runs/<run_id>/`. Commit code/config/docs và evidence chọn lọc tại `docs/evidence/`; không commit toàn bộ dataset, credentials hoặc model binary. `.gitattributes` giữ nguyên byte evidence để checksum dùng được trên Windows/Linux.

## Kiểm tra bằng chứng và nộp riêng

[TEAMMATES.md](TEAMMATES.md) liệt kê đúng năm thành viên. Các báo cáo cá nhân nằm trong `docs/bao_cao_ca_nhan_*.md`; hiện có báo cáo của người 2–5, người 1 cần bổ sung bản riêng. Mỗi người tự nộp báo cáo của mình và cùng URL repository trên VLearn; chưa có bằng chứng xác nhận năm lượt nộp. Báo cáo người 4 còn bố cục lịch sử, cần owner hoàn thiện năm mục trước khi nộp.

Kiểm tra bản evidence từ một clone không có dataset bằng `python scripts/verify_published_evidence.py` sau khi cài requirements. Lệnh kiểm tra checksum 35 artifact, tính lại 6.300 health từ snapshot feature/reference frozen và đối chiếu 12 nhóm trong bảng brightness_down chính. Đây là kiểm tra snapshot; pixel replay/image feature reextraction của lượt chạy trước được ghi trong audit log.

## Quy trình nhóm

Mỗi người một branch và vùng file. Người 5 merge PR và sở hữu contracts/dependency/entry point. Không dùng chung branch làm việc; không sửa file của người khác. Trước PR, chạy kiểm tra contract. Xem [team_ownership.md](docs/team_ownership.md) để biết đầu vào, đầu ra và lịch bàn giao.

Schema version `1.0.0` được đóng băng cho lab. Khi cần thay đổi, gửi người 5; phải sửa schema, config, example, validator/test và downstream tương ứng trước khi merge. Các quy tắc ownership hiện là quy ước nhóm; chưa cấu hình quyền GitHub hoặc branch protection.
