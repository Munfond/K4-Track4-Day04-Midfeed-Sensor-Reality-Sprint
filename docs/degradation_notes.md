# Người 2 — Degradation v1

## Bằng chứng mới: smoke trên ảnh thật, giữ đúng ownership

Đã nhận thư mục mini-nuScenes và nuScenes-C ở repo root. Contract hiện tại
vẫn có `dataset=bdd100k`; chưa có originals.jsonl chuẩn từ người 1. Người 2
không sửa schema, chuẩn bị split hoặc suy đoán weather/timeofday để vượt
validator. Không dùng ảnh nuScenes-C đã corruption làm original để áp thêm.

Đã chạy bốn loại × năm mức trên **6 ảnh thật CAM_FRONT của mini-nuScenes**,
chọn trải đều theo danh sách tên file, tạo **120 PNG** và **6 contact sheet**:

```bash
.venv/bin/python src/corruptions.py --image-smoke \
  --image-dir mini-nuScenes-20261005T155145Z-1-001/mini-nuScenes/samples/CAM_FRONT \
  --run-id p2_nuscenes_image_smoke_001 --limit 6
```

Output `data/generated/p2_nuscenes_image_smoke_001/image_smoke.json` ghi từng
ảnh nguồn/hash, loại/mức/tham số/seed, hash PNG, config/module hash và versions.
Đã kiểm tra PNG round-trip, replay pixel từng output và hash source không đổi.
Đã xem cả sáu contact sheet: blur tăng làm mất chi tiết, gain tăng có clipping,
gain giảm mất chi tiết vùng tối, noise tăng thể hiện rõ. Quan sát trực quan có
cảnh ban ngày và ban đêm; không dùng quan sát đó để tự gán field metadata.
Ảnh gốc đêm có sẵn noise/glare, minh họa original không đồng nghĩa ảnh sạch.

Đây là **diagnostic image-only**, `pipeline_ready=false`, không có augmented
manifest, nhãn hoặc split suy đoán. Người 3/5 không dùng image_smoke.json làm
manifest schema v1. Diagnostic IDs chỉ dùng truy vết test, không thay sample_id
của người 1. Việc này chứng minh module chạy được trên ảnh thật mà vẫn giữ
ownership của cả nhóm.

Sau bổ sung image-only smoke: **280 checks PASS, 12 unittest contract PASS**.
Fixture evidence: `data/generated/degradation_fixture_7gkliwnm/self_check.json`.
Không coi checks fixture là kết quả thực nghiệm nuScenes; lần ảnh thật ghi riêng.

Phần còn phụ thuộc upstream để chạy full integrated:

- Người 1: bàn giao originals manifest với ID/sequence/split/metadata và path ảnh.
- Người 5: thống nhất contract dataset phù hợp dữ liệu nuScenes, điều phối cập
  nhật schema/validator/downstream nếu nhóm đổi dataset.
- Người 2: sau khi nhận contract/manifest hợp lệ, chạy `--handoff` để sinh full
  augmented bundle, gửi người 3/5. Logic corruption và adapter đã sẵn sàng.

Code chia sẻ chỉ gồm ba file sở hữu người 2. Các thư mục dataset mới ở repo root
đang untracked, không nằm dưới data/raw gitignore; không stage cả repo hoặc
commit ảnh. Hãy chỉ stage ba file code/config/notes khi được yêu cầu commit.

## Ghép dữ liệu từ người 1: hướng dẫn nhanh

Code đã có adapter nhận delivery; người 1 không cần sửa code người 2.
Người 1 cung cấp hai thứ, cùng snapshot ổn định:

1. Ảnh nguồn trong repo, thường `data/raw/…`. Không cần tự resize.
2. `data/manifests/originals.jsonl` đúng manifest schema v1. `image_path` phải
   trỏ đúng file, dùng `/` và tương đối với repo root, không tương đối với thư
   mục manifest. Metadata/split/sequence do người 1 chuẩn bị trước corruption.

Không tự tạo manifest từ một folder ảnh vì thiếu nguồn metadata/split/sequence.
`reference_ids.json` của người 1 được người 4 sử dụng; degradation không thay đổi
hay yêu cầu file này. Không đổi metadata rainy/night theo nội dung synthetic.

Ví dụ cấu trúc (tên thư mục ảnh linh hoạt, miễn path trong manifest đúng):

```text
data/raw/bdd100k/images/train/abc123.jpg
data/manifests/originals.jsonl
```

Một record original mẫu (ID/metadata minh họa, không phải dữ liệu thật):

```json
{"schema_version":"1.0.0","record_type":"manifest","sample_id":"abc123","parent_image_id":"abc123","sequence_id":"seq123","dataset":"bdd100k","source_split":"train","image_path":"data/raw/bdd100k/images/train/abc123.jpg","split":"train","timeofday":"daytime","weather":"clear","corruption":"original","severity":0,"seed":null,"parameters":{},"label":null,"label_source":"unlabeled","label_rule_version":null}
```

Từ terminal WSL tại repo root:

```bash
# Kiểm tra đủ input, đọc/chuẩn bị được toàn bộ ảnh; không tạo output.
.venv/bin/python src/corruptions.py --preflight

# Một lệnh tạo gói bàn giao; thay run_id bằng ID người 5 cấp, chưa tồn tại.
.venv/bin/python src/corruptions.py --handoff --run-id p2_bdd_001

# Kiểm tra lại snapshot khi bàn giao; thêm --replay để so pixel tái sinh.
.venv/bin/python src/corruptions.py --verify --run-id p2_bdd_001
```

`--handoff` chạy preflight toàn bộ nguồn, smoke đại diện tối đa 6 ảnh, verify
smoke bằng replay, sinh full subset, rồi verify hash/shape/dtype/contract/coverage.
Kết quả:

| Artifact | Người nhận/cách dùng |
|---|---|
| `data/manifests/augmented_p2_bdd_001.jsonl` | Người 3 trích feature cho toàn bộ ID |
| `data/generated/p2_bdd_001/` | PNG full subset, config snapshot, run summary |
| `data/generated/p2_bdd_001/handoff.json` | Người 5 đọc machine-readable trạng thái và path |
| `data/generated/p2_bdd_001/handoff.md` | Count, hashes, record mẫu và giới hạn để bàn giao |
| `data/generated/p2_bdd_001_smoke/sanity/` | Review original và 5 mức của bốn loại |

Status handoff là `ready_for_review`: automatic checks đã pass, vẫn phải xem
contact sheet thật trước nghiệm thu. Không tự coi kiểm tra code là review chất
lượng hình ảnh hoặc xác nhận downstream đã chạy.

Nếu muốn xem smoke trước khi chạy full, dùng riêng:

```bash
.venv/bin/python src/corruptions.py --smoke --run-id p2_preview_001
.venv/bin/python src/corruptions.py --run-id p2_full_002
```

`--smoke` chọn ổn định theo ID, ưu tiên day/clear, night/clear, rainy; ghi warning
khi thiếu nhóm, không tạo dữ liệu/metadata giả. `--limit N` bình thường vẫn lấy N
record đầu; khi đi với `--smoke`, đặt số lượng smoke N. Full không hardcode 300.
`--handoff` không chấp nhận `--limit` để tránh gọi subset là full.

API tích hợp của người 5:

```python
from src.corruptions import inspect_inputs, generate_batch, run_handoff, verify_batch

originals, config, sources, readiness = inspect_inputs()
handoff = run_handoff(run_id="team_run_001")
# Hoặc runner kiểm soát từng giai đoạn:
summary = generate_batch("data/manifests/originals.jsonl", "team_run_002")
acceptance = verify_batch("team_run_002", replay=False)
```

Có thể truyền `--manifest`, `--config`, `--repo-root` rõ ràng; path relative
được resolve từ repo_root. Không cần copy ảnh nếu người 1 đã đặt ảnh ở path hợp
lệ trong repo. Không tự ghi đè source hoặc snapshot. Thiếu manifest/ảnh hỏng/sai
schema đều báo nguyên nhân vào stderr và CLI exit code 2; thành công exit code 0.
Preflight báo phân bố split/weather/timeofday và các nguồn có hash trùng để
người 1 review; không tự chỉnh split/loại bỏ dữ liệu.

## Phạm vi và tình trạng

Branch: `feat/degradation`. File sở hữu: `src/corruptions.py`,
`configs/corruptions.json`, tài liệu này. Không sửa tests/schema/requirements,
runner chung hoặc module người khác. Standalone CLI là adapter trong module
người 2; người 5 có thể gọi API từ runner tích hợp.

Đã triển khai bốn corruption bắt buộc, mỗi loại năm mức; rain overlay chưa
triển khai. Chưa có originals manifest/ảnh BDD100K trong checkout khi triển khai.
Các kiểm tra tại đây dùng ảnh nhân tạo, không phải kết quả BDD100K, không train
model hoặc suy ra độ tin cậy ADAS. Chưa chạy full subset và chưa bàn giao dữ liệu
thật cho downstream; bước này chờ input từ người 1.

## API và preprocessing

```python
from src.corruptions import degrade, generate_batch
output = degrade(image_rgb, corruption, severity, seed)
```

Input/output: NumPy RGB `uint8`, shape `(360, 640, 3)`. Không sửa input, trả
mảng mới. Sai shape/dtype/type/severity/seed hoặc corruption không hỗ trợ thì
raise `ValueError`. Import không chạy batch, đọc config, hoặc tạo output.

Ảnh nguồn: Pillow `convert('RGB')`, resize `(640,360)` bằng
`Image.Resampling.BILINEAR` trước corruption. Mỗi mức/type lấy trực tiếp từ
original đã chuẩn bị, không áp dụng cộng dồn. Synthetic lưu PNG RGB lossless;
đọc lại từng PNG và so sánh pixel với output trước khi hoàn tất batch.
Người 3 chuẩn bị original giống cách này; đọc synthetic trực tiếp, không resize
hoặc enhance lần nữa.

| Corruption | Tham số mức 1–5 | Công thức/implementation |
|---|---|---|
| gaussian_blur | sigma = 0.6, 1.2, 2.4, 4, 6 pixel | Pillow GaussianBlur(radius=sigma), xấp xỉ Gaussian bằng extended box filters |
| brightness_up | gain = 1.2, 1.5, 1.9, 2.5, 3.2 | RGB × gain |
| brightness_down | gain = 0.8, 0.6, 0.4, 0.25, 0.12 | RGB × gain |
| gaussian_noise | sigma = 5, 10, 20, 35, 50 trên thang 0–255 | RGB + N(0, sigma²), độc lập theo pixel/kênh |

Brightness/noise tính float64, clip [0,255], `np.rint` (ties-to-even), chuyển
uint8. Noise: `np.random.default_rng(seed)` cục bộ, không thay global RNG.
Blur/brightness xác định, seed vẫn được lưu theo contract nhưng không dùng RNG.

API bốn đối số `degrade` dùng đúng bảng mặc định cố định ở trên. Batch đọc bảng
trong `--config` và lưu tham số thực tế vào từng record. Nếu người 5 cần batch
custom config, gọi `generate_batch(...)`; không giả định `degrade` tự đọc config
custom hoặc thay đổi trạng thái toàn cục.

## Seed và provenance

Seed gốc mặc định `20261005`. Serialize tuple
`[base_seed, parent_image_id, corruption, severity]` bằng JSON UTF-8,
`ensure_ascii=True`, `separators=(',', ':')`. Lấy 8 byte đầu SHA256, chuyển sang
unsigned integer big endian. Không dùng Python hash(), run_id hoặc thứ tự dòng.
Cùng ảnh/config/seed và versions cho cùng pixel và hash PNG; không cam kết byte
giống nhau giữa mọi phiên bản Pillow/NumPy.

`run_summary.json` lưu số original/synthetic/record, count theo loại, SHA256
input/output manifest, config, snapshot config, source từng ảnh, PNG từng
synthetic, module Python, commit Git, versions và invocation. Module hash giúp
truy vết code chưa commit; commit Git không đủ để đại diện thay đổi chưa commit.
Hash input config là hash bytes file người chạy cung cấp; snapshot được format
lại nên có hash riêng. `config_snapshot.json` giữ cấu hình thực chạy.

## Manifest, output và chống ghi đè

ID: `<parent_id>_<corruption>_s<severity>`. Path:
`data/generated/<run_id>/<sample_id>.png`. Augmented manifest chứa nguyên record
original và thêm synthetic. Synthetic giữ dataset, sequence_id, source_split,
split, weather, timeofday; parent_image_id trỏ original. Mỗi synthetic mới:
`label=null`, `label_source=unlabeled`, `label_rule_version=null`; không kế thừa
nhãn parent, không suy ra nhãn từ severity.

Với N originals: 20N synthetic, 21N record. Smoke N=6: 120 PNG, 126 record.
Nếu N=300: 6.000 PNG, 6.300 record (chưa thực chạy trên BDD100K).
`--limit 6` lấy sáu record đầu, không bảo đảm đủ day/night/rain; người 1/5 cần
chọn smoke manifest đại diện nếu thứ tự dữ liệu không có đủ nhóm.

Batch validate input, chỉ nhận originals; kiểm tra nguồn đọc được, path ở trong
repo và ID không trùng trước khi tạo ảnh. Chạy validator trên augmented, kiểm
tra count, source/manifest/config hash không đổi trong lần chạy. Existing
run directory hoặc augmented manifest bị từ chối; không có chế độ overwrite.
Lỗi giữa batch giữ partial directory để kiểm tra, báo sample ID; chưa publish
augmented manifest cho batch chưa hoàn tất. Chạy lại bằng run_id mới.
Một process duy nhất ghi mỗi snapshot. Không tự xóa output cũ.

## Lệnh sử dụng trong WSL, từ repo root

Môi trường kiểm tra hiện có `.venv`; dependency đã nằm trong requirements chung.
Không thay file dependency do người 5 sở hữu.

```bash
# Kiểm tra với ảnh nhân tạo; tự tạo fixture và giữ bằng chứng trong generated/.
.venv/bin/python src/corruptions.py --self-check

# Smoke bằng input thật từ người 1 (run_id ví dụ, phải là ID chưa tồn tại).
.venv/bin/python src/corruptions.py \
  --manifest data/manifests/originals.jsonl \
  --config configs/corruptions.json --run-id p2_smoke_001 --limit 6

.venv/bin/python scripts/validate_contract.py \
  --manifest data/manifests/augmented_p2_smoke_001.jsonl --check-files

# Full: dùng run_id được người 5 cấp, bỏ --limit.
.venv/bin/python src/corruptions.py \
  --manifest data/manifests/originals.jsonl \
  --config configs/corruptions.json --run-id p2_full_001

.venv/bin/python scripts/validate_contract.py \
  --manifest data/manifests/augmented_p2_full_001.jsonl --check-files

.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

CLI `--sanity-count` mặc định 6. Contact sheet:
`data/generated/<run_id>/sanity/<parent_id>.png`: 4 hàng corruption × 6 cột
original/mức 1–5, ghi loại/mức/tham số; parent ID nằm trong tên file.
Ảnh thu nhỏ chỉ phục vụ quan sát, không phải ảnh input feature. Downstream phải
dùng augmented manifest, không glob tất cả PNG vì generated còn có contact sheet.

## Kiểm tra nghiệm thu và bằng chứng

Self-check sử dụng gradient, ảnh mức sáng cố định và checkerboard; batch sáu
ảnh thử có kích thước nguồn khác và một ảnh grayscale. Metadata day/night/rain
là fixture để kiểm tra giữ nguyên field; không mô phỏng dữ liệu BDD100K thật.
Field dataset=bdd100k chỉ đáp ứng enum schema, có marker `FIXTURE_ONLY.txt`.

Các nhóm kiểm tra:

- 20 tổ hợp: shape/dtype, không sửa input, trả mảng mới, cùng seed tái hiện,
  giữ global RNG.
- Noise khác seed khác pixel; kiểm tra brightness, noise RMS và blur edge
  response trên ảnh kiểm thử có kiểm soát. Không yêu cầu health/feature thật
  phải luôn đơn điệu.
- Batch đủ 6+120=126 record; hai run có hash PNG giống nhau; đảo thứ tự input
  vẫn có cùng hash theo ID; `--limit` đúng coverage.
- Original record/metadata được giữ, synthetic không tự có nhãn; saved output
  được so với fresh API từ original để phát hiện degradation cộng dồn.
- Từ chối input sai, run_id nguy hiểm, config sai, snapshot đã có, thiếu nguồn;
  lỗi preflight không tạo thư mục batch.
- Validator của repo chạy trên bundles; PNG round-trip và source hash được
  kiểm tra ở runtime. Test contract chung chạy riêng, không sửa tests/.

`--self-check` in thư mục artifact. Trong đó có `self_check.json`, input fixture,
run summaries và sanity sheets. Đây là bằng chứng kiểm tra module; trước handoff
thật phải chạy `--check-files` và review contact sheet BDD100K.

Lần kiểm tra trước khi bổ sung adapter ngày 2026-10-05: **262 checks PASS**, **12 unittest contract PASS**,
`git diff --check` PASS. Môi trường Python 3.12.3, NumPy 2.5.3, Pillow 12.3.0.
Artifacts local:
`data/generated/degradation_fixture_8qxn4nsn/self_check.json`.
Smoke fixture: 6 original, 120 synthetic, 126 record; repeat/reordered hash PNG
giống nhau. Đây không phải số đo trên dataset BDD100K.

Nghiệm thu adapter mới ngày 2026-10-05: **278 checks PASS**, **12 unittest
contract PASS**. Artifact:
`data/generated/degradation_fixture_vwz488ff/self_check.json`.
Đã chạy cả CLI `--preflight`, `--verify`, `--handoff` thực tế với fixture root;
handoff smoke/full đủ 126 record, replay smoke pass, gói JSON/Markdown tồn tại.
Ảnh nguồn hỏng và delivery thiếu bị từ chối với thông báo rõ, không tạo output
batch. PNG bị thay đổi bị verification phát hiện. Dữ liệu thật vẫn chờ người 1.

## Handoff cho người 3 và người 5

Phút 45: gửi smoke manifest, generated path, command thực chạy, config/hash,
seed rule, run_summary, một record synthetic và ảnh sanity day/night/rain có
sẵn. Sau smoke gửi full batch và count thực tế. Người 3 nhận input augmented
để trích feature cho toàn bộ ID; người 5 validate và ghép runner.
Không commit ảnh/data/fixture generated; chỉ ba file thuộc ownership. Không
tự push/merge; người 5 merge PR. Handoff cần ghi dataset thật hay fixture,
limitations và mọi lỗi còn tồn tại.

## Giới hạn cần trình bày khi chấm/báo cáo

Gaussian blur chỉ mô phỏng một phần mất nét; không đại diện đầy đủ motion blur.
Brightness gain trong RGB 8 bit không phải mô hình vật lý của exposure/HDR/glare.
Gaussian noise độc lập không mô phỏng đầy đủ shot/read noise, tương quan màu
hoặc ISP. Clipping ảnh hưởng phân bố noise và gây saturation ở brightness.
Rain overlay tùy chọn chưa triển khai. V1 chưa cover rolling shutter, lens
soiling hoặc glare cục bộ. Original có thể vốn xấu; ảnh đêm/mưa không tự là
unusable. Severity là tham số mô phỏng, không phải nhãn chất lượng.
Noise có thể tăng sharpness/entropy và làm heuristic tăng score; chuyển ngoại lệ
cho người 3/4/5 review. Chưa đo detector AP, chưa train model, chưa chứng minh
fusion benefit hoặc ADAS reliability.
