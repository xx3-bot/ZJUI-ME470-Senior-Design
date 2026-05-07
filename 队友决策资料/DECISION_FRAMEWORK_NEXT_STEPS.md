# 主程序决策框架下一步任务说明

## 1. 当前主程序结构状态

现在主程序已经有一个完整的任务级流程框架，整体状态机和接口分层是对的，不需要推翻重写。

主流程大致是：

```text
启动
→ 扫描 return bin
→ 根据识别到的书名创建 task
→ 选择下一本书
→ 精定位书本
→ 计算抓取点
→ 抓书
→ 扫描目标书架 zone
→ 选择放置位置
→ 计算放置 pose
→ 松爪
→ 更新 world model
→ 回 home / 下一本
```

目前主要相关文件：

```text
主程序代码/controller.py
主程序代码/models.py
主程序代码/world_model.py
主程序代码/decision/task_planner.py
主程序代码/decision/db_manager.py
主程序代码/perception_adapter.py
主程序代码/motion_adapter.py
```

现在的结构优点：

```text
1. controller 主流程已经清楚。
2. perception_adapter / motion_adapter 边界已经存在。
3. Task / BookObservation / ShelfObservation / ShelfGap 等基础模型已经有了。
4. 后续真实视觉和运动控制可以通过 adapter 接入。
```

当前主要不足：

```text
1. 放置决策还比较简单。
2. 目前更像是“找到一个够宽的 gap，然后把书放进去”。
3. 任务失败状态、重试、blocked 记录还不够完整。
4. world model 目前只是轻量存储最新观察，缺少已尝试/已放置/失败位置等记忆。
5. 决策日志还不够可解释，不利于展示“为什么选这个位置”。
```

## 2. 核心方向：不是 Gap Insertion，而是 Placement Opportunity Selection

下一步最重要的不是做复杂 AI，也不是重写 controller，而是把放置决策从简单 `choose_gap()` 升级为一个轻量、可扩展、可解释的：

```text
Placement Opportunity Planner
```

我们不希望系统只是：

```text
找到一个空洞 → 把书插进去
```

更符合项目目标的是：

```text
找到一个低风险、稳定、容易成功的放置机会
→ 判断靠左、靠右、居中哪种方式更好
→ 优先选择一侧有支撑、另一侧有空余、无需挤压的放置方式
```

也就是说，视觉检测到的 `gap` 只是几何空白。真正要选择的是从这个 gap 派生出来的多个放置机会。

例如：

```text
gap A:
  - lean_left   靠左放
  - lean_right  靠右放
  - center      居中放

gap B:
  - lean_left
  - lean_right
  - center
```

最高分的策略通常不应该是“插进两个书之间的紧缝”，而应该是：

```text
一侧有支撑，例如已有书 / 书架侧板
另一侧有足够 clearance
不需要明显挤压已有书
路径和姿态简单
放完以后书能靠住或直立
```

紧缝插入应该是低分策略，甚至只是 fallback。

## 3. 建议新增模块

建议新增文件：

```text
主程序代码/decision/placement_opportunity_planner.py
```

这个模块负责：

```text
1. 从 ShelfObservation / ShelfGap 生成 placement opportunities。
2. 为每个 opportunity 计算 features。
3. 根据规则和权重打分。
4. reject 明显不可行的 opportunity。
5. 选择最高分 opportunity。
6. 输出 PlacementDecision，包括选择理由和候选分数。
```

第一版不需要复杂算法，重点是结构清楚、可扩展、可解释。

## 4. 建议新增数据结构

可以先做轻量版本。

```python
from dataclasses import dataclass
from typing import Optional

from models import Pose, ShelfGap


@dataclass
class PlacementOpportunity:
    gap_id: int
    mode: str  # "lean_left", "lean_right", "center"
    target_x: float
    support_side: str  # "left", "right", "none"
    free_side_clearance: float
    fit_margin: float
    requires_squeezing: bool
    confidence: float = 1.0


@dataclass
class ScoredPlacementOpportunity:
    opportunity: PlacementOpportunity
    score: float
    rejected: bool
    reason: str


@dataclass
class PlacementDecision:
    selected: Optional[PlacementOpportunity]
    scored_candidates: list[ScoredPlacementOpportunity]
    approach_pose: Optional[Pose]
    final_pose: Optional[Pose]
    reason: str
```

如果需要保留原始 gap，也可以在 `PlacementOpportunity` 里加：

```python
gap: ShelfGap
```

或者只保留 `gap_id`，看实现方便程度。

## 5. 第一版打分原则

先做规则打分，不需要机器学习。

硬性 reject：

```text
1. fit_margin < minimum_clearance：放不下，reject
2. requires_squeezing=True 且挤压超过允许范围：reject 或大幅扣分
```

建议优先级：

```text
最高优先级：
  一侧有支撑，另一侧有余量，无需挤压

中高优先级：
  宽 gap 中靠左 / 靠右放置

中等优先级：
  宽 gap 中居中放置，但两侧都没有明显支撑

低优先级：
  紧 gap 插入，fit margin 很小

拒绝：
  宽度不够，或需要明显挤压
```

可以先用这些 feature：

```text
fit_margin
free_side_clearance
support_side
distance_to_preferred
requires_squeezing
confidence
```

示例打分逻辑：

```text
+ fit_margin_score
+ support_side bonus
+ confidence bonus
- distance_to_preferred penalty
- too_tight penalty
- isolated_center penalty
- squeezing penalty
```

重点不是公式多高级，而是让 planner 能输出：

```text
为什么这个 opportunity 被选中
为什么另一个 opportunity 被拒绝或低分
```

## 6. Controller 应该怎么接

不要大改 `controller.py` 的状态机。建议只改 `place_book()` 附近。

现在逻辑大致是：

```python
gap = self.planner.choose_gap(task, shelf, preferred_x)
approach_pose, final_pose = self.planner.compute_place_poses(task, shelf, gap)
```

建议改成：

```python
decision = self.planner.plan_placement(task, shelf, preferred_x)

if decision.selected is None:
    # mark task blocked / return False
    return False

approach_pose = decision.approach_pose
final_pose = decision.final_pose
```

可以保留旧的 `choose_gap()` 兼容接口，但内部调用新的 planner，避免一次性改太多。

## 7. 决策日志要求

这部分很重要，既方便调试，也方便汇报展示。

希望 planner 输出类似：

```text
[PLAN] Placement candidates for Control Systems:
  gap=1 mode=lean_left  score=0.82 rejected=False reason=left support, enough right clearance
  gap=1 mode=center     score=0.45 rejected=False reason=no side support
  gap=2 mode=lean_right score=0.31 rejected=False reason=tight fit
  gap=3 mode=center     score=0.00 rejected=True  reason=not enough width

[PLAN] Selected gap=1 mode=lean_left reason=stable one-side support with free clearance
```

这样可以证明我们的系统不是随机找空，而是在做可解释的放置决策。

## 8. Mock / Demo 场景

视觉模块暂时不一定能给出完整真实数据，所以请先用 mock 场景把决策框架跑通。

建议至少做这些场景：

```text
1. 大空位靠左最优
2. 大空位靠右最优
3. 中间插缝可行但低分
4. 所有位置都太窄，返回 no feasible placement
5. 两个可行位置，选择更靠近 preferred_x 的
```

可以写一个简单脚本，例如：

```text
主程序代码/decision/demo_placement_planner.py
```

或者写一个轻量测试文件。

目标是可以单独运行并看到候选分数和最终选择，不依赖真实硬件、MuJoCo 或 ROS2。

## 9. 任务状态管理也建议轻量增强

除了 placement planner，建议顺手增强 `Task` 状态。

现在 task 状态比较简单，基本是：

```text
PENDING / DONE
```

建议扩展成：

```text
PENDING
LOCALIZED
PICKED
PLACE_PLANNED
DONE
FAILED
BLOCKED
```

并给 `Task` 增加一些字段：

```python
attempt_count: int = 0
failure_reason: str | None = None
last_decision: object | None = None
```

第一版不需要做复杂调度，但至少要能记录：

```text
这本书失败了几次
失败原因是什么
是定位失败、无可行放置位置、运动失败，还是夹爪失败
```

这样以后可以支持 retry、skip、人工介入或重新扫描。

## 10. 失败恢复逻辑建议

建议把 `_move_to()` 改成返回 bool，并要求上层检查。

现在失败处理偏弱。轻量版本可以先做到：

```text
book locate 失败 → 重扫 N 次
shelf scan 失败 → 换高度 / 重扫 N 次
no placement opportunity → 标记 task 为 BLOCKED
move_to 失败 → 当前 task FAILED，不更新 world model
gripper 失败 → 不 mark done
```

重点不是把所有恢复策略写满，而是让框架上有“失败不是直接崩”的能力。

## 11. WorldModel 可做的轻量增强

现在 `world_model.py` 主要记录：

```text
bin_books
latest_shelves
zone_slot_bases
```

可以轻量增强为：

```text
1. 记录每个 zone 最近一次 shelf observation。
2. 记录每个 zone 生成过的 placement opportunities。
3. 记录已经放过的书的位置。
4. 记录失败过 / blocked 的 gap 或 opportunity。
```

第一版不需要复杂地图，只要以后能回答：

```text
这个 zone 上次看到什么？
哪些 opportunity 被尝试过？
哪些失败过？
这本书最后放到哪里了？
```

就很有价值。

## 12. 明确不要做的事情

为了控制工期，这次不要做这些：

```text
不要碰 ROS2 / serial / PWM
不要碰 MuJoCo IK
不要做复杂视觉算法
不要做机器学习
不要大改 controller 状态机
不要写完整导航规划
不要把感知逻辑写死进 planner
```

你的边界应该是：

```text
输入：书本信息 + shelf observation / gap observation
输出：可解释的 task / placement decision
```

## 13. 推荐交付分级

### Must Have

```text
1. 新增 PlacementOpportunityPlanner。
2. 从每个 gap 生成 lean_left / lean_right / center 候选。
3. 对每个候选打分、reject、输出 reason。
4. 输出 PlacementDecision。
5. controller/place_book 能使用 PlacementDecision。
6. 有 mock 场景展示不同选择结果。
```

### Should Have

```text
1. Task 状态扩展。
2. _move_to 返回 bool，并被上层检查。
3. no feasible placement 时标记 BLOCKED。
4. 更清晰的决策日志。
```

### Nice To Have

```text
1. WorldModel 记录已尝试 / 已放置 / blocked opportunity。
2. 简单 demo 或测试脚本。
3. 支持未来视觉传入 confidence / support_side / occupancy 信息。
```

## 14. 一句话总结

这次任务不是把主程序重写成复杂智能系统，而是把它从“流程能跑”升级成“决策框架成立”。

核心目标：

```text
把简单 gap 选择升级为可扩展的 placement opportunity selection。
现阶段用 mock 数据也能展示：
系统为什么选择靠左、靠右或居中；
为什么拒绝某些位置；
为什么这个放置方式更稳定、更简单、更安全。
```

这样以后真实视觉模块给出更准确的空隙、支撑边、置信度和占位信息之后，不需要重写 controller，只需要给 planner 喂更好的 features 或调整打分权重。
