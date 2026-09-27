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

默认预热 3 秒并等待 45 个稳定帧；工具使用前后窗口中位数、亮度分位数和欠曝/过曝比例判断硬件自动调参是否收敛：

```bash
... --warmup-s 5 --stable-frames 60
```

采集使用的自动画面参数文件为 `configs/camera/piper_x_auto_image.parameters.json`。它只保存自动曝光和自动白平衡；分辨率与帧率仍由采集 YAML 控制。自动曝光开启时，适配器会忽略配置中的手动 `exposure`/`gain`；自动白平衡开启时会忽略手动 `white_balance`，避免残留值影响自动调节。
