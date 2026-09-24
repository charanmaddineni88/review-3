from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def build_dataset_yaml(data_dir: str | Path, output_path: str | Path | None = None) -> dict:
    data_dir = Path(data_dir)
    train_dir = data_dir / "train"
    val_dir = data_dir / "val"
    test_dir = data_dir / "test"

    names: dict[int, str] = {}
    for label_file in list(train_dir.rglob("*.txt")) + list(val_dir.rglob("*.txt")) + list(test_dir.rglob("*.txt")):
        for line in label_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                class_id = int(parts[0])
            except ValueError:
                continue
            if class_id not in names:
                names[class_id] = f"class_{class_id}"

    dataset = {
        "path": str(data_dir),
        "train": "train",
        "val": "val",
        "test": "test",
        "names": names,
    }

    output = Path(output_path) if output_path else data_dir / "dataset.yaml"
    output.write_text("\n".join([
        f"path: {dataset['path']}",
        f"train: {dataset['train']}",
        f"val: {dataset['val']}",
        f"test: {dataset['test']}",
        "names:",
        *[f"  {idx}: '{name}'" for idx, name in sorted(names.items())],
    ]) + "\n", encoding="utf-8")
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a YOLO model with dynamically discovered classes.")
    parser.add_argument("--data", type=str, required=True, help="Dataset root directory containing train/val/test")
    parser.add_argument("--weights", type=str, default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="0" if __import__("utils.device", fromlist=["detect_device"]).detect_device() == "cuda" else "cpu")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data)
    dataset_cfg = build_dataset_yaml(data_dir, data_dir / "dataset.yaml")
    model = YOLO(args.weights)
    model.train(
        data=str(data_dir / "dataset.yaml"),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        resume=args.resume,
        project="runs/train",
        exist_ok=True,
    )
    print(f"Training completed using dataset config: {dataset_cfg}")


if __name__ == "__main__":
    main()
