# Phân công và chống conflict — 5 người, tạm hoãn train model

**Phạm vi hiện tại:** data → degradation → feature → health heuristic → evaluation. [Chi tiết công việc, API và output từng người](sprint_assignments.md). Model/prediction schema hiện có dành cho giai đoạn sau. Implementation và bằng chứng hiện tại được ghi trong [integration_status.md](integration_status.md).

| Người | Branch | File sở hữu | Bàn giao |
|---|---|---|---|
| 1: data/reference | `feat/data` | `src/prepare_data.py`, `configs/data.json`, `docs/data_notes.md` | originals manifest, split, reference IDs và data notes |
| 2: corruption | `feat/degradation` | `src/corruptions.py`, `configs/corruptions.json`, `docs/degradation_notes.md` | augmented manifest, ảnh generated, config/seed |
| 3: feature | `feat/features` | `src/features.py`, `docs/feature_notes.md` | features JSONL và giải thích metric |
| 4: health/calibration | `feat/health` | `src/baseline.py`, `configs/health.json`, `docs/health_notes.md` | reference calibration, health fixed/adaptive |
| 5: integration/evaluation | `feat/integration` | `src/run_pipeline.py`, `src/evaluate.py`, `scripts/`, `tests/`, `schemas/`, `configs/contract.json`, `docs/contracts.md`, `docs/team_ownership.md`, `docs/sprint_assignments.md`, `README.md`, requirements, `.github/` | runner, kiểm tra interface, metrics/report và merge |

Người 1 ghi `data/manifests/originals.jsonl` và `reference_ids.json`; người 2 ghi `data/manifests/augmented_<run_id>.jsonl` và `data/generated/<run_id>/`; người 3 ghi `data/features/<run_id>/features.jsonl`; người 4 ghi `data/features/<run_id>/health_scores.jsonl` và `references.json`; người 5 ghi `reports/runs/<run_id>/`. Đây là output local/gitignored; mỗi file chỉ có một writer.

Người 5 sở hữu thêm `scripts/validate_health.py`, `schemas/heuristic_health.schema.json`, `tests/test_integration.py` và `docs/integration_status.md`. Runner chỉ gọi adapter owner để tạo snapshot mới; báo cáo val ở `reports/runs/<run_id>/validation/`, final ở root run. Người 5 không sửa code/config/data gốc của người 1–4.

## Luật phối hợp

1. Mỗi người tạo branch từ main sau bootstrap; không cùng sửa một file, không cùng push một branch.
2. Người 5 là integrator duy nhất merge PR. Muốn đổi file người khác: gửi yêu cầu để owner sửa. Muốn thêm dependency: gửi người 5.
3. Nhãn chất lượng chưa bắt buộc trong sprint này; giữ label=null/label_source=unlabeled khi chưa đánh giá. Nếu annotation bổ sung, mỗi người dùng file riêng, người 1 hợp nhất; không nhìn health prediction để gán nhãn.
4. Không commit/push data lớn; không sửa ảnh gốc. Không chạy hai process ghi cùng output path; dùng run_id riêng.
5. Trước bàn giao, chạy validator/tests và gửi lệnh, input path, output path, example record, limitations. Không merge chỉ vì module chạy riêng.
6. Với schema thay đổi, người 5 nâng version và thống nhất migration trước khi downstream tiếp tục. Không tự đổi class/feature name.
7. Người 5 cấp run_id tích hợp; output cá nhân dùng run_id riêng. Không overwrite batch đã bàn giao; mọi file mới phải chốt owner trước. Ownership giảm conflict file; contract + CI phát hiện một phần conflict dữ liệu/interface, chưa thay thế review hoặc branch protection.

## Handoff 120 phút

Prerequisite: subset BDD100K và package đã chuẩn bị. Không tải full dataset trong đường chạy bắt buộc.

| Mốc | Deliverable |
|---|---|
| Phút 0–15 | Người 5 khóa scope/contract; người 1 khóa subset/split/reference; nhóm thống nhất metric/health |
| 15–35 | Người 1 xuất originals; người 2/3/4 viết module bằng fixture; người 5 ghép runner |
| 35–60 | Người 2 xuất augmented; người 3 xuất features; người 1 kiểm tra split/reference |
| 60–85 | Người 4 calibration/health fixed-adaptive, chọn config trên val; người 5 chuẩn bị evaluation |
| 85–105 | Đóng băng health config; người 4 score test; người 5 đánh giá coverage, curve và failure |
| 105–120 | Mỗi owner viết limitations; người 5 tổng hợp report/pitch và lệnh tái hiện |

Trong PR: vấn đề/behavior mới, file scope, command đã chạy, output contract và failure còn tồn tại. Merge thứ tự: data → corruption/features → health → evaluation. Chưa train model; báo cáo phản ứng metric/health, không gọi là detector AP hoặc ADAS reliability.

## Nghiệm thu

- Không leakage parent/sequence; reference dùng original train-only đã được kiểm tra; feature không chứa severity/label.
- Health config/reference hash và version khớp lần chạy; adaptive lấy ngày/đêm từ metadata.
- Report phân bố score, curve severity, fixed/adaptive, original/synthetic và failure mưa thật.
- Health coverage đúng test ID; config chọn trên val, test chưa dùng tune.
- Có CLI end-to-end và log reproducibility; không báo classification metric khi chưa có quality labels.
- Cả paper claims và số nhóm tự đo đều có nhãn nguồn; không gán fixtures thành số thực nghiệm.
