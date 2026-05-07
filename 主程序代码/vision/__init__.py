"""真实视觉实现包。

按需通过子模块导入，避免没装 numpy/cv2/paddleocr 时 mock/fake 路径崩：
- from vision.bin_scanner import scan_bin_books, locate_book
- from vision.world_pose_provider import get_pick_world_pose

使用方式：
- config.USE_MOCK_VISION = False     → perception_adapter 走真实视觉 pipeline
- config.USE_VISION_FOR_PICK = True  → PickPlacePlan.pick 由视觉 world_pose_provider 提供
"""

__all__: list[str] = []
