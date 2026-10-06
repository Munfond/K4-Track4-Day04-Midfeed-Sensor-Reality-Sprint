# Data notes — Người 1 (data/reference)

## Nguồn

- BDD100K **val 10k** (100k images), qua mirror FiftyOne trên Hugging Face [`dgural/bdd100k`](https://huggingface.co/datasets/dgural/bdd100k) — ảnh JPEG 1280×720 + `samples.json` chứa `weather`/`timeofday` gốc của BDD100K. Dùng theo [BDD100K License](https://doc.bdd100k.com/license.html#license) (giáo dục/nghiên cứu).
- Vì mirror chỉ có split val gốc, **mọi record có `source_split=val`**; lab split `train/val/test` là chia lại bên trong subset này. Không dùng record này để so sánh với benchmark BDD100K val chính thức.
- Có thể chuyển sang bản tải chính thức: đặt `metadata_format: "bdd100k"` và trỏ `metadata_path` tới file label JSON chính thức (`[{name, attributes:{weather,timeofday}}]`), `image_dir` tới thư mục ảnh tương ứng, `source_split` đúng split.

## Lệnh tái hiện

```powershell
# metadata (71 MB) — chỉ cần một lần
curl.exe -L -o data/raw/bdd100k_hf/samples.json https://huggingface.co/datasets/dgural/bdd100k/resolve/main/samples.json
.\.venv\Scripts\python.exe src/prepare_data.py --config configs/data.json --download --contact-sheet data/raw/reference_contact_sheet.png
.\.venv\Scripts\python.exe scripts/validate_contract.py --manifest data/manifests/originals.jsonl --check-files
```

`--download` chỉ tải ảnh được chọn (~300 ảnh, ~15 MB) vào `data/raw/bdd100k/images/val/`. Ảnh nguồn chỉ đọc; script không sửa/ghi đè ảnh đã có. Chạy lại cùng config cho cùng manifest (đã kiểm tra hash trùng giữa hai lần chạy).

## Chọn subset (`configs/data.json`, seed 20261005)

| Nhóm | Điều kiện metadata | Số ảnh |
|---|---|---:|
| day_clear | timeofday=daytime, weather=clear | 100 |
| night_clear | timeofday=night, weather=clear | 100 |
| rainy | weather=rainy, daytime hoặc night | 100 (59 day, 41 night) |

Thứ tự ứng viên: sort tên rồi shuffle bằng `random.Random("<seed>:<group>")` (seed chuỗi ổn định, không dùng `hash()`). Ảnh không qua kiểm tra bị bỏ và lấy ứng viên kế tiếp.

Kiểm tra từng ảnh: Pillow `verify()` + decode lại, JPEG, kích thước 1280×720, convert RGB được, SHA256 không trùng; tên file khớp key metadata (ảnh được chọn trực tiếp từ metadata theo tên). Lần chạy data-v1: **0 ảnh bị loại**, 0 trùng.

Night/rain **không** mặc định là kém chất lượng; weather/timeofday là metadata nguồn, không phải nhãn quality.

## Split

- 60/20/20 theo **sequence**, trước corruption, stratified theo nhóm (sequence gán theo nhóm đa số).
- BDD100K 100k images lấy 1 frame/video nên không có sequence ID thật. Dùng **prefix tên video** (phần trước `-`, ví dụ `b1d22449` của `b1d22449-15fb948f`) làm `sequence_id` — gom bảo thủ các video có cùng prefix (khả năng cùng thiết bị/chuyến đi). **Chưa kiểm chứng** prefix tương ứng chuyến đi; video khác prefix vẫn có thể cùng địa điểm → leakage cảnh/địa điểm chưa loại trừ được.
- Kết quả data-v1: 300 ảnh, 288 sequence.

| Nhóm | train | val | test |
|---|---:|---:|---:|
| day_clear | 61 | 20 | 19 |
| night_clear | 60 | 19 | 21 |
| rainy | 59 | 21 | 20 |
| **Tổng** | 180 | 60 | 60 |

## Reference (`data/manifests/reference_ids.json`)

- Chỉ lấy original **train**; day từ day_clear, night từ night_clear; 10 ảnh mỗi mode; `fixed` = hợp 20 ảnh.
- Lọc QC trên ảnh đã chuẩn bị theo contract (RGB → 640×360 BILINEAR → Pillow L): median luminance, dark ratio (Y≤5), saturation ratio (Y≥250), ln(1+Var(Laplacian)). Ngưỡng nằm trong config. Trong ứng viên đạt QC, chọn ảnh gần median nhóm nhất (luminance, sharpness) — ảnh "điển hình", không phải đẹp nhất.
- Ứng viên train đạt QC: day 50/61, night 43/60.
- File lưu SHA256 manifest + config để người 4 kiểm tra đúng phiên bản.
- **Xem trực quan (contact sheet 20 ảnh):** cả 20 ảnh đọc được, đường/xe nhìn rõ, không bị mờ hay cháy sáng nặng. Ghi chú: phần lớn có nắp capo/dashboard ở đáy khung hình và một số bị phản chiếu kính; 1 ảnh day có giá đỡ điện thoại lọt vào khung; 1 ảnh night (`c33251a6-812a0ea8`) mặt đường ướt dù metadata `clear`. Không loại ảnh nào; `visual_review` để `pending` cho đến khi nhóm xác nhận.

## Rubric nhãn (cho giai đoạn annotation sau)

Sprint này **chưa gán nhãn**: mọi record `label=null`, `label_source=unlabeled`.

- Task/ROI cố định: nửa dưới khung hình, phía trên nắp capo (khoảng hàng 45%–85% chiều cao), nơi có làn đường/xe/người phía trước.
- `good`: quan sát được vạch làn và đối tượng mục tiêu trong ROI.
- `degraded`: vẫn dùng được nhưng mất chi tiết đáng kể (vạch làn mờ, đối tượng xa khó thấy).
- `unusable`: không đủ quan sát cho nhiệm vụ trong ROI.
- Chọn vài mẫu cho 2 người gán độc lập, giải quyết bất đồng trước khi khóa nhãn; không xem health score khi gán.

## Limitations

- Chỉ 1 split nguồn (val), 300 ảnh; rainy lệch về day (59/41); không có dawn/dusk, snowy, foggy trong subset.
- Sequence grouping là xấp xỉ (xem trên). Ảnh original không được khẳng định là sạch: có phản chiếu kính, dashboard, motion blur nhẹ ban đêm.
- Metadata thời tiết do người gán BDD100K, có thể sai (ví dụ ảnh night `clear` có mặt đường ướt).
- Ngưỡng QC reference là heuristic chọn tay, chưa tune.
