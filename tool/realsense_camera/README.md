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

第三个功能是接近 RealSense Viewer 的 RGB 自动收敛工具。它明确选择 RGB Camera 对应的 color sensor，开启 AE/AWB，采集默认 60 帧等待硬件收敛，然后打开可视化确认窗口显示 RGB 画面和稳定参数：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.rgb_auto_tune \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --frames 60 --name rgb_auto_tuned.json \
  --purpose "RGB 自动收敛结果"
```

按 `s` 才会保存；按 `q` 或 `ESC` 退出且不保存。需要把收敛结果固定为手动参数时增加 `--lock`，锁定动作也只会在按 `s` 确认后执行；不加 `--lock` 则保存自动曝光/自动白平衡开关，让后续采集继续由相机自动控制。

预览已经保存的相机参数及其实际画面。每台相机有独立窗口，左侧是实时画面，右侧是参数 GUI：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.saved_preview \
  --name piper_x_balanced_fixed.parameters.json
```

如果系统 OpenCV/Qt 窗口不可用，使用纯 Tkinter 版本。它不调用 OpenCV HighGUI，也不访问 `/dev/video*`，画面仍通过 RealSense SDK 读取：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.saved_preview_gui \
  --name piper_x_balanced_fixed.parameters.json
```

如果 Tkinter 窗口在当前桌面环境中仍然停留在“等待 RealSense RGB 图像”，或右侧参数面板过长，优先使用本地网页版本。它通过浏览器显示 MJPEG 实时画面，右侧参数面板可以独立滚动，不依赖 Tkinter 控件刷新：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.realsense_camera.saved_preview_web \
  --name piper_x_balanced_fixed.parameters.json
```

程序默认打开 `http://127.0.0.1:8765/`；如果不希望自动打开浏览器，增加 `--no-browser`。网页中的取帧错误会直接显示在对应相机卡片状态栏，便于区分“浏览器显示问题”和“RealSense 没有返回 RGB 帧”。参数行同时显示输入值和 `当前值 / Current`；自动曝光或自动白平衡运行时，硬件实时变化后的曝光、增益、白平衡等数值会自动刷新到侧边栏。

Tkinter 版本每台相机一个窗口，支持分辨率、曝光、增益、白平衡、亮度、对比度、饱和度、锐度、Gamma、色调、电源频率调节。参数行同时显示中文/英文名、RealSense 实际允许范围、滑块和数字输入框；输入数字后按回车或点击“应用”即可直接写入 RGB sensor。自动曝光/自动白平衡仍通过复选框控制，并支持 GUI 另存为。

工具会读取 `configs/camera/` 中的分辨率、帧率、序列号和 options，并将参数应用到对应相机；按 `q` 或 `ESC` 退出。所有修改和保存均通过窗口完成，不使用命令行输入。

预览窗口还支持运行时修改参数。先按 `Tab` 选择相机，再使用：

| 按键 | 操作 |
| --- | --- |
| 鼠标点击曝光 `- / +` | 曝光减小 / 增大 |
| 鼠标点击增益 `- / +` | 增益减小 / 增大 |
| 鼠标点击白平衡 `- / +` | 白平衡减小 / 增大 |
| 点击自动曝光 | 切换自动曝光 |
| 点击自动白平衡 | 切换自动白平衡 |
| 点击 Save as new file | 弹出窗口输入新文件名和 `purpose`，另存为新 JSON |
| 点击分辨率文本 | 弹出窗口修改宽度和高度并重启该相机流 |
| `q` / `ESC` | 退出 |

另存为严格禁止使用当前源文件名，因此不会修改原参数文件。曝光步长为 10，增益步长为 1，白平衡步长为 100；滑块和数字输入框都会校验设备返回的最小值、最大值和步长。后台取帧线程不直接操作 Tk 控件，取帧错误会转交主线程显示，避免 Tkinter 回调线程异常导致预览窗口不刷新。
