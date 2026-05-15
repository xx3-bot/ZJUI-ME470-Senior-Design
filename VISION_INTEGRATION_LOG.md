# Vision Integration Log

Last updated: 2026-05-15 (bin ranging + startup-scan reuse + shelf false-positive correction)

本文档记录视觉模块（OCR-first 书脊检测 pipeline）与机械运动模块的集成工作：
做了什么、实现了哪些能力、怎么使用、怎么验证。

---

## 0. Current 2026-05-15 status

Current vision integration progress:

- Bin detection now combines OCR/title matching, book/entity boxes, denoised
  edge preprocessing, and visible bin-grid geometry.
- `startup_scan.py` stores the authoritative per-run pick candidates in
  `bin.pick_candidates`.
- `detected_books_loop.py` now reuses those startup-scan pick candidates during
  `--auto-demo`. This avoids the earlier bug where Auto scanned the bin once,
  moved the arm, then opened the camera again and got a different pick X.
- Recent real tests show this matters: a clean startup snapshot gave picks near
  `X ~= 309.5 mm` and all three target sequences prechecked successfully, while
  a later farther setup produced `X ~= 320.9 mm` and MuJoCo IK rejected all
  three picks. The next software guard should explicitly report "book/bin too
  far" before attempting motion if pick X exceeds the reliable workspace.
- Processed overlays are generated for bin/entity detection, bin grid/depth, and
  shelf slice candidates.
- Shared static and runtime visual test data now lives in `测试文件/`.

Critical shelf correction from 2026-05-15:

- The current shelf scanner can still produce false positives. In
  `测试文件/runtime_artifacts/startup_scan/20260515_180953`, the frame is visibly
  a bin/books view, but the shelf detector accepted the yellow bin bottom as two
  shelf sections and produced fake shelf slots.
- Treat current shelf slot output as provisional. It is useful for software
  integration, but it is not robust enough for autonomous placement unless the
  frame is visually confirmed to contain the actual shelf.
- The next shelf-vision implementation should add a CAD/pose-validation gate:
  use the known 81x162 / 81x81 book-stand geometry, edges/perforation pattern,
  and reprojection or `solvePnP` checks to reject bin views and partial false
  positives.
- Do not depend on full shelf CAD visibility after books are placed. The
  intended design is: valid startup pose initializes shelf coordinates; later
  frames update local occupancy/book-spine support around the known shelf pose.

## 0.1 Previous 2026-05-14 status

2026-05-14 correction from real hardware/camera setup:
- The real book-spine grasp plane is now treated as `arm X ~= 320 mm`, so
  `config.BIN_PICK_DEPTH_MM = 320.0`.
- With the camera mounted at `CAMERA_POSITION_IN_ARM_MM = (90.2, 0, 102.0)`,
  the fixed camera-to-book projection depth is now
  `config.BIN_FIXED_DEPTH_MM = 229.8`.
- Startup-scan reports must use `bin.pick_candidates[*].pick` as the
  user-facing/control pick pose. The older `bin.books[*].pick_point` payload is
  compatibility data only and should not be treated as the execution pose.
- The 2026-05-14 center-bin overlay visually confirmed why this matters: after
  the X update, the visible bin-grid estimate moved from the old misleading
  `arm X ~= 256 mm` to about `arm X ~= 317 mm`, consistent with the measured
  real grasp depth.
- Shelf-view yaw note: startup scan uses physical command `servo000 P2167` for
  the shelf view. This is the correct direction on the real arm and is nominally
  `+90 deg` from center by the current PWM scale, although the user observed it
  may overshoot by roughly 1-2 degrees. Keep the command unchanged for now and
  model the small difference as a future yaw correction.
- Since the camera is rigidly mounted to the rotating base/pan assembly, the
  shelf-view extrinsic can be derived from the initial camera offset
  `(90.2, 0, 102.0)` and the shelf-scan yaw. The shelf pipeline can therefore
  start converting `shelf_scanner` slice pixels/depth into arm-frame placement
  poses.
- Shelf slice scoring correction: shelf candidates now include an occupancy
  estimate from visible-yellow coverage. A slice already occluded by a placed
  book is marked `occupied` and receives a large penalty, so wall support alone
  no longer makes an occupied edge slice rank highly. Adjacent occupied slices
  can give a smaller `left_book/right_book` support bonus to nearby free slices.

The current practical vision-to-motion path is no longer the old
`world_pose_provider` depth-from-book-height experiment. The stable path for
bin picking is:

```text
vision.lateral_pose_provider
-> get_all_book_pick_poses_from_camera()
-> main.py --auto-demo / --run-detected-books-loop
-> target_sequence.generate_target_sequence()
```

Current assumptions:
- The bin depth is fixed for this stage.
- Arm-frame pick X is hardcoded as `config.BIN_PICK_DEPTH_MM = 320.0`.
- Arm-frame pick Z is hardcoded as `config.BIN_PICK_GRASP_HEIGHT_MM = 115.0`.
- Vision only estimates arm-frame lateral `Y`.
- The camera-to-book fixed depth used by the pinhole projection is
  `config.BIN_FIXED_DEPTH_MM = 229.8`, derived from
  `BIN_PICK_DEPTH_MM - CAMERA_POSITION_IN_ARM_MM[0]`.
- Lens distortion is corrected through `cv2.undistortPoints()` using
  `vision/intrinsics_calibration.json`.

Current known-book list:
- `羊皮卷`
- `习近平新时代中国特色社会主义思想概论`
- `聊斋志异`
- `毛泽东思想概况`
- `人性的弱点`
- `鬼谷子`
- `墨菲定律`

Confirmed integration output:
- `main.py --auto-demo` and `main.py --run-detected-books-loop` can detect
  multiple visible known books, order them by `config.KNOWN_BOOK_TITLES`, and
  generate a merged hardware command file.
- OCR text that does not match the known-book list is reported as an
  operator/manual-intervention item. It is not converted into a pick pose.
- Camera selection can be overridden by `--camera-index`; on this Mac, the
  iPhone Continuity camera may appear as OpenCV index `1`, while `auto` remains
  the safer fallback.
- A confirmed 2026-05-11 run exists under
  `sim_output/detected_books_loop/20260511_215629/`, with three detected books:
  `羊皮卷`, `鬼谷子`, and `墨菲定律`.

Important compatibility note:
- `vision.bin_scanner.detect_books_in_frame()` is still used by startup-scan and
  grip-place-test reports, but its `pick_point` shape is the older report-style
  payload.
- For hardware pick poses, prefer `vision.lateral_pose_provider`, which returns
  direct `(arm_X, arm_Y, arm_Z)` tuples.

---

## 1. 集成目标

把 `vision/` 包接入 `主程序代码/` 的运动流水线，让真机机械臂能用真实视觉
数据驱动 `pick` 点，而不是长期依赖 CLI 硬编码。当前阶段优先支持 bin 内
书脊横向测距：X/Z 暂时由机械侧固定，Y 由视觉估计。

设计原则：
- **不破坏**队友核心代码和已验证硬件路径；新增入口必须保持和
  `target_sequence.py` 的正式命令生成链路兼容。
- **加分支**：用 `config.USE_VISION_FOR_PICK` / `VISION_SHADOW_MODE` /
  `FAKE_VISION_PICK_POSE` 三个开关控制。默认全关，行为与队友原 demo 100% 一致。
- **可独立验证**：在没有标定、没有相机的情况下，用 Mock Injection 也能证明
  数据通路打通了。

---

## 2. 做了哪些操作

### 2.1 新增文件

| 文件 | 作用 |
|---|---|
| `主程序代码/vision/` | 整个视觉子包，从 `/Users/zehao/Downloads/ece445/主程序代码/vision/` 完整搬过来 |
| `主程序代码/vision/world_pose_provider.py` | **新文件**。视觉对接入口：返回机械臂世界系下书脊抓取点 (x, y, z) mm |
| `VISION_INTEGRATION_LOG.md` | 本文档 |

`vision/` 子包内部模块：
- `__init__.py` — 包入口；改为 lazy（不再 eager 导入 numpy/cv2/paddleocr）
- `camera.py` — iPhone/C920e 相机封装
- `ocr.py` — PaddleOCR 包装 + 模糊匹配 KNOWN_BOOK_TITLES
- `spine_detector.py` — OCR-first 书脊检测器（聚类 + bbox + 倾角）
- `bin_scanner.py` — 旧版 `scan_bin_books / locate_book` 入口
- `intrinsics.py` — **重写**：新增针孔反投影 + 已知物体尺寸深度估计 + 外参
- `visual_overlay.py` — 可视化叠加
- `__main__.py` — L2 实时相机预览 (`python -m vision`)
- `test_offline.py` — L1 静态图离线测试 (`python -m vision.test_offline`)
- `detector.py` — YOLO（保留但已不调用）
- `world_pose_provider.py` — **新增**对接入口

### 2.2 修改文件

| 文件 | 改动 |
|---|---|
| `主程序代码/config.py` | 新增视觉相关常量段（开关、相机内参/外参、书目先验、OCR 模型）+ `get_pick_place_plan()` 加 USE_VISION_FOR_PICK / SHADOW_MODE 分支 |
| `主程序代码/perception_adapter.py` | `scan_bin_books` / `locate_book` 加 `USE_MOCK_VISION` 分支转发 |
| `主程序代码/main.py` | 加 3 个 CLI flag：`--use-vision-for-pick` / `--vision-shadow-mode` / `--fake-vision-pose X Y Z` |
| `主程序代码/vision/__init__.py` | 改为 lazy（去掉 eager 导入），让 `from vision.world_pose_provider import ...` 不必拉 numpy |

### 2.3 不动的文件

`controller.py`、`motion_adapter.py`、`pick_place_plan.py`、`models.py`、
`coordinate_transformer.py`、`world_model.py`、`decision/*`、`sim/*`、
`sim_output/*`。

---

## 3. 实现了什么能力

### 3.1 三个分发开关（在 `config.py` 顶部）

```python
USE_MOCK_VISION: bool = True           # perception_adapter 走 mock 还是真实视觉
USE_VISION_FOR_PICK: bool = False      # PickPlacePlan.pick 是否用视觉输出替换 FIXED
VISION_SHADOW_MODE: bool = False       # 影子模式：跑视觉 + 写日志，但不替换 pick
FAKE_VISION_PICK_POSE: Tuple | None    # 不为 None 时直接返回这个值（注入测试用）
```

### 3.2 Current lateral pose provider: `vision.lateral_pose_provider`

For the current real demo, use `lateral_pose_provider` rather than the older
depth-from-book-height world provider.

Single target:

```python
from vision.lateral_pose_provider import get_book_pick_pose

pose = get_book_pick_pose(frame, "羊皮卷")
# -> (250.0, arm_y_from_vision, 115.0)
```

All visible known books:

```python
from vision.lateral_pose_provider import get_all_book_pick_poses_from_camera

candidates = get_all_book_pick_poses_from_camera()
```

Each candidate has:

```python
{
    "title": str,
    "pick": (250.0, arm_y_mm, 115.0),
    "confidence": float,
    "bbox": (x1, y1, x2, y2),
}
```

The main integrated user is:

```bash
python3 主程序代码/main.py --auto-demo --place 0 250 140 --camera-index auto --dry-run
```

### 3.3 Legacy world coordinate provider: `vision.world_pose_provider.get_pick_world_pose(title)`

返回值：`(world_x, world_y, world_z)` mm，**世界原点 = 机械臂底座 yaw 关节**。

调用链：
```
config.get_pick_place_plan()
   ↓ (lazy import)
vision.world_pose_provider.get_pick_world_pose(title)
   ↓
    ├─ FAKE_VISION_PICK_POSE 不为 None → 直接返回该值
    │
    └─ 否则 →
       1. RGBCamera.read_frame()
       2. SpineDetector.detect(frame) → SpineHit[]
       3. 取 title 命中的最高 confidence hit
       4. polygon 长边像素 + 已知 spine_height (mm) → estimate_depth_from_known_height_mm
       5. (cx_px, cy_px, depth) → pinhole_pixel_to_camera_mm (相机系 mm)
       6. camera_to_world_mm → 世界系 mm，按 CAMERA_ORIENTATION_MODE 旋转 + CAMERA_TRANSLATION_MM 平移
       7. 返回 (world_x, world_y, world_z)
```

This path remains in the tree as an experiment / compatibility path. It should
not be treated as the current primary demo path unless it is explicitly
revalidated against the physical setup.

### 3.4 三个 CLI flag

```bash
# Test A: 影子模式（不影响 demo 行为，仅写日志）
python 主程序代码/main.py --viewer --vision-shadow-mode

# Test B: Mock Injection（验证 PickPlacePlan 通路，不需要相机/OCR）
python 主程序代码/main.py --viewer \
  --use-vision-for-pick \
  --fake-vision-pose 150.0 100.0 80.0

# Test C: 真实视觉（需要相机 + PaddleOCR）
python 主程序代码/main.py --viewer --use-vision-for-pick
```

### 3.5 优雅降级

`get_pick_world_pose` 任意一步失败 → 返回 `None`：
- 相机打不开
- 没识别到目标书
- KNOWN_BOOK_DIMENSIONS_MM 没配该 title

`get_pick_place_plan()` 收到 `None` 时**自动回退到 `FIXED_PICK_POSE`**，
打印 `[VISION->PLAN] ... → falling back to FIXED_PICK_POSE`。
队友 demo 不会因视觉异常而崩。

---

## 4. 怎么使用

### 4.1 默认（队友原 demo，零变化）

```bash
python 主程序代码/main.py --viewer
```

`pick = (218.0, 120.23, 100.0)`，与原 `FIXED_PICK_POSE` 一致。

### 4.2 影子模式（验证视觉数据通路）

```bash
python 主程序代码/main.py --viewer --vision-shadow-mode
```

终端会多一行 `[VISION->PLAN] vision_pick=(...) title='...'` 或
`vision_pick=None ...`，但 `pick` 还是 `FIXED_PICK_POSE`。MuJoCo 行为不变。

### 4.3 Mock Injection（验证 PickPlacePlan 通路，**无需相机**）

```bash
python 主程序代码/main.py --viewer \
  --use-vision-for-pick \
  --fake-vision-pose 150.0 100.0 80.0
```

MuJoCo 应该飞到 `(150, 100, 80)` 而不是默认的 `(218, 120.23, 100)`。
**这是验证"视觉模块和机械运动程序对接成功"的核心测试**。

### 4.4 真实视觉（需要 C920e/iPhone + PaddleOCR）

前置：
1. `pip install numpy opencv-python paddleocr paddlepaddle`
2. 把 C920e/iPhone 接到 Mac，确认 `cv2.VideoCapture(config.RGB_CAMERA_INDEX)` 能开
3. 把目标书举到相机前（默认 `习近平新时代中国特色社会主义思想概论`）

```bash
python 主程序代码/main.py --viewer --use-vision-for-pick
```

终端会打印：
```
[VISION] '习近平新时代中国特色社会主义思想概论' pixel_h=380 depth=480mm cam=(...) world=(...)
[VISION->PLAN] vision_pick=(...) title='...'
```

MuJoCo 飞到那个 world 坐标。

---

## 5. 验证：怎么证明对接成功

按 `Phase 4` 设计的 4 个测试逐个跑：

### Test A — Shadow Mode（数据通路）
```bash
python 主程序代码/main.py --viewer --vision-shadow-mode
```
**通过判据**：`[VISION->PLAN] vision_pick=...` 出现在终端日志里。

### Test B — Mock Injection（PickPlacePlan 通路）⭐ 最关键
```bash
# 1. 先用默认值
python 主程序代码/main.py --viewer
# 看 MuJoCo pick 标记位置

# 2. 用 Mock Injection 改变值
python 主程序代码/main.py --viewer --use-vision-for-pick --fake-vision-pose 150 100 80
# MuJoCo pick 标记应该飞到不同位置
```
**通过判据**：MuJoCo 中 pick 点的位置随 `--fake-vision-pose` 数值变化。

### Test C — 方向一致性（真视觉，无标定也能定性观测）
书放镜头前，依次：
- 向**右**移 10 cm → MuJoCo `pick.x` 单调变化（方向正确即通过）
- **远离**镜头 → polygon 变小 → `pick.y` 单调增加
- **抬高** → `pick.z` 单调增加

任一轴方向反 → 检查 `CAMERA_ORIENTATION_MODE` / `CAMERA_TRANSLATION_MM`。

### Test D — 边界与失败模式
- 没书：`vision_pick=None ... → falling back`，demo 用 `FIXED_PICK_POSE` 继续
- 拿错书：fuzzy match 失败 → 同上
- 故意书放太远：`pick.y` 算到 `> 1000 mm` → MuJoCo IK 拒绝（这是好事）

---

## 6. 配置参数清单（`config.py`）

视觉相关全部新增项：

```python
# ── 分发开关 ─────────────────────────────────────────────
USE_MOCK_VISION: bool = True
USE_VISION_FOR_PICK: bool = False
VISION_SHADOW_MODE: bool = False
FAKE_VISION_PICK_POSE: Tuple[float, float, float] | None = None

# ── 相机硬件 ─────────────────────────────────────────────
RGB_CAMERA_INDEX: int = 1
RGB_FRAME_WIDTH: int = 1280
RGB_FRAME_HEIGHT: int = 720
RGB_INTRINSICS_FX_PX: float = 810.0    # 标定后替换
RGB_INTRINSICS_FY_PX: float = 810.0
RGB_INTRINSICS_CX_PX: float = 640.0
RGB_INTRINSICS_CY_PX: float = 360.0

# ── 相机外参（相机相对机械臂底座位姿）─────────────────
CAMERA_TRANSLATION_MM: Tuple = (0.0, -400.0, 200.0)
CAMERA_ORIENTATION_MODE: str = "ARM_FACING"
# 可选: "FORWARD_HORIZONTAL" | "TOP_DOWN" | "ARM_FACING"

# ── 已知物体先验 ───────────────────────────────────────
KNOWN_BOOK_TITLES: List[str] = ["习近平新时代中国特色社会主义思想概论"]
KNOWN_BOOK_DIMENSIONS_MM: Dict = {
    "习近平新时代中国特色社会主义思想概论": {
        "spine_height": 210.0,    # 量过的实际值
        "cover_width":  150.0,
        "thickness":     25.0,
    },
}
OCR_TO_REAL_HEIGHT_RATIO: float = 0.85   # OCR polygon 比真实书脊矮的修正系数

# ── OCR / YOLO ─────────────────────────────────────────
OCR_LANG: str = "ch"
OCR_MIN_SCORE: float = 0.4
OCR_FUZZY_MATCH_CUTOFF: float = 0.4
OCR_MAX_INPUT_SIDE: int = 1600
OCR_DET_MODEL_NAME: str = "PP-OCRv5_mobile_det"
OCR_REC_MODEL_NAME: str = "PP-OCRv5_mobile_rec"
```

---

## 7. 已完成的烟雾测试

```
✓ python -m py_compile config.py perception_adapter.py main.py vision/*.py     OK
✓ Default plan.pick = (218.0, 120.23, 100.0)                                   PASS
✓ Fake injection plan.pick = (150.0, 100.0, 80.0) (and pick_approach/lift 派生) PASS
✓ Shadow mode plan.pick = FIXED (vision called and logged but not used)        PASS
✓ python main.py --help 显示 3 个新 flag                                       PASS
```

### 7.1 Test B（Mock Injection）端到端验证 ✅ 已通过 2026-05-01

**目的**：证明视觉端任意 `(x, y, z)` 都能完整传递到 motion_adapter，确认对接成功。

**baseline 命令**：
```bash
python3 主程序代码/main.py --sim-mode --sim-log-path /tmp/test_b_baseline.log
```

**injection 命令**：
```bash
python3 主程序代码/main.py --sim-mode \
  --use-vision-for-pick --fake-vision-pose 150.0 100.0 80.0 \
  --sim-log-path /tmp/test_b_inject.log
```

**对比结果**（终端 + sim_output JSON 日志）：

| 项 | Baseline | Injection (150,100,80) |
|---|---|---|
| 视觉日志 | 无 | `[VISION] FAKE_VISION_PICK_POSE 注入 → (150.0, 100.0, 80.0)` |
|         |    | `[VISION->PLAN] vision_pick=(150.0, 100.0, 80.0) title='习近平...'` |
| controller 收到的 `pick` | `Pose(218.0, 120.23, 100.0)` | `Pose(150.0, 100.0, 80.0)` ✅ |
| `pick_approach`（自动派生 +100mm） | `Pose(218.0, 120.23, 200.0)` | `Pose(150.0, 100.0, 180.0)` ✅ |
| `pick_lift`（自动派生 +50mm） | `Pose(218.0, 120.23, 150.0)` | `Pose(150.0, 100.0, 130.0)` ✅ |
| sim_output JSON 第一条 `move_to.target_pose` | `[218.0, 120.23, 200.0]` | `[150.0, 100.0, 180.0]` ✅ |
| `place_transfer / approach / final / retreat` | `(-40, *, *)` | 同 baseline，未受影响 ✅ |

**Shadow mode 同步验证**：
```bash
python3 主程序代码/main.py --sim-mode --vision-shadow-mode \
  --fake-vision-pose 999 888 777
```
日志显示 `[VISION->PLAN] SHADOW_MODE: keeping FIXED_PICK_POSE`，`pick` 仍为
`(218, 120.23, 100)` —— 影子模式不替换实际 pose 的设计正确生效。

**结论**：**视觉模块与机械运动模块的数据通路已端到端打通**。剩余工作是数值精度
（相机标定）和真实视觉输入（C920e/iPhone + OCR），不是接口问题。

### 7.3 离线图像 → world pose 测试 ✅ 5/6 通过 2026-05-04

**目的**：用 iPhone 拍的现成照片验证视觉 → 世界坐标 pipeline 在真实图像（非
mock 注入）上能跑通；不需要相机硬件、不需要标定。

**新增工具**：
- `vision/world_pose_provider.py` 新增 `get_pick_world_pose_from_frame(frame, title)`
  ——从已加载的 numpy 帧出发，复用所有几何/外参逻辑，跳过相机抓帧
- `vision/test_world_pose.py`（新文件）——CLI 工具，遍历 `vision/test_images/` 下
  所有图，输出每张的 world pose

**命令**：
```bash
python -m vision.test_world_pose
```

**结果**：6 张 iPhone 测试图，5 张成功返回 world pose：

| 图 | OCR 命中 | depth (mm) | world (x, y, z) mm |
|---|---|---|---|
| IMG_8010 | OK | 74 | (-112.5, -473.8, +81.7) |
| IMG_8011 | OK | 56 | (-177.8, -455.6, +83.1) |
| IMG_8012 | OK | 74 | (-73.5, -474.3, +71.9) |
| IMG_8013 | OK | 39 | (-58.2, -438.7, +67.9) |
| IMG_8014 | OK | 75 | (-146.3, -474.6, +72.5) |
| 微信图片 | NO | — | OCR 未命中 |

**验证项**：
- ✅ Pipeline 端到端跑通（OCR + 深度估计 + 反投影 + 外参 + 输出）
- ✅ 输出格式正确，每张图都得到 `(float, float, float)` 元组
- ✅ 不同图给出不同 pose（说明视觉真的在响应输入差异，不是死值）
- ✅ x 坐标随书在画面横向位置变化（-58 到 -178 mm）
- ✅ y 坐标都是负（约 -440 ~ -475），与 `CAMERA_TRANSLATION_MM = (0, -400, 200)`
  的设置一致（相机站在 y=-400 朝 y=0 方向看）

**已知偏差（预期内）**：
- depth 算出来 39-75 mm（书离镜头几厘米），物理上不合理
- 原因：iPhone 主摄实际焦距 ≈ 1100-1200 px @ 1280×720，但 config 里是 C920e 估算
  值 fx=810。Z = H × fy / h，分子偏小 → 估算深度偏小约 30%
- C920e 到位 + 棋盘格标定后这个偏差自动消失

**结论**：算法可以从图像产生 (x, y, z) 世界坐标。**结构、方向、变化趋势全部
正确**，只待硬件标定填入真实内/外参即可获得物理真值。

---

### 7.4 C920e 内参标定 + depth 物理验证 ✅ 2026-05-05

**目的**：把估算的相机参数换成实测值，让 world pose 的 depth 数值有物理意义。

**新增工具**：
- `vision/calibrate_intrinsics.py`：两个子命令 `capture`（实时拍棋盘格、锁焦、
  自动 overlay）+ `solve`（跑 cv2.calibrateCamera）
- `vision/intrinsics_calibration.json`：标定结果存档

**棋盘格**：calib.io 9×6 内角点、25mm 方格、贴在 20×30cm×3mm 亚克力板上

**采集**：25 张图，全部锁焦（FOCUS=30），覆盖近/中/远 + 4 角 + 倾斜姿态

**标定结果**：
```
[CAL] images used     : 25 / 25
[CAL] image size      : 1280 x 720
[CAL] reprojection RMS: 0.299 px   (理想 < 0.5)
[CAL] fx, fy          : 962.98, 964.73    (fx-fy 差距 0.18% → 锁焦成功)
[CAL] cx, cy          : 609.01, 358.15    (画面中心 640, 360)
[CAL] distortion      : [0.039, -0.132, 0.001, 0.000, 0.005]
```

**写回 [config.py](主程序代码/config.py)**：
```python
RGB_INTRINSICS_FX_PX = 962.98   # 之前估算 810
RGB_INTRINSICS_FY_PX = 964.73
RGB_INTRINSICS_CX_PX = 609.01
RGB_INTRINSICS_CY_PX = 358.15
```

### 7.5 修复深度估计 bug + 实测 OCR_TO_REAL_HEIGHT_RATIO ✅ 2026-05-05

**Bug**：[vision/intrinsics.py:estimate_depth_from_known_height_mm](主程序代码/vision/intrinsics.py)
公式写反了，`real / ratio` 应该是 `real * ratio`。已修。

**实测书本几何**（用尺量《习近平...》）：
- 书脊全高 = **227 mm**（之前估算 210）
- 标题文字段 "习近平...概论" 高 = **110 mm**
- ratio = 110 / 227 = **0.485**（之前估算 0.85）

**写回 [config.py](主程序代码/config.py)**：
```python
KNOWN_BOOK_DIMENSIONS_MM["习近平..."]["spine_height"] = 227.0
OCR_TO_REAL_HEIGHT_RATIO = 0.485
```

### 7.6 物理 depth 验证 ✅ 2026-05-05

把书放在已知距离用 C920e 拍照，跑 `python -m vision.test_world_pose`：

| 实际距离 | pixel_h | 算出 depth | 误差 |
|---|---|---|---|
| 250 mm | 440 | 241.4 mm | **-3.60%** |
| 300 mm | 357 | 297.5 mm | **-0.83%** |
| 600 mm | 181 | 586.8 mm | **-2.20%** |

距离 25→60cm（2.4 倍变化），pixel_h 反比变化（440→181），三次测试全部 < ±4%。
**深度估计 pipeline 全部跑通，误差远低于 demo 容忍的 ±15%。**

### 7.8 重构：per-book OCR-visible height + 标题过滤聚类 ✅ 2026-05-05

**起因**：换书测试发现，全局 `OCR_TO_REAL_HEIGHT_RATIO` 不能跨书共用——
- 习近平：标题 110mm / 书脊 227mm = ratio 0.485
- 羊皮卷：标题 28mm  / 书脊 210mm = ratio 0.133

差 3.6 倍。强行共用会导致 depth 失真。

**改动**：
1. **[config.py](主程序代码/config.py)** `KNOWN_BOOK_DIMENSIONS_MM` 加每本书自己的
   `ocr_visible_height_mm` 字段。`OCR_TO_REAL_HEIGHT_RATIO` 降级为 fallback。
2. **[vision/world_pose_provider.py](主程序代码/vision/world_pose_provider.py)**
   把 `_resolve_book_spine_height_mm` 重构为 `_resolve_book_ocr_visible_height_mm`，
   优先用每本书的 `ocr_visible_height_mm`，spine × ratio 兜底。
3. **[vision/spine_detector.py](主程序代码/vision/spine_detector.py)** `_cluster_to_hit`
   加"标题字符过滤"：fuzzy 命中后只保留 cluster 中含 title 字符的 polygon 算
   bbox/tilt。**避免出版社/作者名等同 x 中心的文字把 cluster 拉长**。

**触发场景**：羊皮卷书脊上"羊皮卷"和"出版社" x 中心相同 → cluster 把它们聚一起 →
bbox 高度从 ~50px 变成 507px → 反推 depth 大错 5 倍。

### 7.9 羊皮卷物理 depth 验证 ✅ 2026-05-05

| 标称距离 | pixel_h | 算出 depth | 真距估计 |
|---|---|---|---|
| 30 cm | 87 | 366 mm | 实际约 37 cm（物理量错）|
| 60 cm | 58 | 549 mm | 实际约 55 cm（物理量错）|

**结论**：
- pipeline 端到端工作，depth 公式正确
- 短标题（3 字）depth 精度 ~±10%，远弱于长标题（习近平 ±3%）。
  原因：33mm 参考长度对像素 noise 敏感，1px 抖动 ≈ 3% depth 误差
- Demo 可用，但精度敏感场景建议优先用长标题书

### 7.11 AprilTag 一键启动校准框架 ✅ 2026-05-06

**背景**：bin / shelf 在 demo 时随便摆放，不能预存它们的世界坐标。  
**方案**：每个物体贴 AprilTag。运行时检测 → 通过 cv2.solvePnP 算 tag 在相机系
6D 位姿 → 通过相机相对机械臂底座的固定外参 → 反推 bin / shelf 在世界系下的位姿。  
**好处**：装机后零运行时干预，符合"一键启动" demo 要求。

**物理设计**：
- BIN：2 个 30mm AprilTag (ID 10/11)，贴前面板下横条左右两端
- SHELF：3 个 30mm AprilTag (ID 0/1/2)，贴底部三脚正面
- 相机相对机械臂底座的 `(Δx, Δy, Δz)` + 上仰角，装机一次性测量

**新增文件**：
| 文件 | 作用 |
|---|---|
| [vision/runtime_state.py](主程序代码/vision/runtime_state.py) | 启动校准结果在内存中的存储（`ObjectPose` dataclass + getter/setter）|
| [vision/apriltag_calibrator.py](主程序代码/vision/apriltag_calibrator.py) | `cv2.aruco` + `cv2.solvePnP` 封装：`detect_with_pose(frame, expected_tags)` |
| [vision/object_localization.py](主程序代码/vision/object_localization.py) | `run_startup_calibration(frame_bin, frame_shelf)` 完整启动流程 |

**[config.py](主程序代码/config.py) 新增段**：
```python
BIN_MODEL    = {tags: {10: ..., 11: ...}, pickable_plane_*}
SHELF_MODEL  = {tags: {0:1:2}, zones: A/B/C/D, ...}
CAMERA_MOUNT_OFFSET_MM, CAMERA_MOUNT_PITCH_DEG
JOINT0_BIN_SCAN_DEG, JOINT0_SHELF_SCAN_DEG
GRIPPER_PICK_HEIGHT_MM = 100.0  # 队友硬编码
GRIPPER_OPEN_WIDTH_MM, GRIPPER_SAFETY_MARGIN_MM
APRILTAG_DICT_NAME = "DICT_4X4_50"
```

所有几何参数都标 `# TODO: 实测后填入`，等机械同学装好后用尺测量替换。

**还在做（本次未完成）**：
- `vision/slot_scorer.py` (placement 用，shelf zone 切片 + 评分)
- 重构 `vision/world_pose_provider.py` 走 ray ∩ plane（用 runtime_state 的位姿）
- `main.py` 加 `startup_calibrate` 入口
- AprilTag 打印 PDF 模板生成
- Smoke test

### 7.10 多书支持 ✅ 2026-05-05

`KNOWN_BOOK_TITLES` 现含 2 本：
1. `"习近平新时代中国特色社会主义思想概论"`：精度高（±3%）
2. `"羊皮卷"`：精度中（±10%），demo 可用

加新书的步骤：
1. 拿尺量 `spine_height` + `thickness`（必填）+ `cover_width`（建议）
2. 量"OCR 检测到的标题文字段"物理高度（含 ~3-5mm 边距）→ `ocr_visible_height_mm`
3. 写进 `KNOWN_BOOK_DIMENSIONS_MM`
4. 加 title 到 `KNOWN_BOOK_TITLES`

---

### 7.7 已知工程约束：最小工作距离 ≈ 30cm 2026-05-05

实测中发现：当书离相机 < 30cm 时，**书脊顶/底端可能超出 C920e 1280×720 视场**，
OCR 检测到的 polygon 不完整 → pixel_h 偏小 → depth 系统性偏大。

物理推算（C920e 实测 fy=964.73）：

| 距离 | 垂直 FOV (mm) | 能否容纳 227mm 书脊 |
|---|---|---|
| 20 cm | 149 | 装不下 |
| 25 cm | 187 | 边缘裁切 |
| 30 cm | 224 | 临界 |
| 40 cm | 299 | 有余量 |
| 60 cm | 448 | 大量余量 |

**Demo 建议**：把书架/书放在 **30-50cm 工作距离**，给 OCR 留垂直余量；
低于 30cm 时 OCR 会漏顶/底部字符。

**结论**：视觉端给出的 (x, y, z) 中 **depth 已经达到亚厘米精度**。world 系
x/y/z 还有 cm 级偏差，因为 `CAMERA_TRANSLATION_MM / CAMERA_ORIENTATION_MODE`
仍是占位值——这两个常量需要在物理装机时量一次（相机相对底端云台的实际偏移
+ 上仰角）才能消除。

---

### 7.2 未完成（依赖硬件）

- L2 实时相机 fps（需要插 C920e 或 iPhone Continuity Camera）
- Test A 影子模式 + 真相机
- Test C 方向一致性（需要固定相机 + 可移动书）
- Test D 边界场景（需要相机）
- `--viewer` 模式眼见 MuJoCo 演示（需要 `pip install mujoco`）
- 真机抓取演示（需要队友 ROS2 链路 + 棋盘格标定）

---

## 8. 已知限制与下一步

| 待办 | 优先级 | 说明 |
|---|---|---|
| OpenCV 棋盘格标定 C920e 内参 | HIGH | 现在 fx≈810 是估算值，标定后误差降到 ~1% |
| 量相机相对机械臂底座的物理位置 | HIGH | 现在 `CAMERA_TRANSLATION_MM` 是占位 |
| 量《习近平...》spine_height 真实值 | MEDIUM | 现在 210 mm 是估算值 |
| 拍摄实测 + 调 `OCR_TO_REAL_HEIGHT_RATIO` | MEDIUM | 现在 0.85 是经验值 |
| `scan_bin_books / locate_book` 走完整状态机 | LOW | 当前 demo 走 `PICK_PLACE_ONLY_MODE` 不需要 |
| `scan_shelves` 真实实现 | LOW | 单本 demo 不需要 |

---

## 9. Shelf Section / Slice Scanner v1

新增 `主程序代码/vision/shelf_scanner.py`，作为 shelf 放书感知的第一版
独立模块；当前只输出候选，不接管真机执行。

当前规则：

- 先用长竖直边缘检测框出左右两个 shelf section。
- 每个 section 按物理宽度 `81 mm` 切成 `5` 个 slice。
- 每个 slice 宽约 `16 mm`。
- slice 局部中心坐标为约 `-32.4, -16.2, 0, +16.2, +32.4 mm`。
- 最左 slice 得分 `30`，hint=`lean_left`，support=`left_wall`。
- 最右 slice 得分 `30`，hint=`lean_right`，support=`right_wall`。
- 中间三个 slice 得分 `10`，hint=`center`。
- 当前 `status="unknown"`，后续再接 occupied/free 识别。
- 用已知 section 宽度 `81 mm` 和相机内参 `fx` 估计相机到 shelf 正面的
  深度：`depth_mm = fx * 81 / bbox_width_px`。这是 camera-relative depth，
  不包含相机到机械臂底座的外参转换。

在 `测试图像/test shelf.png` 上验证：

- left section bbox: `[162, 123, 461, 1102]`
- right section bbox: `[648, 123, 460, 1102]`
- average camera depth: `169.4 mm`
- debug overlay: `/private/tmp/test_shelf_5slice_scored.png`

后续用 `测试图像/shelf2.png` 测试时发现真实云台视角会看到两侧挡板，
中央分隔线可能只表现为一条强边。`shelf_scanner.py` 因此加入了
strong-edge fallback：当固定四边界比例检测失败时，用最强结构边推断
left/divider/right 三条边，并把 divider 同时作为左 section 右边界与右
section 左边界。`shelf2.png` 当前结果：

- left section bbox: `[386, 144, 465, 1152]`
- right section bbox: `[851, 144, 465, 1152]`
- average camera depth: `167.7 mm`
- debug overlay: `/private/tmp/shelf2_5slice_scored.png`

`shelf3.png` 是更远、更居中的视角。放宽 strong-edge fallback 阈值后可检测：

- left section bbox: `[632, 129, 378, 1041]`
- right section bbox: `[1010, 129, 351, 1041]`
- average camera depth: `214.3 mm`
- debug overlay: `/private/tmp/shelf3_depth_5slice_scored.png`
- 注意：该图顶部 bbox 包含一段灰色背景上沿，横向 slice 仍可用；若后续要
  用竖向 shelf 高度定位，需要进一步收紧 top/bottom 到实际可放书平面。

OCR / edge preprocessing update:

- Added `主程序代码/vision/image_preprocess.py`.
- Edge-based detectors now have shared helpers for denoise, grayscale cleanup,
  CLAHE, Canny, and morphology close.
- `shelf_scanner.py` keeps the original grayscale edge path first, then falls
  back to cleaned grayscale if border detection fails. This avoids hurting
  already-clean synthetic or high-contrast views while still giving noisy camera
  frames a cleanup path.
- `ocr.py` keeps original-frame PaddleOCR first, then tries a conservative OCR
  enhanced frame only if the original frame returns no text polygons.
- Regression after this change:
  - `test shelf.png`: complete, average depth `169.4 mm`
  - `shelf2.png`: complete, average depth `167.7 mm`
  - `shelf3.png`: complete, average depth `214.3 mm`

注意：当前能稳定给 section/slice 像素位置和局部横向 mm 候选，但真实
`depth_mm` 仍需要外参、AprilTag、已知尺寸尺度或实测相机到 shelf 平面距离。

Book dimension / tilt metadata update:

- `config.py` now defines two shared book size profiles:
  - `compact_200x140x8`: height `200 mm`, width `140 mm`, thickness `8 mm`
  - `tall_209x140x9`: height `209 mm`, width `140 mm`, thickness `9 mm`
- `KNOWN_BOOK_DIMENSIONS_MM` now references those profiles while preserving
  each title's `ocr_visible_height_mm` field for legacy depth experiments.
- `vision.lateral_pose_provider` now includes these fields in each candidate:
  - `tilt_deg`
  - `tilt_direction`
  - `suggested_place_tilt_deg`
  - `book_dimensions_mm`
- `vision.bin_scanner.detect_books_in_frame(frame)` also returns tilt and
  dimension metadata.
- `detected_books_loop.py` records tilt metadata in snapshots and shows a
  human-readable tilt sentence in the Auto Demo report.
- Verification with `测试图像/book1.jpg`: OCR recognized `聊斋志异`, confidence
  `0.999`, tilt `+0.8 deg`, direction `near_vertical`, size profile
  `compact_200x140x8`.

OCR + entity binding update:

- Added `主程序代码/vision/bin_slot_scanner.py`.
- Current v1 output is a `BookInstance`-style dict that binds:
  - OCR title / confidence / OCR bbox / OCR tilt
  - edge-detected physical entity bbox / raw entity bbox / entity tilt
  - book dimension metadata
  - `association_score`
- Entity detection uses the shared denoise / grayscale cleanup / Canny path,
  then trims each coarse contour with robust edge-pixel percentiles. This keeps
  the main book body while reducing shadow/background overreach.
- This is not wired into hardware control yet. It is a candidate source for the
  next bin-slot scanner, where slot geometry should provide the stable pick Y.
- Verification with `测试图像/book1.jpg`:
  - raw physical entity bbox `[2263, 416, 2777, 5299]`
  - refined physical entity bbox `[2280, 468, 2535, 5189]`
  - OCR title `聊斋志异` bbox `[2288, 874, 2484, 1513]`
  - association score `1.0`
  - OCR tilt `+0.8 deg`; entity tilt about `-2.8 deg`
  - debug overlay `/private/tmp/book1_refined_percentile_edges_overlay.png`

Startup scan integration update:

- The existing `主程序代码/startup_scan.py` is now the two-view world
  initialization path; no separate workflow file is used.
- It scans only physical `left-90 deg` and `0 deg`, captures `left.png` and `center.png`,
  then sends measured home/straight.
- Hardware direction correction: current physical left-90 scan uses servo000
  `P2167`; `P0833` was observed to turn the base the wrong way on the real arm.
- `left.png` is processed through `vision.shelf_scanner` for shelf section/slice
  candidates.
- `center.png` is processed through `vision.bin_slot_scanner`,
  `vision.bin_scanner`, and `vision.lateral_pose_provider` for OCR/entity-linked
  books and pick candidates.
- The snapshot now includes `shelf`, `bin`, and `task_queue` fields. It is still
  a perception/planning snapshot and does not send pick/place hardware commands.

Shelf scoring update:

- `vision.shelf_scanner` now adds an image-axis score to every shelf slice.
- The image axis is `frame_width / 2`; no camera extrinsics are used.
- Current score components:
  - base score
  - wall support score
  - image-axis distance bonus, max `+10`
  - reserved adjacent-support score, currently `0`
- This makes wall-supported slices nearer the camera/image center rank higher
  than equally supported outer slices.
- Verification with `测试图像/shelf2.png`:
  - image axis `x=843 px`
  - `left slice 4`: total `39.54`, wall `20`, axis `9.54`, distance `38.5 px`
  - `right slice 0`: total `39.35`, wall `20`, axis `9.35`, distance `54.5 px`
  - outer wall slices rank lower (`35.13` and `34.94`)
  - debug overlay `/private/tmp/shelf2_axis_scored_overlay.png`

Gripper clearance / release feasibility note:

- Placement scoring must eventually include the physical gripper footprint, not
  only shelf slice score.
- A slice may look good visually but still be unsafe if the gripper cannot
  enter, open, release, and retreat without pushing neighboring books.
- Future decision fields should include:
  - required free side for the chosen lean direction
  - available clearance in adjacent slices / millimeters
  - release feasibility
  - expected fall/lean direction
  - reason for any rejection
- Conservative first rule: wall or adjacent-book support is not enough by
  itself; the opposite side must also leave enough free tool space for the claw
  and release motion.

Bin grid local-scale depth update:

- `vision.bin_slot_scanner` now includes `estimate_bin_grid_geometry(frame)`.
- Purpose: estimate bin depth from visible local grid spans rather than relying
  on full bin width, which is often blocked by books.
- Known span hypotheses currently include `5 mm` divider thickness, `10 mm`
  book/spine slot width, `12.5 mm`, `15 mm`, `20 mm`, `22.5 mm`, `25 mm`, and
  `32.5 mm`.
- The function scales the calibrated focal length to the actual frame width,
  detects yellow/orange bin-grid spans in the bottom ROI, matches plausible
  pixel widths to known physical spans, then uses `CAMERA_POSITION_IN_ARM_MM`
  to convert camera-frame depth to arm-frame X depth.
- Latest 2026-05-14 verification with the real startup-scan `center.png`:
  - with `BIN_PICK_DEPTH_MM=320.0` and camera X offset `90.2 mm`
  - selected `53 px` as `12.5 mm` -> camera depth `227.1 mm`,
    arm X depth `317.3 mm`, confidence `0.997`
  - this agrees with the user's measured real book-spine grasp plane of about
    `320 mm`.
  - selected arm X is the highest-confidence candidate rather than the
    unweighted median, because tiny divider spans are noisier.

---

## 10. 文件清单速查

```
Integrated Algorithm/
├── VISION_INTEGRATION_LOG.md   ← 本文档
├── 主程序代码/
│   ├── main.py                 [+3 CLI flags]
│   ├── config.py               [+vision 配置段; get_pick_place_plan() 加分支]
│   ├── perception_adapter.py   [+USE_MOCK_VISION 分支]
│   └── vision/                 [整个新增]
│       ├── __init__.py         (lazy)
│       ├── camera.py
│       ├── ocr.py
│       ├── spine_detector.py
│       ├── bin_scanner.py
│       ├── bin_slot_scanner.py [OCR title + edge entity binding]
│       ├── shelf_scanner.py     [shelf section + 5-slice scoring]
│       ├── intrinsics.py       [新版：针孔 + 外参]
│       ├── world_pose_provider.py  [对接入口]
│       ├── visual_overlay.py
│       ├── __main__.py         (L2 实时)
│       ├── test_offline.py     (L1 离线)
│       └── detector.py         (YOLO，保留不用)
└── (其他队友文件不变)
```
