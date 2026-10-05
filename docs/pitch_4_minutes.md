# Kịch bản pitch 3–5 phút — mục tiêu 4 phút

Đây là kịch bản để nhóm tập; chưa có evidence ghi âm hoặc đo thời gian diễn tập của từng người. Chạy stopwatch khi tập, giữ đúng thứ tự năm mục. Nói số trong bảng chính, không đọc hết config hoặc hash; mở file khi được hỏi.

## 0:00–0:35 — Problem — người 1

Nhóm xây dựng prototype offline để theo dõi trạng thái camera RGB cho bối cảnh ADAS và robot mặt đất. Chúng tôi dùng ảnh camera đường phố BDD100K, chưa triển khai trên xe thật. Khi ảnh tối, mờ hoặc nhiễu, các tín hiệu ảnh thay đổi và có thể ảnh hưởng tới tính năng downstream. Câu hỏi của nhóm là score có phản ứng với lỗi có kiểm soát hay không, và reference ngày/đêm có thể làm đổi quyết định như thế nào.

## 0:35–1:30 — Method — người 2 và 3

Paper Wischow 2023 đặt giám sát camera trong quan hệ với tác vụ và chỉ ra phản ứng có thể không đơn điệu. Nhóm dùng paper làm nền tảng, không tái triển khai estimator ML hoặc bộ điều khiển của tác giả.

Pipeline của nhóm nhận RGB 640×360, tạo bốn corruption với năm mức, rồi tính bảy feature như Laplacian, entropy, dark ratio và median luminance. Calibration dùng 20 ảnh original train, chia mười day và mười night. Health là điểm 0–100 từ penalty có trọng số, không phải accuracy. Fixed dùng reference chung, adaptive chọn nhóm theo metadata. Config được review trên val rồi freeze trước test. Các version, source hashes và lệnh chạy nằm ngay trong Method và Benchmark của report.

## 1:30–2:35 — Benchmark — người 4

Nhóm dùng 300 ảnh thật và tạo 6.000 ảnh synthetic từ chúng. Train, val và test của original là 180, 60 và 60. Bảng chính chỉ lấy split test, corruption giảm sáng. Severity không có đơn vị vật lý; nhóm ghi gain RGB để thấy lượng giảm sáng thực tế. Severity 0 là ảnh gốc và cũng là mốc so sánh.

Với 34 parents metadata daytime, adaptive mean giảm từ 84,54 điểm ở original xuống 30 điểm khi gain bằng 0,12. Với 26 parents night, điểm giảm từ 84,01 xuống 30,15. Đây là phản ứng nhóm tự đo, không phải kết quả của paper. Nó chưa chứng minh adaptive chính xác hơn fixed vì chưa có nhãn quality.

Nhóm có đủ 6.300 features và scores, trong đó 1.260 test records được chấm sau freeze. Audit replay 120 ảnh synthetic khớp pixel và 145 feature records có sai khác tối đa bằng không. Calibration, health và năm CSV evaluation đều tái hiện được. Log và CSV đang có sẵn để mở khi được hỏi.

## 2:35–3:20 — Failure case — người 5

Chúng tôi phân tích một ảnh duy nhất, b329fe7d-f06455d3. Ảnh nhìn giống cảnh đêm nhưng metadata nguồn ghi daytime. Median luminance của frame là 21 trên 255, trong khi day reference có median 102. Diagnostics cho thấy exposure penalty trừ 30 điểm. Fixed score là 82,07, còn adaptive day chỉ 38,66, làm action chuyển từ normal sang strong down-weight nếu so hai policy theo ngưỡng hiện tại.

Handoff khớp metadata nguồn local nên chưa kết luận người chuẩn bị data làm sai. Và khi chưa có quality label hay detector benchmark, nhóm cũng chưa thể nói action nào đúng.

## 3:20–4:00 — Engineering decision — kết luận chung

Số đo dẫn tới một cải tiến đề xuất: metadata-quality gate trước adaptive routing. Khi metadata chưa được review, log phải thể hiện uncertainty để supervisor xử lý; fixed được giữ làm đối chiếu, không coi là fallback an toàn đã được chứng minh. Fallback hiện có chỉ dùng fixed với dawn, dusk hoặc undefined, nên không bắt được trường hợp label daytime nhưng nội dung giống night.

Trade-off là giảm routing sai có thể tăng số frame chưa quyết định và công review. Nhóm giữ nguyên test frozen, cần metadata/reference đã kiểm tra, nhãn quality độc lập và đo detector trên cùng cảnh trước khi dùng score cho phanh, sensor fusion hoặc điều khiển drone.

Trước buổi trình bày, mở sẵn [report nhóm](../report.md), bảng CSV, ảnh failure, penalty JSON và audit summary từ link trong report. Mỗi người tập năm mục của mình từ [bản theo thành viên](report_by_member.md); người trình bày chung dùng kịch bản này. Khi bấm giờ vượt 5 phút, rút phần mô tả feature và audit; giữ số benchmark, failure và trade-off.

Bằng chứng công khai: [integration_20261006_01](evidence/integration_20261006_01/README.md). Code tích hợp đã công bố tại [commit c29e8f9](https://github.com/Munfond/K4-Track4-Day04-Midfeed-Sensor-Reality-Sprint/commit/c29e8f994da629d935f95bb167e8073dfe58cc25). Các ghi chú “chưa commit” mô tả trạng thái tại thời điểm chạy; provenance giữ nguyên lịch sử đó. CSV/plot/log/snapshot chọn lọc mở được trên GitHub; full image replay cần dataset local.
