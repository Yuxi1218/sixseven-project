import os

BASE = r"C:\Users\Yuxi\Desktop\sixseven-project\yolo_workspace"

DATASET_MAPPINGS = {
    "defects": {0: 2, 1: 1, 2: 0},
    "damage_v2": {0: 1, 2: 2},
    "v4": {0: 2},
    "v5": {2: 2, 10: 2, 8: 2, 4: 2},
    "detection": {0: 2, 1: 1},
}


def map_label(content, mapping):
    lines = content.strip().split("\n")
    new_lines = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        old_cls = int(parts[0])
        new_cls = mapping.get(old_cls)
        if new_cls is not None:
            parts[0] = str(new_cls)
            new_lines.append(" ".join(parts))
    return "\n".join(new_lines) + "\n" if new_lines else None


# Get all existing
existing = set()
for sub in ["train", "valid"]:
    path = os.path.join(BASE, sub, "labels")
    existing.update(
        f.replace(".txt", "") for f in os.listdir(path) if f.endswith(".txt")
    )

print(f"Existing: {len(existing)}")

count = 0
for dataset, mapping in DATASET_MAPPINGS.items():
    for sp in ["train", "valid"]:
        src = os.path.join(BASE, "temp", "extracted", dataset, sp, "labels")
        dst = os.path.join(BASE, sp, "labels")

        if not os.path.exists(src):
            continue

        os.makedirs(dst, exist_ok=True)

        merged = 0
        for f in os.listdir(src):
            if not f.endswith(".txt"):
                continue

            base = f.replace(".txt", "")
            if base in existing:
                continue

            with open(os.path.join(src, f), "r") as fp:
                content = fp.read()

            new_content = map_label(content, mapping)
            if new_content:
                with open(os.path.join(dst, f), "w") as fp:
                    fp.write(new_content)
                merged += 1
                count += 1

        if merged:
            print(f"  {dataset}/{sp}: {merged} added")

print(f"\nTotal added: {count}")
