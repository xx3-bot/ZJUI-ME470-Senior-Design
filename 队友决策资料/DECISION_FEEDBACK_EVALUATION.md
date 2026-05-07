# 主程序决策反馈评估

本文档用于评估 `DECISION_FRAMEWORK_NEXT_STEPS.md` 中提出的建议，说明哪些内容采纳、哪些延后、哪些当前不做，以及采纳后的实际实现方向。

## 1. 总体结论

组长的反馈整体是合理的，尤其是以下判断：

1. 当前主程序的状态机和接口分层不需要推翻重写。
2. 当前最薄弱的部分确实是“放置决策过于简单”。
3. 下一步最值得增强的是放置决策的可解释性、任务失败状态记录、以及动作失败检查。

因此，我们的策略不是重构整个控制框架，而是：

- 保留当前 `controller.py` 主状态机
- 保留 `perception_adapter.py / motion_adapter.py` 的边界
- 在放置决策、任务状态、失败处理和日志层面做增强

## 2. 对 placement opportunity selection 的理解

### 2.1 当前算法的实际行为

当前放置算法主要位于：

- [decision/task_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\task_planner.py)
- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)

当前逻辑可以概括为：

1. 筛掉太窄的 `gap`
2. 在可行 gap 中选择离 `preferred_x` 最近的一个
3. 基于这个 gap 直接计算 approach pose 和 final pose

这说明当前算法更像：

```text
找到一个能放下的 gap -> 选一个最近的 -> 放进去
```

这种做法在流程演示上是成立的，但在“决策质量”和“展示可解释性”上还不够。

### 2.2 为什么要升级

我们项目的目标不只是“找到空隙”，而是“找到更稳定、更容易成功、更不容易挤压已有书的放置方式”。

因此，`gap` 本身只是几何空白，不应该直接等价于最终放置方案。真正应该被选择的是：

```text
Placement Opportunity
```

也就是：

- 在某个 gap 中靠左放
- 在某个 gap 中靠右放
- 在某个 gap 中居中放

这些机会不是等价的，它们的稳定性和风险不同。

### 2.3 我们对目标策略的理解

如果书属于左侧书架区域，那么高分放置方式通常不是“找一个中间空隙硬塞进去”，而是：

```text
沿着已有书列的右侧继续放
```

原因是：

1. 一侧天然有支撑
2. 另一侧通常有更大的空余
3. 不容易明显挤压现有书
4. 运动路径和姿态更简单
5. 放置后书更容易保持稳定

因此我们的决策应当：

- 鼓励沿边、沿已有书列延伸式放置
- 降低紧缝插入的优先级
- 对需要明显挤压的机会进行 reject 或大幅扣分

这并不意味着所有 `gap` 都不应该使用，而是：

```text
不是每个 gap 都是同等好的放置位置
```

## 3. 采纳项

以下建议决定采纳。

### 3.1 采纳：将简单 gap 选择升级为 placement opportunity selection

**为什么改**

当前 `choose_gap()` 只能回答“哪个 gap 能放下且更接近 preferred_x”，但不能回答：

- 为什么这个放法更稳定
- 为什么另一个位置虽然能放，但不值得放
- 为什么应该靠左、靠右或居中

这会削弱系统作为“决策框架”的表达能力。

**改哪些文件**

- [decision/task_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\task_planner.py)
- 新增 [decision/placement_opportunity_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\placement_opportunity_planner.py)
- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- [models.py](D:\大四\大四下\ECE445\主程序代码\models.py)

**实际做法**

第一版不做复杂 AI 或机器学习，只做轻量规则规划：

1. 从每个 `ShelfGap` 生成若干候选机会：
   - `lean_left`
   - `lean_right`
   - `center`
2. 计算基础特征：
   - `fit_margin`
   - `distance_to_preferred`
   - 左/右侧余量
   - 是否过紧
3. 先做硬性 reject：
   - gap 太窄
   - fit margin 太小
4. 再做规则打分：
   - margin 大加分
   - 一侧支撑、一侧空余加分
   - 离 preferred_x 近加分
   - 过紧扣分
   - 中间紧缝扣分
5. 输出 `PlacementDecision`，并附带选择原因和候选分数

**做到了什么**

升级后，系统可以表达：

- 为什么选择某个放法
- 为什么拒绝某个机会
- 为什么沿已有书列继续放比插入中间紧缝更优
- 为什么同一个 gap 中 `lean_left` 和 `center` 的分数不同

### 3.2 采纳：增强 Task 状态

**为什么改**

当前 `Task.status` 过于简单，基本只有：

- `PENDING`
- `DONE`

这不足以表达实际执行过程中的中间状态和失败状态。

**改哪些文件**

- [models.py](D:\大四\大四下\ECE445\主程序代码\models.py)
- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- [decision/db_manager.py](D:\大四\大四下\ECE445\主程序代码\decision\db_manager.py)

**实际做法**

扩展状态为：

- `PENDING`
- `LOCALIZED`
- `PICKED`
- `PLACE_PLANNED`
- `DONE`
- `FAILED`
- `BLOCKED`

必要时也可以保留更细粒度状态，但第一版先以可读、可维护为主。

**做到了什么**

增强后，系统可以明确表达：

- 已定位但未抓
- 已抓但未放
- 已规划但 motion 失败
- 找不到可行位置而 blocked

这对调试、日志、汇报和后续 retry 都很有帮助。

### 3.3 采纳：增加任务失败记录

**为什么改**

如果任务失败，只看 `False` 或流程中断是不够的。需要知道失败次数和失败原因。

**改哪些文件**

- [models.py](D:\大四\大四下\ECE445\主程序代码\models.py)
- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)

**实际做法**

在 `Task` 中增加例如：

- `attempt_count`
- `failure_reason`
- `last_decision`

**做到了什么**

增强后，系统可以记录：

- 这本书失败了几次
- 失败是因为定位失败、无可行放置位置、motion 失败，还是 gripper 失败
- 最后一次放置决策是什么

### 3.4 采纳：增强决策日志

**为什么改**

当前流程日志已经能显示状态推进，但还不能充分展示“决策为什么这么做”。

**改哪些文件**

- [decision/task_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\task_planner.py)
- 新增 [decision/placement_opportunity_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\placement_opportunity_planner.py)
- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)

**实际做法**

输出类似：

```text
[PLAN] Placement candidates for Control Systems:
  gap=1 mode=lean_left  score=...
  gap=1 mode=center     score=...
  gap=2 mode=lean_right score=...

[PLAN] Selected gap=1 mode=lean_left reason=...
```

**做到了什么**

增强后，系统可以展示：

- 候选机会列表
- 每个候选的分数
- reject 原因
- 最终选择原因

这既方便调试，也更适合答辩展示。

### 3.5 采纳：`_move_to()` 返回 bool，并在上层检查

**为什么改**

当前 `_move_to()` 只在内部更新 `current_pose`，但不把成功/失败显式反馈给调用者。  
这在 mock 阶段问题不大，但接入真实运动模块后风险较大。

**改哪些文件**

- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- [motion_adapter.py](D:\大四\大四下\ECE445\主程序代码\motion_adapter.py)

**实际做法**

让 `_move_to()` 返回 `bool`，并在以下位置检查：

- 抓取前移动
- 返回 pick-ready pose
- 放置 approach move
- 放置 final move
- 返回 home

**做到了什么**

增强后，系统可以做到：

- 移动失败时不继续错误地执行后续动作
- movement fail 与 gripper fail 分开记录
- 失败后可标记 `FAILED` 或 `BLOCKED`

## 4. 延后项

以下建议认可方向，但第一版先不做太重。

### 4.1 延后：复杂 support_side 推断

**原因**

这个 feature 很有价值，但当前视觉数据结构还不足以稳定支持真实推断。  
第一版可以用轻量启发式或 mock 数据体现概念，不应过早做成强依赖。

### 4.2 延后：复杂 squeezing 建模

**原因**

“是否挤压”“挤压多少”在真实系统里会依赖更精细的感知和机械约束。  
第一版只需要把“明显过紧”当作 reject 或低分即可。

### 4.3 延后：WorldModel 大幅扩展

**原因**

当前 `world_model.py` 仍然以轻量存储为主。  
第一版可先增加少量记忆，例如上次决策、已放置结果或 blocked 信息，不需要立刻做复杂历史地图。

### 4.4 延后：单独 demo/test 框架

**原因**

这项是有价值的，但不是最先阻塞的核心任务。  
如果时间允许，可以补一个轻量 demo 脚本专门展示 placement planner。

## 5. 暂不采纳项

以下内容当前明确不做，避免工期失控。

### 5.1 不做机器学习或复杂 AI 打分

**原因**

当前项目阶段更需要可解释、易调试、能联调的规则系统，而不是复杂模型。

### 5.2 不重写 controller 主状态机

**原因**

当前主状态机结构已经正确。  
下一步应该在 `place_book()` 附近增强决策，而不是推翻现有流程。

### 5.3 不依赖尚未稳定的高阶视觉特征

**原因**

例如非常精细的 occupancy、support_side、confidence 推断，如果现在作为核心输入，容易导致后续真实联调时大改。  
因此第一版 planner 应先围绕现有稳定字段构建。

## 6. 拟修改的主要文件

本次采纳建议后，预计主要涉及：

- [controller.py](D:\大四\大四下\ECE445\主程序代码\controller.py)
- [models.py](D:\大四\大四下\ECE445\主程序代码\models.py)
- [world_model.py](D:\大四\大四下\ECE445\主程序代码\world_model.py)
- [decision/task_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\task_planner.py)
- 新增 [decision/placement_opportunity_planner.py](D:\大四\大四下\ECE445\主程序代码\decision\placement_opportunity_planner.py)

可能的辅助文件：

- 可选新增 demo 或测试脚本

## 7. 一句话总结

我们接受这次反馈的核心思想，但采用“轻量实现、局部增强”的方式推进：

```text
保留当前状态机和接口架构，
把简单 gap 选择升级为可解释的 placement opportunity selection，
同时增强 task 状态、失败记录、动作失败检查和日志能力。
```

目标不是把主程序改成复杂 AI，而是让它真正具备“决策框架成立、理由可解释、失败可记录、后续可扩展”的特征。
