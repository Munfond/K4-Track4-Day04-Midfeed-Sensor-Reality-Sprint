# Ghi chú bộ đặc trưng suy giảm camera — v1.0.0

Tài liệu triển khai của Người 3. Công thức, miền giá trị, cách chuyển grayscale, schema record và thứ tự feature bên dưới tuân theo [contract dùng chung](contracts.md); contract là nguồn chuẩn của module này.

## Phạm vi và API

`src/features.py` cung cấp API:

```python
extract_features(image_rgb) -> dict[str, float]
```

Đầu vào bắt buộc là mảng NumPy RGB `uint8`, shape `(360, 640, 3)`. Kết quả có đúng bảy key theo thứ tự feature dùng cho model; mọi giá trị là Python `float` hữu hạn:

1. `log_laplacian_variance`
2. `saturation_ratio`
3. `dark_ratio`
4. `entropy`
5. `noise_residual`
6. `median_luminance`
7. `contrast`

Vector này gồm các tín hiệu mức thấp để quan sát ảnh, không phải điểm sức khỏe camera. Không tạo điểm tổng hợp và không thêm nhãn, tập dữ liệu, loại suy giảm ảnh hoặc mức độ suy giảm vào vector hay record đặc trưng.

## Tiền xử lý và trích xuất theo lô

Module chuyển RGB sang grayscale 8-bit bằng Pillow `convert("L")`, sau đó đổi grayscale sang `float64` trước khi tính Laplacian và residual.

CLI đọc manifest và áp dụng chính sách tiền xử lý của project:

- `original`: đọc ảnh, chuyển RGB, sau đó đổi kích thước đúng một lần về 640×360 bằng Pillow BILINEAR.
- Ảnh tổng hợp: đọc và chuyển RGB, yêu cầu kích thước 640×360; không đổi kích thước, khử nhiễu, tăng độ nét hoặc tăng cường ảnh thêm.
- Ảnh lỗi làm lô xử lý dừng và báo `sample_id`; không âm thầm bỏ qua.

Chạy từ thư mục gốc repository, thay run ID và đường dẫn bằng giá trị thực:

```powershell
python -m src.features `
  --manifest data/manifests/augmented_<run_id>.jsonl `
  --output data/features/<run_id>/features.jsonl
```

`image_path` trong manifest phải là đường dẫn POSIX an toàn, tương đối với repository. Dùng `--repo-root <path>` nếu ảnh nằm dưới một thư mục checkout khác trên máy cục bộ. Bộ ghi từ chối ID trùng, hằng JSON không chuẩn, đường dẫn ảnh không an toàn hoặc không tồn tại, manifest rỗng, kích thước ảnh tổng hợp sai và file đầu ra đã tồn tại. Bộ ghi lưu tạm cùng thư mục rồi mới chuyển file hoàn chỉnh vào vị trí đích, tránh để lại feature file dở dang khi xử lý ảnh thất bại.

Mỗi dòng đầu ra theo schema dùng chung: `schema_version`, `record_type`, `sample_id`, `feature_version`, `width`, `height` và object `features`. Feature file phủ chính xác các ID trong manifest đầu vào. Ghép metadata khác từ manifest bằng `sample_id`.

## Công thức, đơn vị và miền giá trị

Gọi `Y` là ảnh grayscale 8-bit do Pillow tạo ra và `N = 360 × 640`.

| Feature | Công thức trong contract | Đơn vị / miền schema | Diễn giải và yếu tố gây nhiễu |
|---|---|---|---|
| `log_laplacian_variance` | `ln(1 + Var(Lap(Y)))`; Laplacian 4 láng giềng, bỏ viền 1 pixel | Không thứ nguyên; `≥ 0` | Proxy cho độ nét/blur. Texture cảnh và noise có thể làm giá trị tăng. |
| `saturation_ratio` | `count(Y ≥ 250) / N` | Tỷ lệ pixel; `[0, 1]` | **Tỷ lệ pixel sáng bị clipping**, không phải độ bão hòa màu HSV. Vùng sáng trong cảnh có thể làm tăng giá trị. |
| `dark_ratio` | `count(Y ≤ 5) / N` | Tỷ lệ pixel; `[0, 1]` | Tỷ lệ pixel rất tối. Cảnh đêm hợp lệ cũng có thể có giá trị cao. |
| `entropy` | Entropy Shannon của histogram 256 bin, `−Σ pᵢ log₂(pᵢ)` với `pᵢ > 0` | Bit trên pixel của histogram cường độ; `[0, 8]` | Độ phức tạp phân bố cường độ. Noise có thể làm entropy tăng; entropy không phải thước đo chất lượng đơn điệu. |
| `noise_residual` | `sqrt(mean((Y − median3(Y))²))`; bộ lọc median Pillow 3×3 | Mức cường độ grayscale; `[0, 255]` | Proxy residual tần số cao. Có cả cạnh và texture, không chỉ có nhiễu cảm biến. |
| `median_luminance` | `median(Y)` | Mức cường độ grayscale 8-bit; `[0, 255]` | Độ sáng trung tâm vững hơn mean; ánh sáng của cảnh vẫn là yếu tố gây nhiễu. |
| `contrast` | Độ lệch chuẩn tổng thể `std(Y)`, `ddof=0` | Mức cường độ grayscale 8-bit; `[0, 127.5]` | Độ trải tông toàn ảnh. Cảnh vốn phẳng có thể có tương phản thấp mà camera không hỏng. |

Miền giá trị trong schema suy ra từ công thức áp dụng trên grayscale 8-bit. Entropy dùng log cơ số 2; Laplacian feature dùng log tự nhiên.

## Độ nhạy dự kiến và giới hạn

Đây là xu hướng khi thay đổi có kiểm soát trên cùng cảnh, không phải khẳng định đúng cho mọi ảnh:

| Thay đổi | Phản ứng thường gặp | Yếu tố gây nhiễu chính |
|---|---|---|
| Mờ Gaussian tăng | Laplacian thường giảm; residual có thể giảm | Texture, nội suy đổi kích thước và noise |
| Nhiễu Gaussian tăng | Residual thường tăng; entropy và Laplacian cũng có thể tăng | Texture và cạnh trong cảnh |
| Độ sáng giảm | Median luminance thường giảm, dark ratio thường tăng | Cảnh đêm hoặc vốn tối |
| Clipping vùng sáng tăng | `saturation_ratio` thường tăng | Vật thể sáng và đèn thật trong cảnh |
| Lớp phủ mưa tăng | Không có hướng ổn định cho toàn bộ vector | Cách tạo lớp phủ và nội dung cảnh |

Giữ nguyên vector để so sánh ảnh suy giảm với baseline. Hiệu chỉnh ngưỡng ở bước xử lý phía sau bằng baseline và các nhóm dữ liệu phù hợp. Không diễn giải Laplacian hoặc entropy cao hơn là ảnh tốt hơn, và không suy ra độ chính xác bộ phát hiện vật thể từ các feature này.

## Record ví dụ

Ví dụ minh họa cho frame đen đồng nhất; đây là dữ liệu kiểm thử số học, không phải quan sát BDD100K:

```json
{"schema_version":"1.0.0","record_type":"features","sample_id":"constant_black_demo","feature_version":"1.0.0","width":640,"height":360,"features":{"log_laplacian_variance":0.0,"saturation_ratio":0.0,"dark_ratio":1.0,"entropy":0.0,"noise_residual":0.0,"median_luminance":0.0,"contrast":0.0}}
```

## Kiểm chứng và tái hiện

Kết quả kiểm chứng ngày 2026-10-05: cả bảy kiểm tra tập trung đều đạt: đối chiếu công thức độc lập, ảnh đen/trắng đồng nhất, kiểm tra đầu vào nghiêm ngặt, chỉ đổi kích thước ảnh gốc, từ chối ảnh tổng hợp sai kích thước, manifest sai định dạng và CLI tạo record hợp JSON Schema. Cả 12 test hiện có của repository đều đạt; validator chấp nhận dữ liệu fixture gồm bốn record manifest và bốn record feature. Các kiểm tra tập trung chạy bằng harness tạm; theo phân công repository, Người 5 sở hữu thư mục `tests/` và các test lưu lâu dài.

Trước khi bàn giao lô dữ liệu thật, chạy bộ test chung và validator:

```powershell
python -m unittest discover -s tests -v
python scripts/validate_contract.py `
  --manifest data/manifests/augmented_<run_id>.jsonl `
  --features data/features/<run_id>/features.jsonl
```

Validator cần manifest đã bổ sung đầy đủ cùng các record ảnh tương ứng. Checkout hiện chỉ có JSONL fixture mẫu, không có tập ảnh hoặc manifest run đã bổ sung ảnh suy giảm; vì vậy chưa có lô feature thật, số lượng ID phủ, báo cáo miền giá trị hay thống kê suy giảm ảnh nào được tuyên bố.

## Bối cảnh khoa học

Các bài báo dưới đây gợi ý cách chọn tín hiệu mức thấp và những giới hạn cần lưu ý; chúng không xác nhận chính xác vector bảy feature này và không cung cấp kết quả benchmark của nhóm:

- Wischow và cộng sự, [Monitoring and Adapting the Physical State of a Camera for Autonomous Vehicles](https://arxiv.org/abs/2112.05456), *IEEE Transactions on Intelligent Transportation Systems*, 2023. Nghiên cứu đặt việc tự giám sát tình trạng camera trong mối liên hệ với blur/noise và khả năng phát hiện vật thể ở bước sau; hiệu năng ứng dụng có thể phi tuyến, không đơn điệu.
- Hu và cộng sự, [Toward a No-Reference Quality Metric for Camera-Captured Images](https://pubmed.ncbi.nlm.nih.gov/34847052/), *IEEE Transactions on Cybernetics*, 2023. NR-IQA của bài kết hợp feature mức thấp với feature ngữ nghĩa; các metric thô của project không phải metric đầy đủ đó.
- Pertuz và cộng sự, [Analysis of Focus Measure Operators for Shape-from-Focus](https://www.sciencedirect.com/science/article/pii/S0031320312004736), *Pattern Recognition*, 2013. Bài so sánh toán tử lấy nét trong các điều kiện noise, contrast, saturation và window size, qua đó cho thấy cần thận trọng khi chỉ dùng một Laplacian measure.

\n