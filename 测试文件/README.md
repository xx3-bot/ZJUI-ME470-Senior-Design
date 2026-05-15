# 测试文件说明

Last updated: 2026-05-15

这个文件夹集中保存远程队友需要的视觉测试图像和近期运行归档，避免把临时输出散落在 `sim_output/` 原始工作目录里。

## 内容

- `test_images/`
  - 从 `/Users/xinruixiong/Desktop/ME470/测试图像/` 拷贝来的静态视觉测试图。
  - 包含 `test shelf.png`、`shelf2.png`、`shelf3.png`、`book1.jpg`、`liaozhai.jpg` 等。

- `runtime_artifacts/startup_scan/`
  - 启动扫描运行归档。
  - 包含 `center.png`、`left.png`、bin/shelf overlay、`startup_scan_snapshot.json`、`startup_scan_report.md`。

- `runtime_artifacts/detected_books_loop/`
  - Auto demo / detected-books loop 运行归档。
  - 包含 loop snapshot、report、合并命令文件和可视化计划图。

- `runtime_artifacts/grip_place_test/`
  - 早期 grip/place 小链路测试归档。

- `runtime_artifacts/current_detected_book_sequence/`
  - 当前覆盖式 target sequence 工作目录快照。

## 2026-05-15 注意事项

- `startup_scan/20260515_180123` 是一次较干净的三本书 bin 深度/横向识别样例。
- `startup_scan/20260515_180953` 暴露了一个重要问题：图像内容仍是 bin 视角，但当前 shelf detector 误判出了 shelf slots。这个归档应作为 shelf 误判回归测试样例。
- 后续 shelf 检测必须加入 CAD / pose validation 硬闸：没有通过书立架 CAD 几何约束的图像，不能生成 `shelf_world_model`。

## 使用建议

队友可以直接用这些图跑视觉模块的离线测试，不需要连接机械臂或相机。运行输出如果需要共享，请复制到本文件夹的新子目录，再提交到 Git。
