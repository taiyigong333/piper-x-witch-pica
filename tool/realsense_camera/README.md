# RealSense 参数工具

在仓库根目录运行。当前仓库参数目录为 `configs/camera/`，参数文件统一保存到这里。

读取采集配置涉及的相机当前参数并保存：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.snapshot \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --name current_real_parameters.json \
  --purpose "现场采集前当前参数"
```

实时预览并让相机自动曝光/白平衡；预览窗口按 `s` 保存、按 `q` 退出：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.preview \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --name auto_tuned_parameters.json \
  --purpose "自动调参后的现场参数"
```
