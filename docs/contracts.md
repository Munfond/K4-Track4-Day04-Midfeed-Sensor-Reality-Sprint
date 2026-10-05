# Contract v1.0.0 — dùng chung cho 5 người

## 1. Quy ước toàn pipeline

- Format trao đổi: **JSONL UTF-8**, mỗi dòng một object; model metadata là một file JSON.
- JSON Schema Draft 2020-12 trong `schemas/camera_health.schema.json`; không chấp nhận field dư, NaN/Infinity hoặc version khác.
- Join bằng `sample_id`, không dựa vào thứ tự dòng.
- ID không đổi khi file được di chuyển; chỉ gồm chữ, số, `_`, `-`.
- Path dùng `/`, tương đối với repo root; không dùng absolute path hoặc `..`.
- Ảnh đưa vào API: numpy RGB uint8, shape `(360, 640, 3)`. Chuẩn bị bằng Pillow `convert('RGB')` và resize `Image.Resampling.BILINEAR` **trước** corruption. Không enhance ảnh trước feature extraction.
- Seed mặc định `20261005`; seed từng sample được lưu rõ. Không dùng Python `hash()` để tạo seed vì không ổn định giữa process.
- Thời điểm ngày/đêm dùng metadata nguồn; không suy ra từ độ sáng frame để chọn chế độ.

## 2. Manifest — người 1/2 tạo

| Field | Quy ước |
|---|---|
| `schema_version`, `record_type` | `1.0.0`, `manifest` |
| `sample_id` | ID duy nhất, ví dụ `abc123_gaussian_noise_s3` |
| `parent_image_id` | ID ảnh original; original tự tham chiếu |
| `sequence_id` | ID sequence/video thực; nếu không biết, giữ source image ID và ghi rõ không kiểm chứng sequence grouping đầy đủ |
| `dataset` | `bdd100k` |
| `source_split` | Split gốc BDD100K `train/val/test`; không thay khi tạo lab split |
| `image_path` | Path file ở repo root |
| `split` | Lab `train/val/test`; toàn bộ sequence cùng split |
| `timeofday` | `daytime/night/dawn/dusk/undefined` theo enum schema; giá trị `dawn/dusk` là một chuỗi |
| `weather` | Giữ enum nguồn, gồm `partly cloudy`; không tự đổi tên |
| `corruption` | `original/gaussian_blur/brightness_up/brightness_down/gaussian_noise/rain_overlay` |
| `severity` | Original=0; synthetic=1–5 |
| `seed` | Original=null; synthetic là integer ≥0 |
| `parameters` | Original `{}`; các tham số vật lý bên dưới |
| `label` | `good/degraded/unusable`, hoặc null |
| `label_source` | `human/synthetic_rule/unlabeled` |
| `label_rule_version` | Ví dụ `rubric-v1`, `synthetic-v1`; unlabeled=null |

**Mỗi bundle manifest phải chứa bản original của mọi synthetic record.** Synthetic giữ `sequence_id`, `source_split`, `split`, `timeofday`, `weather` của parent; label được đánh giá riêng, không tự kế thừa. Original nghĩa là ảnh nguồn chưa bị nhóm biến đổi, không khẳng định ảnh sạch.

Parameter bắt buộc:

| Corruption | Parameter | Dải khởi đầu mức 1→5 |
|---|---|---|
| `gaussian_blur` | `sigma > 0`, pixel | 0.6, 1.2, 2.4, 4, 6 |
| `gaussian_noise` | `sigma > 0`, RGB scale 0–255 | 5, 10, 20, 35, 50 |
| `brightness_up` | `gain > 1` | 1.2, 1.5, 1.9, 2.5, 3.2 |
| `brightness_down` | `0 < gain < 1` | 0.8, 0.6, 0.4, 0.25, 0.12 |
| `rain_overlay` | positive integer `streak_count`, `veil_alpha` ∈[0,1] | 80/0.1, 160/0.2, 320/0.3, 640/0.4, 1000/0.5 |

Parameters phải phản ánh config thực sự chạy; version v1 không bắt buộc đúng các dải khởi đầu nhưng phải lưu config/hash. Noise dùng RNG cục bộ, không thay global RNG. Tạo từng mức trực tiếp từ original đã resize, không áp dụng tích lũy.

Người 1 xuất `data/manifests/originals.jsonl`. Người 2 đọc file này, thêm synthetic vào `data/manifests/augmented.jsonl` mà không sửa originals. Người 3 trích feature cho toàn bộ augmented manifest.

## 3. Feature — người 3 tạo

Record có `schema_version`, `record_type=features`, `sample_id`, `feature_version=1.0.0`, `width=640`, `height=360`, object `features`.

Thứ tự input model được cố định trong `configs/contract.json`; JSON key order không phải thứ tự model:

| Index | Feature | Định nghĩa v1 |
|---:|---|---|
| 0 | `log_laplacian_variance` | `ln(1+Var(Lap(Y)))`; Laplacian 4 láng giềng, bỏ border 1 pixel |
| 1 | `saturation_ratio` | fraction `Y >= 250` |
| 2 | `dark_ratio` | fraction `Y <= 5` |
| 3 | `entropy` | Shannon histogram 256 bins, log₂; bỏ bins zero |
| 4 | `noise_residual` | `sqrt(mean((Y-median3(Y))²))`; median3 theo Pillow |
| 5 | `median_luminance` | median(Y) |
| 6 | `contrast` | population std(Y), `ddof=0` |

Y = Pillow RGB `.convert('L')` 8 bit; convert sang float64 trước tính Laplacian/residual để tránh uint8 overflow. Log tự nhiên khác entropy log₂. Không thêm severity, label, corruption type vào feature: tránh học trực tiếp quy tắc nhãn. Noise residual vẫn chứa texture/cạnh; không gọi đó là noise estimate thuần.

File `data/features/features.jsonl` phải phủ chính xác toàn bộ ID trong augmented manifest. Label/split lấy bằng join manifest, không lặp lại trong feature record. Khi chạy train, filter label!=null; báo số mẫu bị bỏ và tỷ lệ class/split.

## 4. Model metadata — người 4 tạo

File `models/<model_id>/metadata.json`: xem example/schema. Phải lưu feature order, class order, estimator, seed, dependency version thực tế, SHA256 file manifest đầu vào và config training. `status=trained` chỉ khi artifact có thật; fixtures dùng `example`.

Artifact là **cả sklearn Pipeline**, chứa scaler và LogisticRegression. Scaler chỉ fit trên train. Hyperparameter chọn trên validation macro-F1; không dùng test để chọn threshold/config. Nhãn null không được train. Báo kết quả nhãn human và synthetic riêng, không coi label weather là chất lượng.

`class_order = [good, degraded, unusable]` là thứ tự output contract; sklearn `classes_` có thể khác. Người 4 phải remap `predict_proba` bằng tên class trước xuất. Training fail rõ nếu thiếu class cần thiết; không tự điền xác suất cho class chưa học.

## 5. Prediction — người 4 tạo, người 5 đánh giá

Record có ID, model ID, probabilities theo tên class, predicted label, health, camera weight và action. Probability tổng bằng 1 với tolerance 1e-6; không round trước khi ghi JSON.

```text
predicted_label = argmax probability; tie theo [good, degraded, unusable]
health_score = 100 × (P(good) + 0.5 × P(degraded))
camera_weight = (health_score / 100)²  # hệ số nhân w_base, không phải fusion weight đã chuẩn hóa
health >=75    → normal
45<=health<75  → down_weight
health<45      → strong_down_weight
```

Prediction có thể là subset manifest; evaluator phải kiểm tra coverage chính xác với split muốn đánh giá. Model metadata bắt buộc khi validate predictions. Heuristic baseline không ghi vào prediction schema này: người 3 xuất file riêng `data/features/baseline_scores.jsonl`, người 5 ghép theo ID để so sánh. Phải báo metric thật hoặc proxy đúng tên; health chưa phải confidence ADAS đã calibrated.

## 6. API và bàn giao

```python
# Người 2; image input/output RGB uint8 (360,640,3)
degrade(image_rgb, corruption: str, severity: int, seed: int) -> image_rgb

# Người 3; đúng 7 key feature, finite float
extract_features(image_rgb) -> dict[str, float]

# Người 4; đọc feature vector theo feature_order, trả records theo prediction schema
predict_quality(feature_rows, pipeline, model_metadata) -> list[dict]
```

File reader/runner là người 5 sở hữu. Module không chạy workload khi import; CLI đặt dưới `if __name__ == '__main__'`. Không ghi stdout bằng dữ liệu nhạy cảm. Mỗi module nhận input/output path rõ, không hardcode máy cá nhân.

## 7. Nhãn và giới hạn

Rubric v1 do người 1 chốt: good = vùng đường/đối tượng mục tiêu quan sát được; degraded = vẫn dùng được nhưng mất chi tiết đáng kể; unusable = không đủ quan sát nhiệm vụ. Ghi task/ROI cố định trong `docs/labeling_rubric.md` trước annotation. Chọn vài mẫu hai người gán độc lập, xử lý disagreement trước khi khóa label.

Nếu chưa có nhãn human đủ lớn, dùng synthetic_rule và ghi `label_scope=synthetic_proxy`. Mapping mức 1/2→good, 3→degraded, 4/5→unusable chỉ là khởi đầu cần kiểm tra; không mặc định dùng hoặc gọi là ground truth. Không lấy health heuristic làm nhãn rồi tuyên bố model là kiểm chứng độc lập.

BDD100K không có paired same-scene clean/adverse như ACDC; original/synthetic là cặp controlled của nhóm. Glare cục bộ, rolling shutter và lens soiling chưa được cover bởi v1. Ảnh thời tiết xấu có health cao phải đưa vào failure review.

## 8. Version và validation

Chạy validator trước mỗi bàn giao. JSON Schema kiểm tra từng record; validator kiểm tra các điều kiện liên-record như sequence leakage, feature coverage, parent và công thức prediction. Validator không kiểm tra nội dung ảnh, truthfulness của annotation hoặc việc scaler thực sự fit đúng split; cần review code/log riêng.

Đổi field, feature formula/order, preprocessing, class mapping hoặc policy phải nâng version và migration, do người 5 quản lý. Không sửa contract cục bộ trên branch cá nhân rồi merge cùng module.
