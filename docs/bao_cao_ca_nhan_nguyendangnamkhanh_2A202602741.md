# BÁO CÁO CÁ NHÂN — NGƯỜI 1: DATA/REFERENCE

**Họ và tên:** Nguyễn Đặng Nam Khánh  
**Mã số sinh viên:** 2A202602741  
**Bài thực hành:** Lab04 — Track4 — Midfeed Sensor Reality Sprint  
**Vai trò:** Người 1 — Chọn subset BDD100K, kiểm tra ảnh, chia split theo sequence, chọn reference train  
**Nhánh làm việc:** `feat/data`  
**Ngày lập báo cáo:** 06/10/2026

## 1. Problem

Phần việc của tôi là tạo dữ liệu đầu vào đáng tin cho cả pipeline data → degradation → feature → health → evaluation. Nền tảng là prototype Python chạy offline trên Windows, dùng ảnh RGB camera đường phố BDD100K cho bài toán giám sát camera ADAS/robot mặt đất; nhóm chưa đo camera vật lý hay triển khai trên xe/drone.

Downstream phụ thuộc trực tiếp vào ba thứ tôi bàn giao: (1) **metadata** `timeofday`/`weather` — health adaptive của người 4 chọn reference ngày/đêm theo metadata, không theo độ sáng frame; (2) **split** — nếu cùng sequence rơi vào cả train và test thì calibration rò rỉ sang test; (3) **reference train** — nếu reference không đại diện thì mọi penalty bị lệch. Weather/timeofday là metadata nguồn, không phải nhãn chất lượng; ảnh đêm hay mưa không mặc định là kém.

Đóng góp của tôi là [src/prepare_data.py](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/blob/35619f012fdd53b1cc260bd7e7ecfb4fc4bab378/src/prepare_data.py), [configs/data.json](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/blob/35619f012fdd53b1cc260bd7e7ecfb4fc4bab378/configs/data.json), [docs/data_notes.md](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/blob/35619f012fdd53b1cc260bd7e7ecfb4fc4bab378/docs/data_notes.md) và hai output `data/manifests/originals.jsonl`, `data/manifests/reference_ids.json`. Corruption, feature, health và evaluation thuộc người 2–5; tôi không nhận các phần đó.

**Trạng thái:** đã bàn giao data và **đã push code/config/notes** lên `origin/feat/data` ([commit `35619f0`](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/35619f012fdd53b1cc260bd7e7ecfb4fc4bab378)), nhưng nhánh **chưa được merge vào main**. Vì vậy audit nhóm (checkout main) ghi “chưa replay được bước chọn subset”. Mục 3 bổ sung lượt replay từ đúng commit này.

## 2. Method

**Nguồn dữ liệu:** [BDD100K](https://github.com/bdd100k/bdd100k) (Yu và cộng sự, CVPR 2020), qua bản FiftyOne trên Hugging Face [`dgural/bdd100k`](https://huggingface.co/datasets/dgural/bdd100k): 10.000 ảnh của split **val** gốc, JPEG 1280×720, kèm `weather`/`timeofday` gốc. Dùng theo [BDD100K License](https://doc.bdd100k.com/license.html#license). Vì nguồn chỉ có split val, mọi record có `source_split=val`; train/val/test của lab là chia lại bên trong subset.

**Chọn subset (seed 20261005):** 3 nhóm × 100 ảnh — `day_clear` (daytime+clear), `night_clear` (night+clear), `rainy` (rainy, daytime hoặc night). Ứng viên được sort theo tên rồi shuffle bằng `random.Random("<seed>:<group>")` (seed chuỗi ổn định giữa các process, không dùng `hash()`). Ảnh lỗi bị bỏ và lấy ứng viên kế tiếp. `--download` chỉ tải ~300 ảnh được chọn, ảnh nguồn chỉ đọc.

**Kiểm tra ảnh:** Pillow `verify()` rồi decode lại, định dạng JPEG, kích thước 1280×720, convert RGB được, SHA256 byte không trùng; tên file là key metadata nên metadata khớp theo cấu trúc.

**Split theo sequence:** BDD100K 100k images lấy 1 frame/video nên không có sequence ID thật. Tôi dùng **prefix tên video** (phần trước `-`, ví dụ `b329fe7d` của `b329fe7d-f06455d3`) làm `sequence_id` để gom bảo thủ các video cùng prefix. Mỗi sequence gán cả khối vào train/val/test theo tỷ lệ 60/20/20, stratified theo nhóm (shuffle sequence theo seed, gán vào split có thiếu hụt lớn nhất).

**Reference train-only:** chỉ original train; day từ `day_clear`, night từ `night_clear`, 10 ảnh mỗi mode; `fixed` = hợp 20 ảnh. Lọc QC trên ảnh chuẩn bị đúng contract (RGB → 640×360 BILINEAR → Pillow L):

| Mode | Median Y | dark_ratio (Y≤5) | saturation_ratio (Y≥250) | ln(1+Var(Lap4)) |
|---|---|---|---|---|
| day | 60–200 | ≤ 0,15 | ≤ 0,05 | ≥ 4,0 |
| night | 10–120 | ≤ 0,60 | ≤ 0,05 | ≥ 3,0 |

Trong ứng viên đạt QC, chọn ảnh gần median nhóm nhất về luminance và sharpness — ảnh “điển hình”, không phải ảnh đẹp nhất. File reference lưu SHA256 của manifest và config để downstream kiểm tra đúng phiên bản.

**Giả định:** metadata nguồn đúng; prefix tên video xấp xỉ được chuyến đi; ngưỡng QC là heuristic chọn tay, chưa tune. Mọi record `label=null`, `label_source=unlabeled`; rubric annotation (ROI cố định, good/degraded/unusable) nằm trong data notes cho giai đoạn sau.

Runtime: Python 3.12.13, NumPy 2.5.3, Pillow 12.3.0, jsonschema 4.26.0.

## 3. Benchmark

**Kết quả subset — số nhóm tự đo, không phải số từ paper:**

| Nhóm | train | val | test | Tổng |
|---|---:|---:|---:|---:|
| day_clear | 61 | 20 | 19 | 100 |
| night_clear | 60 | 19 | 21 | 100 |
| rainy (59 day / 41 night) | 59 | 21 | 20 | 100 |
| **Tổng** | **180** | **60** | **60** | **300** |

- 300 ảnh, 288 sequence; daytime/night = 159/141, clear/rainy = 200/100. **0 ảnh bị loại**, 0 ảnh trùng byte.
- Reference: ứng viên train đạt QC day 50/61, night 43/60; chọn 10 + 10.
- Validator contract: `Contract valid: {"manifest": 300}` với `--check-files`; unittest repo đạt.

**Bằng chứng tái hiện:**

| Kiểm tra | Kết quả |
|---|---|
| Chạy 2 lần liên tiếp cùng config (05/10) | Manifest cùng SHA256 |
| Replay 06/10 từ commit `35619f0` của `origin/feat/data`, ghi ra `data/manifests/replay_p1/` | Manifest SHA256 `ad252ca630b8b35a0e4394ef55d87865aad952da2c4d0f8534f429eab715b57a` — **trùng byte** với bản đã bàn giao và với hash trong [phase_1.json](evidence/integration_20261006_01/audit/phase_1.json); 20 reference ID trùng |
| Config hash | `d3fa6bd65f7762ec552ae0b9f292e10ab6c423804e44b5aed1d79819660eb13e` — trùng `config_sha256` ghi trong `reference_ids.json` |
| Audit độc lập của người 5 ([phase_1.json](evidence/integration_20261006_01/audit/phase_1.json)) | 300/300 ảnh đọc được, split/reference train-only hợp lệ, không trùng byte; 300/300 timeofday/weather khớp metadata nguồn 10.000 mẫu |

Như vậy mục `missing_preparation_files` trong phase_1.json chỉ do code chưa có trên main lúc audit, không phải do thiếu code. Thư mục replay là local/gitignored.

Lệnh tái hiện (từ repo root, sau khi merge `feat/data`):

```powershell
curl.exe -L -o data/raw/bdd100k_hf/samples.json https://huggingface.co/datasets/dgural/bdd100k/resolve/main/samples.json
.\.venv\Scripts\python.exe src/prepare_data.py --config configs/data.json --download --contact-sheet data/raw/reference_contact_sheet.png
.\.venv\Scripts\python.exe scripts/validate_contract.py --manifest data/manifests/originals.jsonl --check-files
```

Output data tôi bàn giao được người 2–5 dùng cho full run `integration_20261006_01`: 6.000 synthetic + 6.300 features + 6.300 health records ([handoff](evidence/integration_20261006_01/snapshots/handoff.json)). Các số health/curve trong [báo cáo nhóm](../report.md) thuộc người 4/5.

**Giới hạn:** một split nguồn, 300 ảnh; rainy lệch về ngày (59/41); không có dawn/dusk, snowy, foggy; sequence grouping chưa kiểm chứng độc lập; chưa có nhãn chất lượng.

## 4. Failure case

Một frame chung của nhóm: original test [`b329fe7d-f06455d3`](evidence/integration_20261006_01/images/b329fe7d-f06455d3.jpg), thuộc nhóm `day_clear` do tôi chọn. Metadata nguồn ghi `timeofday=daytime`, `weather=clear`, nhưng ảnh có trời tối, đèn đường và đèn xe.

**Tôi đã kiểm tra:** [phase_1.json](evidence/integration_20261006_01/audit/phase_1.json) xác nhận record khớp metadata nguồn — pipeline của tôi giữ nguyên đúng giá trị nguồn như contract yêu cầu (“Thời điểm ngày/đêm dùng metadata nguồn; không suy ra từ độ sáng frame”). Lỗi nằm ở **nhãn nguồn so với nội dung ảnh**, không phải do xử lý.

**Số đo của tôi trên 300 originals** (ảnh chuẩn bị theo contract, median Y mỗi frame):

- Median của median Y: daytime = 93, night = 17.
- Daytime có median Y < 40: **3/159** — `b329fe7d-f06455d3` (test, Y=21), `bf8ff5f5-916b50d0` (test, rainy, Y=29), `c4816131-7251b67e` (**train**, Y=28). Xem trực quan cả ba đều giống cảnh đêm/chạng vạng. Không ảnh night nào có median Y > 90.

**Tác động downstream** (số của người 4/5): frame `b329fe7d` có fixed = 82,07 nhưng adaptive day = 38,66 do so với day reference median Y = 102; action đổi từ normal thành strong_down_weight ([penalty JSON](evidence/integration_20261006_01/evaluation/selected_failure_explanation.json)).

**Điều đã chặn được:** ảnh train `c4816131` cũng mang nhãn daytime sai, nhưng **bộ lọc QC reference (median Y ≥ 60) đã loại nó khỏi day reference**, nên nhãn sai không làm hỏng reference ngày. **Điều chưa chặn được:** QC chỉ áp cho ứng viên reference; với ảnh val/test, tôi chuyển metadata nguồn nguyên trạng mà không gắn cờ nghi vấn, nên adaptive chọn nhầm mode cho 2 frame test.

Không sửa metadata/score của run đã freeze sau khi xem failure.

## 5. Engineering decision

**Giữ nguyên:** không tự đổi `timeofday` theo độ sáng (đúng contract) và không sửa snapshot đã bàn giao; mọi chỉnh sửa phải tạo snapshot/run_id mới để người 4 calibration/val/freeze lại.

**Một cải tiến đề xuất, chưa triển khai:** thêm **cờ metadata-plausibility** trong `prepare_data.py` cho run mới — với mỗi original, ghi `metadata_flag` vào file log riêng (ngoài manifest schema v1) khi daytime có median Y < 40 hoặc night có median Y > 90, kèm số đo. Trên data-v1 cờ này bắt đúng 3/159 frame daytime nêu trên, không bắt nhầm frame night nào. Cờ là đầu vào cho metadata-quality gate mà nhóm đề xuất ([báo cáo nhóm, mục 5](../report.md#5-engineering-decision)): người 4/5 quyết định frame có cờ dùng fixed làm đối chiếu hay đánh dấu uncertainty; người 1 review ảnh có cờ trước khi khóa reference. Ngưỡng 40/90 rút ra từ chính subset này nên phải kiểm tra trên subset khác trước khi dùng chung.

**Việc tôi cần làm tiếp:** mở PR `feat/data` → main để người 5 merge, giúp phase_1 replay được trên main; hoàn tất review trực quan reference (hiện `visual_review=pending`: ảnh đêm có glare/mặt đường ướt, ảnh ngày có dashboard và một vật lọt vào khung) và cập nhật trạng thái trong snapshot mới; nếu nhóm cần thêm dữ liệu, bổ sung dawn/dusk và cân bằng rainy ngày/đêm.

**Trade-off:** chọn subset tự động theo seed giúp tái hiện byte-for-byte và nhanh trong 120 phút, nhưng đổi lại không có review thủ công từng ảnh; metadata nguồn được tin tuyệt đối. Cờ luminance rẻ và dễ giải thích nhưng sẽ báo nhầm ở cảnh ngày rất tối (hầm, mưa dày) và bỏ sót lỗi nhãn ở cảnh đêm nhiều đèn — nên chỉ là cờ để review, không phải bộ sửa nhãn tự động. Data này chưa đủ để kết luận về detector AP, độ tin cậy ADAS, robot fusion hay điều khiển drone.

Xem [báo cáo nhóm](../report.md), [năm mục theo thành viên](report_by_member.md), [tiến độ/evidence](integration_status.md) và [bộ evidence công khai](evidence/integration_20261006_01/README.md).
