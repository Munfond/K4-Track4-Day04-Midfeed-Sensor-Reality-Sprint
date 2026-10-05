# Evidence theo phase trên BDD100K thật

Run: `integration_20261006_01`. Evidence: `evidence_20261006_01`.

| Người | Phase | Kết quả |
|---|---|---|
| 1 | data_handoff_audit | delivery_verified_preparation_not_replayed |
| 2 | degradation_verification_and_pixel_replay | passed |
| 3 | feature_coverage_and_image_reextraction | passed |
| 4 | reference_recalibration_and_full_health_recomputation | passed |
| 5 | evaluation_report_reproduction | passed |

Phase 1: audit delivery 300 ảnh và đối chiếu metadata nguồn local; chưa replay bước chuẩn bị data vì thiếu code/config người 1.
Phase 2: kiểm tra full 6.000 synthetic; tái sinh pixel 120 variants của 6 parents đủ train/val/test, ngày/đêm và clear/rainy.
Phase 3: validate 6.300 features; tính lại từ ảnh 145 records, gồm toàn bộ 20 reference. Sai khác tối đa 0.
Phase 4: recalibrate từ 20 train ảnh thật; reference hash khớp; recompute 6.300 scores và evidence freeze/val khớp.
Phase 5: tái xuất report; năm CSV có byte/hash giống run đã nghiệm thu. Xem evaluation_replay/report.md.

Inputs, owner code/config và output bàn giao không đổi. Mỗi phase có JSON, timestamp UTC, thời gian, số record và scope rõ ràng.
Không gọi sample replay là full image-computation replay. Full integration run trước đó đã tính tất cả 6.300 frames từ ảnh thật.
Reference review và visual metadata flags vẫn là limitations; hai daytime flags khớp metadata nguồn local, chưa chứng minh lỗi xử lý người 1.
