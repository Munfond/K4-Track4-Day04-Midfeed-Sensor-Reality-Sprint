# Tiến độ và bàn giao thành viên 5 — 06/10/2026

Đánh giá dựa trên checkout `0917990`, lịch sử Git, code và dữ liệu local. Không suy ra phần trăm hoàn thành chỉ từ số commit. Nhánh phần việc mới: `feat/integration`; không sửa logic/config của người 1–4.

| Thành viên | Bằng chứng hiện có | Tiến độ và phần còn lại |
|---|---|---|
| 1 — data/reference | Người dùng xác nhận đã làm xong và bàn giao folder data. Local có 300 originals, reference IDs, ảnh BDD100K; code data chưa có trong Git. | Manifest và file paths đạt validator; train/val/test=180/60/60, day/night=159/141, clear/rainy=200/100. Reference gồm 10 day + 10 night train originals. Handoff ghi visual_review=pending, chọn bằng QC tự động; code/config/data notes còn chờ commit owner 1 để tái hiện bước lấy subset. |
| 2 — Bùi Đình Đề, corruption | PR #1, `0edb21b`, `src/corruptions.py`, config và báo cáo cá nhân. | API bốn corruption × năm severity, stable seed, snapshot/hash/checks đã merge. Báo cáo cũ là pilot nuScenes và fixture; tích hợp BDD100K được chạy riêng bởi runner mới. Rain overlay tùy chọn chưa có. |
| 3 — Nguyễn Hoàng Duy, feature | PR #2, `069f950`, `src/features.py`, `docs/Metrics.md`, contribution report. | Bảy feature và CLI đã merge, original resize/synthetic strict size. Bàn giao trước đó chưa có full BDD100K features; runner gọi adapter hiện có để tạo output mới. Không đổi metric của owner. |
| 4 — Bùi Quang Vinh, health | PR #3/#4, `31d9a93`, baseline/config/health notes và health runner. | Calibration train-only, fixed/day-night, freeze val trước test, diagnostics đã merge. Pilot trong notes không được coi là full kết quả BDD100K của run này. Config 75/45 là heuristic mô tả, chưa tối ưu bằng quality labels. |
| 5 — integration/evaluation | Bootstrap contract/validator/ownership và merge đã có trên main. Phần mới trên `feat/integration`. | Bổ sung runner, evaluator, heuristic schema/validator, integration tests, dependencies/README/CI support, report/provenance và pitch. Kết quả thật và quyết định review được ghi bên dưới sau khi thực chạy. |

## Phần người 5 đã triển khai

- `src/run_pipeline.py`: một CLI với prepare/finalize. Preflight metadata/reference, tạo run_id riêng; gọi writer của từng owner, không tự sửa output bàn giao. Prepare chỉ score val; finalize kiểm chứng degradation và freeze trước test.
- `src/evaluate.py`: join theo ID, bảng mean/median/population std/min/max, paired delta về original, fixed/adaptive theo split/time/weather/corruption/severity. CSV giữ original/synthetic riêng qua trường corruption.
- Curve severity, distribution, contact sheet original/degraded, rainy originals, lowest originals và noise score tăng. CSV giữ cả tăng so với parent và tăng so với severity trước, fixed/adaptive riêng.
- Schema heuristic độc lập với schema ML v1.0.0; validator kiểm tra finite/range, policy, metadata mode/fallback, weight/action, coverage test, reference train-only và frozen validation evidence. Tái tính score qua baseline để bắt interface sai mà không sửa công thức owner.
- Provenance: input/code/config/reference hashes, package/Python versions, Git commit và dirty state, argv, số frame/split, seed count; full batch summary giữ seed/config/ảnh/source hashes. Không gọi fixture là kết quả thật.
- Dependencies runtime chỉ gồm NumPy/Pillow/jsonschema/matplotlib, dev requirements bao gồm runtime để CI chạy test pipeline. ML dependencies bỏ khỏi sprint chưa train.

## Không gây conflict

Danh sách code/config owner 1–4 được giữ nguyên; originals/reference_ids và ảnh nguồn chỉ đọc. Output owner được tạo qua API owner trong run_id mới, mỗi path một writer. Báo cáo này thuộc tài liệu tổng hợp của người 5; báo cáo cá nhân người khác không sửa. Không commit dataset/generated/model, không push hoặc merge tự động.

## Tái hiện

Xem README cho lệnh prepare/finalize. Giữ raw images, originals manifest và reference_ids đi kèm; Git không chứa dữ liệu. Chọn run_id mới cho lần lặp. Nếu cần đổi công thức/threshold, owner 4 xử lý rồi chạy val lại; không tune theo test đã xem. Nếu cần sửa split/reference/data provenance, owner 1 xử lý và bàn giao snapshot mới.

Các kiểm tra split/sequence dùng sequence_id trong manifest (prefix tên ảnh); chưa xác minh độc lập sequence metadata từ dataset. Weather và synthetic severity không phải nhãn quality. Không có F1/false alarm/AP/fusion benefit hoặc chứng cứ ADAS reliability.

## Review reference thực tế

Integrator đã xem 20 ảnh qua contact sheet day/night và xem full resolution hai ảnh đêm `c33251a6-812a0ea8`, `bdcd6f24-e3a675af`. Có đường/cảnh giao thông nhìn thấy, nhưng bộ đêm chứa glare, vùng tối rộng và ảnh có dấu hiệu nhòe/mặt đường ướt. Day reference có dashboard/wiper và bóng râm. Đây là review quan sát bởi integrator, không phải annotation độc lập hoặc xác nhận reference pristine.

Giữ nguyên danh sách train reference do người 1 chọn để không đổi data bàn giao; đánh giá tích hợp là exploratory với baseline này. File người 1 vẫn ghi visual_review=pending. Đề nghị owner 1 bổ sung data notes/code/config và kiểm tra lại reference đêm; nếu thay reference, tạo snapshot và run_id mới rồi calibration/val/freeze lại. `configs/data.json` được reference handoff dẫn chiếu nhưng chưa có trong checkout nên config hash của bước data chưa thể tái hiện từ Git.

## Review val trước freeze

Run `integration_20261006_01` xử lý 300 originals + 6.000 synthetic, đủ 6.300 features. Chỉ chấm 1.260 val frames trước freeze (60 original + 1.200 synthetic). Adaptive mean: original **89,4142**, synthetic **68,6560**; fixed mean tương ứng **88,0251** và **71,7732**. Đây là số tự đo BDD100K của lượt chạy này.

Integrator xem curve severity, lowest originals, rainy originals và cặp original/noise trong `reports/runs/integration_20261006_01/validation_review/`. Có 391 findings tăng so với original parent (fixed/adaptive riêng); nếu tính thêm so với severity trước, có 923 findings. Hai cách đếm không phải số frame độc lập. Brightness_up trên ảnh đêm và noise nhẹ có thể cải thiện score; blur từ severity 2 trở lên có plateau/tăng nhỏ. Lowest originals đều là night và explanation cho thấy dark_ratio là exposure driver; ảnh mưa thật có nước/glare/giảm tương phản nhưng vẫn có thể có health cao. Không suy ra false alarm từ ảnh chưa có quality labels.

Quyết định: giữ nguyên công thức/config của owner 4 và ngưỡng mặc định 75/45 cho exploratory run; không tune theo test. Review note ghi rõ chưa tối ưu bằng labels, không gọi đây là validation của ADAS. Chuyển các ngoại lệ exposure/noise/blur cho owner 4 nghiên cứu trong một run mới.

Val report ở `validation_review/` được tái tạo bằng evaluator hoàn chỉnh sau khi hoàn tất code. Report ban đầu ở `validation/` được tạo bởi process đã khởi động trong lúc phát triển evaluator, giữ lại để trace và được supersede; dùng `validation_review/` để review/hash source/reproduce. Features/health_val/reference draft không đổi.

## Nghiệm thu tích hợp và kết quả test

- **Hoàn tất run:** `integration_20261006_01`; 300 original + 6.000 synthetic; đủ 6.300 feature và health IDs, không duplicate/leakage theo manifest. Split frame: train=3.780, val=1.260, test=1.260. 6.000 seed synthetic duy nhất. Batch verifier kiểm tra source/generated hashes, parameters, seeds và coverage.
- **Freeze:** policy `heuristic-v1-5a7bf047d3a775aa`; config snapshot trong `data/features/integration_20261006_01/references.json` đã frozen sau review val. Frozen val features/metadata/health hashes khớp; test chấm sau freeze; không tune theo kết quả test.
- **Test originals (60):** fixed mean 86,9075; adaptive mean 84,3116, median 89,7866, population std 16,9671.
- **Test synthetic (1.200):** fixed mean 71,3974; adaptive mean 66,3843, median 68,0, std 20,4242. Adaptive có score thấp hơn không tự chứng minh policy tốt hơn khi chưa có nhãn quality.
- **Ngoại lệ test:** 448 findings tăng so với original parent và 564 so với severity trước (fixed/adaptive riêng); toàn run có 4.818 findings. CSV giữ nguyên các ngoại lệ, không lọc để làm curve đẹp.
- **Báo cáo đầy đủ:** `reports/runs/integration_20261006_01/report.md`; `evaluation/` có samples/groups/split_totals/curves/score_increases CSV, biểu đồ, contact sheets và provenance. Output local gitignored; giữ kèm data khi bàn giao ngoài Git.
- **Kiểm chứng code:** 32 unittest đạt (24 có sẵn + 8 bổ sung), validator fixture ML đạt, manifest thật và augmented check-files đạt, compileall và git diff --check đạt. Production evaluator kiểm tra lại health formula/coverage/reference/freeze evidence trên toàn bộ 6.300 frame. Code/config owner 1–4 và originals manifest giữ nguyên.

### Failure metadata cần owner 1 kiểm tra

Review cuối phát hiện `b329fe7d-f06455d3` và `bf8ff5f5-916b50d0` trong test ghi timeofday=daytime nhưng ảnh nhìn giống cảnh đêm (trời tối, đèn đường/đèn xe). Sample đầu fixed≈82,1 nhưng adaptive≈38,7; sample sau fixed=100 nhưng adaptive≈64,9. Đây là nghi vấn từ review ảnh, cần đối chiếu metadata gốc, không tự sửa label trong run đã freeze. Adaptive hiện chọn mode đúng **metadata đã bàn giao** nên lỗi metadata có thể làm policy lệch. Đã giữ ảnh/record và ghi failure; không tune hoặc sửa score test.

### Phần chờ owner và trạng thái Git

Người 5 đã hoàn thành runner/evaluator/validator/report/pitch trong phạm vi phân công. Các PR người 2–4 đã merge trước lượt làm việc này; không phát sinh PR ngoài phạm vi. Phần mới nằm trên `feat/integration`, chưa commit/push để người dùng review. Chờ owner 1 commit code/config/data notes và xác minh reference/metadata; các thay đổi đó phải dùng snapshot/run_id mới. Chờ owner 4 nghiên cứu ngoại lệ nếu nhóm muốn cải thiện policy; không sửa module của owner để tránh conflict.

## Evidence bổ sung theo từng phase — 06/10/2026

Chạy `scripts/audit_real_run.py --run-id integration_20261006_01 --evidence-id evidence_20261006_01` bằng `.venv/Scripts/python.exe`. Script thuộc người 5; không sửa logic của owner. Audit hoàn tất, hashes của input/code/config/output bàn giao trước/sau giống nhau.

| Người | Phase đã chạy trên data thật | Evidence mới |
|---|---|---|
| 1 | Dữ liệu thật đã bàn giao; integrator audit 300 ảnh và metadata. Chưa replay bước prepare_data vì code/config/notes chưa có. | `phase_1.json`: đủ 300 ảnh đọc được, split/reference train-only hợp lệ, không duplicate byte; 300/300 weather/timeofday khớp metadata nguồn local 10.000 mẫu. Visual reference review vẫn pending ở handoff. |
| 2 | Full run sinh 6.000 synthetic từ 300 BDD100K originals. | `phase_2.json` + `pixel_replay.json`: verify toàn bộ hashes/format/seed/parameter/coverage; replay 120 variants của 6 parents phân tầng train/val/test × day/night, bao gồm clear/rainy. Pixel khớp hoàn toàn. |
| 3 | Full run tính đủ 6.300 features từ ảnh thật. | `phase_3.json` + `feature_replay.json`: schema/finite/range/coverage toàn bộ; tái tính 145 records từ ảnh, gồm 120 synthetic, 6 parent và tất cả 20 reference (có overlap). Max absolute difference=0. |
| 4 | Calibration dùng 20 train reference ảnh thật; val review/freeze; chấm 6.300 records gồm 1.260 test. | `phase_4.json`: recalibrate từ feature vừa tính lại từ ảnh; reference hash khớp. Recompute toàn bộ score, policy/mode/weight/action và freeze evidence khớp; 1.260 val record khớp snapshot trước freeze. |
| 5 | Full evaluation trên 6.300 real-run frames. | `phase_5.json`: tái xuất report/plots/contact sheets; `groups`, `samples`, `curves`, `score_increases`, `split_totals` CSV có hash/byte giống báo cáo đã nghiệm thu. |

Thư mục evidence: `reports/runs/integration_20261006_01/evidence_20261006_01/`; entry là `report.md` và `summary.json`. Report tái xuất: `evaluation_replay/report.md`. Mỗi phase JSON ghi số mẫu, scope và thời gian chạy; summary ghi argv, commit, script hash và hashes bảo vệ. Đây là bằng chứng code của các phase đã được integrator thực chạy, không suy ra rằng từng owner đã tự chạy BDD100K trên máy riêng.

Đối chiếu metadata nguồn xác nhận hai flag `b329fe7d-f06455d3` và `bf8ff5f5-916b50d0` cũng mang label daytime trong `data/raw/bdd100k_hf/samples.json`. Do đó handoff của người 1 **khớp nguồn local**; nghi vấn từ review ảnh chưa chứng minh lỗi xử lý của người 1. Giữ nguyên labels và chuyển việc đánh giá chất lượng metadata/reference cho owner trong một snapshot mới.

Không cần sinh lại full 6.000 ảnh hoặc thay snapshot khi replay khớp. Phase 1 vẫn thiếu khả năng tái hiện bước chọn subset/split/QC từ code/config, và reference chưa phải pristine ground truth. Health vẫn là heuristic exploratory, không có nhãn quality/detector/ADAS evidence.
