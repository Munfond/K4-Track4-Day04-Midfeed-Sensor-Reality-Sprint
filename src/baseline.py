"""Train-reference camera health heuristic for feature contract v1.

This module uses only the Python standard library and performs no work on import.
Health is a descriptive heuristic, not a calibrated probability of camera safety.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import median


FEATURE_NAMES = (
    "log_laplacian_variance", "saturation_ratio", "dark_ratio", "entropy",
    "noise_residual", "median_luminance", "contrast",
)
PENALTY_FEATURES = FEATURE_NAMES[:-1]
LIMITS = (None, 1, 1, 8, 255, 255, 127.5)
TIME_MODES = {"daytime": "day", "night": "night"}
TIME_VALUES = {"daytime", "night", "dawn/dusk", "undefined"}
FORMULA_VERSION = "weighted_reference_penalties_v1"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, name, minimum=0, maximum=None):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool),
             f"{name}: expected a number")
    _require(math.isfinite(value), f"{name}: number must be finite")
    _require(value >= minimum and (maximum is None or value <= maximum),
             f"{name}: number outside allowed range")
    return float(value)


def _hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sample_id(row):
    sid = row.get("sample_id")
    _require(isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9_-]+", sid),
             f"Invalid sample_id: {sid!r}")
    return sid


def _index(rows, name):
    indexed = {}
    for row in rows:
        _require(isinstance(row, dict), f"{name}: expected object records")
        sid = _sample_id(row)
        _require(sid not in indexed, f"{name}: duplicate sample_id {sid}")
        indexed[sid] = row
    _require(bool(indexed), f"{name}: cannot be empty")
    return indexed


def _feature_values(row):
    sid = _sample_id(row)
    _require(set(row) == {"schema_version", "record_type", "sample_id",
                          "feature_version", "width", "height", "features"},
             f"{sid}: unexpected or missing feature record fields")
    _require(row["schema_version"] == "1.0.0" and row["record_type"] == "features"
             and row["feature_version"] == "1.0.0", f"{sid}: incompatible feature version/type")
    _require(row["width"] == 640 and row["height"] == 360,
             f"{sid}: features must describe 640x360 images")
    values = row["features"]
    _require(isinstance(values, dict) and set(values) == set(FEATURE_NAMES),
             f"{sid}: expected exactly the seven v1 features")
    return {key: _number(values[key], f"{sid}.{key}", maximum=limit)
            for key, limit in zip(FEATURE_NAMES, LIMITS)}


def _metadata_index(metadata):
    indexed = _index(metadata, "metadata")
    sequences = {}
    for sid, row in indexed.items():
        _require(row.get("schema_version") == "1.0.0"
                 and row.get("record_type") == "manifest", f"{sid}: expected v1 manifest metadata")
        _require(row.get("split") in {"train", "val", "test"}, f"{sid}: invalid lab split")
        _require(row.get("timeofday") in TIME_VALUES, f"{sid}: invalid timeofday metadata")
        seq = row.get("sequence_id")
        _require(isinstance(seq, str) and bool(seq), f"{sid}: missing sequence_id")
        _require(seq not in sequences or sequences[seq] == row["split"],
                 f"{sid}: sequence split leakage")
        sequences[seq] = row["split"]
    return indexed


def _policy_content(config):
    return {key: config[key] for key in (
        "feature_version", "formula_version", "weights", "scale_multiplier",
        "scale_floors", "tolerances", "thresholds",
    )}


def policy_id_for(config):
    """Return a new policy ID whenever a scoring parameter changes."""
    content = {"parameters": _policy_content(config),
               "reference_sha256": config.get("reference_sha256")}
    return "heuristic-v1-" + _hash(content)[:16]


def prepare_config(config):
    """Copy a draft config and refresh its policy ID after manual val tuning."""
    _require(isinstance(config, dict), "Health config must be a JSON object")
    result = copy.deepcopy(config)
    _require(result.get("frozen") is False, "Cannot edit a frozen config; start a new draft")
    result["policy_id"] = policy_id_for(result)
    validate_config(result)
    return result


def validate_config(config):
    _require(isinstance(config, dict), "Health config must be a JSON object")
    _require(config.get("schema_version") == "1.0.0"
             and config.get("feature_version") == "1.0.0", "Unsupported health config version")
    _require(config.get("formula_version") == FORMULA_VERSION, "Unsupported health formula")
    weights = config.get("weights", {})
    _require(set(weights) == {"sharpness", "exposure", "noise", "entropy"}, "Invalid weight keys")
    total = sum(_number(value, f"weights.{key}", maximum=1) for key, value in weights.items())
    _require(abs(total - 1) <= 1e-9, "Health weights must sum to one")
    _require(_number(config.get("scale_multiplier"), "scale_multiplier") > 0,
             "scale_multiplier must be positive")
    for field in ("scale_floors", "tolerances"):
        values = config.get(field, {})
        _require(set(values) == set(PENALTY_FEATURES), f"Invalid {field} keys")
        for key, value in values.items():
            parsed = _number(value, f"{field}.{key}")
            _require(field != "scale_floors" or parsed > 0, f"{field}.{key} must be positive")
    thresholds = config.get("thresholds", {})
    _require(set(thresholds) == {"normal_min", "down_weight_min"}, "Invalid threshold keys")
    low = _number(thresholds["down_weight_min"], "down_weight_min", maximum=100)
    high = _number(thresholds["normal_min"], "normal_min", maximum=100)
    _require(low < high, "Thresholds must satisfy 0 <= down_weight_min < normal_min <= 100")
    _require(isinstance(config.get("frozen"), bool), "Config must declare frozen true/false")
    _require(config.get("policy_id") == policy_id_for(config), "Policy ID does not match config")
    ref_hash = config.get("reference_sha256")
    _require(ref_hash is None or (isinstance(ref_hash, str) and re.fullmatch(r"[a-f0-9]{64}", ref_hash)),
             "Invalid reference_sha256")
    _require(not config["frozen"] or ref_hash is not None, "Frozen config requires a reference hash")


def _summaries(reference_rows):
    groups = {}
    for mode in ("fixed", "day", "night"):
        rows = [row for row in reference_rows
                if mode == "fixed" or TIME_MODES.get(row["timeofday"]) == mode]
        _require(bool(rows), f"Missing original train references for {mode}")
        centers, deviations = {}, {}
        for key in FEATURE_NAMES:
            values = [row["features"][key] for row in rows]
            center = median(values)
            centers[key] = center
            deviations[key] = median(abs(value - center) for value in values)
        groups[mode] = {"sample_ids": [row["sample_id"] for row in rows],
                        "count": len(rows), "median": centers, "mad": deviations}
    return groups


def _reference_content(references):
    return {key: references[key] for key in ("feature_version", "reference_rows", "groups")}


def calibrate(reference_features, metadata, config):
    """Summarize only the selected original train feature records.

    The caller selects reference_features using person 1's reference IDs.
    metadata may be the complete augmented manifest or just the selected rows.
    Both day and night reference groups are required; missing groups fail clearly.
    """
    validate_config(config)
    _require(not config["frozen"], "Calibration requires a draft config")
    _require(config["reference_sha256"] is None, "New calibration requires an unbound draft config")
    selected = _index(reference_features, "reference features")
    images = _metadata_index(metadata)
    rows = []
    for sid in sorted(selected):
        _require(sid in images, f"Reference metadata missing: {sid}")
        image = images[sid]
        _require(image["split"] == "train" and image.get("corruption") == "original"
                 and image.get("parent_image_id") == sid and image.get("severity") == 0,
                 f"Reference must be a self-parent original in lab train: {sid}")
        rows.append({"sample_id": sid, "split": "train", "corruption": "original",
                     "sequence_id": image["sequence_id"],
                     "timeofday": image["timeofday"], "features": _feature_values(selected[sid])})
    result = {"schema_version": "1.0.0", "record_type": "heuristic_references",
              "feature_version": "1.0.0", "reference_rows": rows, "groups": _summaries(rows)}
    result["reference_sha256"] = _hash(_reference_content(result))
    snapshot = copy.deepcopy(config)
    snapshot["reference_sha256"] = result["reference_sha256"]
    snapshot["policy_id"] = policy_id_for(snapshot)
    result["config"] = snapshot
    result["config_sha256"] = _hash(snapshot)
    result["policy_sha256"] = _hash(_policy_content(config))
    return result


def _validate_references(references, config):
    validate_config(config)
    _require(references.get("schema_version") == "1.0.0"
             and references.get("record_type") == "heuristic_references"
             and references.get("feature_version") == "1.0.0", "Unsupported references artifact")
    rows = references.get("reference_rows", [])
    _index(rows, "reference rows")
    for row in rows:
        sid = row["sample_id"]
        _require(row.get("split") == "train" and row.get("corruption") == "original",
                 f"Reference artifact contains a non-train/original row: {sid}")
        _require(row.get("timeofday") in TIME_VALUES, f"Invalid reference timeofday: {sid}")
        _require(isinstance(row.get("sequence_id"), str) and bool(row["sequence_id"]),
                 f"Missing reference sequence_id: {sid}")
        _feature_values({"schema_version": "1.0.0", "record_type": "features", "sample_id": sid,
                         "feature_version": "1.0.0", "width": 640, "height": 360,
                         "features": row["features"]})
    _require(references.get("groups") == _summaries(rows), "Reference summary does not match rows")
    expected_hash = _hash(_reference_content(references))
    _require(references.get("reference_sha256") == expected_hash, "Reference hash mismatch")
    _require(config["reference_sha256"] == expected_hash, "Config bound to a different reference")
    _require(references.get("policy_sha256") == _hash(_policy_content(config)),
             "Config changed after calibration; recalibrate and score val again")
    snapshot = references.get("config", {})
    validate_config(snapshot)
    _require(references.get("config_sha256") == _hash(snapshot), "Config snapshot hash mismatch")
    _require(snapshot["reference_sha256"] == expected_hash
             and snapshot["frozen"] == config["frozen"]
             and _policy_content(snapshot) == _policy_content(config), "Reference config snapshot mismatch")
    if config["frozen"]:
        evidence = config.get("validation", {})
        _require(isinstance(evidence, dict) and evidence.get("split") == "val"
                 and isinstance(evidence.get("sample_ids"), list) and bool(evidence["sample_ids"])
                 and isinstance(evidence.get("sequence_ids"), list) and bool(evidence["sequence_ids"])
                 and isinstance(evidence.get("note"), str) and bool(evidence["note"].strip()),
                 "Frozen config requires validation evidence")
        _require(snapshot.get("validation") == evidence, "Frozen validation evidence mismatch")


def _reference_details(values, group, config):
    """Compute the unchanged score and explain each weighted penalty."""
    centers = group["median"]
    scales = {key: max(config["scale_floors"][key],
                       1.4826 * group["mad"][key] * config["scale_multiplier"])
              for key in PENALTY_FEATURES}
    _require(all(math.isfinite(value) for value in scales.values()), "Reference scales overflowed")

    def penalty(key, deviation):
        normalized = deviation / scales[key] - config["tolerances"][key]
        return min(1.0, max(0.0, normalized))

    exposure_details = {
        "dark_ratio": penalty("dark_ratio", values["dark_ratio"] - centers["dark_ratio"]),
        "saturation_ratio": penalty("saturation_ratio", values["saturation_ratio"] - centers["saturation_ratio"]),
        "median_luminance": penalty("median_luminance", abs(values["median_luminance"] - centers["median_luminance"])),
    }
    penalties = {
        "sharpness": penalty("log_laplacian_variance",
                             centers["log_laplacian_variance"] - values["log_laplacian_variance"]),
        "entropy": penalty("entropy", centers["entropy"] - values["entropy"]),
        "noise": penalty("noise_residual", values["noise_residual"] - centers["noise_residual"]),
        "exposure": max(exposure_details.values()),
    }
    weighted = sum(config["weights"][key] * value for key, value in penalties.items())
    return {
        "health_score": min(100.0, max(0.0, 100.0 * (1.0 - weighted))),
        "reference_count": group["count"],
        "penalties": penalties,
        "penalty_points": {key: 100.0 * config["weights"][key] * value
                           for key, value in penalties.items()},
        "reference_median": dict(centers),
        "scales": scales,
        "deadbands": {key: scales[key] * config["tolerances"][key] for key in scales},
        "exposure_penalties": exposure_details,
        "exposure_driver": max(exposure_details, key=exposure_details.get)
                           if penalties["exposure"] > 0 else None,
    }


def _reference_score(values, group, config):
    return _reference_details(values, group, config)["health_score"]


def _score_row(feature_row, timeofday, references, config):
    values = _feature_values(feature_row)
    _require(timeofday in TIME_VALUES, f"{feature_row['sample_id']}: invalid timeofday")
    mode = TIME_MODES.get(timeofday, "fixed_fallback")
    fixed = _reference_score(values, references["groups"]["fixed"], config)
    adaptive = fixed if mode == "fixed_fallback" else _reference_score(
        values, references["groups"][mode], config)
    thresholds = config["thresholds"]
    action = ("normal" if adaptive >= thresholds["normal_min"] else
              "down_weight" if adaptive >= thresholds["down_weight_min"] else "strong_down_weight")
    result = {"schema_version": "1.0.0", "record_type": "heuristic_health",
              "sample_id": feature_row["sample_id"], "policy_id": config["policy_id"], "mode": mode,
              "health_fixed": fixed, "health_adaptive": adaptive, "health_score": adaptive,
              "camera_weight": (adaptive / 100.0) ** 2, "action": action}
    if mode == "fixed_fallback":
        result["fallback_reason"] = "timeofday=" + timeofday
    return result


def score_health(feature_row, timeofday, references, config):
    """Score one feature record using source metadata to select day/night mode.

    This API has no split argument. Use score_bundle for test freeze enforcement.
    """
    _validate_references(references, config)
    return _score_row(feature_row, timeofday, references, config)


def explain_health(feature_row, timeofday, references, config):
    """Return review diagnostics without changing the health record or policy.

    Exposure uses the maximum of its three signals; do not add them together.
    Like score_health, this frame API has no split. Bundle callers enforce freeze.
    """
    _validate_references(references, config)
    record = _score_row(feature_row, timeofday, references, config)
    values = _feature_values(feature_row)
    adaptive_group = TIME_MODES.get(timeofday, "fixed")
    return {
        "record_type": "heuristic_health_explanation",
        "explanation_version": "1.0.0",
        "health_record": record,
        "feature_values": values,
        "fixed": _reference_details(values, references["groups"]["fixed"], config),
        "adaptive": _reference_details(values, references["groups"][adaptive_group], config),
    }


def score_bundle(feature_rows, metadata, references, config, split=None):
    """Join by ID, verify exact input coverage, and protect test from draft configs."""
    _validate_references(references, config)
    features = _index(feature_rows, "features")
    images = _metadata_index(metadata)
    _require(set(features) == set(images), "Features must cover exactly the supplied manifest IDs")
    for row in features.values():
        _feature_values(row)
    _require(split in (None, "train", "val", "test"), "Invalid scoring split")
    selected = [sid for sid in sorted(images) if split is None or images[sid]["split"] == split]
    _require(bool(selected), f"No samples for scoring split {split}")
    _require(config["frozen"] or not any(images[sid]["split"] == "test" for sid in selected),
             "Test scoring requires a frozen config after validation review")
    reference_sequences = {row["sequence_id"] for row in references["reference_rows"]}
    _require(not any(row["sequence_id"] in reference_sequences and row["split"] != "train"
                     for row in images.values()), "Reference sequence leaked outside lab train")
    for row in references["reference_rows"]:
        sid = row["sample_id"]
        if sid in images:
            _require(images[sid]["split"] == "train" and images[sid].get("corruption") == "original"
                     and images[sid].get("parent_image_id") == sid,
                     f"Reference metadata changed: {sid}")
            _require(images[sid]["timeofday"] == row["timeofday"]
                     and images[sid]["sequence_id"] == row["sequence_id"]
                     and images[sid].get("severity") == 0
                     and _feature_values(features[sid]) == row["features"],
                     f"Reference features/timeofday/sequence changed: {sid}")
    if config["frozen"]:
        val_ids = set(config["validation"]["sample_ids"])
        _require(not any(sid in val_ids and images[sid]["split"] != "val" for sid in images),
                 "Validation IDs have been reassigned to another split")
        val_sequences = set(config["validation"]["sequence_ids"])
        _require(not any(row["sequence_id"] in val_sequences and row["split"] != "val"
                         for row in images.values()), "Validation sequence leaked into another split")
    return [_score_row(features[sid], images[sid]["timeofday"], references, config) for sid in selected]


def freeze_references(references, validation_features, metadata, config, note):
    """Freeze after manual val review, retaining config and validation input hashes.

    Pass a val-only manifest and matching feature records. Calling this function
    records a review decision; it does not optimize or infer action thresholds.
    """
    _require(not config["frozen"], "References are already frozen")
    _require(isinstance(note, str) and bool(note.strip()), "A validation review note is required")
    images = _metadata_index(metadata)
    _require(all(row["split"] == "val" for row in images.values()), "Freeze input must be val-only")
    features = list(validation_features)
    scores = score_bundle(features, list(images.values()), references, config, split="val")
    result = copy.deepcopy(references)
    snapshot = copy.deepcopy(config)
    snapshot["frozen"] = True
    snapshot["reference_sha256"] = result["reference_sha256"]
    snapshot["validation"] = {
        "split": "val", "sample_ids": sorted(images), "note": note.strip(),
        "sequence_ids": sorted({row["sequence_id"] for row in images.values()}),
        "features_sha256": _hash(sorted(features, key=lambda row: row["sample_id"])),
        "metadata_sha256": _hash([{"sample_id": sid, "split": images[sid]["split"],
                                   "timeofday": images[sid]["timeofday"],
                                   "sequence_id": images[sid]["sequence_id"]} for sid in sorted(images)]),
        "health_sha256": _hash(scores),
    }
    result["config"] = snapshot
    result["config_sha256"] = _hash(snapshot)
    _validate_references(result, snapshot)
    return result


def find_score_increases(health_rows, metadata, tolerance=1e-9):
    """Report synthetic scores above their originals without using metadata to score."""
    tolerance = _number(tolerance, "increase tolerance")
    health = _index(health_rows, "health")
    images = _metadata_index(metadata)
    findings = []
    for sid in sorted(health):
        _require(sid in images, f"Unknown health ID: {sid}")
        image = images[sid]
        if image.get("corruption") == "original":
            continue
        parent_id = image.get("parent_image_id")
        _require(parent_id in health, f"Missing parent health for increase review: {sid}")
        for field in ("health_fixed", "health_adaptive"):
            increase = health[sid][field] - health[parent_id][field]
            if increase > tolerance:
                findings.append({"sample_id": sid, "parent_image_id": parent_id,
                                 "score_field": field, "increase": increase})
    return findings


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)


def _read_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line, parse_constant=_reject_constant))
            except ValueError as error:
                raise ValueError(f"{path}:{number}: {error}") from error
    return rows


def _write_new(path, value, jsonl=False):
    """Validate serialization before exclusively creating a new output snapshot."""
    content = ("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in value)
               if jsonl else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _select_reference_ids(value):
    """Accept ID lists or the enriched day/night handoff from person 1."""
    if isinstance(value, dict):
        _require({"day", "night"} <= set(value), "Reference object requires day and night lists")
        _require(all(isinstance(value[key], list) and bool(value[key]) for key in ("day", "night")),
                 "Reference groups must be nonempty lists")
        ids = value["day"] + value["night"]
    else:
        ids = value
    _require(isinstance(ids, list) and bool(ids), "Reference IDs must be a nonempty list")
    _require(all(isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9_-]+", sid) for sid in ids),
             "Invalid reference ID")
    _require(len(ids) == len(set(ids)), "Duplicate reference IDs")
    if isinstance(value, dict) and "fixed" in value:
        fixed = value["fixed"]
        _require(isinstance(fixed, list) and all(isinstance(sid, str) for sid in fixed),
                 "Fixed reference IDs must be a list of strings")
        _require(len(fixed) == len(set(fixed)) and set(fixed) == set(ids),
                 "Fixed reference IDs must equal the unique day/night union")
    return ids


def _validate_reference_source(value, metadata, repo_root=None):
    """Verify the source manifest hash and original rows for enriched handoffs."""
    if not isinstance(value, dict) or "manifest_sha256" not in value:
        return {}
    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    relative = value.get("manifest_path")
    _require(isinstance(relative, str) and bool(relative), "Reference handoff requires manifest_path")
    _require(not Path(relative).is_absolute(), "Reference manifest_path must be repo-relative")
    path = (root / relative).resolve()
    _require(path.is_relative_to(root), "Reference manifest_path escapes repository")
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(actual_hash == value["manifest_sha256"], "Reference source manifest hash mismatch")
    source = _metadata_index(_read_jsonl(path))
    originals = {sid: row for sid, row in metadata.items() if row.get("corruption") == "original"}
    _require(source == originals, "Reference source originals differ from the scoring manifest")
    return {"source_manifest_path": relative, "source_manifest_sha256": actual_hash,
            "source_visual_review": value.get("visual_review", "unspecified")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    calibration = commands.add_parser("calibrate", help="Build references from selected original train IDs")
    calibration.add_argument("--manifest", required=True)
    calibration.add_argument("--features", required=True)
    calibration.add_argument("--reference-ids", required=True)
    calibration.add_argument("--config", required=True)
    calibration.add_argument("--output", required=True)
    freeze = commands.add_parser("freeze", help="Freeze a config snapshot after manual val review")
    freeze.add_argument("--manifest", required=True)
    freeze.add_argument("--features", required=True)
    freeze.add_argument("--references", required=True)
    freeze.add_argument("--validation-note", required=True)
    freeze.add_argument("--output", required=True)
    scoring = commands.add_parser("score", help="Write health records for an exact selected split")
    scoring.add_argument("--manifest", required=True)
    scoring.add_argument("--features", required=True)
    scoring.add_argument("--references", required=True)
    scoring.add_argument("--split", choices=("train", "val", "test", "all"), required=True)
    scoring.add_argument("--output", required=True)
    explanation = commands.add_parser("explain", help="Print one frame's reference values and penalties")
    explanation.add_argument("--manifest", required=True)
    explanation.add_argument("--features", required=True)
    explanation.add_argument("--references", required=True)
    explanation.add_argument("--sample-id", required=True)
    args = parser.parse_args(argv)
    try:
        images = _read_jsonl(args.manifest)
        features = _read_jsonl(args.features)
        if args.command == "calibrate":
            indexed = _index(features, "features")
            metadata = _metadata_index(images)
            _require(set(indexed) == set(metadata), "Features must cover exactly the supplied manifest IDs")
            for row in features:
                _feature_values(row)
            reference_file = _read_json(args.reference_ids)
            ids = _select_reference_ids(reference_file)
            provenance = _validate_reference_source(reference_file, metadata)
            provenance["reference_ids_sha256"] = hashlib.sha256(Path(args.reference_ids).read_bytes()).hexdigest()
            _require(set(ids) <= set(indexed), "Reference feature coverage is incomplete")
            if isinstance(reference_file, dict):
                for mode in ("day", "night"):
                    _require(all(TIME_MODES.get(metadata[sid]["timeofday"]) == mode
                                 for sid in reference_file[mode]), f"Reference IDs mislabeled as {mode}")
            config = prepare_config(_read_json(args.config))
            output = calibrate([indexed[sid] for sid in ids], images, config)
            output["provenance"] = provenance
            _write_new(args.output, output)
            summary = {"reference_count": len(ids), "reference_sha256": output["reference_sha256"],
                       "policy_id": output["config"]["policy_id"], "frozen": False}
        elif args.command == "freeze":
            references = _read_json(args.references)
            metadata = _metadata_index(images)
            indexed = _index(features, "features")
            _require(set(indexed) == set(metadata), "Features must cover exactly the supplied manifest IDs")
            for row in features:
                _feature_values(row)
            ids = [sid for sid in sorted(metadata) if metadata[sid]["split"] == "val"]
            output = freeze_references(references, [indexed[sid] for sid in ids],
                                       [metadata[sid] for sid in ids], references["config"], args.validation_note)
            _write_new(args.output, output)
            summary = {"validation_count": len(ids), "policy_id": output["config"]["policy_id"], "frozen": True}
        elif args.command == "explain":
            references = _read_json(args.references)
            metadata = _metadata_index(images)
            indexed = _index(features, "features")
            _require(set(indexed) == set(metadata), "Features must cover exactly the supplied manifest IDs")
            for row in features:
                _feature_values(row)
            sid = args.sample_id
            _require(sid in indexed, f"Unknown explanation sample_id: {sid}")
            # Validate the requested frame's split, reference linkage, and freeze state.
            score_bundle(features, images, references, references["config"], split=metadata[sid]["split"])
            summary = explain_health(indexed[sid], metadata[sid]["timeofday"],
                                     references, references["config"])
        else:
            references = _read_json(args.references)
            output = score_bundle(features, images, references, references["config"],
                                  None if args.split == "all" else args.split)
            summary = {"score_count": len(output), "policy_id": references["config"]["policy_id"],
                       "frozen": references["config"]["frozen"]}
            if args.split == "all":
                summary["score_increase_count"] = len(find_score_increases(output, images))
            _write_new(args.output, output, jsonl=True)
        print(json.dumps(summary, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Health baseline error: {error}\n")


if __name__ == "__main__":
    main()
