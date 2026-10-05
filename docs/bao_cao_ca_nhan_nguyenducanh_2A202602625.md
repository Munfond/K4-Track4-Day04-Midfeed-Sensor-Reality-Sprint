# BÁO CÁO CÁ NHÂN — NGƯỜI 5: INTEGRATION/EVALUATION

**Họ và tên:** Nguyễn Đức Anh  
**Mã số sinh viên:** 2A202602625  
**Bài thực hành:** Lab04 — Track4 — Midfeed Sensor Reality Sprint  
**Vai trò:** Người 5 — Tích hợp pipeline, kiểm chứng interface, đánh giá và tổng hợp báo cáo  
**Nhánh làm việc:** `feat/integration`  
**Ngày lập báo cáo:** 06/10/2026

## 1. Problem

Phần việc của tôi là ghép các module data → degradation → feature → health → evaluation thành một pipeline có thể chạy và truy vết. Nền tảng hiện tại là Python chạy offline trên Windows, dùng ảnh RGB camera đường phố BDD100K cho bối cảnh giám sát camera trong ADAS/robot mặt đất. Nhóm chưa triển khai trên camera vật lý, xe hoặc drone.

Tính năng cần bàn giao gồm runner, kiểm tra contract/coverage, so sánh health fixed và adaptive ngày/đêm, bảng/biểu đồ, failure analysis và lệnh tái hiện. Khi ảnh tối, mờ hoặc nhiễu, score có thể thay đổi; metadata/reference không phù hợp cũng có thể làm đổi action downstream. Ảnh thiếu sáng có metadata daytime là tình huống thực tế được tôi chọn để phân tích ở mục 4.

Tôi tiếp nhận dữ liệu local của người 1 và các module đã merge của người 2–4. Theo [phân công](team_ownership.md), tôi giữ nguyên logic/config và dữ liệu bàn giao của các owner, gọi API của họ để tạo snapshot mới. Tôi không nhận phần triển khai corruption, công thức feature hoặc thuật toán health của các thành viên khác là đóng góp cá nhân của mình.

Trạng thái: **đã hoàn thành phần tích hợp, đánh giá và audit trên dữ liệu thật** trong run `integration_20261006_01`. Phần chuẩn bị data của người 1 chưa thể replay từ code/config vì các file đó chưa có trong checkout; dữ liệu bàn giao đã được kiểm tra. Sprint chưa gồm huấn luyện model.

## 2. Method

**Nền tảng tham khảo:** [Monitoring and Adapting the Physical State of a Camera for Autonomous Vehicles, v3](https://arxiv.org/abs/2112.05456v3), Wischow và cộng sự, IEEE T-ITS 2023; [repo tác giả](https://github.com/MaikWischow/Camera-Condition-Monitoring). Paper đặt việc giám sát blur/noise trong quan hệ với tác vụ và mô tả phản ứng có thể phi tuyến, không đơn điệu. Đây là kết luận của paper. Nhóm dùng heuristic tự triển khai, không tái chạy estimator ML hoặc bộ điều khiển của tác giả.

Input của runner là originals manifest, ảnh thật, reference IDs và config của các owner. Ảnh original được chuẩn bị RGB `uint8` 640×360 bằng Pillow BILINEAR; synthetic đã có đúng kích thước. Output của phần tôi gồm báo cáo/CSV/biểu đồ/contact sheets/provenance trong `reports/runs/<run_id>/`, cùng evidence audit riêng theo phase. Feature và health do adapter của owner tương ứng ghi trong snapshot mới.

| Sản phẩm cá nhân | Nội dung thực hiện |
|---|---|
| [src/run_pipeline.py](../src/run_pipeline.py) | CLI prepare/finalize, preflight, gọi API owner, review val trước freeze và chạy evaluation |
| [src/evaluate.py](../src/evaluate.py) | Join theo ID; mean/median/population std, paired delta, fixed/adaptive, score increases; CSV/plot/contact sheets và provenance |
| [scripts/validate_health.py](../scripts/validate_health.py) và [heuristic schema](../schemas/heuristic_health.schema.json) | Kiểm tra heuristic riêng với schema ML; coverage, finite/range, reference, mode, weight/action và freeze evidence |
| [tests/test_integration.py](../tests/test_integration.py) | Tám test bổ sung về end-to-end, thiếu/trùng ID, score/mode/fallback sai, draft test scoring, val tampering và thống kê theo ID |
| [scripts/audit_real_run.py](../scripts/audit_real_run.py) | Lưu evidence từng phase; kiểm tra artifact toàn batch và replay computation trên ảnh thật |
| [scripts/build_group_report.py](../scripts/build_group_report.py) | Tạo report nhóm năm mục từ CSV/evidence; giữ số liệu dài trong phụ lục |
| Requirements/README/tài liệu tích hợp | Bổ sung dependency runtime cho CI, lệnh tái hiện, trạng thái bàn giao, [báo cáo nhóm](../report.md) và [kịch bản pitch](pitch_4_minutes.md) |

Scorer của người 4 sử dụng bảy feature v1, reference median/MAD từ 20 original train và penalty sharpness/exposure/noise/entropy với trọng số 0.3/0.3/0.3/0.1. Fixed dùng reference chung; adaptive chọn day/night từ metadata. `health_score=health_adaptive`, `camera_weight=(health/100)^2`; ngưỡng mặc định 75/45. Tôi kiểm chứng interface và kết quả qua API owner, không thay công thức.

Giả định quan trọng là metadata đáng tin và reference đại diện cho điều kiện cần so sánh. Reference đêm có glare/vùng tối/nhòe; chưa có quality labels. Cấu hình được giữ sau review val và freeze trước test; ngưỡng chưa được tối ưu bằng nhãn người thật. `dawn/dusk/undefined` dùng fixed_fallback hiện có.

**Truy vết:** [repo nhóm](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint), HEAD [`0917990`](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/0917990c809ed503ec29240ff6b61d29bbb8e4cc). Phần integration đang uncommitted tại thời điểm báo cáo; HEAD không đủ định danh source thực chạy, cần [module hashes/runtime/argv](../reports/runs/integration_20261006_01/evaluation/provenance.json). Contract/feature v1.0.0; policy frozen `heuristic-v1-5a7bf047d3a775aa`.

Runtime đã chạy: Python 3.12.14, NumPy 2.5.3, Pillow 12.3.0, jsonschema 4.26.0, matplotlib 3.11.2. Config frozen và reference/config hashes nằm trong [references.json](../data/features/integration_20261006_01/references.json).

## 3. Benchmark

**Dataset:** [BDD100K](https://github.com/bdd100k/bdd100k). Nhóm nhận 300 ảnh thật từ source_split=val; lab split train/val/test=180/60/60 theo sequence_id đã cung cấp. Day/night=159/141; clear/rainy=200/100. Bốn corruption × năm mức tạo 6.000 synthetic, tổng 6.300 frame. Synthetic severity là proxy; weather/timeofday không phải nhãn quality.

**Cấu hình:** RGB 640×360, base seed 20261005, corruption trực tiếp từ original, không cộng dồn; 20 train references gồm 10 day và 10 night. Review 1.260 val records trước freeze; chấm 1.260 test records sau freeze. Tôi giữ nguyên config owner 4 cho run exploratory này, không tune theo test.

**Bảng chính — test brightness_down, 34 parents metadata daytime.** Severity 0 là ảnh gốc; severity 1–5 là synthetic trên cùng 34 parents. Fixed baseline là policy reference chung, adaptive day là policy reference ngày. Đơn vị health là **điểm 0–100**, không phải % accuracy.

| Severity | Gain RGB (×) | N | Fixed baseline (điểm) | Adaptive day (điểm) |
|---:|---:|---:|---:|---:|
| 0 — original | 1.00 | 34 | 95.60 | 84.54 |
| 1 | 0.80 | 34 | 94.78 | 75.08 |
| 2 | 0.60 | 34 | 88.32 | 57.23 |
| 3 | 0.40 | 34 | 75.32 | 37.76 |
| 4 | 0.25 | 34 | 62.08 | 30.88 |
| 5 | 0.12 | 34 | 44.85 | 30.00 |

Nguồn bảng: [curves.csv](../reports/runs/integration_20261006_01/evaluation/curves.csv), [groups.csv](../reports/runs/integration_20261006_01/evaluation/groups.csv) và [provenance](../reports/runs/integration_20261006_01/evaluation/provenance.json). Các số là **nhóm tự benchmark**, làm tròn hai chữ số; không lấy từ paper. Adaptive giảm 54,54 điểm khi gain giảm 1→0,12. Phản ứng này chưa chứng minh adaptive chính xác hơn fixed khi chưa có quality labels.

Toàn test: 60 original có adaptive mean 84,31, median 89,79 và population std 16,97; 1.200 synthetic có mean 66,38, median 68,00 và std 20,42. [Split totals](../reports/runs/integration_20261006_01/evaluation/split_totals.csv) giữ đầy đủ số đo. Full coverage=6.300/6.300, test=1.260/1.260; coverage không phải accuracy.

**Kiểm chứng do tôi thực hiện:**

- 32 unittest đạt: 24 có sẵn và 8 test tích hợp/thống kê bổ sung. Tests fixture không được tính là benchmark ảnh thật.
- Validator đạt trên fixture ML, originals thật và augmented manifest; check-files, compileall và git diff --check đạt.
- Audit 300 originals đọc được; 300/300 weather/timeofday khớp metadata nguồn local 10.000 mẫu. Reference IDs thuộc original train và đúng nhóm metadata.
- Verify toàn bộ 6.000 synthetic về hash/format/seed/parameter/coverage; replay 120 variants của 6 parents phân tầng train/val/test × day/night, pixel khớp.
- Tính lại 145 feature records từ ảnh thật, gồm các variants, parent và tất cả 20 references; max absolute difference=0.
- Recalibration 20 train reference khớp hash; recompute 6.300 health records và 1.260 val records khớp snapshot/freeze evidence.
- Tái xuất evaluation; năm CSV groups/samples/curves/score_increases/split_totals giống từng byte. Hashes bảo vệ trước/sau không đổi.

[Evidence năm phase](../reports/runs/integration_20261006_01/evidence_20261006_01/report.md), [audit summary](../reports/runs/integration_20261006_01/evidence_20261006_01/summary.json), [batch log](../data/generated/integration_20261006_01/run_summary.json) và [health handoff](../data/features/integration_20261006_01/handoff.json) là bằng chứng chạy thật.

**Lệnh đã chạy từ repo root:**

```powershell
.\.venv\Scripts\python.exe src/run_pipeline.py prepare --run-id integration_20261006_01
.\.venv\Scripts\python.exe scripts/audit_real_run.py --run-id integration_20261006_01 --evidence-id evidence_20261006_01
.\.venv\Scripts\python.exe scripts/build_group_report.py --run-id integration_20261006_01
```

Sau prepare, tôi review val rồi gọi finalize với validation-note và reference-review-note; argv đầy đủ nằm trong [provenance](../reports/runs/integration_20261006_01/evaluation/provenance.json). Snapshot pipeline/audit đã tồn tại được bảo vệ: muốn lặp phải chọn run_id/evidence_id mới. Build report chỉ đọc số liệu và cập nhật tài liệu, không chạy lại benchmark.

## 4. Failure case

Tôi chọn một tình huống: test original `b329fe7d-f06455d3`. [Ảnh thật](../data/raw/bdd100k/images/val/b329fe7d-f06455d3.jpg) nhìn giống cảnh đêm, có trời tối và đèn đường/đèn xe, nhưng metadata nguồn ghi daytime. Phân tích này dùng original, không áp corruption synthetic.

Số đo: median luminance=21/255; dark_ratio≈9,42%. Fixed health=82,07 nhưng adaptive day=38,66, chênh −43,41 điểm. Day reference median luminance=102/255; exposure penalty do median_luminance trừ 30 điểm. Sharpness và entropy penalties cũng tăng so với reference chung.

Adaptive action là `strong_down_weight`, camera_weight≈0,1494; nếu xét fixed theo ngưỡng hiện tại thì action sẽ `normal`. Vì vậy, metadata/reference có thể làm đổi quyết định dù pixel không đổi. Chưa có quality label hoặc detector benchmark để kết luận action nào đúng.

Tôi dùng [penalty diagnostics](../reports/runs/integration_20261006_01/evaluation/selected_failure_explanation.json), [samples.csv](../reports/runs/integration_20261006_01/evaluation/samples.csv) và [đối chiếu metadata nguồn](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_1.json) để truy nguyên. Handoff khớp label trong nguồn local nên chưa chứng minh người 1 xử lý sai. Tôi giữ nguyên test metadata/score và không tune lại sau khi xem failure.

## 5. Engineering decision

Từ chênh lệch 43,41 điểm trên cùng frame, quyết định của tôi là giữ bằng chứng frozen và coi độ tin cậy metadata là điều kiện cần kiểm tra trước khi dùng adaptive score cho downstream.

**Đã triển khai:** logs gồm sample_id, source/input/config/reference hashes, mode, fixed/adaptive health, weight/action, số frame thực chạy, package versions và argv. CSV giữ cả ngoại lệ score tăng theo parent/severity, không lọc để làm curve đẹp. Fallback hiện có dùng fixed cho dawn/dusk/undefined, nhưng chưa phát hiện label daytime có nội dung giống night.

**Một cải tiến đề xuất, chưa triển khai:** metadata-quality gate trước adaptive routing trong run mới. Owner 1 review provenance/nhãn/reference; metadata chưa đáng tin được ghi uncertainty ngoài health schema hiện tại để supervisor xử lý. Fixed chỉ được giữ làm đối chiếu, không coi là fallback an toàn đã được chứng minh. Tôi sẽ phối hợp owner 4 chốt interface và đánh giá gate trên val mới, thay vì tự đổi day/night từ luminance.

Trade-off là gate có thể giảm routing sai nhưng tăng số frame uncertain và công review. Heuristic dễ giải thích, phù hợp kiểm tra offline; nhóm chưa đo latency nên không khẳng định real-time. Chưa dùng score đơn lẻ cho phanh/steering, fusion robot hoặc điều khiển drone khi thiếu task-level validation/supervisor.

Dữ liệu cần tiếp theo là metadata/reference đã review, code/config chuẩn bị data của người 1, quality labels độc lập và detector benchmark trên cùng cảnh thiếu sáng. Sequence leakage được kiểm tra theo manifest, chưa xác minh độc lập sequence metadata. Nhóm chưa train classifier, không báo F1/false alarm/AP/fusion benefit hoặc ADAS reliability.

**Bàn giao cá nhân:** code/config/README/tests thuộc phạm vi người 5, [báo cáo nhóm năm mục](../report.md), [tiến độ/evidence](integration_status.md), [năm mục theo thành viên](report_by_member.md) và [kịch bản pitch 3–5 phút](pitch_4_minutes.md). Kịch bản mục tiêu 4 phút đã soạn; chưa có log ghi âm hoặc thời gian một buổi diễn tập. Khi trình bày có thể mở bảng CSV → ảnh failure → penalty JSON → audit summary từ các link trên.

Phần integration hiện nằm trên `feat/integration`, chưa commit/push tại thời điểm lập báo cáo. Dữ liệu/generated/run evidence được gitignore và phải bàn giao kèm thư mục local khi cần mở ảnh/log. Báo cáo này chỉ ghi kết quả run `integration_20261006_01`, không trộn số từ pilot nuScenes hoặc các run riêng của thành viên khác.
