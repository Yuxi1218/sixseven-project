from pathlib import Path
from collections import Counter

V3 = Path("/home/sixseven/sixseven-project/yolo_workspace_v3")

# Drop classes 3(Hole),4(Scratch),5(Leak)
REMOVE = {3, 4, 5}
# reindex: old class -> new (compress)
KEEP_WEIGHTS = [0, 1, 2, 6, 7, 8, 9]  # old indices kept in this order
REMAP = {old: new for new, old in enumerate(KEEP_WEIGHTS)}
NAMES = ["Crack", "Dent", "Missing_Fastener", "Skin_Cover", "Fuselage_damage", "Wing_damage", "Engine_damage"]

stats = {"removed_boxes": 0, "removed_files": 0, "kept_files": 0, "classes": Counter()}
for split in ["train", "valid", "test"]:
    img_dir = V3 / split / "images"
    lbl_dir = V3 / split / "labels"
    for lbl in list(lbl_dir.glob("*.txt")):
        new_lines = []
        for line in lbl.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if not parts:
                continue
            cls = int(parts[0])
            if cls in REMOVE:
                stats["removed_boxes"] += 1
                continue
            new_cls = REMAP[cls]
            new_lines.append(f"{new_cls} " + " ".join(parts[1:]))
        if not new_lines:
            # drop image + label
            img_candidates = list(img_dir.glob(lbl.stem + ".*"))
            if img_candidates:
                img_candidates[0].unlink()
            lbl.unlink()
            stats["removed_files"] += 1
        else:
            lbl.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            stats["kept_files"] += 1
            for nl in new_lines:
                stats["classes"][int(nl.split()[0])] += 1

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

print("removed_boxes:", stats["removed_boxes"])
print("removed_files(whole image):", stats["removed_files"])
print("kept_files:", stats["kept_files"])
print("class boxes (new ids):", dict(sorted(stats["classes"].items())))
print("names:", NAMES)

for split in ["train", "valid", "test"]:
    img = len(list((V3 / split / "images").glob("*.*")))
    lbl = len(list((V3 / split / "labels").glob("*.txt")))
    print(f"{split}: images={img}, labels={lbl}")
print("Wrote data.yaml (7 classes)")
