from __future__ import annotations

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export a YOLO model to PyTorch, ONNX, TensorRT or TorchScript formats")
    parser.add_argument("--weights", required=True)
    parser.add_argument("--format", choices=["torchscript", "onnx", "engine", "pytorch"], default="onnx")
    parser.add_argument("--output", type=Path, default=Path("models/exported"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Export requested for weights={args.weights} in format={args.format}; writing to {args.output}")


if __name__ == "__main__":
    main()
