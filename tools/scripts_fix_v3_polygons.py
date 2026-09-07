from pathlib import Path

V3 = Path("/home/sixseven/sixseven-project/yolo_workspace_v3")

def polygon_to_bbox(coords):
    """coords: flat list [x1,y1,x2,y2,...]. Returns (cx,cy,w,h)."""
    xs = coords[0::2]
    ys = coords[1::2]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    w = x_max - x_min
    h = y_max - y_min
    return cx, cy, w, h

def convert_line(line):
    parts = line.split()
    if len(parts) < 5:
        return None
    cls = parts[0]
    rest = parts[1:]
    try:
        nums = [float(x) for x in rest]
    except ValueError:
        return None
    if len(rest) == 4:
        # already bbox: cls cx cy w h
        return (cls, nums)
    # polygon case
    flag = None
    if len(rest) % 2 == 1 and len(rest) >= 5 and rest[0] in ("0", "1"):
        # format: cls <0/1 flag> x1 y1 x2 y2 ... -> drop flag
        flag = rest[0]
        nums = nums[1:]
    if len(nums) < 6 or len(nums) % 2 != 0:
        # not a valid polygon (need >=3 points = 6 numbers, even)
        return None
    cx, cy, w, h = polygon_to_bbox(nums)
    return (cls, [cx, cy, w, h])

stats = {"converted_files": 0, "dropped_lines": 0, "kept_bbox": 0, "converted_lines": 0, "unparsable_lines": 0}
for split in ["train", "valid", "test"]:
    lbl = V3 / split / "labels"
    for f in lbl.glob("*.txt"):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        new_lines = []
        changed = False
        for line in lines:
            if not line.strip():
                continue
            if len(line.split()) == 5:
                new_lines.append(line)
                stats["kept_bbox"] += 1
                continue
            conv = convert_line(line)
            if conv is None:
                stats["unparsable_lines"] += 1
                continue
            cls, nums = conv
            if len(nums) == 4:
                new_lines.append(f"{cls} {nums[0]:.6f} {nums[1]:.6f} {nums[2]:.6f} {nums[3]:.6f}")
                changed = True
                stats["converted_lines"] += 1
        if changed:
            stats["converted_files"] += 1
            if new_lines:
                f.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            else:
                # empty -> leave; will be reported
                stats["dropped_lines"] += 1

print(stats)
