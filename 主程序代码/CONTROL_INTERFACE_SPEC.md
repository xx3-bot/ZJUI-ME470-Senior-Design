# 控制系统对接说明

这个文档是写给感知同学和运动同学看的，目的是让大家知道主控程序到底需要什么输入输出。

## 1. 坐标和单位约定

- 全部单位统一使用 `mm`
- 任务启动瞬间，把“摄像头中心”视为世界参考原点 `(0, 0, 0)`
- 夹爪初始坐标不是直接输入的，而是根据以下超参数推出来：
  - `OFFSET_X`
  - `OFFSET_Y`
  - `GRIP_ORIENTATION`
- 感知模块返回的是“相对于当前摄像头中心”的坐标
- 控制系统负责把相机坐标转换成世界坐标
- 运动模块接收到的一律是世界坐标下的夹爪位置

## 2. 运行时输入的 11 个超参数

输入顺序必须是：

1. `ARM_LENGTH`
2. `SCAN_ARC`
3. `OFFSET_X`
4. `OFFSET_Y`
5. `GRIP_ORIENTATION`
6. `TIP_GAP`
7. `TIP_DEPTH`
8. `SAMPLE_RATE_MS`
9. `BOOK_VERT_HEIGHT`
10. `SHELF_H_MIN`
11. `SHELF_H_MAX`

其中比较关键的是：

- `TIP_GAP`：两个爪尖之间的间距
- `TIP_DEPTH`：爪尖距离机械臂参考点的深度，用于决定书要卡进去多深
- `SAMPLE_RATE_MS`：扫描过程中每隔多少毫秒请求一次视觉数据

## 3. 运动模块接口

控制系统现在通过 [motion_adapter.py](D:\大四\大四下\ECE445\主程序代码\motion_adapter.py) 调用运动模块。

### 3.1 移动函数

函数形式：

```python
move_to(current_pose: Pose, target_pose: Pose) -> bool
```

含义：

- `current_pose`：当前夹爪世界坐标
- `target_pose`：目标夹爪世界坐标

要求：

- 运动模块内部自己完成路径规划、插补、控制
- 控制系统不会传速度、关节角、轨迹点等额外参数
- 只有真的移动完成后，才能返回 `True`
- 如果以后支持失败处理，可以返回 `False`

### 3.2 夹爪指令

函数形式：

```python
gripper_command(command: str) -> bool
```

当前只允许两个命令：

- `OPEN`
- `CLOSE`

要求：

- 只有动作完成后才能返回 `True`

## 4. 感知模块接口

控制系统现在通过 [perception_adapter.py](D:\大四\大四下\ECE445\主程序代码\perception_adapter.py) 调用感知模块。

### 4.1 扫描书框中的所有书

函数形式：

```python
scan_bin_books(camera_pose: Pose) -> list[dict]
```

每本书必须至少返回这些字段：

- `title`
- `rel_x`
- `rel_y`
- `rel_z`
- `left_edge`
- `right_edge`
- `depth`
- `confidence`

说明：

- 一次调用可能返回多本书
- `rel_x / rel_y / rel_z` 是相对当前摄像头中心的坐标
- `left_edge / right_edge` 也是相机坐标系下的值
- `depth` 是抓取算法会使用的前向深度信息
- 控制系统会自己去重、建 task、记录 pose stamp

### 4.2 精定位某一本目标书

函数形式：

```python
locate_book(title: str, camera_pose: Pose) -> dict | None
```

要求：

- 找到目标书就返回一个 dict
- 字段和 `scan_bin_books` 单本结果保持一致
- 如果这一帧没找到目标书，返回 `None`

控制系统最依赖的字段是：

- `left_edge`
- `right_edge`
- `depth`

### 4.3 扫描书架层

函数形式：

```python
scan_shelves(camera_pose: Pose) -> list[dict]
```

每层书架至少返回：

- `zone`
- `depth`
- `bottom`
- `top`
- `height`
- `gaps`
- `tilted_books`

其中 `gaps` 里每个 gap 至少包含：

- `gap_id`
- `start_x`
- `width`

说明：

- `depth / bottom / top / start_x` 都是相对于当前摄像头中心的
- `zone` 是逻辑分区名，比如：
  - `A_left`
  - `A_right`
  - `B_left`
  - `B_right`
- `tilted_books` 是一个布尔值，主控会据此询问终端是否修复倾斜书本

## 5. 主控程序当前流程

1. 输入 11 个超参数
2. 执行一次全局书框扫描
3. 根据识别到的书名建立任务
4. 选择下一本待归还的书
5. 重新扫描并精定位该书
6. 计算抓取目标坐标
7. 通知运动模块移动并抓取
8. 返回该书的 `pick_ready_pose`
9. 对书架做纵向扫描，直到找到目标分区
10. 根据 gap 和书厚度做放置规划
11. 通知运动模块移动并放书
12. 如果检测到书倾斜，终端交互决定是否修复
13. 返回系统初始位，继续下一本书

## 6. 最小抓放仿真计划接口

当前 MuJoCo 验证程序使用 `PICK_PLACE_ONLY_MODE` 跑一个最小抓放流程。主控从
`config.get_pick_place_plan()` 读取统一的抓放计划。今天这个计划来自默认值或 CLI
参数；以后视觉/规划算法接入时，只需要生成同样的 7 个世界坐标点，不需要重写主控
状态机。

职责边界必须说清楚：视觉/决策/规划系统负责识别书本、判断书架空位，并给出抓取起点和放置终点；
控制/MuJoCo 模块不负责生成最优放置点。控制模块负责在拿到这些目标点以后，按通用抓放策略派生
上方接近、抓后抬升、高位转移、高位推进、下放释放、释放后退开等中途动作，并通过 IK 判断这些
动作是否可达。当前默认坐标写死或通过 CLI 输入只是为了模拟未来视觉/决策输出，不代表核心控制
算法依赖固定场景。

计划字段全部使用 `mm`：

```text
pick_approach   = (x, y, z)  # 抓握点正上方，同 X/Y，更高 Z
pick             = (x, y, z)  # 书脊/左侧边抓握标志点，不是书本中心
pick_lift        = (x, y, z)  # 夹住书后回抽+抬升：朝原点最多回抽 50 mm，最低半径 170 mm，Z + 65 mm
transport_retract = (x, y, z) # 若回抽后仍很远，再额外向原点水平回收 70 mm 的运输姿态
place_transfer   = (x, y, z)  # 带书侧转到书架附近高位
place_approach   = (x, y, z)  # 高位向书架内推进点，通常接近 final 的 X/Y
place_final      = (x, y, z)  # 从 approach 往下放后的水平末端释放点
place_retreat    = (x, y, z)  # 释放后退开点
```

当前 CLI 参数只是这个计划的一种输入来源：

```bash
python3 主程序代码/main.py --viewer \
  --book-xy 218.0 120.23 --book-z 100.0 \
  --pick-approach-clearance 100.0 \
  --post-grasp-lift 65.0 \
  --place-transfer -40.0 220.0 150.0 \
  --place-approach -40.0 260.0 150.0 \
  --place-final -40.0 260.0 124.25 \
  --place-retreat -40.0 220.0 150.0
```

未来视觉/规划算法接入建议：

- 视觉算法输出 `pick`：书脊/左侧边的抓握点。
- 抓取规划输出 `pick_approach`：默认可取 `pick.x/pick.y` 不变，`pick.z + 100 mm`。
- 抓取规划输出 `pick_lift`：当前 target-sequence 不再原地竖直抬升，而是朝原点最多回抽 `50 mm`，最低保留 `170 mm` 半径，同时抬到 `pick.z + 65 mm`。例如 `pick=(220,0,115)` 会生成 `pick_lift=(170,0,180)`。
- 控制策略派生 `transport_retract`：如果 `pick_lift` 后水平半径仍大于 `240 mm`，保持 `pick_lift.z`，再沿 XY 平面向原点额外回收 `70 mm`，但不低于 `170 mm` 半径。
- 规划算法输出 `place_transfer/place_approach/place_final/place_retreat`。
- 放书顺序应是先高位推进到书架内，再往下放，最后 `OPEN` 松手。
- `place_final` 必须满足末端水平放书语义。
- `place_retreat` 必须让夹爪在释放后离开书本，之后才能进入下一步或手动控制。
- MuJoCo viewer 会把 `pick` 当作待归还书的书脊标志点，并把书本主体从该点向书体内部偏移显示。
- 接入视觉/规划时，优先保持 `PickPlacePlan` 字段不变，只替换坐标来源；不要把坐标硬编码进
  `controller.py` 状态机。

## 7. IK 候选解代价结构

当前仿真后端已经预留了一个很轻量的 IK candidate ranking 结构，用来以后做关节姿态优化。它不是完整
MPC 或轨迹优化，只是在同一个末端目标点存在多个 IK/alpha 候选解时，给候选解打分并选择代价较低的
解。

当前配置在 `config.py`：

```python
IK_COST_WEIGHTS = {
    "joint_limit": 0.0,
    "preferred_posture": 0.0,
    "motion_smoothness": 0.0,
    "alpha": 0.0,
}
```

全部权重现在都是 `0.0`，所以这套结构**不影响当前结果**。它只是给未来调参留下接口。以后如果某个关节
大角度姿态不好看、不安全，或者需要远离关节极限，可以逐步调高对应权重。仿真日志会记录
`selection_cost` 和 `cost_breakdown`，方便之后比较不同参数的效果。

## 8. 队友改代码时的建议

### 感知同学

- 优先改 [perception_adapter.py](D:\大四\大四下\ECE445\主程序代码\perception_adapter.py) 里的函数实现
- 尽量不要直接改 [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- 如果字段不够，先和我确认后再扩展

### 运动同学

- 优先改 [motion_adapter.py](D:\大四\大四下\ECE445\主程序代码\motion_adapter.py) 里的函数实现
- 保持函数签名不要乱改
- 只要保证“动作完成才返回 True”，主控流程就能继续工作
