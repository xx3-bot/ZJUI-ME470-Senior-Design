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
- `end_x`
- `width`
- `left_boundary_type`
- `right_boundary_type`
- `confidence`

说明：

- `depth / bottom / top / start_x / end_x` 都是相对于当前摄像头中心的
- `zone` 是逻辑分区名，比如：
  - `A_left`
  - `A_right`
  - `B_left`
  - `B_right`
- `tilted_books` 是一个布尔值，主控会据此询问终端是否修复倾斜书本
- `left_boundary_type / right_boundary_type` 表示 gap 两侧真实边界类型，建议取值：
  - `book`
  - `side_panel`
  - `open`
  - `unknown`
- `confidence` 是对这个 gap 几何判断的置信度
- 这几个字段会直接影响放置决策，主控不应该再自行假设哪一侧有支撑

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

## 6. 队友改代码时的建议

### 感知同学

- 优先改 [perception_adapter.py](D:\大四\大四下\ECE445\主程序代码\perception_adapter.py) 里的函数实现
- 尽量不要直接改 [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- 如果字段不够，先和我确认后再扩展

### 运动同学

- 优先改 [motion_adapter.py](D:\大四\大四下\ECE445\主程序代码\motion_adapter.py) 里的函数实现
- 保持函数签名不要乱改
- 只要保证“动作完成才返回 True”，主控流程就能继续工作
