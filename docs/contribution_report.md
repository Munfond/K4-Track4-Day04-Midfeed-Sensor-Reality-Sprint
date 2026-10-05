# Báo cáo đóng góp cá nhân — Camera Degradation Metrics

| Thông tin | Giá trị |
|---|---|
| Người đóng góp | Nguyễn Hoàng Duy |
| MSSV | 2A202602751 |
| Vai trò | Người 3 — Feature/Metric |
| Nhánh Git | `metric` |
| Ngày ghi nhận | 05/10/2026 |

## Mục tiêu

Triển khai bộ bảy đặc trưng ảnh camera theo contract v1.0.0 để mô tả các tín hiệu mức thấp như độ nét, clipping vùng sáng, vùng tối, entropy, residual tần số cao, độ sáng trung vị và tương phản. Các đặc trưng là tín hiệu quan sát; không gộp thành camera-health score trong module này.

## Nội dung đã thực hiện

- Xây dựng API `extract_features(image_rgb)` trong `src/features.py`, kiểm tra đầu vào RGB `uint8` kích thước `(360, 640, 3)` và trả đúng bảy giá trị hữu hạn theo thứ tự contract.
- Hiện thực công thức v1.0.0 bằng Pillow và NumPy, gồm grayscale Pillow, `float64` trước Laplacian/residual, Laplacian 4 láng giềng, histogram entropy 256 bin và median filter Pillow 3×3.
- Bổ sung CLI xử lý manifest theo lô, ghi JSONL theo schema, kiểm tra ID trùng, đường dẫn ảnh và kích thước synthetic; lỗi ảnh làm dừng batch và nêu `sample_id`.
- Áp dụng preprocessing theo loại ảnh: ảnh `original` được resize BILINEAR một lần về 640×360; ảnh tổng hợp phải đúng kích thước sẵn có và không bị resize lại.
- Viết tài liệu metric bằng tiếng Việt tại [`Metrics.md`](Metrics.md), gồm công thức, đơn vị, miền giá trị, cách tái hiện, giới hạn diễn giải và nguồn tham khảo.

## Kiểm chứng

Ngày 05/10/2026, các kiểm tra sau đều đạt:

- Bảy kiểm tra tập trung cho công thức, ảnh đen/trắng, kiểm tra đầu vào, chính sách resize, manifest lỗi và CLI tạo record hợp JSON Schema.
- 12 test hiện có của repository.
- Validator trên fixture ví dụ: 4 record manifest và 4 record feature có coverage hợp lệ.
- Biên dịch Python bằng `python -m compileall -q src`.

Các kiểm tra tập trung dùng harness tạm, không lưu trong `tests/` vì repository giao quyền sở hữu test lâu dài cho Người 5.

## Bàn giao và giới hạn

Code được bàn giao trong `src/features.py`; tài liệu metric nằm tại [`Metrics.md`](Metrics.md). Chưa tạo `data/features/<run_id>/features.jsonl` từ dữ liệu thật vì workspace chưa có augmented manifest và ảnh đầu vào. Record ví dụ trong tài liệu metric là fixture ảnh đen đồng nhất, không phải kết quả BDD100K hay benchmark của nhóm.
