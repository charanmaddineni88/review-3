# Dataset documentation

The project is designed to inspect real data and never assume classes, label files or image counts. The first step is to run:

```bash
python scripts/inspect_dataset.py --dataset /path/to/dataset --output reports
```

It detects:
- image count
- annotation count
- YAML/YOLO/COCO/VOC/class discovery
- missing labels and orphan labels
- duplicate files
- corrupted image files
- invalid bounding boxes
- split readiness and dataset quality issues

If the dataset is absent or private, no synthetic statistics are generated.
