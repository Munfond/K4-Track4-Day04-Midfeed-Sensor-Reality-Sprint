# Nhiệm vụ chi tiết — 5 người, chưa train model

Mục tiêu 120 phút: chạy BDD100K subset xuyên suốt; tạo degradation, tính metric, health heuristic, so sánh fixed/adaptive ngày/đêm và xuất bằng chứng. Dataset/dependency cần chuẩn bị trước giờ lab. Đây là hướng dẫn triển khai, chưa khẳng định các module đã có.

## Người 1 — Data và reference (branch feat/data)

**Sở hữu:** `src/prepare_data.py`, `configs/data.json`, `docs/data_notes.md`.

1. Đọc metadata BDD100K; lấy khoảng 300 ảnh gồm day/clear, night/clear và rainy. Ghi phân bố thực tế nếu thiếu mẫu; không mặc định night/rain là kém chất lượng.
2. Kiểm tra ảnh đọc được, RGB, ảnh trùng, tên ảnh khớp metadata. Xem trực quan ảnh làm reference; không mặc định original sạch.
3. Chia lab 60% train (calibration), 20% val, 20% test theo sequence trước corruption. Giữ source_split riêng. Nếu thiếu sequence ID, ghi rõ mức leakage chưa kiểm chứng.
4. Xuất originals manifest schema v1: original tự parent, severity=0, seed=null, parameters={}; label=null, label_source=unlabeled nếu chưa annotation.
5. Chọn reference original day/night từ **train**, đã kiểm tra chất lượng; xuất ID/reference list riêng. Không dùng val/test làm reference.

**Output duy nhất:** `data/manifests/originals.jsonl`, `data/manifests/reference_ids.json`. Đường ảnh nguồn chỉ đọc. Config có ID dataset cụ thể giữ local; config template commit.

**Bàn giao phút 30:** manifest, reference IDs, phân bố nhóm/split, command đã chạy và 3 records mẫu.

**Pass:** validator manifest + check-files; ID duy nhất; split/sequence hợp lệ; reference không chứa ảnh synthetic hoặc val/test.

## Người 2 — Degradation (branch feat/degradation)

**Sở hữu:** `src/corruptions.py`, `configs/corruptions.json`, `docs/degradation_notes.md`.

1. Nhận originals manifest. Chuẩn bị RGB 640×360 bằng Pillow BILINEAR **trước** corruption. Original được người 3 chuẩn bị cùng cách khi tính feature.
2. Implement blur, brightness_up/down và gaussian_noise, mỗi loại 5 mức theo contract. Rain overlay là tùy chọn, phải ghi proxy và limitations.
3. Dùng RNG cục bộ/seed ổn định; không Python hash(), không thay global RNG. Tạo mỗi mức trực tiếp từ original đã resize, không cộng dồn.
4. Lưu PNG, ID mới, parent ID, severity và tham số thực tế; giữ split/sequence/weather/timeofday parent.
5. Giữ label=null nếu chưa có đánh giá; không tự gọi mức 5 là unusable. Xuất manifest bao gồm original và synthetic.

**API:** `degrade(image_rgb, corruption, severity, seed) -> image_rgb`, numpy RGB uint8 `(360,640,3)`.

**Output duy nhất:** `data/generated/<run_id>/`, `data/manifests/augmented_<run_id>.jsonl`.

**Bàn giao phút 45:** smoke batch 6 ảnh trước, rồi full subset; manifest + config + seed + ảnh sanity check.

**Pass:** đủ ID, dtype/shape đúng, mức degradation nhìn thấy; cùng seed tái hiện cùng ảnh; không sửa/overwrite source.

## Người 3 — Feature/metric (branch feat/features)

**Sở hữu:** `src/features.py`, `docs/feature_notes.md`.

1. Implement đúng 7 feature v1: log_laplacian_variance, saturation_ratio, dark_ratio, entropy, noise_residual, median_luminance, contrast.
2. Đọc original → RGB resize BILINEAR 640×360. Synthetic đã chuẩn bị cùng kích thước; không resize/denoise/sharpen lại synthetic.
3. Grayscale Pillow, float64 trước Laplacian/residual để tránh overflow. Công thức/unit/order giữ nguyên `docs/contracts.md`.
4. Mỗi ID một record finite; lỗi ảnh phải báo ID và fail rõ nếu coverage thiếu. Không chép split/label/severity vào feature.
5. Ghi interpretation: noise có thể tăng Laplacian/entropy; residual còn chứa texture, không phải noise estimate thuần.

**API:** `extract_features(image_rgb) -> dict[str,float]`, đúng 7 key; input RGB uint8 `(360,640,3)`.

**Output duy nhất:** `data/features/<run_id>/features.jsonl`.

**Bàn giao phút 55:** batch đầu + CLI + example record + feature version.

**Pass:** validator với augmented manifest; coverage ID chính xác; không duplicate/NaN; đúng range/version và kích thước.

## Người 4 — Health/calibration (branch feat/health)

**Sở hữu:** `src/baseline.py`, `configs/health.json`, `docs/health_notes.md`. Train/predict/model artifact tạm hoãn.

1. Nhận feature/metadata/reference IDs. Tính tham chiếu chỉ từ original train được người 1 chọn; kiểm tra reference coverage.
2. Implement health heuristic dựa trên feature v1. Dùng sharpness, exposure, noise, entropy; công bố công thức, trọng số và penalty. Không gọi là confidence đã calibrated.
3. Chạy fixed reference và day/night reference riêng. Chọn mode từ metadata, không chọn từ luminance frame; dawn/dusk/undefined dùng fixed fallback và ghi reason.
4. Chọn hệ số/threshold trên val; đóng băng config phút 85, sau đó chạy test. Không dùng severity/corruption name/label làm đầu vào health.
5. Tính camera_weight=(health/100)^2. 75/45 là mặc định minh họa; lưu threshold thực tế trong config. Báo ngoại lệ nhẹ degradation làm score tăng.

**API đề xuất:** `calibrate(reference_features, metadata, config) -> references`; `score_health(feature_row, timeofday, references, config) -> health_record`.

**Output duy nhất:** `data/features/<run_id>/references.json`, `data/features/<run_id>/health_scores.jsonl`.

**Record health tạm thời, không dùng ML prediction schema:**

```json
{"schema_version":"1.0.0","record_type":"heuristic_health","sample_id":"example_003","policy_id":"heuristic-v1","mode":"day","health_fixed":80.0,"health_adaptive":85.0,"health_score":85.0,"camera_weight":0.7225,"action":"normal"}
```

Mode `day/night/fixed_fallback`; health_score=health_adaptive; score [0,100], weight [0,1]. Với threshold mặc định: ≥75 normal, 45–<75 down_weight, <45 strong_down_weight. Nếu đổi threshold, evaluator đọc config frozen. Config lưu policy_id/công thức/threshold/reference hash; đổi công thức/config thì đổi policy_id. Không tạo probability giả để hợp schema ML.

**Bàn giao:** score batch đầu phút 70; frozen config phút 85; kèm công thức, reference IDs/hash và limitations.

**Pass:** đủ score ID, finite/range, reference train-only, mode đúng, fixed/adaptive báo riêng. Người 5 đã bổ sung schema độc lập `schemas/heuristic_health.schema.json` và `scripts/validate_health.py` cho record tạm thời v1.0.0; schema ML v1 giữ nguyên. Trạng thái thực hiện và bằng chứng: [integration_status.md](integration_status.md).

## Người 5 — Integration/evaluation/pitch (branch feat/integration)

**Sở hữu:** runner/evaluator, scripts/tests/schema/contract, requirements/README/CI, tài liệu ownership và report tổng hợp. Không sửa logic module người 1–4.

1. Khóa interface, requirements, run_id và CLI; viết runner theo các API trên. Module owner có thể phát triển bằng fixtures trong lúc chờ data.
2. Validate manifest/features trước downstream. Riêng health kiểm tra coverage, finite/range, mode, weight/action theo config; validator ML hiện có không validate heuristic record.
3. Join bằng ID; tính mean/median/độ phân tán theo severity/day/night; so sánh fixed/adaptive. Giữ ngoại lệ không đơn điệu trong report.
4. Xuất bảng original/degraded, curve và contact sheet. Review mưa thật, noise score tăng, ảnh original vốn xấu.
5. Ghi hash manifest/config, git commit, versions, seed, số frame thực chạy và command. Phân biệt paper claims, số tự đo, fixture.
6. Merge PR duy nhất theo dependencies; gửi lỗi module cho owner sửa. Nếu chưa quality labels, không báo macro-F1/false alarm; chưa chạy detector thì không báo AP hoặc fusion benefit.

**Output duy nhất:** `reports/runs/<run_id>/evaluation/` và `reports/runs/<run_id>/report.md`. Chỉ đọc feature/health, không sửa output người khác.

**Pass:** một CLI end-to-end; coverage test đúng; test config freeze; bảng/curve/failure đủ; kết quả ghi rõ chưa train model và health chưa kiểm chứng ADAS.

## Bàn giao và khóa conflict

- Mỗi người chỉ sửa file sở hữu trong bảng `team_ownership.md`; file mới phải chốt owner với người 5. Person 1–4 ghi notes riêng, person 5 tổng hợp; không cùng edit report/README.
- Branch riêng từ main mới nhất; PR về main, người 5 merge duy nhất. Dependency thay đổi do người 5 thực hiện. Bug file người khác gửi owner, không sửa song song.
- Mỗi output file có một writer. Người 5 cấp run_id cho tích hợp; experiment cá nhân dùng run_id riêng. Không overwrite snapshot đã bàn giao; tái sinh dữ liệu đổi run_id và báo downstream.
- PR kèm command thực chạy, input/output path, example record, config/hash và limitations. Không commit ảnh/model/generated; nguồn chỉ đọc.
- Reference train-only, tune val-only, test freeze. Metadata day/night không đổi theo corruption. Đổi contract do người 5 điều phối trước khi merge.
- Ownership là quy ước, chưa có branch protection; giảm conflict code/output nhưng vẫn cần review và resolve merge nếu xảy ra.

## Timeline 120 phút

| Phút | Người 1 | Người 2 | Người 3 | Người 4 | Người 5 |
|---|---|---|---|---|---|
| 0–15 | Chốt subset/split/reference | Khóa tham số/dtype | Khóa feature | Khóa baseline | Khóa scope/contract/run_id |
| 15–35 | Xuất originals | API + smoke ảnh | Feature API | Calibration/score với mock | Runner/dependency |
| 35–60 | Kiểm tra reference | Xuất augmented | Xuất features | Nhận feature/reference | Merge + validate |
| 60–85 | Review metadata | Review reproducibility | Review metric | Fixed/adaptive + val; freeze | Evaluation/plots |
| 85–105 | Review ảnh thật | Review corruption | Metric interpretation | Score test frozen | Chạy test/report |
| 105–120 | Data limitations | Simulation limitations | Metric limitations | Health limitations | Pitch/reproduction |

Merge: data → degradation/features → health → evaluation. Các module viết bằng contract/fixture trước nên không cần chờ full dataset để bắt đầu. Chưa có human quality labels: tập trung severity-response và failure review, không suy ra detector accuracy.
