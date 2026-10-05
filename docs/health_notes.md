# Health/calibration — phần người 4

Báo cáo cá nhân: [Bùi Quang Vinh — 2A202603012](bao_cao_ca_nhan_buiquangvinh_2A202603012.md).

Implementation: `src/baseline.py`; config template: `configs/health.json`.
Module dùng Python standard library, không cần GPU hoặc package bổ sung.
Runner `scripts/run_health.py` dùng NumPy, Pillow và jsonschema để trích feature,
validate input và tạo contact sheet. Không cần GPU.
Config template giữ giá trị khởi đầu; config đã chọn trên BDD100K validation và
frozen cho lần chạy chính thức nằm trong `references.json["config"]` bên dưới.
Health là heuristic mô tả ảnh, chưa phải confidence ADAS đã calibrated.

## Kết quả BDD100K hoàn tất ngày 06/10/2026

Run health: `p4_bdd100k_20261006_04`, nhánh `health`. Batch degradation đầu vào:
`p4_bdd100k_20261006_01`. Feature batch: `p4_bdd100k_20261006_02`.
Các mục nuScenes bên dưới là lịch sử pilot, không phải input của lượt chạy này.

- 300 ảnh BDD100K original, 6.000 synthetic, 6.300 manifest/feature/health records.
- Original split: 180 train, 60 val, 60 test; sau degradation: 3.780/1.260/1.260.
- Reference: 20 original train, 10 day và 10 night, kiểm tra hash/coverage và đã
  xem cả 20 ảnh trên contact sheet. Night có natural darkness/glare; day có
  scene/windshield variation. Không khẳng định reference sạch hoặc tạo quality labels.
- Upstream `reference_ids.json["visual_review"]` vẫn là `pending`, giữ nguyên file
  người 1. Review cho lượt health này được ghi riêng trong provenance frozen.
- Validation: xem 1.260 score, 8 original có điểm thấp nhất và contact sheet
  degradation day/night. So sánh scale multiplier 2/3/4 chỉ trên val, chọn 3;
  giữ weights 0.3/0.3/0.3/0.1 và ngưỡng minh họa 75/45. Chưa có quality labels
  để tối ưu F1 hoặc false alarm. Không dùng test để chọn hệ số/ngưỡng.
- Sau freeze mới chấm 1.260 test records. Final gồm 2.296 normal, 3.006 down_weight,
  998 strong_down_weight. Riêng test: 429/609/222; đây là policy actions, không phải
  quality ground truth. Original test: 47 normal, 9 down_weight, 4 strong_down_weight.
- Fixed/adaptive mean của original test: day 95.60/84.54 (34 ảnh), night
  75.54/84.01 (26 ảnh). Adaptive không mặc định tốt hơn fixed.

Ngoại lệ đã giữ nguyên: noise nhẹ làm Laplacian/entropy tăng; brightness_up có
thể cải thiện ảnh night vốn tối; blur penalty đạt trần rồi score có thể tăng nhẹ.
Val có 391 và final có 2.141 score-increase findings so với original parent,
đếm fixed/adaptive riêng. Không ép score giảm đơn điệu hoặc gọi mọi severity là xấu.

Output bàn giao:

- `data/features/p4_bdd100k_20261006_04/references.json`: reference và config frozen.
- `data/features/p4_bdd100k_20261006_04/health_scores.jsonl`: đủ 6.300 health records.
- `data/features/p4_bdd100k_20261006_04/handoff.json`: paths, hashes, review notes.
- `data/features/p4_bdd100k_20261006_04/verification.json`: acceptance checks.
- `data/features/p4_bdd100k_20261006_04/validation/`: val scores summary, reference
  contact sheets, lowest originals, explanations và `config_candidates.json`.
- `data/features/p4_bdd100k_20261006_04/final_review/`: bảng JSON/CSV/Markdown theo
  split/mode/corruption/severity và tất cả ngoại lệ score tăng.

Policy: `heuristic-v1-5a7bf047d3a775aa`.
Reference SHA256: `0ba1cbe2c782bc7a23548c6d56d3cfc42808fcee63f1901e18bf3ff065a8fd65`.
Config SHA256: `f647557d17b1c3bdadb0614e734a1dae69ebc986903d266ce72af012d04b926c`.

Đã sửa adapter để nhận reference handoff có metadata và nhóm fixed; kiểm tra fixed
khớp day/night union, hash/source originals và reference sequence. Runner chặn
test trước freeze, input/code/val score đổi sau review và ghi đè output cũ.
24 tests trong repo pass, bao gồm contract, health và runner prepare/finalize.
Full corruption verification pass; smoke 120 PNG replay pixel pass. Final ID coverage,
finite/range, mode, weight/action và hash pass; 1.260 val scores khớp hoàn toàn
trước/sau freeze. Split leakage chỉ được kiểm tra theo sequence_id người 1 khai báo.

## Chạy lại trên Windows

Chạy từ repository root. Môi trường `.venv` hiện có Python 3.12.14, NumPy 2.3.5,
Pillow 12.3.0, jsonschema 4.26.0. Máy mới cần tạo venv và cài các dependency tối thiểu:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install 'numpy>=1.26,<3' 'Pillow>=10,<13' 'jsonschema>=4.18,<5'
```

Dùng run_id mới cho mỗi snapshot. Ví dụ bên dưới chưa được thực chạy; đổi tên nếu
đã tồn tại. Có thể tái dùng augmented manifest đã kiểm tra để bỏ bước corruption.

```powershell
# Generate a new degradation snapshot only when a fresh batch is needed.
.\.venv\Scripts\python.exe src/corruptions.py --handoff --run-id p4_bdd_next

# Extract features, calibrate train references and score validation only.
.\.venv\Scripts\python.exe scripts/run_health.py prepare `
  --manifest data/manifests/augmented_p4_bdd_next.jsonl `
  --run-id p4_health_next

# Inspect reference sheets, validation tables and failure images before finalizing.
.\.venv\Scripts\python.exe scripts/run_health.py finalize `
  --run-dir data/features/p4_health_next `
  --reference-review-note '<describe the actual reference review>' `
  --validation-note '<describe the actual validation review and selected settings>'

.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`prepare --features <features.jsonl>` tái dùng feature snapshot hiện có; `--config`
nhận draft config khác nếu muốn thử hệ số mới. Review từng draft trên val rồi chọn
run để finalize. Không chỉnh code/input/draft giữa prepare và finalize; runner kiểm
tra hash. Template config vẫn draft, không thay bằng frozen config của dataset khác.
Người 5 đọc frozen config từ references artifact và dùng heuristic records riêng,
không đưa chúng vào validator ML prediction. Dữ liệu/output giữ local, không commit.

## Input và API

- Feature records đúng contract v1: đúng 7 feature, finite, 640×360.
- Metadata là manifest v1, join bằng `sample_id`, dùng lab `split`.
- Reference IDs do người 1 chọn và kiểm tra chất lượng. API `calibrate` nhận
  **chỉ feature rows của các ID đã chọn**, không tự chọn toàn bộ train.
- Reference bắt buộc original train, tự parent, severity 0; cần ít nhất một
  reference daytime và một reference night. Thiếu coverage/group thì fail rõ.
- Contrast được kiểm tra và lưu reference thống kê nhưng chưa tham gia score.
- Không xử lý ảnh, tạo degradation hoặc train model trong module này.

```python
from src.baseline import calibrate, score_health, score_bundle, freeze_references

# selected_reference_rows are selected using person 1's reference IDs.
references = calibrate(selected_reference_rows, manifest_rows, draft_config)
config = references["config"]
record = score_health(feature_row, "daytime", references, config)
val_scores = score_bundle(feature_rows, manifest_rows, references, config, split="val")

# Freeze only after the owner has reviewed validation results.
frozen = freeze_references(
    references, val_feature_rows, val_manifest_rows, config,
    note="Describe the validation review and the retained settings here.",
)
test_scores = score_bundle(
    feature_rows, manifest_rows, frozen, frozen["config"], split="test",
)
```

`score_bundle` kiểm tra feature/manifest coverage chính xác, duplicate, finite/range,
metadata, reference và sequence leakage. Input có thể là toàn bundle hoặc một
subset nhưng features và manifest phải chứa cùng bộ ID. Dùng `score_bundle` khi
chạy test: `score_health` chỉ nhận một frame và timeofday nên không biết split.
Validator manifest/features do người 5 quản lý vẫn cần chạy trước downstream;
module này không thay thế full JSON Schema validator.

## Công thức heuristic v1

Với mỗi feature `j` và mỗi nhóm reference `g`:

```text
c[g,j] = median(feature j of the selected reference originals)
m[g,j] = median(abs(feature j - c[g,j]))
s[g,j] = max(scale_floor[j], 1.4826 * m[g,j] * scale_multiplier)
p(j,d) = clip(d / s[g,j] - tolerance[j], 0, 1)

sharpness = p(log_laplacian_variance, c - x)
entropy   = p(entropy, c - x)
noise     = p(noise_residual, x - c)
exposure  = max(
    p(dark_ratio, x - c),
    p(saturation_ratio, x - c),
    p(median_luminance, abs(x - c))
)

health = clip(100 * (1 - sum(weight[k] * penalty[k])), 0, 100)
camera_weight = (health / 100)^2
```

Các `c` và `s` trong penalty thuộc đúng feature đang xét. Scale có unit của
feature; tolerance là phần scale, không phải giá trị pixel trực tiếp.
Floor tránh chia zero khi reference ít hoặc MAD=0. Exposure dùng max để không
cộng trùng ba dấu hiệu thường liên quan. Sharpness/entropy tăng vượt reference
không nhận điểm thưởng; residual thấp hơn reference không tự bị phạt.

Config khởi đầu: weights sharpness/exposure/noise/entropy = 0.3/0.3/0.3/0.1;
`scale_multiplier=3`; scale floors và tolerance từng feature nằm trong config.
Đây là lựa chọn heuristic để bắt đầu review, không phải hệ số đã được thực nghiệm
chứng minh. Không dùng severity/corruption/label làm đầu vào `_reference_score`.
Corruption và severity chỉ được đọc khi kiểm tra original reference hoặc diagnostic.

## Fixed, adaptive và action

- `health_fixed`: dùng tất cả original reference được chọn, gồm ngày và đêm.
- Metadata `daytime` → `mode=day`, dùng reference daytime.
- Metadata `night` → `mode=night`, dùng reference night.
- Metadata `dawn/dusk` hoặc `undefined` → `mode=fixed_fallback`, score adaptive
  bằng fixed; record thêm `fallback_reason`. Không suy mode từ luminance.
- `health_score=health_adaptive`; không round trước khi ghi JSON.
- Threshold khởi đầu: score ≥75 → `normal`; 45≤score<75 → `down_weight`;
  score<45 → `strong_down_weight`. Evaluator phải đọc config snapshot thực tế.

Record dùng `record_type=heuristic_health`, version `1.0.0` theo record tạm trong
sprint assignments. Không thêm probability hoặc ghi vào prediction ML schema.
`fallback_reason` là field giải thích bổ sung; người 5 sở hữu machine-readable
heuristic schema và cần đưa field này vào schema khi tích hợp.

## Policy, reference hash và freeze

`policy_id=heuristic-v1-<16 hex>` được dẫn xuất từ SHA256 của feature/formula version,
weights, scale multiplier/floors, tolerances, thresholds và reference hash.
Policy ID trong config template là ID draft chưa bound reference; calibration
trả config snapshot với ID đã bound, vì vậy dùng `references["config"]` để score.
Đổi hành vi scoring hoặc tập reference sẽ
đổi policy ID. `prepare_config` cập nhật ID khi sửa draft; CLI calibrate gọi helper
này. Config frozen không được chỉnh qua helper. Muốn thử cấu hình mới, dùng draft
với `frozen=false`, `reference_sha256=null`, `validation=null`, rồi calibration lại.

`references.json` chứa reference IDs, metadata tối thiểu, feature values, median/MAD
từng group, hash và **config snapshot**. Hash là SHA256 của JSON canonical UTF-8:
keys sorted, separators `(',', ':')`, không NaN; payload gồm feature version,
reference rows và groups. Thứ tự input calibration không đổi hash vì ID được sort.
Config snapshot giữ reference hash và artifact giữ `config_sha256` của toàn snapshot.
Artifact bị chỉnh sai hash/statistics hoặc
config khác calibration sẽ bị từ chối. Freeze giữ nguyên reference và policy,
thêm validation IDs/sequence IDs, hash feature/metadata/health và review note.

Freeze ghi nhận quyết định review của owner, không tự tối ưu threshold. Với label
chưa có, không có quality ground truth để tối ưu F1 hoặc false alarm. Review val
fixed/adaptive, phân bố original/degraded và failure; sửa draft parameters, chạy
calibration và val lại, rồi freeze. Chỉ sau freeze mới score test. Từ chối test
trong draft, kể cả `--split all`; kiểm tra reference/validation sequence không
lọt sang split khác. Không dùng kết quả test để chọn hệ số.

## CLI trên Windows

Chạy từ repo root bằng Python 3.12 hoặc phiên bản mới hơn. `python` dưới đây có
thể được thay bằng đường dẫn Python/venv hiện có. Mọi output được tạo với chế độ
exclusive: file đã tồn tại thì fail; dùng run_id mới để giữ snapshot bàn giao.
Ví dụ này yêu cầu input thật từ người 1 và 3; `lab_input` là run_id minh họa.

Reference ID file được hỗ trợ ở hai dạng:

```json
["train_day_001", "train_night_001"]
```

```json
{"day": ["train_day_001"], "night": ["train_night_001"]}
```

Dạng nhóm được đối chiếu metadata. Đây là adapter local; người 1/người 5 cần
thống nhất representation khi tích hợp vì contract chưa chốt cấu trúc file này.

```powershell
python src/baseline.py calibrate `
  --manifest data/manifests/augmented_lab_input.jsonl `
  --features data/features/lab_input/features.jsonl `
  --reference-ids data/manifests/reference_ids.json `
  --config configs/health.json `
  --output data/features/health_draft_01/references.json

python src/baseline.py score `
  --manifest data/manifests/augmented_lab_input.jsonl `
  --features data/features/lab_input/features.jsonl `
  --references data/features/health_draft_01/references.json `
  --split val `
  --output data/features/health_val_01/health_scores.jsonl

# Run only after reviewing val results and retaining the selected settings.
python src/baseline.py freeze `
  --manifest data/manifests/augmented_lab_input.jsonl `
  --features data/features/lab_input/features.jsonl `
  --references data/features/health_draft_01/references.json `
  --validation-note "Reviewed validation curves and failures; retained these settings." `
  --output data/features/health_frozen_01/references.json

python src/baseline.py score `
  --manifest data/manifests/augmented_lab_input.jsonl `
  --features data/features/lab_input/features.jsonl `
  --references data/features/health_frozen_01/references.json `
  --split test `
  --output data/features/health_frozen_01/health_scores.jsonl
```

CLI freeze chọn val từ input bundle; API freeze yêu cầu val-only. Chỉ ghi output
reference/health mới, không sửa feature, manifest, source ảnh, config template hay
snapshot cũ. `references.json["config"]` là config mà evaluator cần đọc; người 5
có thể gọi các API trực tiếp trong runner, không cần dùng CLI standalone này.

## Ngoại lệ và limitations

`find_score_increases(health_rows, metadata)` join synthetic với original parent,
báo ID, score field và độ tăng nếu fixed/adaptive lớn hơn original. Đây là
diagnostic sau scoring; không dùng metadata degradation để tính health. Truyền
health của cả original và synthetic; thiếu parent score thì fail. CLI score với
`--split all` báo số findings; evaluator có thể dùng API để lưu chi tiết trong report.
Không ép score giảm đơn điệu hoặc sửa điểm để làm curve đẹp.

- Noise có thể tăng Laplacian/entropy và giảm penalty của ảnh vốn kém; residual
  vẫn chứa texture và cạnh. Có thể xảy ra score tăng sau degradation.
- Reference khác nội dung cảnh nên thay đổi texture, contrast hoặc lighting có
  thể bị hiểu nhầm là suy giảm. Original reference cũng không chắc sạch.
- Mixed fixed reference có thể tạo mốc luminance giữa ngày và đêm; adaptive giúp
  đối chiếu nhưng cần đo trên dữ liệu thật. Dawn/dusk không có calibration riêng.
- Health là tổng penalty có trọng số: một dấu hiệu đơn lẻ có thể không chạm
  strong_down_weight. Hệ số/threshold khởi đầu không có ý nghĩa xác suất an toàn.
- Với reference ít, MAD/floors quyết định scale nhiều; cần xem phân bố và sample
  count của mỗi nhóm. Missing day/night bị chặn thay vì âm thầm giả adaptive.
- Chưa có labels, detector run hoặc fusion run: không báo F1, AP, fusion benefit
  hoặc độ tin cậy ADAS. Fixture chỉ kiểm tra phần mềm, không chứng minh mô hình.

## Trạng thái bàn giao local trước lượt BDD100K (lịch sử)

Code, config và công thức đã được triển khai. Calibration/tuning trên BDD100K
thật còn chờ manifest/features/reference IDs. Config template chưa frozen;
không biến fixture thành reference hoặc config thực nghiệm của nhóm.

Kiểm tra local bằng Python 3.12.14: 23 kiểm tra fixture đều pass, gồm API,
fixed/adaptive/fallback, train-only reference, coverage, finite/range, hash/policy,
val freeze/test protection, sequence leakage, score-increase diagnostic và CLI
calibrate → freeze → score. CLI cũng được kiểm tra từ chối overwrite snapshot.
Fixture và output của checks dùng temporary directory, đã được dọn sau khi chạy.
Không ghi thêm file vào `tests/` vì người 5 sở hữu phần này.

Bộ test contract hiện có được gọi bằng `python -m unittest discover -s tests -v`
nhưng bị dừng khi import vì interpreter local thiếu `jsonschema`. Đây là
dependency của contract tooling, không phải của baseline standard-library này;
requirements và môi trường dependency chưa bị chỉnh trong phần người 4.

Python đã dùng trên máy này nằm ở
`C:/Users/goose/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
Có thể chạy CLI help ngay trong PowerShell:

```powershell
& 'C:/Users/goose/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' src/baseline.py --help
```

## Lần chạy dữ liệu thật local ngày 05/10/2026

Đã đọc branch `origin/metric`, commit
`27d90997d73ca1784c3c28bdd03ed445dea746f6`. Branch này có module người 3
`src/features.py`, chưa có prepare-data/corruption module, manifest run,
reference IDs hoặc feature batch thật. Code health local được giữ khi tạo branch
`codex/health-metric` từ metric; không commit hoặc push.

Data local là mini-nuScenes/nuScenes-C, không phải BDD100K. Vì shared schema
chỉ nhận dataset BDD100K, lần chạy này dùng metadata adapter trong temporary
state để gọi trực tiếp API người 3/4. Không đổi schema hoặc giả dataset thành
BDD100K. Feature records và health records vẫn giữ đúng 7 feature/API và record
heuristic đã triển khai. Đây là pilot trên ảnh thật, chưa phải run integration
theo shared BDD100K manifest contract.

Kiểm tra data:

- `CAM_BACK`: đủ 404 original keyframe, 283 daytime và 121 night; toàn bộ decode
  và trích feature thành công. Resize original RGB 1600×900 về 640×360 bằng
  Pillow BILINEAR, rồi gọi `src.features.extract_features`.
- `CAM_FRONT`: 219/404 original keyframe đọc được; thiếu 185, gồm toàn bộ 121
  ảnh night. Không dùng camera này để giả so sánh day/night.
- `nuScenes-C/iso_noise/CAM_BACK`: 77 ảnh decode được và ghép đúng filename
  original. Ảnh corruption 1600×900, chưa có severity/seed/physical parameter
  handoff. Không resize hoặc đưa chúng vào batch synthetic chuẩn 640×360 này.
- Các thư mục corruption khác hiện chưa tìm thấy ảnh JPEG. Dataset local chưa
  đầy đủ cho chạy severity-response theo phân công người 2.

Run ID: `health_nuscenes_original_20261005_1fa0fd8f`.
Scene split cố định trước calibration: train gồm scene-0061/0103/0553/0655/0757/1077,
val gồm scene-0796/1094, test gồm scene-0916/1100. Tương ứng 243/80/81 original.
Mode lấy từ mô tả `Night` trong scene và giờ capture trong source log, không từ
luminance. Ba scene night cùng source log; dù scene không giao nhau giữa split,
không coi đây là kiểm chứng tổng quát hóa giữa các recording độc lập.

Reference pilot: 20 ảnh original train, gồm 10 daytime và 10 night, đã xem trên
contact sheet. Đây là reference tạm cho pilot, chưa phải bàn giao chính thức của
người 1. Ảnh night vẫn có noise tự nhiên và glare; không khẳng định reference sạch.
Calibration chỉ nhận các ID này, rồi score val. Review phân bố 80 val scores và
bốn ảnh night có score thấp nhất trước freeze. Giữ weights/scale và ngưỡng 75/45
minh họa do chưa có quality labels hoặc corruption validation; không tối ưu bằng
test. Sau freeze mới score test và xuất health cho toàn bộ 404 ID.

| Split/mode | Số ảnh | Fixed mean | Adaptive mean | Action adaptive |
|---|---:|---:|---:|---|
| train/day | 202 | 92.31 | 95.19 | 202 normal |
| train/night | 41 | 94.56 | 96.67 | 41 normal |
| val/day | 40 | 93.73 | 98.70 | 40 normal |
| val/night | 40 | 99.08 | 93.69 | 39 normal, 1 down_weight |
| test/day | 41 | 93.51 | 95.47 | 41 normal |
| test/night | 40 | 100.00 | 98.13 | 40 normal |

Adaptive không mặc định tốt hơn fixed. Frame val
`nusc_900bc0bbe72d450280ba29074520c926` có fixed=94.53, adaptive=74.05,
camera_weight=0.54836 và `down_weight`; ảnh có glare đèn mạnh và noise tự nhiên.
Đây là quan sát score/ảnh, không phải human quality label. 81 test originals đều
có action normal trong policy này, không suy ra detector accuracy hoặc camera an toàn.

Output local cuối cùng:

- `data/features/health_nuscenes_original_20261005_1fa0fd8f/references.json`
- `data/features/health_nuscenes_original_20261005_1fa0fd8f/health_scores.jsonl`

Draft reference và val score ở hai run directory riêng với suffix `_draft` và
`_val`, giữ nguyên snapshot. Config frozen nằm trong `references.json["config"]`;
`configs/health.json` vẫn là draft template. Output chứa 404 unique ID, các số
finite/in-range, đúng mode/action và công thức camera weight; kiểm tra reference
integrity/config snapshot hash đều pass. Thời gian đọc/resize/trích feature và
calibrate/score val đo được khoảng 13.6 giây trên máy local.

Policy ID: `heuristic-v1-7d70a79c48527899`.
Reference SHA256: `53a38379455e0d00d190853123405ef702a611e5dc6445d921338502205acfa8`.
Config SHA256: `61b9392bd2dfe24b6677feb4b79a624b6be7733b72ffa88181b8a8b73e356389`.
Source metadata hashes, image-bundle hash, feature-input hash, module hashes và
runtime versions nằm trong `references.json["provenance"]`.

Script pilot và temporary feature/metadata state được giữ để tái hiện local;
không thêm runner/schema hoặc logic vào file người 1–3/5:

```powershell
& 'C:/Users/goose/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' `
  'C:/Users/goose/AppData/Local/Temp/health_nuscenes_original_pilot_20261005.py' prepare

# Use the new state path printed by prepare after reviewing its val results.
& 'C:/Users/goose/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' `
  'C:/Users/goose/AppData/Local/Temp/health_nuscenes_original_pilot_20261005.py' finish `
  --state '<new state.json path>' `
  --validation-note '<describe the actual validation review>'
```

Mỗi lần prepare cấp run ID mới; không overwrite các file đã bàn giao. Tiếp tục
batch degraded cần người 1/2/5 thống nhất dataset adapter, metadata và preprocessing
của external corruption trước; chưa có severity-response hay nhãn chất lượng để
báo metric phân loại trong lần chạy này.

## Review trong lúc chờ degraded data

Đã hoàn tất audit 20 reference và sáu case validation, bảng penalty activation,
phân tích scale/deadband và nội dung handoff ngắn cho người 5. Kết quả chi tiết:

- [Review ảnh và phân tích](C:/Users/goose/.codex/visualizations/2026/10/05/01a10bb1-0dcb-7dc1-ab75-da2a2ef646a9/health_review_1fa0fd8f/review.md).
- [Reference day](C:/Users/goose/.codex/visualizations/2026/10/05/01a10bb1-0dcb-7dc1-ab75-da2a2ef646a9/health_review_1fa0fd8f/references_day.png).
- [Reference night](C:/Users/goose/.codex/visualizations/2026/10/05/01a10bb1-0dcb-7dc1-ab75-da2a2ef646a9/health_review_1fa0fd8f/references_night.png).
- [Case validation](C:/Users/goose/.codex/visualizations/2026/10/05/01a10bb1-0dcb-7dc1-ab75-da2a2ef646a9/health_review_1fa0fd8f/validation_cases.png).
- [Machine-readable review](C:/Users/goose/.codex/visualizations/2026/10/05/01a10bb1-0dcb-7dc1-ab75-da2a2ef646a9/health_review_1fa0fd8f/review.json).

20/20 reference là original train; feature khớp snapshot. Day bao phủ 5 scene,
night chỉ một scene với natural noise/glare nên vẫn cần người 1 duyệt reference.
Review ảnh không tạo nhãn human quality, không khẳng định reference clean.

Điểm quan trọng: case val 74.05 bị trừ 25.75 điểm bởi exposure driver
`median_luminance`, 0.20 điểm sharpness, 0 điểm noise/entropy. Noise penalty
không kích hoạt trên 404 originals; scale floor/deadband còn rộng. Day có 6/6
scale do floor quyết định, night có 5/6. Giữ các nhận xét này thành giả thuyết
để kiểm tra trên degraded val, không chỉnh hệ số theo kết quả test đã thấy.

### API và CLI giải thích score

`explain_health(feature_row, timeofday, references, config)` trả một object
diagnostics có `health_record`, `feature_values`, `fixed` và `adaptive`.
Mỗi phần chứa median reference, scales, deadbands, penalty chuẩn hóa, điểm trừ
có trọng số và `exposure_driver`. Exposure lấy **max**, không cộng ba tín hiệu.
Diagnostics không ghi thêm field vào health record hoặc giả probability.
Explanation là output local riêng, không thuộc shared ML/heuristic schema của
người 5. Like `score_health`, frame API không biết split; CLI kiểm tra qua bundle.

```python
from src.baseline import explain_health

# Use the config snapshot bound to the reference artifact.
details = explain_health(feature_row, source_timeofday, references, references["config"])
record = details["health_record"]
penalty_points = details["adaptive"]["penalty_points"]
exposure_driver = details["adaptive"]["exposure_driver"]
```

Khi có manifest/features đúng contract, CLI in JSON diagnostics ra stdout:

```powershell
python src/baseline.py explain `
  --manifest data/manifests/augmented_lab_input.jsonl `
  --features data/features/lab_input/features.jsonl `
  --references data/features/health_frozen_01/references.json `
  --sample-id '<sample_id to review>'
```

CLI kiểm tra coverage/full reference linkage và freeze cho split của frame:
draft val được phép, draft test bị chặn. Nên truyền cùng input bundle đã dùng
để scoring. Không ghi đè hoặc sửa score/reference/config khi explain.

Sau refactor, 404 health records khớp hoàn toàn với snapshot đã xuất và mọi
explanation fixed/adaptive cộng đúng điểm trừ. Chín kiểm tra bổ sung API/CLI đều
pass. Noise boundary được kiểm tra bằng feature fixture, chưa phải ảnh degraded
thực tế. Các config/source/output hash của run cũ được giữ nguyên; baseline có
thêm diagnostics API nên source hash của code hiện tại khác source hash đã ghi
cho lượt chạy cũ. Không đổi công thức, policy hoặc config frozen vì thay đổi này.

### Nội dung bàn giao người 5

- APIs: `calibrate`, `score_health`, `score_bundle`, `freeze_references`,
  `find_score_increases`; diagnostics tùy chọn: `explain_health`.
- Config thực tế: đọc `references.json["config"]`, kiểm tra `config_sha256`,
  `reference_sha256` và policy ID; template chỉ dành cho draft mới.
- Kết quả pilot/reference IDs/hash/output path và lệnh chạy nằm ở mục trên.
- NuScenes pilot dùng local metadata adapter, chưa hợp shared BDD100K manifest.
  Người 5 cần thống nhất dataset/schema trước run tích hợp; score record không
  được đưa vào validator ML prediction hiện tại.
- Khi tạo heuristic schema, cần hỗ trợ `mode=day/night/fixed_fallback` và field
  `fallback_reason` ở fallback; action phải theo thresholds trong config frozen.
- Chờ reference chính thức và augmented manifest/features trước calibration
  degraded val; nhận metadata severity/seed/parameters để phân tích paired response.
- Chưa có labels/detector/fusion run; limitations và đoạn pitch nằm trong review.

Để nhận degraded batch, cần đủ feature/manifest ID và original parents, RGB
640×360 đã resize trước corruption, cùng seed/config thực chạy, split/sequence
giữ nguyên với parent. Không resize lại synthetic hoặc đưa severity/name/label
vào scorer. Review val rồi freeze snapshot mới; báo cả score tăng nếu có và
camera weight là hệ số tương đối, không phải fusion weight đã chuẩn hóa.
