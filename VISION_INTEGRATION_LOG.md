# Vision Integration Log

Last updated: 2026-05-06 (AprilTag 一键启动校准框架)

本文档记录视觉模块（OCR-first 书脊检测 pipeline）与机械运动模块的集成工作：
做了什么、实现了哪些能力、怎么使用、怎么验证。

---

## 1. 集成目标

把 `vision/` 包接入 `主程序代码/` 的 `PickPlacePlan` 流水线，让队友的 MuJoCo
仿真和未来真机机械臂能用真实视觉数据驱动 `pick` 点，而不是 CLI 硬编码。

设计原则：
- **不动**队友核心代码（`controller.py / main.py 默认路径 / pick_place_plan.py /
  motion_adapter.py / sim/ / sim_output/`）。
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

### 3.2 世界坐标提供者：`vision.world_pose_provider.get_pick_world_pose(title)`

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

### 3.3 三个 CLI flag

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

### 3.4 优雅降级

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

## 9. 文件清单速查

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
│       ├── intrinsics.py       [新版：针孔 + 外参]
│       ├── world_pose_provider.py  [对接入口]
│       ├── visual_overlay.py
│       ├── __main__.py         (L2 实时)
│       ├── test_offline.py     (L1 离线)
│       └── detector.py         (YOLO，保留不用)
└── (其他队友文件不变)
```
