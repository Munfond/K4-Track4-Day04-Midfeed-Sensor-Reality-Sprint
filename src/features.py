"""Contract v1.0.0 camera-frame features and their JSONL batch writer."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

FEATURE_VERSION = "1.0.0"
FEATURE_ORDER = (
    "log_laplacian_variance",
    "saturation_ratio",
    "dark_ratio",
    "entropy",
    "noise_residual",
    "median_luminance",
    "contrast",
)
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 360
SCHEMA_VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
CORRUPTIONS = {
    "original",
    "gaussian_blur",
    "brightness_up",
    "brightness_down",
    "gaussian_noise",
    "rain_overlay",
}
SAMPLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_rgb(image_rgb: np.ndarray) -> None:
    if not isinstance(image_rgb, np.ndarray):
        raise ValueError("image_rgb must be a numpy.ndarray")
    if image_rgb.dtype != np.uint8:
        raise ValueError(f"image_rgb must have dtype uint8, got {image_rgb.dtype}")
    if image_rgb.shape != (IMAGE_HEIGHT, IMAGE_WIDTH, 3):
        raise ValueError(
            f"image_rgb must have shape ({IMAGE_HEIGHT}, {IMAGE_WIDTH}, 3), "
            f"got {image_rgb.shape}"
        )


def extract_features(image_rgb: np.ndarray) -> dict[str, float]:
    """Return the seven ordered, finite v1 features for an RGB uint8 frame."""
    _validate_rgb(image_rgb)

    gray_u8 = np.asarray(Image.fromarray(image_rgb).convert("L"), dtype=np.uint8)
    gray = gray_u8.astype(np.float64)

    # Four-neighbour Laplacian, excluding the one-pixel border per contract.
    laplacian = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - 4.0 * gray[1:-1, 1:-1]
    )
    probabilities = np.bincount(gray_u8.ravel(), minlength=256).astype(np.float64)
    probabilities /= gray_u8.size
    probabilities = probabilities[probabilities > 0]

    median3_u8 = np.asarray(
        Image.fromarray(gray_u8).filter(ImageFilter.MedianFilter(size=3)),
        dtype=np.uint8,
    )
    residual = gray - median3_u8.astype(np.float64)

    features = {
        "log_laplacian_variance": float(np.log1p(np.var(laplacian, ddof=0))),
        "saturation_ratio": float(np.count_nonzero(gray_u8 >= 250) / gray_u8.size),
        "dark_ratio": float(np.count_nonzero(gray_u8 <= 5) / gray_u8.size),
        "entropy": float(-np.sum(probabilities * np.log2(probabilities))),
        "noise_residual": float(np.sqrt(np.mean(residual * residual))),
        "median_luminance": float(np.median(gray)),
        "contrast": float(np.std(gray, ddof=0)),
    }
    if tuple(features) != FEATURE_ORDER or not all(math.isfinite(value) for value in features.values()):
        raise FloatingPointError("feature calculation produced an invalid v1 vector")
    return features


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is forbidden")


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    sample_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line, parse_constant=_reject_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: manifest row must be a JSON object")
            sample_id = record.get("sample_id")
            if not isinstance(sample_id, str) or not SAMPLE_ID_PATTERN.fullmatch(sample_id):
                raise ValueError(f"{path}:{line_number}: invalid or missing sample_id")
            if sample_id in sample_ids:
                raise ValueError(f"{path}:{line_number}: duplicate sample_id {sample_id}")
            sample_ids.add(sample_id)
            corruption = record.get("corruption")
            if not isinstance(corruption, str) or corruption not in CORRUPTIONS:
                raise ValueError(f"{path}:{line_number}: invalid corruption for {sample_id}")
            if not isinstance(record.get("image_path"), str) or not record["image_path"]:
                raise ValueError(f"{path}:{line_number}: missing image_path for {sample_id}")
            record["_manifest_line"] = line_number
            records.append(record)
    if not records:
        raise ValueError(f"manifest is empty: {path}")
    return records


def _load_manifest_image(record: dict[str, Any], image_root: Path) -> np.ndarray:
    sample_id = record["sample_id"]
    image_path = record["image_path"]
    posix_path = PurePosixPath(image_path)
    windows_path = PureWindowsPath(image_path)
    if (
        Path(image_path).is_absolute()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or "\\" in image_path
        or ".." in posix_path.parts
    ):
        raise ValueError(f"{sample_id}: image_path must be a safe repo-relative POSIX path")
    resolved_path = (image_root / Path(*posix_path.parts)).resolve()
    if not resolved_path.is_relative_to(image_root):
        raise ValueError(f"{sample_id}: image_path escapes the repository root")
    if not resolved_path.is_file():
        raise FileNotFoundError(f"{sample_id}: image file not found: {image_path}")

    with Image.open(resolved_path) as source:
        rgb = source.convert("RGB")
        if record["corruption"] == "original":
            rgb = rgb.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.Resampling.BILINEAR)
        elif rgb.size != (IMAGE_WIDTH, IMAGE_HEIGHT):
            raise ValueError(
                f"{sample_id}: synthetic image must already be "
                f"{IMAGE_WIDTH}x{IMAGE_HEIGHT}, got {rgb.width}x{rgb.height}"
            )
        return np.array(rgb, dtype=np.uint8, copy=True)


def extract_manifest(
    manifest_path: str | Path,
    output_path: str | Path,
    image_root: str | Path | None = None,
) -> int:
    """Extract one contract feature record per manifest ID without partial output."""
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    image_root = Path(image_root or REPO_ROOT).resolve()
    if not image_root.is_dir():
        raise NotADirectoryError(f"repository root does not exist: {image_root}")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite feature output: {output_path}")

    manifest = _read_manifest(manifest_path)
    expected_ids = {record["sample_id"] for record in manifest}
    features: list[dict[str, Any]] = []
    for record in manifest:
        sample_id = record["sample_id"]
        try:
            image_rgb = _load_manifest_image(record, image_root)
            vector = extract_features(image_rgb)
            features.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "features",
                    "sample_id": sample_id,
                    "feature_version": FEATURE_VERSION,
                    "width": IMAGE_WIDTH,
                    "height": IMAGE_HEIGHT,
                    "features": vector,
                }
            )
        except (OSError, ValueError, FloatingPointError) as exc:
            line_number = record["_manifest_line"]
            raise ValueError(f"{sample_id} (manifest line {line_number}): {exc}") from exc

    produced_ids = [record["sample_id"] for record in features]
    if len(produced_ids) != len(set(produced_ids)) or set(produced_ids) != expected_ids:
        raise RuntimeError("feature output IDs do not exactly match manifest IDs")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for record in features:
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
                stream.write("\n")
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return len(features)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract contract v1.0.0 camera features from a manifest.")
    parser.add_argument("--manifest", required=True, type=Path, help="input JSONL manifest")
    parser.add_argument("--output", required=True, type=Path, help="new output features JSONL path")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="root used to resolve manifest image_path values (default: repository root)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        count = extract_manifest(args.manifest, args.output, image_root=args.repo_root)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"feature extraction failed: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {count} feature records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
