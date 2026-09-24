from __future__ import annotations

import argparse
import json

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a YOLO model on a dataset and output actual metrics only.")
    parser.add_argument("--weights", type=str, required=True)
    parser.add_argument("--data", type=str, required=True)
    parser.add_argument("--split", type=str, default="val")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="0" if __import__("utils.device", fromlist=["detect_device"]).detect_device() == "cuda" else "cpu")
    args = parser.parse_args()

    model = YOLO(args.weights)
    metrics = model.val(data=args.data, split=args.split, imgsz=args.imgsz, device=args.device)
    payload = {
        "precision": float(metrics.results_dict.get("precision", 0.0)),
        "recall": float(metrics.results_dict.get("recall", 0.0)),
        "f1": float(metrics.results_dict.get("f1", 0.0)),
        "mAP50": float(metrics.results_dict.get("mAP50", 0.0)),
        "mAP50_95": float(metrics.results_dict.get("mAP50-95", 0.0)),
        "per_class": metrics.results_dict.get("per_class", {}),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
