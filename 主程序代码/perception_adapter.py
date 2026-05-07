"""感知模块适配层。

给视觉同学看的重点：
1. 控制系统只会调用这个文件里的函数，不会直接调用你们的模型代码。
2. 你们以后接入真实视觉时，优先改这个文件里的函数体，尽量不要改主控逻辑。
3. 所有坐标单位统一用 mm。
4. 返回的坐标一律是“相对于当前摄像头中心”的坐标，不是世界坐标。
5. 如果当前画面看不到目标，就返回空列表或 None，不要伪造数据。
"""

from __future__ import annotations

from typing import Dict, List

import interfaces
from models import Pose


def scan_bin_books(camera_pose: Pose) -> List[Dict[str, float]]:
    """扫描书框，返回当前画面里所有能识别到的书。

    视觉同学以后需要保证返回格式严格如下：
    [
        {
            "title": str,        # 书名/条码映射后的唯一标识
            "rel_x": float,      # 书相对摄像头中心的横向坐标
            "rel_y": float,      # 书相对摄像头中心的纵深坐标
            "rel_z": float,      # 书相对摄像头中心的高度坐标，没有可先给 0.0
            "left_edge": float,  # 书在相机坐标系下的左边缘 x
            "right_edge": float, # 书在相机坐标系下的右边缘 x
            "depth": float,      # 抓取时使用的前向深度，通常和 rel_y 同量纲
            "confidence": float, # 识别置信度，0~1
        },
        ...
    ]

    注意：
    - 一次调用可能返回多本书，控制系统会自己去重并建任务。
    - 这里不要返回世界坐标，主控会结合 camera_pose 自己转换。
    """

    return interfaces.vision_scan_bin_books(camera_pose)


def locate_book(title: str, camera_pose: Pose) -> Dict[str, float] | None:
    """精定位某一本目标书，用于抓取。

    视觉同学以后需要保证：
    - 找到目标书就返回一个 dict，字段和 scan_bin_books 的单本结果一致。
    - 没找到就返回 None。
    - left_edge / right_edge / depth 是控制系统抓取算法最依赖的字段。
    - 如果你们后面有更稳定的中心点、法向量等信息，可以再和我对接加字段，
      但先不要随便改现有字段名。
    """

    return interfaces.vision_locate_book(title, camera_pose)


def scan_shelves(camera_pose: Pose) -> List[Dict[str, object]]:
    """扫描书架，返回当前画面里能看到的书架层信息。

    返回格式：
    [
        {
            "zone": str,          # 逻辑分区名，例如 A_left / A_right / B_left / B_right
            "depth": float,       # 书架层相对摄像头的深度
            "bottom": float,      # 书架下沿相对摄像头的 z
            "top": float,         # 书架上沿相对摄像头的 z
            "height": float,      # top - bottom
            "gaps": [
                {
                    "gap_id": int,
                    "start_x": float,           # gap 左边界相对摄像头中心的 x
                    "end_x": float,             # gap 右边界相对摄像头中心的 x
                    "width": float,             # gap 宽度
                    "left_boundary_type": str,  # "book" / "side_panel" / "open" / "unknown"
                    "right_boundary_type": str, # "book" / "side_panel" / "open" / "unknown"
                    "confidence": float,        # 对这个 gap 几何判断的置信度
                },
                ...
            ],
            "tilted_books": bool, # 是否检测到倾斜书本，供主控弹终端确认
        },
        ...
    ]

    注意：
    - 这里仍然返回相机坐标系数据。
    - 主控会把 start_x / end_x / bottom / top / depth 转成世界坐标。
    - 如果当前没看到书架层，就返回 []。
    - 如果暂时还不能稳定判断某一侧边界类型，可以先返回 "unknown"，
      但不要由主控自己假设哪一侧有支撑。
    """

    return interfaces.vision_scan_shelves(camera_pose)
