# Local dataset usage

The FASDD dataset is intentionally not committed to GitHub because it is approximately 13.5 GB. The configured local Windows path is:

```text
C:\Users\dines\Downloads\FASDD_UAV
```

Run inspection from the repository root:

```powershell
python scripts\inspect_dataset.py --dataset "C:\Users\dines\Downloads\FASDD_UAV" --output reports
```

The command reads the dataset in place; it does not copy it into the repository. It creates `reports/dataset_report.json` and `reports/dataset_report.html`.

You can override the path at any time:

```powershell
$env:FIREGUARD_DATASET_PATH = "E:\datasets\FASDD_UAV"
python scripts\inspect_dataset.py --output reports
```

Do not commit the dataset, extracted archives, model weights, training runs, or generated processed data.
