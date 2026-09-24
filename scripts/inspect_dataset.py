from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
LABEL_EXTENSIONS = {".txt", ".xml", ".json"}


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def is_label(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LABEL_EXTENSIONS


def detect_annotation_format(paths: list[Path]) -> list[str]:
    suffixes = {path.suffix.lower() for path in paths}
    formats: list[str] = []
    if ".txt" in suffixes:
        formats.append("YOLO")
    if ".xml" in suffixes:
        formats.append("VOC/XML")
    if ".json" in suffixes:
        formats.append("COCO/JSON")
    return formats or ["UNKNOWN"]


def parse_yolo_label(path: Path) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"line {line_number}: expected 5 YOLO fields")
        try:
            class_id = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"line {line_number}: non-numeric YOLO value") from exc
        boxes.append(
            {
                "class_id": class_id,
                "x_center": values[0],
                "y_center": values[1],
                "width": values[2],
                "height": values[3],
            }
        )
    return boxes


def box_is_valid(box: dict[str, Any]) -> bool:
    x, y, width, height = (
        float(box[key]) for key in ("x_center", "y_center", "width", "height")
    )
    return (
        width > 0
        and height > 0
        and 0 <= x <= 1
        and 0 <= y <= 1
        and width <= 1
        and height <= 1
        and 0 <= x - width / 2
        and x + width / 2 <= 1
        and 0 <= y - height / 2
        and y + height / 2 <= 1
    )


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_label_candidates(image: Path) -> list[Path]:
    return [image.with_suffix(extension) for extension in LABEL_EXTENSIONS]


def inspect_dataset(dataset_root: Path) -> dict[str, Any]:
    dataset_root = dataset_root.expanduser().resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_root}")
    if not dataset_root.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_root}")

    images = sorted(path for path in dataset_root.rglob("*") if is_image(path))
    labels = sorted(path for path in dataset_root.rglob("*") if is_label(path))
    image_keys = {
        path.with_suffix("").relative_to(dataset_root) for path in images
    }
    label_keys = {
        path.with_suffix("").relative_to(dataset_root) for path in labels
    }

    # any() receives one iterable. Passing several boolean arguments raises
    # TypeError, which previously prevented inspection from starting.
    missing_labels = [
        str(image.relative_to(dataset_root))
        for image in images
        if not any(candidate.exists() for candidate in relative_label_candidates(image))
    ]
    orphan_labels = [
        str(label.relative_to(dataset_root))
        for label in labels
        if label.with_suffix("").relative_to(dataset_root) not in image_keys
    ]

    corrupted_files: list[dict[str, str]] = []
    invalid_boxes: list[dict[str, Any]] = []
    class_counts: Counter[int] = Counter()
    image_dimensions: Counter[str] = Counter()
    subset_counts: Counter[str] = Counter()

    for image in images:
        relative = image.relative_to(dataset_root)
        subset = relative.parts[0] if len(relative.parts) > 1 else "root"
        subset_counts[subset] += 1
        try:
            with Image.open(image) as picture:
                image_dimensions[f"{picture.width}x{picture.height}"] += 1
                picture.verify()
        except Exception as exc:
            corrupted_files.append(
                {"file": str(relative), "error": str(exc)}
            )

    for label in labels:
        if label.suffix.lower() != ".txt":
            continue
        try:
            for box in parse_yolo_label(label):
                class_counts[box["class_id"]] += 1
                if not box_is_valid(box):
                    invalid_boxes.append(
                        {"file": str(label.relative_to(dataset_root)), "box": box}
                    )
        except Exception as exc:
            corrupted_files.append(
                {"file": str(label.relative_to(dataset_root)), "error": str(exc)}
            )

    duplicates: list[dict[str, str]] = []
    seen_hashes: dict[str, str] = {}
    for path in images + labels:
        try:
            digest = compute_sha256(path)
        except OSError as exc:
            corrupted_files.append(
                {"file": str(path.relative_to(dataset_root)), "error": str(exc)}
            )
            continue
        relative = str(path.relative_to(dataset_root))
        if digest in seen_hashes:
            duplicates.append({"file": relative, "same_as": seen_hashes[digest]})
        else:
            seen_hashes[digest] = relative

    issues: list[dict[str, Any]] = []
    for name, values in (
        ("missing_labels", missing_labels),
        ("orphan_labels", orphan_labels),
        ("corrupted_files", corrupted_files),
        ("invalid_boxes", invalid_boxes),
        ("duplicates", duplicates),
    ):
        if values:
            issues.append({"issue": name, "count": len(values)})

    return {
        "dataset": str(dataset_root),
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "images": len(images),
            "annotations": len(labels),
            "classes_detected": len(class_counts),
            "label_files": len(labels),
            "txt_files": sum(path.suffix.lower() == ".txt" for path in labels),
            "xml_files": sum(path.suffix.lower() == ".xml" for path in labels),
            "json_files": sum(path.suffix.lower() == ".json" for path in labels),
        },
        "annotation_formats": detect_annotation_format(labels),
        "classes": {str(key): value for key, value in sorted(class_counts.items())},
        "image_dimensions": dict(image_dimensions),
        "subset_distribution": dict(subset_counts),
        "missing_labels": missing_labels,
        "orphan_labels": orphan_labels,
        "corrupted_files": corrupted_files,
        "invalid_boxes": invalid_boxes,
        "duplicates": duplicates,
        "quality": {
            "status": "PASS" if not issues else "WARN",
            "issues": issues,
            "issue_count": sum(item["count"] for item in issues),
        },
    }


def write_html_report(report: dict[str, Any], output_path: Path) -> None:
    rows = "".join(
        f"<tr><td>{html.escape(str(key))}</td>"
        f"<td>{html.escape(str(value))}</td></tr>"
        for key, value in report["counts"].items()
    )
    document = (
        "<html><head><meta charset='utf-8'><title>FIREGUARD Dataset Report</title>"
        "<style>body{font-family:Arial;margin:2rem}table{border-collapse:collapse}"
        "td,th{border:1px solid #bbb;padding:.5rem}</style></head><body>"
        f"<h1>FIREGUARD Dataset Report</h1>"
        f"<p>Status: {html.escape(report['quality']['status'])}</p>"
        f"<table><tr><th>Metric</th><th>Value</th></tr>{rows}</table>"
        f"<h2>Details</h2><pre>{html.escape(json.dumps(report, indent=2))}</pre>"
        "</body></html>"
    )
    output_path.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a real FIREGUARD dataset without copying it."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset root; defaults to FIREGUARD_DATASET_PATH or configured path",
    )
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()

    if args.dataset is None:
        from fireguard.config import settings

        args.dataset = Path(settings.dataset_path)

    args.output.mkdir(parents=True, exist_ok=True)
    try:
        report = inspect_dataset(args.dataset)
    except (FileNotFoundError, NotADirectoryError) as exc:
        parser.error(str(exc))

    (args.output / "dataset_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_html_report(report, args.output / "dataset_report.html")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
