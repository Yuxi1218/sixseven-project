import os
import sys
from pathlib import Path
import glob

RAW = Path("/home/sixseven/sixseven-project/yolo_workspace_raw")
OUT = Path("/home/sixseven/sixseven-project")

def parse_data_yaml(path):
    txt = path.read_text(encoding="utf-8", errors="ignore")
    names = None
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("names"):
            # inline list
            import re
            m = re.search(r"\[(.*)\]", line)
            if m:
                names = [x.strip().strip("'\"") for x in m.group(1).split(",")]
            else:
                # multi-line
                pass
    # multi-line names
    if names is None:
        names = []
        in_names = False
        for line in txt.splitlines():
            s = line.strip()
            if s.startswith("names:"):
                in_names = True
                continue
            if in_names:
                if s.startswith("-"):
                    names.append(s[1:].strip())
                else:
                    in_names = False
    return names

def class_hist(labels_dir):
    if not labels_dir.exists():
        return {}
    hist = {}
    for f in labels_dir.glob("*.txt"):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if not parts:
                continue
            cls = int(parts[0])
            hist[cls] = hist.get(cls, 0) + 1
    return dict(sorted(hist.items()))

def images_labels(split_dir):
    img = (split_dir / "images")
    lb = (split_dir / "labels")
    n_img = len(list(img.glob("*.*"))) if img.exists() else 0
    n_lbl = len(list(lb.glob("*.txt"))) if lb.exists() else 0
    return n_img, n_lbl

report = []
report.append("# Raw Dataset Inventory (re-extracted from originals)")
report.append("")

report.append("Source zips: `/home/sixseven/yolo_workspace/temp/*.zip` extracted to `yolo_workspace_raw/`")
report.append("")

for ds in sorted(RAW.iterdir()):
    if not ds.is_dir():
        continue
    report.append(f"## Dataset: {ds.name}")
    dy = ds / "data.yaml"
    if dy.exists():
        names = parse_data_yaml(dy)
        report.append(f"- data.yaml names ({len(names)}): {names}")
    report.append("")
    # README
    for rd in ["README.dataset.txt", "README.roboflow.txt"]:
        p = ds / rd
        if p.exists():
            first_lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[:6]
            report.append(f"### {rd}")
            for ln in first_lines:
                if ln.strip():
                    report.append(f"  {ln.strip()}")
            report.append("")
    for split in ["train", "valid", "test"]:
        sd = ds / split
        if not sd.exists():
            continue
        n_img, n_lbl = images_labels(sd)
        hist = class_hist(sd / "labels")
        hist_str = ", ".join(f"cls{cls}={cnt}" for cls, cnt in hist.items())
        report.append(f"### {split}: images={n_img}, labels={n_lbl}")
        report.append(f"  label hist: {hist_str}")
        report.append("")
    report.append("---")
    report.append("")

report.append("## Folders in repo that (previously) used these datasets")
report.append("""From `yolo_workspace/merge_labels.py` (build script):
- `defects`   <- Aircraft Defects v2 (`Crack,Dent,Missing Fastener`)
- `damage_v2` <- Aircraft Damage Detection v5 (`crack,dent`)
- `v4`        <- ac_damage_detector v4 (`damages`)
- `v5`        <- ac_damage_detector v5 (`11 classes`)
- `detection` <- Aircraft Damage v2 (`hole,leak,scratch,stucturaldamage`)
""")

OUT.joinpath("DATASET_INVENTORY.md").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))
print("\n\nWrote DATASET_INVENTORY.md")
