# Piper-X Pika Sense 数据采集

本项目用于 Piper-X 机械臂、原装 AGX 夹爪、Pika Sense 遥操和 RealSense D405/D435 相机的数据采集，输出 HDF5 轨迹、质量报告、清单和校验文件。

`pyAgxArm/` 是项目使用的机械臂 SDK；`/home/cv/pika_ros` 是外部 ROS 工作区，本项目只调用其中的程序，不修改其源码。

## 安装

```bash
cd /home/cv/gcj/project/data_collect/piper-x-witch-pica
git submodule update --init --recursive
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra dev --extra realsense
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect --help
```

## 配置

- `configs/camera/`：RealSense 参数文件。真实采集必须显式填写 `session.camera_parameters_file`。
- `configs/teleop/`：Pika Sense 遥操配置。
- `configs/tasks/`：任务、机械臂、数据输出配置。
- `configs/pass/`：可复制的示例配置。

相机 JSON 中的 option 会在启动时写入设备。采集时会读取设备信息、传感器 option、范围、流配置、内参、外参、深度比例和 Advanced Mode 信息，并保存到批次参数文件。

## 常用命令

```bash
uv run piper-x-collect preflight --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml
uv run piper-x-collect teleop-session \
  --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml \
  --teleop-config configs/teleop/pika_sense_piper_x.example.yaml \
  --reverse-recording
uv run piper-x-collect trajectory-viewer --root /home/cv/gcj/data_collect/data
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q
```

数据目录为 `data/batch_N/<采集时间>/forward` 和 `reverse`，批次根目录保存 `camera_parameters.json`。同一批次再次采集时，相机参数摘要不一致会直接拒绝。

## Piper-X 手动控制

机械臂失能或电子急停后，可运行：

```bash
python -m tool.piper_x_control.gui
```

GUI 提供读取状态、停止保持、失能和恢复使能。恢复使能会在二次确认后执行 `reset()` 再 `enable()`；`reset()` 可能造成瞬时失电，悬空或带负载时禁止操作。

## 安全边界

采集预检和普通采集只读取 Piper-X CAN 反馈。只有配置 `robot.initial_pose.enabled: true` 时，程序才会在遥操 ROS 启动前调用 `enable()` 和低速运动指令。起始位姿超时会触发电子急停；请先按现场流程确认机械臂状态，再使用手动控制工具恢复。

不要修改 `/home/cv/pika_ros`。完整现场流程见 [`docs/使用说明.md`](docs/使用说明.md) 和 [`docs/项目交接.md`](docs/项目交接.md)。
