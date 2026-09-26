# Piper-X 手动控制工具

在仓库根目录执行：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m tool.piper_x_control.gui
```

先在仓库根目录执行 `UV_CACHE_DIR=/tmp/uv-cache uv sync`，确保使用项目锁定的
Python 3.10 环境和仓库内 `pyAgxArm`。

工具只使用本仓库 `pyAgxArm` 的 CAN 接口，不启动也不修改 `/home/cv/pika_ros`。

- `停止保持（阻尼）`：调用阻尼电子急停，停止当前运动并保持当前位置，不使能/失能电机；
- `失能`：调用 `disable()`；
- `恢复使能`：在二次确认后先调用 `reset()` 清除电子急停，再调用 `enable()`；
- 连接后实时显示关节角、末端 flange 位姿、机械臂状态和夹爪反馈；
- `reset()` 可能造成瞬时失电和机械臂下坠，只有现场确认机械臂已安全支撑后才能点击恢复。
