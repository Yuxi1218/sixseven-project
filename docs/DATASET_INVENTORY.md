# Raw Dataset Inventory (re-extracted from originals)

Source zips: `/home/sixseven/yolo_workspace/temp/*.zip` extracted to `yolo_workspace_raw/`

## Dataset: Aircraft Damage Detection.v5-extra-finetuning-current-best-.yolov11
- data.yaml names (2): ['crack', 'dent']

### README.dataset.txt
  # Aircraft Damage Detection > Extra Finetuning -current best-
  https://universe.roboflow.com/youssef-donia-fhktl/aircraft-damage-detection-1j9qk
  Provided by a Roboflow user
  License: CC BY 4.0

### README.roboflow.txt
  Aircraft Damage Detection - v5 Extra Finetuning -current best-
  ==============================
  This dataset was exported via roboflow.com on March 9, 2025 at 2:35 AM GMT

### train: images=2574, labels=2574
  label hist: cls0=3120, cls1=2667

### valid: images=452, labels=452
  label hist: cls0=538, cls1=484

### test: images=148, labels=148
  label hist: cls0=142, cls1=158

---

## Dataset: Aircraft Damage.v2-roboflow-instant-1--eval-.yolov11
- data.yaml names (4): ['hole', 'leak', 'scratch', 'stucturaldamage']

### README.dataset.txt
  # Aircraft Damage > Roboflow Instant 1 [Eval]
  https://universe.roboflow.com/damage-aled6/aircraft-damage-l59wk
  Provided by a Roboflow user
  License: CC BY 4.0

### README.roboflow.txt
  Aircraft Damage - v2 Roboflow Instant 1 [Eval]
  ==============================
  This dataset was exported via roboflow.com on May 2, 2026 at 5:25 AM GMT

### train: images=16, labels=16
  label hist: cls0=2, cls2=8, cls3=13

### valid: images=12, labels=12
  label hist: cls1=1, cls2=10, cls3=9

### test: images=12, labels=12
  label hist: cls0=2, cls1=1, cls2=5, cls3=7

---

## Dataset: Aircraft Defects.v2-showcase-demo-roboflow-model.yolov11
- data.yaml names (3): ['Crack', 'Dent', 'Missing Fastener']

### README.dataset.txt
  # Aircraft Defects > Showcase Demo - Roboflow Model
  https://universe.roboflow.com/aircraft-defects/aircraft-defects-8plvs
  Provided by a Roboflow user
  License: CC BY 4.0

### README.roboflow.txt
  Aircraft Defects - v2 Showcase Demo - Roboflow Model
  ==============================
  This dataset was exported via roboflow.com on October 15, 2024 at 12:11 PM GMT

### train: images=5428, labels=5428
  label hist: cls0=7501, cls1=5749, cls2=6787

### valid: images=263, labels=263
  label hist: cls0=227, cls1=119, cls2=279

### test: images=122, labels=122
  label hist: cls0=95, cls1=58, cls2=126

---

## Dataset: ac_damage_detector.v4i.yolov11
- data.yaml names (1): ['damages']

### README.dataset.txt
  # ac_damage_detector > 2025-02-08 12:24am
  https://universe.roboflow.com/experimentcv/ac_damage_detector
  Provided by a Roboflow user
  License: Public Domain

### README.roboflow.txt
  ac_damage_detector - v4 2025-02-08 12:24am
  ==============================
  This dataset was exported via roboflow.com on February 7, 2025 at 7:51 PM GMT

### train: images=160, labels=160
  label hist: cls0=402

### valid: images=46, labels=46
  label hist: cls0=158

### test: images=23, labels=23
  label hist: cls0=52

---

## Dataset: ac_damage_detector.v5i.yolov11
- data.yaml names (11): ['burnt', 'cockpit-glass', 'engine-damage', 'faced-with-bird', 'fuselage-damage', 'icing', 'landing-gear-damage', 'nose-damage', 'skin-cover', 'tail-unit-damage', 'wing-damage']

### README.dataset.txt
  # ac_damage_detector > 2025-02-10 5:50pm
  https://universe.roboflow.com/experimentcv/ac_damage_detector
  Provided by a Roboflow user
  License: Public Domain

### README.roboflow.txt
  ac_damage_detector - v5 2025-02-10 5:50pm
  ==============================
  This dataset was exported via roboflow.com on February 10, 2025 at 12:50 PM GMT

### train: images=145, labels=145
  label hist: cls0=2, cls1=17, cls2=101, cls3=1, cls4=129, cls5=1, cls6=3, cls7=85, cls8=82, cls9=18, cls10=175

### valid: images=43, labels=43
  label hist: cls1=3, cls2=31, cls3=2, cls4=52, cls5=2, cls7=43, cls8=43, cls10=19

### test: images=19, labels=19
  label hist: cls1=3, cls2=4, cls4=12, cls7=9, cls8=11, cls9=3, cls10=7

---

## Folders in repo that (previously) used these datasets
From `yolo_workspace/merge_labels.py` (build script):
- `defects`   <- Aircraft Defects v2 (`Crack,Dent,Missing Fastener`)
- `damage_v2` <- Aircraft Damage Detection v5 (`crack,dent`)
- `v4`        <- ac_damage_detector v4 (`damages`)
- `v5`        <- ac_damage_detector v5 (`11 classes`)
- `detection` <- Aircraft Damage v2 (`hole,leak,scratch,stucturaldamage`)
