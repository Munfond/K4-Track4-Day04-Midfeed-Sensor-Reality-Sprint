# BÁO CÁO CÁ NHÂN — NGƯỜI 2: DEGRADATION

**Họ và tên:** Bùi Đình Đề  
**Mã số sinh viên:** 2A202602818  
**Bài thực hành:** Lab04 — Track4 — Midfeed Sensor Reality Sprint  
**Vai trò:** Người 2 — Tạo suy giảm chất lượng ảnh camera có kiểm soát  
**Nhánh triển khai:** `feat/degradation`  
**Ngày lập:** 05/10/2026 · **Cập nhật sau bàn giao data:** 06/10/2026

## 1. Problem

Phần việc của tôi là tạo biến thể blur, tăng/giảm sáng và Gaussian noise để nhóm quan sát phản ứng metric/health trên cùng cảnh. Nền tảng benchmark hiện tại là Python offline trên Windows, dùng camera RGB đường phố BDD100K cho bối cảnh giám sát camera ADAS/robot mặt đất; chưa triển khai trên xe hoặc sensor vật lý.

Blur làm mất chi tiết cạnh; thiếu sáng làm giảm thông tin vùng tối; clipping và noise có thể làm sai tín hiệu ảnh. Đây là động cơ xây dựng corruption có kiểm soát, chưa phải số đo detector AP. Failure chung được phân tích ở mục 4 là một ảnh thật thiếu sáng có metadata daytime; synthetic không thay thế việc kiểm tra điều kiện original.

**Trạng thái cập nhật:** module degradation đã được người 5 gọi trong full run BDD100K `integration_20261006_01`, sinh **6.000 synthetic từ 300 originals**, augmented manifest đủ **6.300 records** và downstream đã xử lý đủ ID. Trạng thái “chưa có originals/chưa chạy full” trong báo cáo ngày 05/10 đã được thay bằng evidence mới.

Tôi sở hữu [src/corruptions.py](../src/corruptions.py), [configs/corruptions.json](../configs/corruptions.json) và [degradation_notes.md](degradation_notes.md). Full integration/audit là lượt chạy của người 5 trên code đã bàn giao; báo cáo không suy ra tôi đã tự chạy BDD100K riêng hoặc nhận phần feature/health/evaluator là đóng góp của mình.

## 2. Method

**Nguồn nền tảng:** [paper Wischow và cộng sự, v3](https://arxiv.org/abs/2112.05456v3), IEEE T-ITS 2023, và [repo tác giả](https://github.com/MaikWischow/Camera-Condition-Monitoring) nghiên cứu camera-condition monitoring theo tác vụ với blur/noise. Corruption của nhóm là proxy tự triển khai, không tái hiện đầy đủ mô hình vật lý hoặc estimator ML của paper.

API: `degrade(image_rgb, corruption, severity, seed) -> image_rgb`. Input/output là NumPy RGB uint8 `(360,640,3)`. Original được convert RGB và resize Pillow BILINEAR **trước** corruption. Mỗi mức bắt đầu trực tiếp từ original đã chuẩn bị, không cộng dồn. Output là PNG, sample_id mới, parent/split/sequence/weather/timeofday giữ nguyên; nhãn chưa đánh giá giữ null.

| Corruption | Tham số severity 1→5 | Thuật toán / đơn vị |
|---|---|---|
| Gaussian blur | 0.6, 1.2, 2.4, 4, 6 | Pillow GaussianBlur; σ pixel, xấp xỉ extended box filters |
| Brightness up | 1.2, 1.5, 1.9, 2.5, 3.2 | Gain nhân RGB, không thứ nguyên |
| Brightness down | 0.8, 0.6, 0.4, 0.25, 0.12 | Gain nhân RGB, không thứ nguyên |
| Gaussian noise | 5, 10, 20, 35, 50 | σ theo mức cường độ RGB 8-bit |

Brightness/noise tính float64, clip [0,255], `np.rint` rồi chuyển uint8. Seed gốc 20261005; seed mẫu là tám byte đầu big-endian của SHA256 tuple `[base_seed,parent_id,corruption,severity]`. RNG cục bộ `np.random.default_rng(seed)` không thay global RNG. Snapshot tồn tại bị từ chối overwrite; batch lưu hash source/config/manifest/module/PNG. Rain overlay là tùy chọn và chưa triển khai.

CLI có preflight, smoke, batch, verify/replay và handoff. Synthetic giữ metadata của parent; downstream đọc manifest, không glob contact sheets như sample. Giả định là original/metadata của người 1 đã bàn giao đúng; ảnh gốc không mặc nhiên pristine và severity không phải quality label.

**Truy vết code:** [commit triển khai `0edb21b`](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/0edb21bc5fce28f017c7ec1028198ca01dc26af3), đã merge qua PR #1. HEAD full integration là `0917990`; tại thời điểm chạy phần người 5 chưa commit, nên dùng [module hashes/argv/runtime](evidence/integration_20261006_01/evaluation/provenance.json). Contract v1.0.0; runtime full run: Python 3.12.14, NumPy 2.5.3, Pillow 12.3.0.

## 3. Benchmark

**Dataset:** [BDD100K](https://github.com/bdd100k/bdd100k); 300 ảnh thật người 1 bàn giao, source_split=val. Lab train/val/test=180/60/60 originals; day/night=159/141; clear/rainy=200/100. Split/sequence được giữ theo manifest và kiểm tra leakage trong contract; sequence provenance chưa được xác minh độc lập.

**Bảng chính — kết quả nhóm tự chạy code degradation trên dữ liệu thật.** Baseline là original severity 0. Synthetic severity 1–5 có tham số như Method; đơn vị số lượng là frame/PNG, không phải accuracy.

| Nhóm | Severity | Parents thật | Output synthetic (PNG) | Records của nhóm |
|---|---|---:|---:|---:|
| Original baseline | 0 | 300 | 0 | 300 |
| Gaussian blur | 1–5, σ=0.6→6 pixel | 300 | 1.500 | 1.500 |
| Brightness up | 1–5, gain=1.2→3.2 | 300 | 1.500 | 1.500 |
| Brightness down | 1–5, gain=0.8→0.12 | 300 | 1.500 | 1.500 |
| Gaussian noise | 1–5, σ=5→50 RGB intensity | 300 | 1.500 | 1.500 |
| Tổng augmented | 0–5 | **300 originals duy nhất** | **6.000** | **6.300** |

Nguồn số đo: [run_summary.json](evidence/integration_20261006_01/generation/run_summary.json), [augmented manifest](evidence/integration_20261006_01/snapshots/augmented_integration_20261006_01.jsonl), [config snapshot](evidence/integration_20261006_01/generation/config_snapshot.json) và [evidence phase 2](evidence/integration_20261006_01/audit/phase_2.json). Các dòng corruption dùng cùng parents, không cộng thành 1.200 ảnh nguồn độc lập.

**Kết quả nghiệm thu:** đủ 6.000/6.000 synthetic và 6.300/6.300 records; verifier kiểm tra toàn bộ PNG RGB uint8 640×360, hashes, seed, parameters, coverage và parent metadata/split. Hash source không đổi. Pixel replay **120/120 variants khớp** trên 6 parents phân tầng train/val/test × day/night, có clear/rainy; đây là sample replay, không gọi là tái sinh toàn bộ 6.000 ảnh. [Pixel replay](evidence/integration_20261006_01/audit/pixel_replay.json).

Integrator đã xem contact sheet sanity có các mức blur/brightness/noise; [ví dụ original và 20 biến thể](evidence/integration_20261006_01/images/degradation_sanity.png). Downstream tạo đủ 6.300 features/health; [handoff](evidence/integration_20261006_01/snapshots/handoff.json). Số health là sản phẩm chung và thuộc scorer người 4, không phải metric nội tại của module degradation.

**Lịch sử kiểm thử, tách khỏi benchmark BDD100K:** báo cáo 05/10 ghi 280 self-checks và 12 unittest contract đạt trên fixture; 280 không phải số ảnh thật hay 280 unittest độc lập. Pilot image-only mini-nuScenes dùng 6 CAM_FRONT images từ 404 ứng viên, sinh 120 PNG nhưng không tạo manifest BDD100K. Những lượt đó không được chạy lại hoặc dùng thay evidence full run hiện tại. Bộ test tích hợp hiện tại của nhóm có 32 tests đạt, do người 5 nghiệm thu.

**Lệnh đã chạy qua integrator:** `python src/run_pipeline.py prepare --run-id integration_20261006_01`; adapter gọi `generate_batch`. Audit đọc lại full batch và replay mẫu:

```powershell
.\.venv\Scripts\python.exe scripts/audit_real_run.py --run-id integration_20261006_01 --evidence-id evidence_20261006_01
```

Đây là command lịch sử của evidence có sẵn; muốn lặp audit chọn evidence_id mới. Có thể chạy lại kiểm tra read-only riêng module:

```powershell
.\.venv\Scripts\python.exe src/corruptions.py --verify --run-id integration_20261006_01
```

Lệnh verify trên không replay pixel toàn batch; thêm `--replay` khi cần tái sinh và so pixel toàn bộ. Không cần tạo lại data khi verifier/audit đã khớp. [Audit summary](evidence/integration_20261006_01/audit/summary.json) chứa argv, hashes và scope kiểm chứng.

## 4. Failure case

Một tình huống chung: original test `b329fe7d-f06455d3` [nhìn giống cảnh đêm](evidence/integration_20261006_01/images/b329fe7d-f06455d3.jpg) nhưng metadata nguồn ghi daytime. Failure analysis dùng original, không có synthetic corruption áp vào frame này. Module của tôi giữ nguyên metadata; nó không sửa hoặc phát hiện nhãn ngày/đêm không phù hợp với nội dung ảnh.

Downstream đo median luminance=21/255, fixed health=82,07 và adaptive day=38,66; reference day làm exposure penalty trừ 30 điểm. Action theo adaptive là strong_down_weight, trong khi fixed theo ngưỡng hiện tại sẽ normal. [Diagnostics](evidence/integration_20261006_01/evaluation/selected_failure_explanation.json) giải thích số đo; chưa có quality labels để kết luận action nào đúng.

Đối chiếu [metadata nguồn local](evidence/integration_20261006_01/audit/phase_1.json) cho thấy handoff khớp nguồn, chưa chứng minh lỗi xử lý người 1. Bài học cho degradation là replay đúng và bảo toàn metadata vẫn chưa đủ chứng minh original pristine hoặc benchmark phản ánh camera vật lý. Không thay tình huống original bằng synthetic severity hay tự gán lại nhãn.

## 5. Engineering decision

Giữ source/parent/seed/parameter/config hashes và augmented manifest làm giao diện bàn giao; chỉ chạy snapshot mới khi dữ liệu được owner cập nhật. Pipeline hiện bảo toàn nguồn, metadata/split và từ chối overwrite; các điều kiện này đã được kiểm chứng trên full BDD100K.

**Cải tiến đề xuất từ failure, chưa triển khai:** cùng người 1/5 bổ sung trạng thái metadata/reference đã review trong provenance/handoff của run mới, làm input cho metadata-quality gate của nhóm. Module corruption tiếp tục bảo toàn metadata; không tự chọn day/night từ luminance hoặc đổi schema v1 trước khi người 5 chốt contract.

Trade-off: Gaussian blur/gain/noise thuận tiện cho paired comparison và tái hiện bằng seed, nhưng không mô phỏng đầy đủ motion blur, exposure/HDR, ISP noise hoặc lens/raindrop effects. Original có sẵn glare/noise; synthetic severity không phải ground truth camera hỏng. Không dùng kết quả corruption đơn lẻ để khẳng định detector AP, fusion benefit hoặc ADAS/robot/drone reliability.

Code đã merge và full output đã được downstream tiếp nhận. Phần chờ tiếp theo là code/config selection và review metadata/reference của người 1; bộ nhãn quality và task-level validation chưa có. Ảnh mưa thật có trong subset nhưng rain overlay chưa triển khai; không đồng nhất hai nguồn đó.

Bàn giao: [báo cáo nhóm năm mục](../report.md), [evidence per-phase](evidence/integration_20261006_01/audit/report.md), [notes degradation](degradation_notes.md) và [kịch bản pitch](pitch_4_minutes.md). Những mô tả “chờ data” trong notes/báo cáo lịch sử phản ánh thời điểm trước handoff; trạng thái nghiệm thu cập nhật là báo cáo này và integration_status. Full dataset/generated vẫn gitignore; bản evidence chọn lọc có link công khai bên dưới để người chấm mở CSV/plot/log.

Bằng chứng công khai: [integration_20261006_01](evidence/integration_20261006_01/README.md). Code tích hợp đã công bố tại [commit c29e8f9](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/c29e8f994da629d935f95bb167e8073dfe58cc25). Các ghi chú “chưa commit” mô tả trạng thái tại thời điểm chạy; provenance giữ nguyên lịch sử đó. CSV/plot/log/snapshot chọn lọc mở được trên GitHub; full image replay cần dataset local.
