import shutil
from pathlib import Path
from collections import Counter

RAW = Path("/home/sixseven/sixseven-project/yolo_workspace_raw")
V3 = Path("/home/sixseven/sixseven-project/yolo_workspace_v3")

# Canonical 10-class target
NAMES = [
    "Crack",          # 0
    "Dent",           # 1
    "Missing_Fastener",# 2
    "Hole",           # 3
    "Scratch",        # 4
    "Leak",           # 5
    "Skin_Cover",     # 6
    "Fuselage_damage",# 7
    "Wing_damage",    # 8
    "Engine_damage",  # 9
]
NAME2IDX = {n: i for i, n in enumerate(NAMES)}

# Source -> mapping dict {source_class_id: target_name}
# Wildcard 'DROP' marks classes we exclude.
SOURCES = {
    "Aircraft Defects.v2-showcase-demo-roboflow-model.yolov11": {
        0: "Crack", 1: "Dent", 2: "Missing_Fastener",
    },
    "Aircraft Damage Detection.v5-extra-finetuning-current-best-.yolov11": {
        0: "Crack", 1: "Dent",
    },
    "ac_damage_detector.v4i.yolov11": {
        0: "Fuselage_damage",  # generic 'damages' -> structural/fuselage (documented decision)
    },
    "ac_damage_detector.v5i.yolov11": {
        2: "Engine_damage",    # engine-damage
        4: "Fuselage_damage",  # fuselage-damage
        8: "Skin_Cover",       # skin-cover
        10: "Wing_damage",     # wing-damage
        # dropped: burnt(0), cockpit-glass(1), faced-with-bird(3),
        #          icing(5), landing-gear-damage(6), nose-damage(9), tail-unit-damage(7)
    },
    "Aircraft Damage.v2-roboflow-instant-1--eval-.yolov11": {
        0: "Hole", 1: "Leak", 2: "Scratch",
        3: "Fuselage_damage",  # 'stucturaldamage' -> structural (documented decision)
    },
}

def rebuild_split(ds_name, mapping):
    src_ds = RAW / ds_name
    report = {"files": 0, "classes": Counter(), "dropped_boxes": 0, "skipped_empty_files": 0, "dups": 0}
    for split in ["train", "valid", "test"]:
        src_img = src_ds / split / "images"
        src_lbl = src_ds / split / "labels"
        if not (src_img.exists() and src_lbl.exists()):
            continue
        dst_img = V3 / split / "images"
        dst_lbl = V3 / split / "labels"
        dst_img.mkdir(parents=True, exist_ok=True)
        dst_lbl.mkdir(parents=True, exist_ok=True)
        seen = set()
        for lbl in sorted(src_lbl.glob("*.txt")):
            stem = lbl.stem
            img_candidates = list(src_img.glob(stem + ".*"))
            if not img_candidates:
                report["dropped_boxes"] += 1  # label w/o image at source
                continue
            img = img_candidates[0]
            new_lines = []
            dropped_any = False
            for line in lbl.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.split()
                if not parts:
                    continue
                cls = int(parts[0])
                target = mapping.get(cls)
                if target is None:
                    dropped_any = True
                    report["dropped_boxes"] += 1
                    continue
                target_id = NAME2IDX[target]
                new_lines.append(f"{target_id} " + " ".join(parts[1:]))
            if not new_lines:
                report["skipped_empty_files"] += 1
                continue
            if stem in seen:
                report["dups"] += 1
                continue
            seen.add(stem)
            # copy image (dedupe extension)
            shutil.copy2(img, dst_img / img.name)
            dst_lbl.joinpath(lbl.name).write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            for tok in new_lines:
                report["classes"][tok.split()[0]] += 1
            report["files"] += 1
    return report

def main():
    if V3.exists():
        print("WARNING: yolo_workspace_v3 already exists — aborting to avoid overwrite.")
        raise SystemExit(1)
    V3.mkdir()
    (V3 / "train" / "images").mkdir(parents=True, exist_ok=True)
    (V3 / "train" / "labels").mkdir(parents=True, exist_ok=True)

    all_classes = Counter()
    for ds_name, mapping in SOURCES.items():
        rep = rebuild_split(ds_name, mapping)
        print(f"== {ds_name}")
        print(f"   files written: {rep['files']}, dropped_boxes(not-mapped/missing-img): {rep['dropped_boxes']}, skipped_empty: {rep['skipped_empty_files']}, dups: {rep['dups']}")
        print(f"   class hist (target ids): {dict(rep['classes'])}")
        for k, v in rep["classes"].items():
            all_classes[int(k)] += v

    # data.yaml with absolute paths
    root = str(V3)
    yaml = f"""train: {root}/train/images
val: {root}/valid/images
test: {root}/test/images
nc: {len(NAMES)}
names:
"""
    for n in NAMES:
        yaml += f"- {n}\n"
    (V3 / "data.yaml").write_text(yaml, encoding="utf-8")

    print("\nTotal target-class boxes:", dict(sorted(all_classes.items())))
    print("Classes with 0 boxes:", [NAMES[i] for i in range(len(NAMES)) if all_classes.get(i, 0) == 0])
    for split in ["train", "valid", "test"]:
        img = len(list((V3 / split / "images").glob("*.*")))
        lbl = len(list((V3 / split / "labels").glob("*.txt")))
        print(f"{split}: images={img}, labels={lbl}")
    print("\nWrote data.yaml and rebuilt yolo_workspace_v3")

if __name__ == "__main__":
    main()
