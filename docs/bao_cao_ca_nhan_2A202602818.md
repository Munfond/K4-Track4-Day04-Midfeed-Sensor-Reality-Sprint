# BÁO CÁO CÁ NHÂN — NGƯỜI 2: DEGRADATION

**Họ và tên:** Bùi Đình Đề  
**Mã số sinh viên:** 2A202602818  
**Bài thực hành:** Lab04 — Track4 — Midfeed Sensor Reality Sprint  
**Vai trò:** Người 2 — Tạo suy giảm chất lượng ảnh camera có kiểm soát  
**Nhánh làm việc:** `feat/degradation`  
**Ngày lập báo cáo:** 05/10/2026

## 1. Mục tiêu và phạm vi công việc

Phần việc cá nhân tập trung xây dựng module degradation để tạo các biến thể
ảnh camera theo loại và mức độ suy giảm. Các ảnh này là đầu vào cho người 3
trích xuất feature và người 4 đánh giá health heuristic; người 5 tích hợp pipeline.
Phạm vi sprint hiện tại chưa gồm huấn luyện model.

Các yêu cầu chính là triển khai blur, tăng sáng, giảm sáng và Gaussian noise,
mỗi loại năm mức; giữ đúng định dạng ảnh, tái hiện được bằng seed, bảo toàn ảnh
nguồn và metadata, đồng thời cung cấp bằng chứng kiểm tra và tài liệu bàn giao.
Rain overlay là tùy chọn và chưa được triển khai.

Trạng thái tại thời điểm báo cáo: **đã hoàn thành code, kiểm thử fixture và smoke
trên ảnh thật; chưa nghiệm thu full pipeline trên dữ liệu thật** do còn thiếu
originals manifest và cần thống nhất contract dataset giữa người 1/người 5.

## 2. Các sản phẩm đã thực hiện

| Sản phẩm | Nội dung |
|---|---|
| `src/corruptions.py` | API degradation, xử lý ảnh, preflight, smoke/full, verification và adapter bàn giao |
| `configs/corruptions.json` | Tham số năm mức của bốn corruption, schema version và base seed |
| `docs/degradation_notes.md` | Hướng dẫn tích hợp, lệnh chạy, kiểm thử, kết quả và limitations |
| Báo cáo cá nhân này | Tổng hợp đóng góp, bằng chứng, trạng thái nghiệm thu và phụ thuộc |

Không sửa logic feature/health, schema chung, requirements, tests chung hoặc
runner do thành viên khác sở hữu. Các phép kiểm tra riêng đặt trong self-check
của module degradation; bộ test contract hiện có được chạy lại mà không sửa.

## 3. Thiết kế và triển khai

### 3.1. API và chuẩn bị ảnh

API đúng interface đã thống nhất:

```python
degrade(image_rgb, corruption, severity, seed) -> image_rgb
```

Input/output là NumPy RGB `uint8`, shape `(360, 640, 3)`. API kiểm tra kiểu dữ
liệu, kích thước, loại corruption, severity và seed; trả mảng mới và không sửa
mảng đầu vào. Import module không tự chạy workload.

Ảnh nguồn được chuyển RGB và resize về 640×360 bằng Pillow BILINEAR trước
corruption. Mỗi loại và mỗi mức đều bắt đầu trực tiếp từ original đã chuẩn bị,
không biến đổi cộng dồn. Ảnh synthetic được lưu PNG và đọc lại để kiểm tra
pixel, mode và kích thước.

### 3.2. Bốn loại corruption và năm mức

| Loại | Tham số mức 1 → 5 | Phương pháp |
|---|---|---|
| Gaussian blur | sigma: 0.6, 1.2, 2.4, 4, 6 pixel | Pillow GaussianBlur, xấp xỉ Gaussian bằng extended box filters |
| Brightness up | gain: 1.2, 1.5, 1.9, 2.5, 3.2 | Nhân RGB với gain |
| Brightness down | gain: 0.8, 0.6, 0.4, 0.25, 0.12 | Nhân RGB với gain |
| Gaussian noise | sigma: 5, 10, 20, 35, 50 | Cộng nhiễu độc lập theo pixel/kênh trên thang RGB 0–255 |

Brightness và noise tính bằng float64, clip về [0,255], làm tròn bằng
`np.rint` rồi chuyển về uint8 để tránh overflow. API bốn đối số dùng bảng
mặc định; batch adapter nhận config riêng và ghi tham số thực chạy.

### 3.3. Tái hiện và bảo toàn nguồn

Base seed là `20261005`. Seed từng synthetic được suy ra từ SHA256 của tuple
`[base_seed, parent_id, corruption, severity]`, lấy tám byte đầu theo big endian.
Noise dùng `np.random.default_rng(seed)` cục bộ; không dùng Python hash() hoặc
thay đổi global RNG. Run ID và thứ tự dòng không ảnh hưởng seed.

Các batch lưu SHA256 của nguồn, manifest, config, module và PNG đầu ra, kèm
phiên bản thư viện. Snapshot output đã có sẽ bị từ chối ghi đè. Nếu batch lỗi,
thông báo chỉ rõ ảnh liên quan; partial output được giữ để kiểm tra.

### 3.4. Luồng tích hợp

Đã triển khai các chế độ:

- `--preflight`: kiểm tra originals manifest và khả năng đọc/chuẩn bị toàn bộ
  ảnh; báo phân bố metadata, nguồn trùng và nhóm smoke còn thiếu.
- `--smoke`: chọn ổn định các ảnh đại diện theo metadata có sẵn.
- Batch mặc định: sinh augmented manifest chứa nguyên original và synthetic.
- `--verify`, tùy chọn `--replay`: kiểm tra coverage, tham số, seed, hash,
  định dạng ảnh và pixel tái sinh.
- `--handoff`: preflight → smoke → full → verification → gói JSON/Markdown.
- `--image-smoke`: kiểm chứng API trên ảnh thật khi chưa có manifest hợp lệ;
  không suy đoán nhãn, metadata hoặc split.

Với manifest hợp lệ, mỗi original tạo 20 synthetic, tổng 21 record gồm original.
Synthetic giữ metadata/split của parent; nhãn chưa đánh giá giữ null và không
được suy ra từ severity. Downstream phải đọc manifest, không glob mọi PNG vì
thư mục generated còn chứa contact sheet phục vụ quan sát.

## 4. Kiểm thử và kết quả

### 4.1. Kiểm thử bằng fixture

Môi trường chạy: Python 3.12.3, NumPy 2.5.3, Pillow 12.3.0 trong WSL.

**Kết quả:** 280 checks trong self-check và 12 unittest contract đều PASS.
280 checks là các phép kiểm tra trong self-check, không phải 280 unittest
độc lập và không phải số mẫu của dataset thật.

Nội dung kiểm chứng gồm shape/dtype, không sửa input, global RNG không đổi,
seed tái hiện, noise khác seed khác pixel, phản ứng severity trên ảnh kiểm thử,
không corruption cộng dồn, coverage, metadata, chống overwrite, phát hiện ảnh
hỏng, config sai, input thiếu và PNG bị chỉnh sửa.

Batch fixture sáu ảnh tạo 120 synthetic và 126 record. Các lần chạy cùng cấu
hình và khi đảo thứ tự manifest có cùng hash PNG theo ID. Các CLI preflight,
verify và handoff đã được kiểm thử thực tế với fixture root.

Bằng chứng:
`data/generated/degradation_fixture_7gkliwnm/self_check.json`.
Fixture là dữ liệu nhân tạo, không phải kết quả BDD100K hoặc nuScenes.

### 4.2. Smoke trên ảnh thật

Sau khi nhận dữ liệu, kiểm tra thấy các thư mục là mini-nuScenes và nuScenes-C.
Đã chọn trải đều sáu ảnh từ **404 ảnh ứng viên CAM_FRONT của mini-nuScenes**
theo thứ tự tên file; đây không phải subset được chia train/val/test.
Không dùng ảnh nuScenes-C đã bị corruption làm original.

| Hạng mục | Kết quả thực chạy |
|---|---:|
| Ảnh nguồn được xử lý | 6 |
| Loại corruption | 4 |
| Mức mỗi loại | 5 |
| Synthetic PNG | 120 |
| Contact sheet đã xem | 6 |

Đã kiểm tra PNG round-trip, cùng seed tái hiện cùng pixel và hash nguồn không
đổi. Quan sát cả sáu contact sheet cho thấy blur tăng làm mất chi tiết, tăng
sáng có clipping, giảm sáng mất chi tiết vùng tối và noise tăng thể hiện rõ.
Có cảnh ngày và đêm trong quan sát trực quan; không dùng quan sát này để tự gán
timeofday/weather vào metadata. Ảnh đêm có noise/glare sẵn, cho thấy original
không mặc nhiên là ảnh chất lượng tốt.

Run ID: `p2_nuscenes_image_smoke_001`. Bằng chứng:

- `data/generated/p2_nuscenes_image_smoke_001/image_smoke.json`.
- `data/generated/p2_nuscenes_image_smoke_001/images/`.
- `data/generated/p2_nuscenes_image_smoke_001/sanity/`.

Run thật là diagnostic image-only: `pipeline_ready=false`,
`manifest_generated=false`. **Không có 126 record augmented cho run thật**;
con số 126 record ở trên chỉ thuộc batch fixture.

## 5. Đối chiếu yêu cầu nghiệm thu

| Yêu cầu người 2 | Trạng thái và bằng chứng |
|---|---|
| Bốn corruption, mỗi loại năm mức | Đã triển khai và chạy đủ 120 output trên sáu ảnh thật |
| RGB uint8, 640×360, resize trước corruption | Đã kiểm tra API và PNG round-trip |
| Seed ổn định, RNG cục bộ | Fixture PASS; replay từng output của smoke thật PASS |
| Mỗi mức từ original, không cộng dồn | Đã kiểm chứng bằng đối chiếu saved output với fresh API |
| Không sửa nguồn hoặc overwrite snapshot | Hash nguồn smoke thật không đổi; kiểm tra overwrite PASS |
| Manifest giữ parent/metadata/split, nhãn đúng | Đã triển khai và kiểm chứng trên fixture; chờ input thật hợp lệ |
| Smoke và ảnh sanity | Đã chạy sáu ảnh thật và review sáu contact sheet |
| Full subset và bàn giao downstream | Adapter sẵn sàng; chưa thực chạy full integrated hoặc xác nhận người 3/5 đọc output |

## 6. Phụ thuộc và giới hạn

Schema hiện tại chỉ chấp nhận `dataset="bdd100k"`, trong khi dữ liệu nhận được
là nuScenes. Chưa có `data/manifests/originals.jsonl` do người 1 bàn giao.
Để giữ đúng nguồn và ownership, không đổi nuScenes thành BDD100K, không tự tạo
split/metadata và không sửa contract của người 5.

Người 1 cần cung cấp originals manifest; người 5 cần điều phối contract phù hợp
dataset nếu nhóm chuyển sang nuScenes. Khi input và contract hợp lệ, phần người
2 có thể chạy handoff để sinh full augmented bundle. Chưa xác nhận downstream
đã chạy, chưa commit/push phần code ở thời điểm lập báo cáo.

Gaussian blur chỉ mô phỏng một phần mất nét; brightness gain không phải mô
hình exposure/HDR/glare vật lý. Noise Gaussian không mô phỏng đầy đủ noise cảm
biến hoặc ISP; clipping ảnh hưởng phân bố đầu ra. Rain overlay chưa triển khai.
Severity không phải nhãn quality; chưa đo health, train model, detector AP,
fusion benefit hoặc ADAS reliability. Noise có thể làm sharpness/entropy tăng,
cần chuyển ngoại lệ cho người 3/4/5 khi đánh giá.

## 7. Lệnh tái hiện và bàn giao

Từ terminal WSL tại repo root:

```bash
# Kiểm tra fixture; mỗi lần tạo thư mục evidence mới.
.venv/bin/python src/corruptions.py --self-check
.venv/bin/python -m unittest discover -s tests -v

# Lặp smoke thật với run_id mới để giữ snapshot đã có.
.venv/bin/python src/corruptions.py --image-smoke \
  --image-dir mini-nuScenes-20261005T155145Z-1-001/mini-nuScenes/samples/CAM_FRONT \
  --run-id p2_nuscenes_image_smoke_002 --limit 6

# Chỉ chạy khi người 1/5 đã cung cấp input và contract hợp lệ.
.venv/bin/python src/corruptions.py --preflight
.venv/bin/python src/corruptions.py --handoff --run-id team_p2_001
```

Tài liệu bàn giao kỹ thuật: [degradation_notes.md](degradation_notes.md).
Chỉ chia sẻ code/config/tài liệu qua Git; ảnh và evidence generated giữ local.
Các path evidence nêu trong báo cáo tồn tại ở workspace hiện tại, không được
đóng gói kèm báo cáo Markdown. Khi nộp riêng cần gửi các contact sheet và JSON
evidence cùng báo cáo theo phương thức bàn giao của nhóm.
