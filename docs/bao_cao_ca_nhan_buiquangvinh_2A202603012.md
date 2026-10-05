# Báo cáo cá nhân — Người 4: Health/Calibration

**Họ tên:** Bùi Quang Vinh. **MSSV:** 2A202603012.
**Vai trò:** Người 4 — Hiệu chuẩn reference và tính điểm sức khỏe camera.
**Cập nhật:** 06/10/2026. **Nhánh:** `health`.

## Các phần đã thực hiện

- Triển khai `src/baseline.py`: tính reference từ ảnh original train, chấm health
  theo sharpness, exposure, noise và entropy; so sánh fixed với reference ngày/đêm.
- Tính `camera_weight = (health/100)^2` và action theo ngưỡng; bổ sung kiểm tra
  coverage, dữ liệu hữu hạn, reference hash và khóa config trước khi chấm test.
- Xây dựng `configs/health.json` và CLI `calibrate`, `score`, `freeze`, `explain`;
  giải thích từng penalty để review các trường hợp điểm bất thường.
- Dùng API feature từ nhánh `metric` để chạy thử trên 404 ảnh gốc nuScenes
  CAM_BACK: 243 train, 80 val, 81 test; chọn 20 reference train gồm ngày và đêm.
- Review 20 reference và 6 trường hợp validation; phân tích noise chưa kích hoạt,
  ảnh đêm bị phạt exposure và hạn chế của reference. Ghi công thức, lệnh chạy,
  bằng chứng và nội dung bàn giao tại [health_notes.md](health_notes.md).
- Hoàn tất lượt BDD100K: 300 originals và 6.000 degraded; trích 6.300 feature
  records, calibration 20 reference original train, review 1.260 validation records,
  so sánh scale 2/3/4, freeze config rồi chấm 1.260 test records.
- Sửa enriched reference adapter, kiểm tra source/hash/sequence; bổ sung runner
  `scripts/run_health.py prepare/finalize` và test chống test-before-freeze,
  input/code thay đổi sau review hoặc ghi đè snapshot.

## Kết quả và kiểm tra

- Xuất đủ 404 health records: 403 `normal`, 1 `down_weight`, theo policy minh họa.
  Output gồm `references.json` và `health_scores.jsonl` trong run
  `health_nuscenes_original_20261005_1fa0fd8f`.
- 23 kiểm tra fixture ban đầu và 9 kiểm tra diagnostics bổ sung đều đạt;
  sau bổ sung giải thích penalty, toàn bộ 404 score vẫn khớp snapshot đã xuất.
- Bộ test hiện tại: **24 tests pass**. Full degradation verification và replay
  smoke pass. Final BDD100K coverage/finite/range/mode/weight/action/hash pass.
- Output chính thức: `data/features/p4_bdd100k_20261006_04/references.json` và
  `health_scores.jsonl`, đủ **6.300 unique IDs**: 2.296 normal, 3.006 down_weight,
  998 strong_down_weight. Bàn giao/hash/review tại `handoff.json`, `verification.json`,
  `validation/` và `final_review/`; feature source nằm ở run `p4_bdd100k_20261006_02`.

## Hạn chế và phạm vi bàn giao

Phần health của lượt BDD100K đã chạy xong local. Người 5 tiếp nhận output để ghép
runner/evaluation chung. Ngưỡng 75/45 còn minh họa vì chưa có human quality labels;
noise nhẹ, tăng sáng ảnh đêm và blur đạt trần có thể làm score tăng. Source reference
review flag của người 1 được giữ nguyên; review local ghi riêng trong provenance.
Chưa train model hoặc kiểm chứng bằng nhãn chất lượng, chưa báo accuracy/F1/AP hay
độ tin cậy ADAS. Dữ liệu/output được gitignore; code và báo cáo bàn giao trên nhánh `health`.

Bằng chứng công khai: [integration_20261006_01](evidence/integration_20261006_01/README.md). Code tích hợp đã công bố tại [commit c29e8f9](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/c29e8f994da629d935f95bb167e8073dfe58cc25). Các ghi chú “chưa commit” mô tả trạng thái tại thời điểm chạy; provenance giữ nguyên lịch sử đó. CSV/plot/log/snapshot chọn lọc mở được trên GitHub; full image replay cần dataset local.

Bộ công khai trên là lượt tích hợp nhóm `integration_20261006_01` do integrator chạy bằng scorer người 4; không thay thế evidence cho lượt riêng `p4_bdd100k_20261006_04` hoặc pilot nuScenes được mô tả ở trên. Các số đếm/action của những lượt riêng chưa được công bố trong bundle này.
