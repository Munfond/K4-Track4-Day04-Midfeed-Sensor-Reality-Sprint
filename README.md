# T1 — Camera Degradation Health Score

Shared contract and collaboration starter for a five-person BDD100K lab.

**Bắt đầu:** đọc [contract v1](docs/contracts.md) và [phân công 5 người](docs/team_ownership.md). Đây là schema/interface đã có validator; các module data, degradation, feature và training do nhóm tiếp tục triển khai. Chưa có model đã train hoặc kết quả BDD100K trong repo này.

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
BDD100K manifest → degradation → features → train classifier
                                         → predictions → evaluation
```

Model đầu tiên: `StandardScaler + LogisticRegression`, train bằng bảy feature v1; chọn regularization bằng validation macro-F1; chỉ fit scaler trên train. Health model và health heuristic báo cáo riêng.

Tải ảnh cùng detection labels/metadata từ [nguồn BDD100K](https://github.com/bdd100k/bdd100k). Chọn subset khoảng 300 ảnh; giữ ảnh gốc và mọi bản degraded cùng split. Weather/timeofday không phải nhãn quality. Nhãn synthetic là proxy và phải báo cáo riêng với nhãn người thật. Nhãn detection chưa được chuyển thành health labels.

Lưu dữ liệu trong `data/raw/`, ảnh generated trong `data/generated/`; các đường này đã gitignore. Model binary trong `models/`; báo cáo lần chạy trong `reports/runs/<run_id>/`. Chỉ commit code/config, không commit dataset, credentials hoặc model binary.

## Quy trình nhóm

Mỗi người một branch và vùng file. Người 5 merge PR và sở hữu contracts/dependency/entry point. Không dùng chung branch làm việc; không sửa file của người khác. Trước PR, chạy kiểm tra contract. Xem [team_ownership.md](docs/team_ownership.md) để biết đầu vào, đầu ra và lịch bàn giao.

Schema version `1.0.0` được đóng băng cho lab. Khi cần thay đổi, gửi người 5; phải sửa schema, config, example, validator/test và downstream tương ứng trước khi merge. Các quy tắc ownership hiện là quy ước nhóm; chưa cấu hình quyền GitHub hoặc branch protection.
