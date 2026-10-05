# Năm mục báo cáo theo thành viên

Bản người 5 tổng hợp từ evidence chung ngày 06/10/2026; không thay lời xác nhận hoặc báo cáo cá nhân của owner. Các con số là nhóm tự benchmark BDD100K; kết luận paper chỉ được dẫn ở [Method của báo cáo nhóm](../report.md#2-method). Cả năm người dùng **cùng một failure case** `b329fe7d-f06455d3`, không thêm tình huống khác.

## Người 1 — Data/reference

- **Problem:** Camera RGB cho prototype giám sát ADAS cần metadata/reference đáng tin khi cảnh thiếu sáng.
- **Method:** Bàn giao 300 originals và 20 reference train; integrator đối chiếu với 10.000 metadata nguồn local. Code/config chọn subset chưa có để replay.
- **Benchmark:** 180/60/60 original train/val/test; day/night=159/141, clear/rainy=200/100; 300/300 timeofday/weather khớp nguồn. [Evidence phase 1](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_1.json).
- **Failure case:** Frame chung nhìn giống night nhưng source label là daytime; handoff khớp source nên chưa chứng minh lỗi xử lý của tôi.
- **Engineering decision:** Review metadata/reference và bàn giao code/config; trạng thái đã review là input cho metadata-quality gate đề xuất ở run mới.

## Người 2 — Bùi Đình Đề, degradation

- **Problem:** Cần biến thể cùng cảnh để tách phản ứng metric với blur, gain sáng và noise khỏi khác biệt nội dung ảnh.
- **Method:** RGB 640×360; bốn corruption, năm mức trực tiếp từ original, seed ổn định và PNG. Đây là proxy nhóm, không phải mô hình sensor vật lý của paper.
- **Benchmark:** Full 6.000 synthetic; 120 variants từ 6 parents phân tầng được replay, pixel khớp. [Evidence phase 2](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_2.json).
- **Failure case:** Frame chung là original, không có corruption synthetic trong phân tích failure; darkness thực và nhãn nguồn không được thay bằng severity.
- **Engineering decision:** Giữ seed/parameter/source hashes để gate và owner kiểm tra lại; không dùng synthetic severity làm nhãn quality hoặc sửa metadata.

## Người 3 — Nguyễn Hoàng Duy, feature

- **Problem:** Cần tín hiệu ảnh giải thích được vì health đơn lẻ che nguyên nhân cảnh thiếu sáng.
- **Method:** Tính bảy feature v1; grayscale Pillow, float64 trước Laplacian/residual, median filter 3×3; feature không chứa severity/label.
- **Benchmark:** 6.300 records hợp contract; re-extract 145 ảnh thật, max absolute difference=0. [Evidence phase 3](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_3.json).
- **Failure case:** Frame chung có median luminance=21/255 và dark_ratio≈9,42%; các feature mô tả cảnh tối nhưng chưa phải ground truth camera hỏng.
- **Engineering decision:** Log feature/version cùng sample_id để review metadata gate; không tự suy ra day/night từ luminance để đổi policy.

## Người 4 — Bùi Quang Vinh, health/calibration

- **Problem:** Cùng feature có thể bị chấm khác khi reference ngày/đêm không phù hợp với frame.
- **Method:** Median/MAD train-only, weighted penalties 0.3/0.3/0.3/0.1; fixed và metadata adaptive; val review rồi freeze. Heuristic của nhóm không phải estimator ML của paper.
- **Benchmark:** 20 real train references recalibrate khớp; 6.300 scores recompute khớp, gồm 1.260 test. Bảng chính: test daytime gain 1→0,12 làm adaptive mean 84,54→30,00 điểm. [Evidence phase 4](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_4.json).
- **Failure case:** Frame chung fixed=82,07 nhưng adaptive day=38,66; exposure trừ 30 điểm, action strong_down_weight; chưa biết action nào đúng khi thiếu quality labels.
- **Engineering decision:** Validate metadata-quality gate với owner 1/5 và val mới; fixed chỉ làm đối chiếu, chưa coi là fallback an toàn. Giữ nguyên test frozen hiện tại.

## Người 5 — Integration/evaluation

- **Problem:** Cần chứng cứ end-to-end và phân biệt ảnh thật, synthetic proxy, fixture và paper claims.
- **Method:** Runner gọi API owner, join theo ID, schema/coverage/freeze validators và report từ CSV. HEAD 0917990 cộng source hashes vì phần integration chưa commit.
- **Benchmark:** Full/test coverage=6.300/6.300 và 1.260/1.260; năm CSV replay giống byte; 32 tests đạt. [Evidence phase 5](../reports/runs/integration_20261006_01/evidence_20261006_01/phase_5.json).
- **Failure case:** Chọn đúng một frame chung, mở ảnh và penalty JSON để truy vì sao fixed/adaptive đổi action; không gọi chênh score là detector accuracy.
- **Engineering decision:** Giữ logs/hash/snapshot, gắn metadata uncertainty vào log ngoài schema hiện tại trong thiết kế gate mới, chốt contract với owner; cần quality labels và task-level validation trước ADAS/robot/drone deployment.

Nguồn/dataset/commit/version và lệnh chạy dùng chung nằm cạnh [Method](../report.md#2-method) và [Benchmark](../report.md#3-benchmark), không trích số benchmark từ paper. [Báo cáo nhóm](../report.md) và [kịch bản pitch 4 phút](pitch_4_minutes.md).
