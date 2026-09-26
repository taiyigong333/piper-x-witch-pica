# RealSense 参数工具

在仓库根目录运行。当前仓库参数目录为 `configs/camera/`，参数文件统一保存到这里。

读取采集配置涉及的相机当前参数并保存：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.snapshot \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --name current_real_parameters_night.json \
  --purpose "现场采集前当前参数"
```

实时预览并让相机自动曝光/白平衡。工具会先预热，再根据中心区域亮度、欠曝/过曝比例和连续帧波动判断是否稳定；窗口显示实时指标，稳定后按 `s` 保存，按 `q` 退出：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.preview \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --name auto_tuned_parameters_night.json \
  --purpose "自动调参后的现场参数"
```

默认预热 2 秒并等待 30 个稳定帧；现场光线变化较慢时可以增加等待帧数：

```bash
... --warmup-s 3 --stable-frames 60
```
