# BÁO CÁO CÁ NHÂN — NGƯỜI 3: FEATURE/METRIC

**Họ và tên:** Nguyễn Hoàng Duy  
**Mã số sinh viên:** 2A202602751  
**Bài thực hành:** Lab04 — Track4 — Midfeed Sensor Reality Sprint  
**Vai trò:** Người 3 — Trích xuất feature và giải thích metric ảnh camera  
**Nhánh triển khai:** `metric`  
**Ngày lập:** 05/10/2026 · **Cập nhật sau bàn giao data:** 06/10/2026

## 1. Problem

Phần việc của tôi là đo bảy đặc trưng ảnh để nhóm quan sát độ nét, vùng sáng bị clipping, vùng tối, entropy, residual, luminance và contrast. Nền tảng full benchmark là Python offline trên Windows với ảnh RGB camera đường phố BDD100K, phục vụ prototype giám sát camera ADAS/robot mặt đất; chưa đo một camera vật lý hay triển khai trên xe/drone.

Feature là tín hiệu mức thấp. Cảnh tối, texture và noise có thể làm metric thay đổi dù camera chưa hỏng, nên không được suy ra health hoặc detector accuracy chỉ từ một feature. Failure chung ở mục 4 cho thấy feature đúng về số học vẫn có thể được downstream diễn giải khác khi metadata/reference không phù hợp.

**Trạng thái cập nhật:** người 5 đã chạy CLI/API feature của tôi trên full run BDD100K `integration_20261006_01`, tạo đủ **6.300 records từ 300 originals + 6.000 synthetic**. Tuyên bố “chưa có augmented manifest/ảnh thật” của báo cáo 05/10 không còn là trạng thái hiện tại.

Đóng góp của tôi là [src/features.py](../src/features.py), API/CLI và [Metrics.md](Metrics.md). Người 5 chạy integration/audit, tính bảng tổng hợp và làm report; người 4 sở hữu health/calibration. Báo cáo không nhận phần thuật toán health/evaluator hoặc lượt chạy riêng của các thành viên khác là đóng góp cá nhân của tôi.

## 2. Method

**Nguồn nền tảng:** [paper Wischow và cộng sự, v3](https://arxiv.org/abs/2112.05456v3), IEEE T-ITS 2023, và [repo tác giả](https://github.com/MaikWischow/Camera-Condition-Monitoring) đặt giám sát camera trong quan hệ với tác vụ. Bộ bảy feature v1 của nhóm là implementation riêng, không phải estimator ML của paper; số benchmark dưới đây là nhóm tự đo.

API: `extract_features(image_rgb) -> dict[str,float]`. Input RGB uint8 `(360,640,3)`; output đúng bảy key hữu hạn. CLI đọc manifest, join theo sample_id và ghi JSONL schema/feature v1.0.0. Original convert RGB/resize BILINEAR một lần; synthetic phải đúng 640×360 sẵn có, không resize/denoise/sharpen lại. Lỗi ảnh làm dừng batch với ID; không publish feature file thiếu coverage.

| Feature | Công thức tóm tắt | Đơn vị / miền |
|---|---|---|
| log_laplacian_variance | ln(1+Var(Lap4(Y))), bỏ biên một pixel | Không thứ nguyên, ≥0 |
| saturation_ratio | Tỷ lệ Y≥250 | [0,1]; bright clipping, không phải HSV saturation |
| dark_ratio | Tỷ lệ Y≤5 | [0,1] |
| entropy | Histogram 256 bin, −Σp log₂p | Bit, [0,8] |
| noise_residual | RMS(Y−median3(Y)) | Mức grayscale, [0,255] |
| median_luminance | Median(Y) | Mức grayscale 8-bit, [0,255] |
| contrast | Population std(Y), ddof=0 | Mức grayscale, [0,127.5] |

Grayscale do Pillow tạo; float64 trước Laplacian/residual để tránh overflow; median filter Pillow 3×3. Feature không chép label/severity/split. Noise/texture có thể tăng Laplacian/entropy/residual; residual không phải noise estimate thuần. Giả định input preprocessing đúng contract; feature không tự xác minh truthfulness của metadata hoặc chất lượng reference.

**Truy vết code:** [commit triển khai `069f950`](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/069f95052746b4eccf1be8c39c970d7bf28c2989), đã merge qua PR #2. HEAD integration=`0917990`; code người 5 chưa commit nên dùng [module hashes/runtime/argv](../reports/runs/integration_20261006_01/evaluation/provenance.json). Runtime full run: Python 3.12.14, NumPy 2.5.3, Pillow 12.3.0; [contract](contracts.md) và [feature bundle](../data/features/integration_20261006_01/features.jsonl).

## 3. Benchmark

**Dataset/cấu hình:** [BDD100K](https://github.com/bdd100k/bdd100k), 300 ảnh thật source_split=val, lab train/val/test=180/60/60 originals; day/night=159/141, clear/rainy=200/100. Bốn corruption × năm mức từ original tạo 6.000 synthetic PNG. Toàn bộ 6.300 frame được trích feature; corruption seed gốc=20261005. Metadata/severity không phải quality labels.

**Bảng chính — nhóm tự đo feature, test brightness_down, cùng 34 parents metadata daytime.** Severity 0 là original baseline; gain=1. Các dòng là mean của feature từng frame. Cột luminance là **trung bình median mỗi frame**, không phải mean của toàn bộ pixel. Dark ratio được nhân 100 để biểu diễn % pixel; entropy có đơn vị bit.

| Severity | Gain RGB (×) | N | Mean median Y (0–255) | Mean dark ratio (% pixel) | Mean ln(1+Var(Lap4)) | Mean entropy (bit) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 — original | 1.00 | 34 | 92.29 | 0.66 | 5.73 | 7.39 |
| 1 | 0.80 | 34 | 73.85 | 1.06 | 5.29 | 7.06 |
| 2 | 0.60 | 34 | 55.38 | 1.89 | 4.73 | 6.66 |
| 3 | 0.40 | 34 | 36.91 | 4.15 | 3.94 | 6.09 |
| 4 | 0.25 | 34 | 23.12 | 8.78 | 3.08 | 5.42 |
| 5 | 0.12 | 34 | 11.09 | 24.44 | 1.89 | 4.41 |

Nguồn số đo: [member3_feature_summary.csv](../reports/runs/integration_20261006_01/evaluation/member3_feature_summary.csv), [provenance thống kê + IDs](../reports/runs/integration_20261006_01/evaluation/member3_feature_summary_provenance.json), [features](../data/features/integration_20261006_01/features.jsonl) và [manifest](../data/manifests/augmented_integration_20261006_01.jsonl). Người 5 tổng hợp từ output module, không chạy feature formula khác hoặc lấy số từ paper; bảng làm tròn hai chữ số, CSV giữ số đầy đủ và cả bảy feature.

Khi gain giảm 1→0,12, mean median Y giảm 92,29→11,09 và mean dark ratio tăng 0,66→24,44%. Laplacian/entropy cũng giảm trên tập này. Đây là phản ứng controlled paired của metric; không suy ra accuracy detector, camera hỏng hoặc quality label từ xu hướng đó.

**Kết quả kiểm chứng thực tế:** coverage=6.300/6.300 unique IDs; validator schema/finite/range hợp lệ; không duplicate/NaN. Audit tính lại **145 records từ ảnh thật**, bao gồm 120 synthetic của 6 parents, 6 originals và toàn bộ 20 reference train (có overlap), max absolute difference=0. Đây là sample image-computation replay; full run trước đã tính tất cả 6.300 frame. [Evidence phase 3](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_3.json), [feature replay](../reports/runs/integration_20261006_01/evidence_20261006_01/feature_replay.json).

Người 4/người 5 đã dùng full feature bundle để calibration/health và evaluation; [handoff](../data/features/integration_20261006_01/handoff.json). Việc downstream chạy được không biến health heuristic thành ground truth chất lượng. Các con số health trong báo cáo nhóm thuộc scorer người 4.

**Lịch sử kiểm thử, tách khỏi benchmark thật:** báo cáo 05/10 ghi bảy kiểm tra tập trung, 12 repository tests, validator fixture 4 manifest/4 feature và compileall đạt. Harness tập trung là tạm vì người 5 sở hữu tests lâu dài; các số này không phải dataset thật. Bộ test tích hợp hiện tại có 32 tests đạt, do người 5 nghiệm thu. Ví dụ frame đen trong Metrics.md vẫn là fixture, không phải BDD100K.

Lệnh đã tạo feature qua integration: `python src/run_pipeline.py prepare --run-id integration_20261006_01`; health adapter gọi `extract_manifest`. Lệnh đối chiếu read-only và tái tạo bảng từ snapshot hiện tại:

```powershell
.\.venv\Scripts\python.exe scripts/validate_contract.py --manifest data/manifests/augmented_integration_20261006_01.jsonl --features data/features/integration_20261006_01/features.jsonl
.\.venv\Scripts\python.exe scripts/summarize_member_features.py --run-id integration_20261006_01
```

Script thống kê thuộc người 5, chỉ đọc feature/manifest và ghi CSV/provenance báo cáo, không sửa feature output. Audit computation đã chạy bằng `scripts/audit_real_run.py --run-id integration_20261006_01 --evidence-id evidence_20261006_01`; muốn lặp phải đổi evidence_id. [Audit summary](../reports/runs/integration_20261006_01/evidence_20261006_01/summary.json) giữ command/hash/scope; feature CLI từ chối overwrite output đã có.

## 4. Failure case

Một frame chung: original test `b329fe7d-f06455d3` [nhìn giống cảnh đêm](../data/raw/bdd100k/images/val/b329fe7d-f06455d3.jpg) nhưng metadata ghi daytime. Feature của frame có median luminance=21/255 và dark_ratio≈9,42%, phản ánh cảnh tối; feature API không đọc timeofday để đổi vector hoặc gán nhãn.

Downstream dùng vector này với day reference median Y=102/255, exposure penalty do median_luminance trừ 30 điểm. Fixed health=82,07 và adaptive day=38,66, khiến action theo adaptive thành strong_down_weight; fixed theo ngưỡng hiện tại sẽ normal. [Penalty JSON](../reports/runs/integration_20261006_01/evaluation/selected_failure_explanation.json) ghi rõ số đo. Đây là bằng chứng reference/metadata có thể đổi diễn giải của **cùng vector**, chưa chứng minh feature tính sai hay action nào đúng.

[Đối chiếu nguồn](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_1.json) cho thấy handoff khớp metadata local, chưa kết luận lỗi người 1. Original không có synthetic corruption trong phân tích này; không sửa test vector/metadata hoặc tune sau khi xem failure.

## 5. Engineering decision

Giữ bảy feature đúng version và tách khỏi metadata/health. Log sample_id, preprocessing, feature version và input hashes để owner 4/5 giải thích penalty; không tự suy ra day/night hoặc camera quality từ luminance, Laplacian hay entropy.

**Một cải tiến đề xuất từ failure, chưa triển khai:** phối hợp người 1/4/5 bổ sung metadata-quality gate trước adaptive routing của run mới. Feature vector vẫn giữ nguyên; các record chưa review metadata được ghi uncertainty trong log ngoài feature schema. Reference/quality labels độc lập cần được kiểm tra trước khi đánh giá policy mới; giữ test frozen hiện tại làm evidence, không tune theo test.

Trade-off: feature mức thấp dễ giải thích và phù hợp phân tích offline, nhưng chịu tác động nội dung cảnh, noise và texture. Noise residual chứa cả cạnh; entropy/Laplacian cao không đồng nghĩa ảnh tốt. Chưa đo latency nên không khẳng định real-time, chưa dùng vector/score đơn lẻ cho ADAS phanh/steering, robot fusion hoặc drone control.

Bàn giao đã hoàn tất: code feature và Metrics.md đã merge, full feature JSONL được downstream sử dụng, evidence replay và thống kê thật có link ở trên. Các nhận xét “chưa có data” trong tài liệu ngày 05/10 là lịch sử trước handoff; báo cáo này cập nhật trạng thái 06/10. Phần còn thiếu của nhóm là prepare_data code/config, review reference/metadata, quality labels và task-level benchmark; chưa train model hoặc báo F1/false alarm/AP/fusion benefit/ADAS reliability.

Xem [báo cáo nhóm](../report.md), [tiến độ/evidence](integration_status.md), [năm mục theo thành viên](report_by_member.md) và [kịch bản pitch 3–5 phút](pitch_4_minutes.md). Data/log được gitignore và cần bàn giao kèm khi trình bày; các link local không đi theo Markdown nếu chỉ gửi riêng file báo cáo.
