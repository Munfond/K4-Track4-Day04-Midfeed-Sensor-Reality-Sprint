# Camera Degradation Features — v1.0.0

Implementation notes for Người 3. The formulas, ranges, grayscale conversion, record schema, and feature order below follow [the shared contract](contracts.md), which is authoritative for this module.

## Scope and API

`src/features.py` exposes:

```python
extract_features(image_rgb) -> dict[str, float]
```

The input must be a NumPy RGB `uint8` array with shape `(360, 640, 3)`. The result contains exactly these seven keys, in model order, and each value is a finite Python `float`:

1. `log_laplacian_variance`
2. `saturation_ratio`
3. `dark_ratio`
4. `entropy`
5. `noise_residual`
6. `median_luminance`
7. `contrast`

The vector is low-level observation data, not a camera-health score. No composite score, label, split, corruption name, or severity is added to the feature vector or output record.

## Preprocessing and batch behavior

The module converts RGB to 8-bit grayscale with Pillow `convert("L")`, then converts grayscale to `float64` before Laplacian and residual arithmetic.

The manifest CLI applies the project preprocessing policy:

- `original`: read and convert to RGB, then resize once to 640×360 with Pillow BILINEAR.
- Synthetic corruption: read and convert to RGB, require 640×360, and do not resize, denoise, sharpen, or enhance it.
- Any bad image fails with its `sample_id`; it is not silently skipped.

Run from the repository root, substituting the real run ID and paths:

```powershell
python -m src.features `
  --manifest data/manifests/augmented_<run_id>.jsonl `
  --output data/features/<run_id>/features.jsonl
```

`image_path` entries are safe, repository-relative POSIX paths. Use `--repo-root <path>` if the images live under a different local checkout root. The writer rejects duplicate IDs, non-standard JSON constants, unsafe/missing image paths, empty manifests, mismatched synthetic dimensions, and an existing output path. It writes to a temporary sibling and moves the finished JSONL into place, so an image failure does not leave a partial feature file.

Each output line follows the shared schema: `schema_version`, `record_type`, `sample_id`, `feature_version`, `width`, `height`, and the nested `features` object. The feature file covers exactly the IDs in its input manifest. Join additional fields from the manifest by `sample_id`.

## Exact formulas, units, and ranges

Let `Y` be the Pillow 8-bit grayscale image and let `N = 360 × 640`.

| Feature | Contract formula | Unit / schema range | Interpretation and confounder |
|---|---|---|---|
| `log_laplacian_variance` | `ln(1 + Var(Lap(Y)))`; 4-neighbour Laplacian, excluding a 1-pixel border | Dimensionless; `≥ 0` | Sharpness/blur proxy. Scene texture and noise can increase it. |
| `saturation_ratio` | `count(Y ≥ 250) / N` | Pixel fraction; `[0, 1]` | **Clipped bright-pixel ratio**, not HSV color saturation. Scene highlights can raise it. |
| `dark_ratio` | `count(Y ≤ 5) / N` | Pixel fraction; `[0, 1]` | Very-dark-pixel ratio. Legitimate night scenes can be high. |
| `entropy` | Shannon entropy of the 256-bin histogram, `−Σ pᵢ log₂(pᵢ)` for `pᵢ > 0` | Bits per pixel of the intensity histogram; `[0, 8]` | Intensity-distribution complexity. Noise can increase it; it is not a monotonic quality score. |
| `noise_residual` | `sqrt(mean((Y − median3(Y))²))`; Pillow 3×3 median filter | Grayscale code values; `[0, 255]` | High-frequency residual proxy. It includes edges and texture, not just sensor noise. |
| `median_luminance` | `median(Y)` | 8-bit grayscale code values; `[0, 255]` | Robust central brightness; scene illumination remains a confounder. |
| `contrast` | Population `std(Y)`, `ddof=0` | 8-bit grayscale code values; `[0, 127.5]` | Global tonal spread. Naturally flat scenes can have low contrast without camera failure. |

The schema is stricter for ranges than the API needs to be; these limits follow from the formulas on 8-bit grayscale. Entropy uses log base 2. The Laplacian feature uses the natural logarithm.

## Expected sensitivity and limitations

These are tendencies for controlled changes to the same scene, not universal assertions:

| Change | Likely response | Main confounder |
|---|---|---|
| Gaussian blur increases | Laplacian feature often decreases; residual may decrease | Texture, resampling, and noise |
| Gaussian noise increases | Residual often increases; entropy and Laplacian can also increase | Scene texture and edges |
| Brightness decreases | Median luminance often decreases and dark ratio often increases | Naturally dark/night scenes |
| Bright clipping increases | `saturation_ratio` often increases | Real bright objects and lights |
| Rain overlay increases | No reliable direction expected across the full vector | Overlay design and scene content |

Keep the vector intact for baseline-versus-degraded comparisons. Calibrate thresholds on appropriate training references and slices downstream. Do not interpret a higher Laplacian value or entropy as proof of better image quality, and do not infer detector accuracy from these features.

## Example record

Illustrative output for an all-black constant frame; this is a numeric fixture, not a BDD100K observation:

```json
{"schema_version":"1.0.0","record_type":"features","sample_id":"constant_black_demo","feature_version":"1.0.0","width":640,"height":360,"features":{"log_laplacian_variance":0.0,"saturation_ratio":0.0,"dark_ratio":1.0,"entropy":0.0,"noise_residual":0.0,"median_luminance":0.0,"contrast":0.0}}
```

## Verification and reproduction

Verification on 2026-10-05: seven focused feature checks passed for independent formula calculations, constant black/white images, strict input validation, original-only resizing, synthetic-size rejection, malformed manifests, and the module CLI against the JSON Schema. The 12 existing repository tests pass, and the validator accepts the four-record example manifest/features fixture. The focused checks used a temporary harness; the repository assigns permanent `tests/` ownership to Người 5.

Before a real-data handoff, run the shared repository suite and validator:

```powershell
python -m unittest discover -s tests -v
python scripts/validate_contract.py `
  --manifest data/manifests/augmented_<run_id>.jsonl `
  --features data/features/<run_id>/features.jsonl
```

The validator command requires a real augmented manifest with its complete image records. This checkout currently contains example JSONL fixtures but no image dataset or augmented run manifest, so no real feature batch, coverage count, range report, or degradation statistics are claimed here.

## Scientific context

These papers motivate the choice of interpretable low-level signals and the limitations below; they do not validate this exact seven-feature vector or provide results for this lab:

- Wischow et al., [Monitoring and Adapting the Physical State of a Camera for Autonomous Vehicles](https://arxiv.org/abs/2112.05456), *IEEE Transactions on Intelligent Transportation Systems*, 2023. The camera self-health framing relates blur/noise to downstream object detection and reports non-linear, non-monotonic application behavior.
- Hu et al., [Toward a No-Reference Quality Metric for Camera-Captured Images](https://pubmed.ncbi.nlm.nih.gov/34847052/), *IEEE Transactions on Cybernetics*, 2023. Its learned NR-IQA combines low-level properties with semantic features; this project's raw metrics are not that full metric.
- Pertuz et al., [Analysis of Focus Measure Operators for Shape-from-Focus](https://www.sciencedirect.com/science/article/pii/S0031320312004736), *Pattern Recognition*, 2013. The comparison studies focus operators under changes including noise, contrast, saturation, and window size, supporting caution around a single Laplacian measure.
