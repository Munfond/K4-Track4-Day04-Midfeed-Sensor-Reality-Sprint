# Phân công và chống conflict — 5 người

| Người | Branch | File sở hữu | Bàn giao |
|---|---|---|---|
| 1: data/labels | `feat/data` | `src/prepare_data.py`, `docs/labeling_rubric.md` | originals manifest, split, rubric và nhãn |
| 2: corruption | `feat/degradation` | `src/corruptions.py`, `configs/corruptions.yaml` | augmented manifest, ảnh generated, config/seed |
| 3: feature/baseline | `feat/features` | `src/features.py`, `src/baseline.py` | features JSONL, baseline scores |
| 4: train/predict | `feat/training` | `src/train.py`, `src/predict.py`, `configs/model.yaml` | model pipeline, metadata, prediction JSONL |
| 5: integration/evaluation | `feat/integration` | `src/run_pipeline.py`, `src/evaluate.py`, `scripts/`, `tests/`, `schemas/`, `configs/contract.json`, `docs/contracts.md`, `docs/team_ownership.md`, `README.md`, requirements, `.github/` | runner, kiểm tra interface, metrics/report và merge |

Người 1 là writer duy nhất của `data/manifests/originals.jsonl`; người 2 viết `augmented.jsonl`; người 3 viết `data/features/`; người 4 viết `models/` và predictions trong `reports/runs/<run_id>/predictions.jsonl`; người 5 viết evaluation/plots ở cùng run folder nhưng không sửa prediction. Đây là output local/gitignored.

## Luật phối hợp

1. Mỗi người tạo branch từ main sau bootstrap; không cùng sửa một file, không cùng push một branch.
2. Người 5 là integrator duy nhất merge PR. Muốn đổi file người khác: gửi yêu cầu để owner sửa. Muốn thêm dependency: gửi người 5.
3. Chia annotation thành `annotations/person_1.jsonl` đến `person_5.jsonl`; không cùng edit một file. Người 1 là người duy nhất hợp nhất label. Annotator đánh giá task quality, không nhìn health prediction để gán nhãn.
4. Không commit/push data lớn; không sửa ảnh gốc. Không chạy hai process ghi cùng output path; dùng run_id riêng.
5. Trước bàn giao, chạy validator/tests và gửi lệnh, input path, output path, example record, limitations. Không merge chỉ vì module chạy riêng.
6. Với schema thay đổi, người 5 nâng version và thống nhất migration trước khi downstream tiếp tục. Không tự đổi class/feature name.
7. Không cam kết “không conflict” tuyệt đối: quy tắc ownership giảm conflict file; contract + CI phát hiện một phần conflict dữ liệu/interface. Cần review nhãn, model và merge thực tế.

## Handoff 120 phút

Prerequisite: subset BDD100K và package đã chuẩn bị. Không tải full dataset trong đường chạy bắt buộc.

| Mốc | Deliverable |
|---|---|
| Phút 0–15 | Người 5 khóa contract; người 1 khóa subset/split; cả nhóm khóa rubric |
| 15–35 | Người 1 xuất originals; người 2/3/4 viết module bằng fixture; người 5 ghép runner |
| 35–60 | Người 2 xuất augmented; người 3 xuất features; người 1 hợp nhất nhãn và kiểm tra split |
| 60–85 | Người 4 train/chọn hyperparameter trên val; người 3 xuất baseline; người 5 chuẩn bị evaluation |
| 85–105 | Đóng băng model/config; người 5 chạy test, kiểm tra coverage và false-good trên unusable |
| 105–120 | Mỗi owner viết limitations; người 5 tổng hợp report/pitch và lệnh tái hiện |

Trong PR: vấn đề/behavior mới, file scope, command đã chạy, output contract và failure còn tồn tại. Merge thứ tự: data → corruption/features → training → evaluation. Nếu chưa có human labels đủ, vẫn train synthetic proxy và báo rõ label_scope, không gọi kết quả đó là ADAS reliability.

## Nghiệm thu

- Không leakage parent/sequence; scaler fit train-only; feature không chứa severity/label.
- Class probability remap bằng tên class; metadata/config hash và version khớp lần chạy.
- Report macro-F1, confusion matrix, tỷ lệ unusable→good, phân nhóm day/night, human/synthetic riêng.
- Prediction coverage đúng test ID; test chưa dùng chọn cấu hình.
- Model load lại được; có CLI end-to-end và log reproducibility.
- Cả paper claims và số nhóm tự đo đều có nhãn nguồn; không gán fixtures thành số thực nghiệm.
